
from app.models import Area, Subarea, Criteria, AreaBlueprint, SubareaBlueprint, CriteriaBlueprint
from app import db
import pandas as pd
import numpy as np
import math
import ast, json
from sklearn.metrics.pairwise import cosine_similarity



def reapply_template(templateID, applied_template):
    """
    Archives old applied Areas/Subareas/Criteria for the given AppliedTemplate,
    then copies all blueprints from the Template into the Program’s live tables.
    """

    # ===== 1️⃣ Archive old areas in bulk =====
    old_areas = Area.query.filter_by(appliedTemplateID=applied_template.appliedTemplateID, archived=False).all()
    old_area_ids = [a.areaID for a in old_areas]

    if old_area_ids:
        # Bulk archive all levels
        db.session.query(Criteria).filter(Criteria.subareaID.in_(
            db.session.query(Subarea.subareaID).filter(Subarea.areaID.in_(old_area_ids))
        )).update({"archived": True}, synchronize_session=False)

        db.session.query(Subarea).filter(Subarea.areaID.in_(old_area_ids)).update({"archived": True}, synchronize_session=False)
        db.session.query(Area).filter(Area.areaID.in_(old_area_ids)).update({"archived": True}, synchronize_session=False)

    # ===== 2️⃣ Copy all blueprints -> applied data =====
    area_blueprints = AreaBlueprint.query.filter_by(templateID=templateID).all()

    for ab in area_blueprints:
        new_area = Area(
            appliedTemplateID=applied_template.appliedTemplateID,
            programID=applied_template.programID,
            areaBlueprintID=ab.areaBlueprintID,
            areaName=ab.areaName,
            areaNum=ab.areaNum,
            archived=False
        )
        db.session.add(new_area)
        db.session.flush()

        subarea_blueprints = SubareaBlueprint.query.filter_by(areaBlueprintID=ab.areaBlueprintID).all()
        new_subareas = []
        for sb in subarea_blueprints:
            sub = Subarea(
                areaID=new_area.areaID,
                subareaBlueprintID=sb.subareaBlueprintID,
                subareaName=sb.subareaName,
                archived=False
            )
            new_subareas.append(sub)
        db.session.add_all(new_subareas)
        db.session.flush()

        # Preload criteria blueprints once (performance boost)
        all_criteria_bps = CriteriaBlueprint.query.filter(
            CriteriaBlueprint.subareaBlueprintID.in_([sb.subareaBlueprintID for sb in subarea_blueprints])
        ).all()
        criteria_map = {}
        for cb in all_criteria_bps:
            criteria_map.setdefault(cb.subareaBlueprintID, []).append(cb)

        for sub in new_subareas:
            if sub.subareaBlueprintID in criteria_map:
                db.session.add_all([
                    Criteria(
                        subareaID=sub.subareaID,
                        criteriaBlueprintID=cb.criteriaBlueprintID,
                        criteriaContent=cb.criteriaContent,
                        criteriaType=cb.criteriaType,
                        archived=False
                    ) for cb in criteria_map[sub.subareaBlueprintID]
                ])


def ensure_numeric_embeddings(df, column="embedding"):
    """Converts string embeddings to numeric NumPy arrays."""
    if isinstance(df[column].iloc[0], str):
        df[column] = df[column].apply(
            lambda x: np.array(ast.literal_eval(x.replace("np.str_(", "").replace(")", "")))
        )

    emb_df = pd.DataFrame(df[column].to_list(), index=df.index)
    emb_df.columns = [f"emb_{i}" for i in range(emb_df.shape[1])]
    return emb_df

