import requests
import os
from urllib.parse import quote, urlparse, unquote
from requests.auth import HTTPBasicAuth
from io import BytesIO
from werkzeug.utils import secure_filename
from flask import Response, stream_with_context, send_file, jsonify
from app.models import Document
import uuid
from urllib.parse import urlparse


NEXTCLOUD_URL = os.getenv('NEXTCLOUD_URL')
NEXTCLOUD_USER = os.getenv('NEXTCLOUD_USER')
NEXTCLOUD_PASSWORD = os.getenv('NEXTCLOUD_PASSWORD')

# Reuse a single HTTP session for keep-alive/connection pooling
_session = requests.Session()
_session.auth = HTTPBasicAuth(NEXTCLOUD_USER, NEXTCLOUD_PASSWORD)
_session.headers.update({'Connection': 'keep-alive'})

def safe_path(path :str):
    # Encode each segment separately to keep `/` intact
    return "/".join(quote(p.strip()) for p in path.split('/'))


def _get_webdav_bases():
    """Return (dav_base, files_base, uploads_base) built from NEXTCLOUD_URL root.
    dav_base:  <origin>/remote.php/dav/
    files:     dav_base + files/<username>/
    uploads:   dav_base + uploads/<username>/
    """
    parsed = urlparse(NEXTCLOUD_URL)
    # If NEXTCLOUD_URL already points to /remote.php/dav, keep only origin
    origin = f"{parsed.scheme}://{parsed.netloc}"
    dav_base = origin.rstrip('/') + '/remote.php/dav/'
    files_base = dav_base + f'files/{NEXTCLOUD_USER}/'
    uploads_base = dav_base + f'uploads/{NEXTCLOUD_USER}/'
    # Debug print of bases for troubleshooting
    try:
        print(f"WEBDAV BASES -> dav: {dav_base} | files: {files_base} | uploads: {uploads_base}")
    except Exception:
        pass
    return dav_base, files_base, uploads_base

def build_nextcloud_url(doc_path: str):
    # Build a URL inside the user's files namespace
    _, files_base, _ = _get_webdav_bases()
    encoded_path = "/".join(quote(p) for p in doc_path.strip("/").split("/"))
    return f"{files_base}{encoded_path}"


# Create folder if it doesn't exists under files namespace
created_dirs = set()
def ensure_directories(path: str):   
    # Remove leading/trailing slashes and split into segments
    path = path.strip("/")
    if not path:
        return True
    
    segments = path.split("/")
    current_path = ""
    
    for segment in segments:
        if not segment.strip():  # Skip empty segments
            continue
            
        current_path += "/" + segment.strip()
        
        # Skip if we've already created this directory
        if current_path in created_dirs:
            continue
            
        # Construct the full URL for this directory
        # Create inside files namespace
        _, files_base, _ = _get_webdav_bases()
        url = f"{files_base}{current_path.strip('/')}"
        
        print(f"Creating directory: {url}")
        
        try:
            resp = requests.request(
                "MKCOL", 
                url, 
                auth=(NEXTCLOUD_USER, NEXTCLOUD_PASSWORD),
                timeout=30
            )
            
            if resp.status_code == 201:
                # Directory created successfully
                created_dirs.add(current_path)
                print(f"Directory created: {current_path}")
            elif resp.status_code == 405:
                # Directory already exists
                created_dirs.add(current_path)
                print(f"Directory already exists: {current_path}")
            else:
                print(f"Error creating directory {current_path}: {resp.status_code} - {resp.text}")
                return False
                
        except requests.exceptions.RequestException as e:
            print(f"Network error creating directory {current_path}: {e}")
            return False
            
    return True



def upload_to_nextcloud(file, path):    
    
    filename = secure_filename(file.filename)
    target_url = build_nextcloud_url(f"{path}/{filename}")
    
    print(f"Uploading to Nextcloud URL: {target_url}")
    print(f"Using credentials - User: {NEXTCLOUD_USER}, Password: {'*' * len(NEXTCLOUD_PASSWORD)}")

    #idk what the f is this tbh
    def _chunk_iter(stream, chunk_size=1024 * 1024):  # 1MB chunks
        while True:
            data = stream.read(chunk_size)
            if not data:
                break
            yield data

    # Use the underlying Werkzeug FileStorage stream
    file.stream.seek(0)
    try:
        response = _session.put(
            target_url,
            data=_chunk_iter(file.stream),
            headers={'Content-Type': 'application/octet-stream'},
            timeout=120
        )
        return response
    finally:
        try:
            file.stream.seek(0)
        except Exception:
            pass



def preview_from_nextcloud(doc_path):
    try:
        target_url = build_nextcloud_url(doc_path)

        response = _session.get(
                target_url, 
                timeout = 30, 
                stream = True
            )

        print(f"Response status: {response.status_code}")
        print(f"Content-Type: {response.headers.get('Content-Type')}")
        print(f"Content-Length: {response.headers.get('Content-Length')}")

        return response
    
    except requests.exceptions.RequestException as e:
        print(f"Nextcloud request failed: {e}")

        class MockResponse:
            status_code = 500
            text = str(e)
            headers = {}
        return MockResponse()
    

def rename_file_nextcloud(old_path, new_path):
    # Use the proper webdav base function
    _, files_base, _ = _get_webdav_bases()
    
    # Decode paths to check structure
    old_path_decoded = unquote(old_path) if old_path else ""
    new_path_decoded = unquote(new_path) if new_path else ""
    
    # Remove leading/trailing slashes
    old_path_decoded = old_path_decoded.strip('/')
    new_path_decoded = new_path_decoded.strip('/')
    
    # Ensure UDMS_Repository prefix exists
    if old_path_decoded and not old_path_decoded.startswith('UDMS_Repository'):
        old_path_decoded = f"UDMS_Repository/{old_path_decoded}"
    if new_path_decoded and not new_path_decoded.startswith('UDMS_Repository'):
        new_path_decoded = f"UDMS_Repository/{new_path_decoded}"
    
    # Build URLs using files_base
    old_url = files_base + safe_path(old_path_decoded)
    new_url = files_base + safe_path(new_path_decoded)
    
    # Ensure destination parent directory exists
    new_path_parent = os.path.dirname(new_path_decoded.strip('/'))
    if new_path_parent:
        try:
            ensure_directories(new_path_parent)
        except Exception as e:
            print(f"WARN: Could not ensure destination directory exists: {e}")

    print(f"Renaming in Nextcloud:")
    print(f"  Old path: {old_path_decoded}")
    print(f"  New path: {new_path_decoded}")
    print(f"  Old URL: {old_url}")
    print(f"  New URL: {new_url}")

    try:
        # MOVE request with absolute Destination URL
        response = _session.request(
            "MOVE",
            old_url,
            headers={
                "Destination": new_url,
                "Overwrite": "T"  # Allow overwrite if destination exists
            },
            timeout=60
        )
        
        print(f"Nextcloud rename response: {response.status_code}")
        if response.status_code not in (200, 201, 204, 207):
            print(f"Response body: {response.text}")
        
        return response  
    
    except requests.exceptions.RequestException as e:
        print(f"Nextcloud rename error: {str(e)}")
        raise Exception(f"Nextcloud connection failed: {str(e)}")



# Upload or overwrite (edit) a file in Nextcloud
def edit_file_nextcloud(file_path, file_content):
   
    _, files_base, _ = _get_webdav_bases()
    file_url = files_base + '/'.join(quote(part) for part in file_path.split('/'))

    try:
        # If file_content is string, encode to bytes
        if isinstance(file_content, str):
            file_content = file_content.encode("utf-8")

        response = _session.put(
            file_url,
            data=file_content,
            timeout=120
        )

        if response.status_code in [200, 201, 204]:
            return jsonify({
                "success": True,
                "message": "File updated successfully",
                "path": file_path
            }), response.status_code
        else:
            return jsonify({
                "error": f"Failed to update file. Status {response.status_code}",
                "details": response.text
            }), response.status_code

    except Exception as e:
        return jsonify({"error": str(e)}), 500



def delete_from_nextcloud(doc_path):
    try:
        _, files_base, _ = _get_webdav_bases()
        encoded_path = quote(doc_path.strip('/'))
        target_url = f"{files_base}{encoded_path}"

        print(f"Deleting at Nextcloud: {target_url}")

        response = _session.delete(
                target_url, 
                timeout = 30
            )

        print(f"Response status: {response.status_code}")
        print(f"Response text: {response.text}")

        return response
    except requests.exceptions.RequestException as e:
        print(f"Nextcloud request failed: {e}")

        class MockResponse:
            status_code = 500
            text = str(e)
            headers = {}
        return MockResponse()