def compare_documents(new_doc, past_docs, model, top_n=5):
    print(f"[compare_documents] ENTRY - past_docs type: {type(past_docs)}, shape: {getattr(past_docs, 'shape', 'N/A')}")
    
    is_empty = getattr(past_docs, 'empty', True)
    print(f"[compare_documents] past_docs.empty: {is_empty}")
    
    if is_empty:
        print("[compare_documents] early return: past_docs is empty → returning (None, empty_df)")
        return None, pd.DataFrame()

    # === Compute probability (if classifier) ===
    prob = None
    print(f"[compare_documents] Starting probability computation...")
    try:
        emb = pd.DataFrame([new_doc["embedding"]])
        emb.columns = [f"emb_{i}" for i in range(len(emb.columns))]
        print(f"[compare_documents] Created embedding dataframe: shape {emb.shape}")

        input_df = pd.DataFrame([new_doc]).drop(columns=["embedding"], errors="ignore")
        print(f"[compare_documents] input_df before concat: shape {input_df.shape}, columns: {list(input_df.columns)}")
        
        input_df = pd.concat([input_df, emb], axis=1)
        print(f"[compare_documents] input_df after concat: shape {input_df.shape}, columns: {list(input_df.columns)[:10]}{'...' if len(input_df.columns)>10 else ''}")

        # --- Align features with model expected inputs if available ---
        required_features = None
        try:
            print(f"[compare_documents] model type: {type(model)}")
            print(f"[compare_documents] model attributes: hasattr feature_names_in_={hasattr(model, 'feature_names_in_')}, hasattr steps={hasattr(model, 'steps')}")
            
            # sklearn Pipeline or estimator may expose feature_names_in_
            if hasattr(model, "feature_names_in_"):
                required_features = list(model.feature_names_in_)
                print(f"[compare_documents] model.feature_names_in_ found: {len(required_features)} features → {required_features[:5]}{'...' if len(required_features)>5 else ''}")
            # If pipeline, try to get feature_names_in_ from final estimator
            elif hasattr(model, "steps"):
                print(f"[compare_documents] model has steps (pipeline) with {len(model.steps)} steps")
                for name, step in reversed(model.steps):
                    print(f"[compare_documents]   checking step '{name}': hasattr feature_names_in_={hasattr(step, 'feature_names_in_')}")
                    if hasattr(step, "feature_names_in_"):
                        required_features = list(step.feature_names_in_)
                        print(f"[compare_documents] final pipeline step '{name}' feature_names_in_ found: {len(required_features)} features → {required_features[:5]}{'...' if len(required_features)>5 else ''}")
                        break
            else:
                print(f"[compare_documents] model is not a pipeline and has no feature_names_in_")
        except Exception as _ferr:
            print(f"[compare_documents] Error inspecting model features: {_ferr}")
            import traceback
            traceback.print_exc()

        if required_features is not None:
            print(f"[compare_documents] Aligning input_df to required features ({len(required_features)} total)")
            # add missing columns with zeros and drop extras
            for f in required_features:
                if f not in input_df.columns:
                    input_df[f] = 0.0
            # Keep only required order
            input_df = input_df[required_features]
            print(f"[compare_documents] input_df after alignment: shape {input_df.shape}")
        else:
            print(f"[compare_documents] No required features determined; using input_df as-is: shape {input_df.shape}")

        print(f"[compare_documents] Calling model.predict with input shape: {input_df.shape}")
        print(f"[compare_documents] input_df dtypes: {dict(input_df.dtypes)}")

        # Predict rating using regressor
        pred_raw = model.predict(input_df)
        print(f"[compare_documents] model.predict returned: type={type(pred_raw)}, value={pred_raw}")
        
        pred = float(pred_raw[0])
        print(f"[compare_documents] Raw predicted rating: {pred}")
        
        # Convert predicted rating (1–5) → probability (0–1)
        prob = float(1 / (1 + math.exp(-2.0 * (pred - 3))))
        print(f"[compare_documents] Scaled probability (via logistic): {prob}")
    except Exception as e:
        print(f"[compare_documents] ❌ Error computing probability: {e}")
        import traceback
        traceback.print_exc()
        prob = None

    # === Parse and validate embeddings ===
    print(f"[compare_documents] Starting embedding validation...")
    print(f"[compare_documents] past_docs has {len(past_docs)} rows")
    print(f"[compare_documents] past_docs['embedding'].dtype: {past_docs['embedding'].dtype}")
    print(f"[compare_documents] Sample past_docs['embedding'][0]: type={type(past_docs['embedding'].iloc[0])}, len={len(past_docs['embedding'].iloc[0]) if hasattr(past_docs['embedding'].iloc[0], '__len__') else 'N/A'}")
    print(f"[compare_documents] new_doc['embedding']: type={type(new_doc['embedding'])}, len={len(new_doc['embedding']) if hasattr(new_doc['embedding'], '__len__') else 'N/A'}")
    
    def parse_embedding(val):
        if val is None:
            return None
        if isinstance(val, (list, tuple, np.ndarray)):
            arr = np.array(val, dtype=float)
            return arr if arr.size > 0 else None
        if isinstance(val, (str, np.str_)):
            s = str(val)
            if s.startswith("np.str_(") and s.endswith(")"):
                s = s[len("np.str_("):-1].strip("'\"")
            try:
                return np.array(ast.literal_eval(s), dtype=float)
            except Exception:
                try:
                    return np.array(json.loads(s), dtype=float)
                except Exception:
                    try:
                        # last resort: strip brackets and split
                        s2 = s.strip("[]() ")
                        parts = [p.strip() for p in s2.split(",") if p.strip()]
                        return np.array([float(p) for p in parts], dtype=float)
                    except Exception:
                        return None
        return None

    parsed_embeddings = []
    valid_indices = []

    for idx, val in enumerate(past_docs["embedding"].values):
        arr = parse_embedding(val)
        if arr is not None:
            emb_len = len(arr)
            new_emb_len = len(new_doc["embedding"])
            if emb_len == new_emb_len:
                parsed_embeddings.append(arr)
                valid_indices.append(idx)
                if idx < 3:  # Log first 3 for sample
                    print(f"[compare_documents]   idx={idx}: ✓ parsed embedding len={emb_len}")
            else:
                if idx < 3:  # Log first 3 for sample
                    print(f"[compare_documents]   idx={idx}: ✗ length mismatch: {emb_len} vs {new_emb_len}")
        else:
            if idx < 3:  # Log first 3 for sample
                print(f"[compare_documents]   idx={idx}: ✗ failed to parse")

    print(f"[compare_documents] Embedding validation result: {len(parsed_embeddings)}/{len(past_docs)} embeddings valid")
    
    if not parsed_embeddings:
        print("[compare_documents] ❌ No valid past embeddings found → returning (prob={prob}, empty_df)")
        return prob, pd.DataFrame()

    # === Compute cosine similarities ===
    print(f"[compare_documents] Computing cosine similarities...")
    try:
        past_embedding = np.vstack(parsed_embeddings)
        new_embedding = np.array(new_doc["embedding"], dtype=float).reshape(1, -1)

        print(f"[compare_documents] past_embedding shape: {past_embedding.shape}")
        print(f"[compare_documents] new_embedding shape: {new_embedding.shape}")

        if past_embedding.shape[1] != new_embedding.shape[1]:
            print(f"[compare_documents] ❌ Shape mismatch: past={past_embedding.shape[1]} vs new={new_embedding.shape[1]}")
            return prob, pd.DataFrame()

        similarities = cosine_similarity(new_embedding, past_embedding).flatten()
        print(f"[compare_documents] Computed {len(similarities)} similarity scores: min={similarities.min()}, max={similarities.max()}, mean={similarities.mean()}")
        
        past_docs = past_docs.iloc[valid_indices].copy()
        past_docs["similarity"] = similarities

        top_similar = past_docs.sort_values(by="similarity", ascending=False).head(top_n)
        print(f"[compare_documents] Top {top_n} similar docs: {len(top_similar)} returned")
        if not top_similar.empty:
            print(f"[compare_documents]   top doc similarity: {top_similar['similarity'].iloc[0]}")
    except Exception as e:
        print(f"[compare_documents] ❌ Error computing cosine similarity: {e}")
        import traceback
        traceback.print_exc()
        top_similar = pd.DataFrame()

    # === Return probability and top similar documents ===
    print(f"[compare_documents] RETURN: prob={prob}, top_similar rows={len(top_similar)}")
    return prob, top_similar[["docName", "similarity", "isApproved"]] if not top_similar.empty else top_similar