# Fetch all files & folders from Nextcloud and return as a nested dict (tree).
def list_files_from_nextcloud():
    # root of repository inside user's files namespace
    _, files_base, _ = _get_webdav_bases()
    UDMS_URL = f"{files_base}UDMS_Repository/"

    response = _session.request(
        "PROPFIND",
        UDMS_URL,
        headers={"Depth": "infinity"}
    )

    if response.status_code != 207:
        raise Exception(f"NextCloud Error: {response.status_code} - {response.text}")

    from xml.etree import ElementTree as ET
    from urllib.parse import unquote, urlparse
    import os

    tree = ET.fromstring(response.content)
    ns = {"d": "DAV:"}

    paths = []
    responses = [] 

    parsed = urlparse(UDMS_URL)
    base_path = parsed.path if parsed.path else "/"
    if not base_path.endswith('/'):
        base_path += '/'

    for resp in tree.findall("d:response", ns):
        href = resp.find("d:href", ns).text.rstrip("/")
        if href.rstrip("/") == base_path.rstrip("/"):
            continue

        relative_path = unquote(href)
        if relative_path.startswith(base_path):
            relative_path = relative_path[len(base_path):]
        relative_path = relative_path.lstrip("/")

        paths.append(relative_path)
        responses.append((relative_path, resp))  # map path → XML node

    root = {"files": [], "folders": {}}
    file_ext = {"pdf", "docx", "xlsx", "txt", "pptx", "jpg", "png", "jpeg", "xls", "ppt", "csv", "webp"}

    # Preload all docs from DB into a dict {path: Document}
    db_docs = {doc.docPath: doc for doc in Document.query.all()}

    for path, resp in responses:
        parts = path.split("/")
        current = root
        for i, part in enumerate(parts):
            is_last = i == len(parts) - 1
            props = resp.find("d:propstat/d:prop", ns)

            size = props.find("d:getcontentlength", ns)
            mime = props.find("d:getcontenttype", ns)
            modified = props.find("d:getlastmodified", ns)            

            if is_last:
                ext = os.path.splitext(part)[1].lower().lstrip(".")
                if ext in file_ext:
                    # Add UDMS_Repository to match DB docPath                    
                    db_doc = db_docs.get(f"UDMS_Repository/{path}")     
                    print(f"Looking for: UDMS_Repository/{path}")                    

                    file_obj = {
                        "name": unquote(part),
                        "type": "file",
                        "size": int(size.text) if size is not None and size.text else None,
                        "mime": mime.text if mime is not None else None,
                        "modified": modified.text if modified is not None else None,
                        "docID": db_doc.docID if db_doc else None,
                        "docName": db_doc.docName if db_doc else None,
                        "docTag": db_doc.tags if db_doc else None,
                    }
                    current["files"].append(file_obj)
                else:
                    if part not in current["folders"]:
                        current["folders"][unquote(part)] = {
                            "files": [],
                            "folders": {},
                            "type": "folder",
                            "meta": {
                                "name": unquote(part),
                                "modified": modified.text if modified is not None else None
                            }
                        }
            else:                
                decoded_part = unquote(part)
                if decoded_part not in current["folders"]:
                    current["folders"][decoded_part] = {"files": [], "folders": {}, "meta": {"name": decoded_part}}
                current = current["folders"][decoded_part]

    return root



    # Preview file from Nextcloud
def preview_file_nextcloud(file_path):
    _, files_base, _ = _get_webdav_bases()
    url = f"{files_base}{safe_path(file_path)}"

    response = _session.get(
        url,
        stream=True
    )

    if response.status_code == 200:
        return Response(
            stream_with_context(response.iter_content(chunk_size=8192)),
            content_type=response.headers.get("Content-Type")

        )
    else:
        return Response(f"Error fetching file: {response.status_code} - {response.text}", status=response.status_code)
 
def download_file_nextcloud(file_path):
    _, files_base, _ = _get_webdav_bases()
    url = f"{files_base}{safe_path(file_path)}"

    response = _session.get(
        url,
        stream=True
    )
    print(f"Downloading: {file_path} -> Status {response.status_code}")

    if response.status_code == 200:
        # Wrap response content in a BytesIO for Flask
        return send_file(
            BytesIO(response.content),
            as_attachment=True,
            download_name=os.path.basename(file_path),
            mimetype=response.headers.get("Content-Type", "application/octet-stream")
        )
    else:
        return jsonify({"error": f"Failed to download file: {response.status_code}"}), response.status_code

#idk fk
def upload_to_nextcloud_chunked(file, nextcloud_final_path, empID=None, redis_client=None):
    print("DEBUG: Entered upload_to_nextcloud_chunked")
    username = NEXTCLOUD_USER
    print(f"DEBUG: User is {empID}, NEXTCLOUD_USER is {NEXTCLOUD_USER}")
    # Derive correct WebDAV base: scheme://host/remote.php/dav/
    # This avoids duplicating remote.php if NEXTCLOUD_URL already contains paths
    parsed = urlparse(NEXTCLOUD_URL)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    webdav_base = origin.rstrip('/') + '/remote.php/dav/'
    upload_id = str(uuid.uuid4().hex)
    chunk_size = 5 * 1024 * 1024  # 5MB

    # Ensure the upload directory exists
    upload_base_dir = f"{webdav_base}uploads/{username}/{upload_id}"
    mkcol_resp = _session.request("MKCOL", upload_base_dir, timeout=60)
    # 201 Created, 405 Method Not Allowed = already exists
    if mkcol_resp.status_code not in [201, 405]:
        raise Exception(f"Failed to initialize upload dir: {mkcol_resp.status_code} {mkcol_resp.text}")

    # Nextcloud expects zero-padded 16-digit decimal chunk names
    chunks = []
    idx = 0
    chunk_url = None  # initialize to avoid UnboundLocalError on early failures
    file.stream.seek(0)
    total_size = 0
    while True:
        data = file.stream.read(chunk_size)
        if not data:
            break
        chunk_name = f"{idx:016d}"
        chunk_url = f"{upload_base_dir}/{chunk_name}"
        print(f"DEBUG CHUNK {idx} URL: {chunk_url}")
        resp = _session.put(chunk_url, data=data, timeout=120)
        if resp.status_code not in [201, 204]:
            if redis_client and empID:
                redis_client.setex(f"upload_status:{empID}:{file.filename}", 300, f"Failed at chunk {idx}")
            raise Exception(f"Failed uploading chunk {idx} url={chunk_url}: {resp.status_code} {resp.text}")
        total_size += len(data)
        chunks.append(chunk_name)
        percent = int((file.stream.tell() / file.content_length) * 100) if hasattr(file, 'content_length') and file.content_length else int(len(chunks) * chunk_size / (file.content_length or (len(chunks) * chunk_size)) * 100)
        if redis_client and empID:
            redis_client.setex(f"upload_status:{empID}:{file.filename}", 300, percent)
        idx += 1
    # Ensure destination directory exists under files namespace
    try:
        dest_dir = os.path.dirname(nextcloud_final_path.strip('/'))
        if dest_dir:
            print(f"DEBUG ENSURE DIRS -> {dest_dir}")
            ensure_directories(dest_dir)
    except Exception as e:
        print(f"WARN ensure_directories failed: {e}")

    # Finalize upload by MOVING the virtual `.file` resource (Nextcloud assembles on MOVE)
    assembled_url = f"uploads/{username}/{upload_id}/.file"
    final_url_path = nextcloud_final_path.lstrip('/')
    src_url = f"{webdav_base}{assembled_url}"
    dst_url = f"{webdav_base}files/{username}/{final_url_path}"

    # MOVE (assemble) to final – no prior PUT required for .file
    try:
        print(f"DEBUG MOVE ASSEMBLE -> SRC: {src_url}  DST: {dst_url}")
    except Exception:
        pass
    move_resp = _session.request(
        "MOVE",
        src_url,
        headers={
            "Destination": dst_url,
            "Overwrite": "T"
        },
        timeout=180
    )
    if move_resp.status_code not in [201, 204]:
        if redis_client and empID:
            redis_client.setex(f"upload_status:{empID}:{file.filename}", 300, "Failed MOVE assemble")
        raise Exception(f"Failed to finalize (MOVE) file: {move_resp.status_code} {move_resp.text}")
    if redis_client and empID:
        redis_client.setex(f"upload_status:{empID}:{file.filename}", 120, 100)
    return move_resp