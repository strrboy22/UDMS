import json
from flask import jsonify, request, session, send_from_directory, current_app, Response, render_template
from app import db, redis_client, socketio, mail
from werkzeug.security import check_password_hash, generate_password_hash, _hash_internal
from werkzeug.utils import secure_filename
from flask_jwt_extended import create_access_token, create_refresh_token, get_jwt_identity, jwt_required, decode_token, exceptions, verify_jwt_in_request                                
from flask_jwt_extended import set_access_cookies, set_refresh_cookies, unset_jwt_cookies
from flask_jwt_extended.exceptions import JWTExtendedException
from datetime import timedelta, datetime, timezone
from app.utils.normalize_path import normalize_path
from app.utils.file_extractor import extract_pdf, extract_docs, extract_excel, extract_image
from app.utils.tagging_utils import rule_based_tag, extract_global_tfid_tags
from app.utils.helper_functions import reapply_template, compare_documents
from app.nextcloud_service import upload_to_nextcloud, preview_from_nextcloud, delete_from_nextcloud, ensure_directories, safe_path, list_files_from_nextcloud, preview_file_nextcloud, download_file_nextcloud, rename_file_nextcloud, edit_file_nextcloud, upload_to_nextcloud_chunked
from sentence_transformers import SentenceTransformer
from urllib.parse import quote, unquote
import numpy as np
import pandas as pd
import joblib
import mimetypes
import os
import re
import time
import redis
from app.otp_utils import generate_random
from flask_mail import Message as MailMessage
from app.login_handlers import complete_user_login
from app.models import Employee, Program, Area, Subarea, Institute, Document, Deadline, AuditLog, Announcement, Criteria, Conversation, ConversationParticipant, Message, MessageDeletion, Template, AreaBlueprint, SubareaBlueprint, CriteriaBlueprint, AppliedTemplate, Notification, EmployeeProgram, EmployeeArea, EmployeeFolder, AreaReference, EmployeeProgram, EmployeeArea, EmployeeFolder, AreaReference, DeadlineCriteria
from sqlalchemy import cast, String, func, text
from app.security.anti_brute_force import get_client_ip, is_ip_blocked, track_failed_login, block_ip, clear_failed_attempts

def register_routes(app):
    # =================================w=========== AUTHENTICATION(LOGIN/LOGOUT) PAGE ROUTES ============================================
    
    # JWT Exception Handler
    @app.errorhandler(JWTExtendedException)
    def handle_jwt_exception(e):
        return jsonify({"error": str(e)}), 401 
    
    #LOGIN API
    @app.route('/api/login', methods=["POST"])
    
    def login():
        try:
            #Get the JSON from the request
            data = request.get_json()
            empID = data.get("employeeID")
            user_ip = get_client_ip()

            if is_ip_blocked(user_ip):
                return jsonify({
                    'success': False,
                    'message': 'Too many login attempts. IP has temporarily blocked.'
                }), 429

            password = data.get("password")

            #Fetches the user from the db using the employeeID
            user = Employee.query.filter_by(employeeID=empID).first()
            #If the user is not found in the db
            if user is None:
                return jsonify({'success': False, 'message': 'Employee not found'})
            
            # Check if the user has a valid password hash
            if not user.password or len(user.password.strip()) == 0:
                return jsonify({'success': False, 'message': 'User account has no password set. Contact administrator.'}), 400
            
            # Try to verify the password hash, handle invalid hash format errors
            try:
                is_valid_password = check_password_hash(user.password, password)
            except ValueError as hash_error:
                current_app.logger.error(f"Invalid password hash for user {empID}: {hash_error}")
                return jsonify({'success': False, 'message': 'User account has invalid password format. Contact administrator.'}), 400
                
            if is_valid_password:
                # Clear failed login attempts on successful login
                clear_failed_attempts(user_ip)
                
                # audit successful login
                new_log = AuditLog(
                    employeeID = user.employeeID,
                    action = f"{user.lName}, {user.fName} {user.suffix}. LOGGED IN. Admin={user.isAdmin}"
                )
                db.session.add(new_log)
                db.session.commit()

                bypass = redis_client.get(f'otp_bypass:{empID}')
                if bypass:
                    print(f"DEBUG: Skipping OTP generate for {empID} due to otp_bypass.")
                    return complete_user_login(user, empID)
                else:
                    # Defensive: ensure empID is string
                    if not empID or not isinstance(empID, str):
                        print(f"ERROR: empID for OTP is not a valid string! empID={empID}")
        
                    otp_code = generate_random()
                    # Store OTP in Redis with TTL (3 minutes)
                    redis_key = f'otp:{empID}'
                    redis_client.setex(redis_key, 180, str(otp_code))
                    print(f"DEBUG: Stored OTP in Redis as {redis_key} = {otp_code}")


                    html_body = render_template(
                        'email/otp.html',
                        otp=str(otp_code),
                        user_name=user.fName,
                        app_name='UDMS',
                        recipients=user.email,
                        logo_url='https://external-content.duckduckgo.com/iu/?u=https%3A%2F%2Fudmwebsite.udm.edu.ph%2Fwp-content%2Fuploads%2F2023%2F11%2Fudm-logo-1.png&f=1&nofb=1&ipt=a0799b507adde1d83ee8939c52524c6fb2053df034c369f55787f6b1d5db7574'
                    )
                    msg = MailMessage('Your UDMS Login OTP Code', recipients=[user.email])
                    msg.html = html_body

                    redis_client.hset('pending_otps', empID, 'waiting')
                    mail.send(msg)

                    return jsonify({'success': True, 'message': 'OTP email sent succesfully'})
            else:
                attempts = track_failed_login(user_ip)
                if attempts >= 5:
                    block_ip(user_ip, employee_id=empID)
                    return jsonify({
                        'success': False,
                        'message': 'Too many failed attempts. IP has been temporarily blocked.'
                    }), 429
                return jsonify({'success': False, 'message': 'Invalid password'}), 401
        except Exception as e:
            current_app.logger.error(f"Login error: {e}")
            return jsonify({'success': False, 'message': 'Internal server error'}), 500
    
    @app.route('/api/verify-otp', methods=['POST'])
    def verify_otp():
        data = request.get_json()
        otp = data.get('otp')
        employeeID = data.get('employeeID')

        if not employeeID:
            return jsonify({'success': False, 'message': 'Employee ID are required.'}), 400
        if not otp:
            return jsonify({'success': False, 'message': 'OTP are required'}), 400
        if not otp.isdigit() or not len(otp) == 6:
            return jsonify({'success': False, 'message': 'OTP "ONLY" contains number and MUST be 6 digits.'}), 400
        pending_status = redis_client.hget('pending_otps', employeeID)
        if not pending_status:
            return jsonify({'success': False, 'message': 'No pending OTP request for this user.'}), 400
        #why this?
        user = Employee.query.filter_by(employeeID=employeeID).first()
        if not user:
            return jsonify({'success': False, 'message': 'User not found in database.'}), 400
        # Validate OTP from Redis
        otp_key = f"otp:{employeeID}"
        stored_code = redis_client.get(otp_key)
        if not stored_code:
            return jsonify({'success': False, 'message': 'OTP has expired or is invalid. Please request a new OTP.'}), 400
        if str(otp) != stored_code.decode():
            return jsonify({'success': False, 'message': "OTP Doesn't match!"}), 400
        # Success: invalidate OTP and allow login
        redis_client.delete(otp_key)
        redis_client.hdel('pending_otps', employeeID)
        # set otp_bypass for 24hrs
        redis_client.setex(f'otp_bypass:{employeeID}', 24*60*60, '1')
        return complete_user_login(user, employeeID)

        
    @app.route('/api/me', methods=['GET'])
    @jwt_required()
    def me():
        emp_id = get_jwt_identity()
        # 1) Try Redis cache first
        cache_key = f'user_profile:{emp_id}'
        cached = redis_client.get(cache_key)
        if cached:
            try:
                return jsonify({'success': True, 'user': json.loads(cached.decode())}), 200
            except Exception:
                pass

        # 2) Fallback to DB and rebuild cache
        user = Employee.query.filter_by(employeeID=emp_id).first()
        if not user:
            return jsonify({'success': False, 'message': 'User not found'})

        user_programs = []
        user_areas = []

        for ep in user.employee_programs:
            program = Program.query.get(ep.programID)
            if program:
                user_programs.append({
                    'programID': program.programID,
                    'programCode': program.programCode,
                    'programName': program.programName
                })

        for ea in user.employee_areas:
            area = Area.query.get(ea.areaID)
            if area:
                user_areas.append({
                    'areaID': area.areaID,
                    'areaName': area.areaName,
                    'areaNum': area.areaNum
                })

        profile = {
            'employeeID': user.employeeID,
            'firstName': user.fName,
            'lastName': user.lName,
            'programs': user_programs,
            'areas': user_areas,
            'suffix': user.suffix,
            'email': user.email,
            'contactNum': user.contactNum,
            'profilePic': user.profilePic,
            'isAdmin': user.isAdmin,
            'isRating': user.isRating,
            'isEdit': user.isEdit,
            'crudFormsEnable': user.crudFormsEnable,
            'crudProgramEnable': user.crudProgramEnable,
            'crudInstituteEnable': user.crudInstituteEnable,
            'role': 'admin' if user.isAdmin else 'user',
            'isCoAdmin': user.isCoAdmin
        }

        try:
            redis_client.setex(cache_key, 300, json.dumps(profile))
        except Exception:
            pass

        return jsonify({'success': True, 'user': profile}), 200
    
    @app.route('/api/validate-session', methods=['POST'])
    def validate_session():
        try:
            session_id = request.json.get('session_id')
            print(f"Validating session: {session_id}")  # Debug log
            
            if not session_id:
                return jsonify({'valid': False, 'error': 'No session ID'}), 400
            
            # Check if session exists in Redis
            redis_key = f'session:{session_id}'
            exists = redis_client.exists(redis_key)
            print(f"Redis key {redis_key} exists: {exists}")  # Debug log
            
            if not exists:
                return jsonify({'valid': False}), 401
            
            return jsonify({'valid': True}), 200
            
        except Exception as e:
            print(f"Validation error: {e}")
            return jsonify({'valid': False, 'error': str(e)}), 500

        
    @app.route('/api/protected', methods=["GET"])
    @jwt_required()
    def protected():
         # Access the identity of the current user with get_jwt_identity
        current_user = get_jwt_identity()
        return jsonify(logged_in_as=current_user), 200
    
    
    # REFRESH TOKEN ENDPOINT
    @app.route('/api/refresh-token', methods=["POST"])
    @jwt_required(refresh=True)  # This decorator requires refresh token, not access token
    def refresh():
        try:
            # Get the user identity from the refresh token
            current_user_id = get_jwt_identity()
            
            # Fetch user from database to get latest info
            user = Employee.query.filter_by(employeeID=current_user_id).first()
            
            if not user:
                return jsonify({'success': False, 'message': 'User not found'}), 404
            
            # Create new access token with fresh data
            new_access_token = create_access_token(
                identity=current_user_id,
                expires_delta=timedelta(minutes=15),
                additional_claims={
                    'role': 'admin' if user.isAdmin else 'user',
                    'firstName': user.fName,
                    'lastName': user.lName
                }
            )
            
            # Optionally create new refresh token (recommended for security)
            new_refresh_token = create_refresh_token(
                identity=current_user_id,
                expires_delta=timedelta(days=7)
            )
            
            # Prepare updated user data
            user_data = {
                'employeeID': user.employeeID,
                'firstName': user.fName,
                'lastName': user.lName,
                'suffix': user.suffix,
                'email': user.email,
                'contactNum': user.contactNum,
                'profilePic': user.profilePic,
                'isAdmin': user.isAdmin,
                'role': 'admin' if user.isAdmin else 'user'
            }
            
            resp = jsonify({
                'success': True,
                'message': 'Token refreshed successfully',
                'access_token': new_access_token,
                'refresh_token': new_refresh_token,
                'user': user_data
            })
            # Also set cookies so subsequent requests with credentials include them
            try:
                from flask_jwt_extended import set_access_cookies, set_refresh_cookies
                set_access_cookies(resp, new_access_token)
                set_refresh_cookies(resp, new_refresh_token)
            except Exception as _:
                pass
            return resp, 200
            
        except Exception as e:
            # Audit failed token refresh instead of repeating new token
            if current_user_id:
                user = Employee.query.filter_by(employeeID=current_user_id).first()
                if user:
                    new_log = AuditLog(
                        employeeID=current_user_id,
                        action=f"{user.lName}, {user.fName} {user.suffix or ''}. TOKEN REFRESH FAILED. Admin={user.isAdmin}"
                    )
                    db.session.add(new_log)
                    db.session.commit()

            current_app.logger.error(f"Token refresh error: {e}")
            return jsonify({'success': False, 'message': 'Token refresh failed'}), 500
    

    def get_session_from_request():
        # Get session ID from request headers or body
        session_id = request.json.get('sessionId') if request.is_json else None
        return session_id

    #Audit session expired
    @app.route('/api/session-expired', methods=["POST"])
    def sessionExpired():
        try:
            data = request.get_json() or {}
            empID = data.get('employeeID')
            session_id = data.get('session_id')

            # Clean up session from Redis
            if session_id:
                redis_key = f'session:{session_id}'
                redis_client.delete(redis_key)
                redis_client.hdel('user_status', empID)

            # Clean up user from online users (if empID provided)
            if empID:
                redis_client.srem('online_users', empID)
            
            # Always return success for logout (even if empID missing)
            resp = jsonify({'success': True})
            unset_jwt_cookies(resp) 

            # Audit session expired
            user = Employee.query.filter_by(employeeID=empID).first()
            new_log = AuditLog(
                employeeID = empID,
                action = f"{user.lName}, {user.fName} {user.suffix}. SESSION EXPIRED. Admin={user.isAdmin}"
            )
            db.session.add(new_log)
            db.session.commit()

            return resp
            
        except Exception as e:
            print(f"Logout error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
        
    # Audit Logout
    @app.route('/api/logout', methods=["POST"])
    @jwt_required()
    def logout():
        try:
            data = request.get_json() or {}
            empID = data.get('employeeID')
            session_id = data.get('session_id')

            # Clean up session from Redis
            if session_id:
                redis_key = f'session:{session_id}'
                redis_client.delete(redis_key)
                redis_client.hdel('user_status', empID)

            # Clean up user from online users (if empID provided)
            if empID:
                redis_client.srem('online_users', empID)
            
            # Always return success for logout (even if empID missing)
            resp = jsonify({'success': True})
            unset_jwt_cookies(resp) 

            # Audit successful logouts
            user = Employee.query.filter_by(employeeID=get_jwt_identity()).first()
            new_log = AuditLog(
                employeeID = empID,
                action = f"{user.lName}, {user.fName} {user.suffix}. LOGGED OUT. Admin={user.isAdmin}"
            )
            db.session.add(new_log)
            db.session.commit()

            return resp
            
        except Exception as e:
            print(f"Logout error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500



    # ============================================ DASHBOARD ROUTES ============================================

    @app.route('/api/announcement/post', methods=["POST"])
    @jwt_required()
    def post_announce():
        try:
            data = request.get_json()
            title = data.get("title") 
            message = data.get("message")
            duration = data.get("duration")
            userID = get_jwt_identity()

            duration = datetime.strptime(duration, "%Y-%m-%d").date()


            new_announcement = Announcement(
                employeeID = userID,
                announceTitle = title, 
                announceText = message, 
                duration = duration
            )
            db.session.add(new_announcement)

            # Audit new announcement
            currentUser = Employee.query.filter_by(employeeID=userID).first()
            new_log = AuditLog(
                employeeID = currentUser.employeeID,
                action = f"{currentUser.lName}, {currentUser.fName} {currentUser.suffix} Created a new announcement {title}"
            )
            db.session.add(new_log)
            db.session.commit()

            # Real-time notifications: notify all active users about the announcement
            try:
                from app.socket_handlers import create_notification
                # Notify every employee except the author
                employees = Employee.query.with_entities(Employee.employeeID).all()
                for (emp_id,) in employees:
                    if str(emp_id) == str(userID):
                        continue
                create_notification(
                        recipient_id=str(emp_id),
                    notification_type='announcement',
                        title=title or 'New Announcement',
                        content=message or '',
                        sender_id=str(userID),
                        link='/Dashboard'
                    )
            except Exception as notify_err:
                current_app.logger.error(f"Announcement notification emit failed: {notify_err}")

            return jsonify({'success': True, 'message': 'Announcement created successfully'}), 200 
        except Exception as e:
            return jsonify({'success': False, 'message': f'Failed to create announcement, {e}'}), 500

    @app.route('/api/announcements', methods=["GET"])
    def get_announcements():
        try:            
            announcement = (Announcement.query
                            .join(Employee, Employee.employeeID == Announcement.employeeID)
                            .add_columns(
                                Announcement.announceID,
                                Announcement.announceTitle,
                                Announcement.announceText,
                                Announcement.duration,
                                Employee.fName,
                                Employee.lName,
                                Employee.suffix                                
                            )).all()

            result = []

            for ann in announcement:
                announce_data = {
                    'announceID': ann.announceID,
                    'announceTitle': ann.announceTitle,
                    'announceText': ann.announceText,
                    'duration': ann.duration,
                    'author': f"{ann.fName} {ann.lName} {ann.suffix or ''}".strip()
                }
                
                result.append(announce_data)
                
            return jsonify(result), 200
        
        except Exception as e:
            return jsonify({'success': False, 'message': f'Failed to fetch announcements, {e}'}), 500

    @app.route('/api/announcement/delete/<int:announcement_id>', methods=['DELETE'])
    @jwt_required()
    def delete_announcement(announcement_id):
        try:
            current_user_id = get_jwt_identity()
            admin_user = Employee.query.filter_by(employeeID=current_user_id).first()
            if not admin_user or not admin_user.isAdmin:
                return jsonify({'success': False, 'message': 'Admins only'}), 403

            announcement = Announcement.query.filter_by(announceID=announcement_id).first()
            if not announcement:
                return jsonify({'success': False, 'message': 'Announcement not found'}), 404

            db.session.delete(announcement)

            # Audit deleted announcement
            new_log = AuditLog(
                employeeID = admin_user.employeeID,
                action = f"{admin_user.lName}, {admin_user.fName} {admin_user.suffix} DELETED ANNOUNCEMENT {announcement.announceTitle}"
            )
            db.session.add(new_log)
            db.session.commit()

            return jsonify({'success': True, 'message': 'Announcement deleted successfully'}), 200

        except Exception as e:
            current_app.logger.error(f"Delete announcement error: {e}")
            return jsonify({'success': False, 'message': 'Failed to delete announcement'}), 500

        

    

    # ============================================ USER PAGE ROUTES ============================================

    # CREATE USER
    @app.route('/api/user', methods=["POST"])
    @jwt_required()
    def create_user():
        # admin-only
        current_user_id = get_jwt_identity()
        admin_user = Employee.query.filter_by(employeeID=current_user_id).first()
        if not admin_user or not admin_user.isAdmin:
            return jsonify({'success': False, 'message': 'Admins only'}), 403

        # get the user input 
        data = request.form
        profilePic = request.files.get("profilePic")  #  Do not override this
        empID = data.get("employeeID", "").strip()
        password = data.get("password", "").strip()
        first_name = data.get("fName", "").strip()
        last_name = data.get("lName", "").strip()
        suffix = data.get("suffix", "").strip()
        email = data.get("email", "").strip()
        contactNum = data.get("contactNum", "").strip()
        
        # Parse JSON arrays for programs and areas
        try:
            programs = json.loads(data.get("programs", "[]"))
            areas = json.loads(data.get("areas", "[]"))
        except json.JSONDecodeError:
            return jsonify({'success': False, 'message': 'Invalid programs or areas format'}), 400
        
        # Parse selected folders for folder permissions
        try:
            selected_folders = json.loads(data.get("selectedFolder", "[]"))
        except json.JSONDecodeError:
            selected_folders = []
        
        isAdmin = str(data.get("isAdmin", "false")).lower() in ["true", "1", "yes", "y"]
        isRating = str(data.get("isRating", "false")).lower() in ["true", "1", "yes", "y"]
        isEdit = str(data.get("isEdit", "false")).lower() in ["true", "1", "yes", "y"]
        isCoAdmin = str(data.get("isCoAdmin", "false")).lower() in ["true", "1", "yes", "y"]
        crudFormsEnable = str(data.get("crudFormsEnable", "false")).lower() in ["true", "1", "yes", "y"]
        crudProgramEnable = str(data.get("crudProgramEnable", "false")).lower() in ["true", "1", "yes", "y"]
        crudInstituteEnable = str(data.get("crudInstituteEnable", "false")).lower() in ["true", "1", "yes", "y"]
        created_at = datetime.now()

        # email regex for validation
        validEmail = "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        
        # Check if this is an update operation (user already exists)
        existing_user = Employee.query.filter_by(employeeID=empID).first()
        is_update = existing_user is not None

        # Validate required fields based on operation type
        if not empID:
            return jsonify({'success': False, 'message': 'Employee ID is required'}), 400
            
        if not is_update:
            # For new users, all fields are required
            if not password:
                return jsonify({'success': False, 'message': 'Password cannot be empty'}), 400
            if not first_name:
                return jsonify({'success': False, 'message': 'First name is required'}), 400
            if not last_name:
                return jsonify({'success': False, 'message': 'Last name is required'}), 400
            if not email or not re.match(validEmail, email):
                return jsonify({'success': False, 'message': 'Please enter a valid email'}), 400
            # Accept both formats: +63 XXX XXX XXXX or 09XXXXXXXXX
            if not contactNum or not (re.match(r'^\+63 \d{3} \d{3} \d{4}$', contactNum) or re.match(r'^\d{11}$', contactNum)):
                return jsonify({'success': False, 'message': 'Contact number must be in format +63 XXX XXX XXXX'}), 400
        else:
            # For updates, only validate fields that are provided
            if first_name and not first_name.strip():
                return jsonify({'success': False, 'message': 'First name cannot be empty if provided'}), 400
            if last_name and not last_name.strip():
                return jsonify({'success': False, 'message': 'Last name cannot be empty if provided'}), 400
            if email and not (re.match(validEmail, email)):
                return jsonify({'success': False, 'message': 'Please enter a valid email'}), 400
            if contactNum and not (re.match(r'^\+63 \d{3} \d{3} \d{4}$', contactNum) or re.match(r'^\d{11}$', contactNum)):
                return jsonify({'success': False, 'message': 'Contact number must be in format +63 XXX XXX XXXX'}), 400
        
        # === Handle the Profile Picture (optional) ===
        profilePicPath = None
        if profilePic:  #  Only validate and upload if provided
            if profilePic.filename == '':
                return jsonify({'success': False, 'message': 'No selected file'}), 400
            
            allowed_extensions = {'jpg', 'png'}
            if '.' not in profilePic.filename:
                return jsonify({'success': False, 'message': 'Invalid file format'}), 400

            file_extension = profilePic.filename.rsplit('.', 1)[1].lower()
            if file_extension not in allowed_extensions:
                return jsonify({'success': False, 'message': 'Invalid file format. Only jpg and png allowed.'}), 400

            # Build Nextcloud path
            path = f"UDMS_Repository/Profile_Pictures"
            encoded_path = safe_path(path)
            ensure_directories(encoded_path)

            filename = f"{empID}.{file_extension}"
            filename = secure_filename(filename)

            if not filename:
                return jsonify({'success': False, 'message': 'Invalid filename'}), 400

            # Upload to Nextcloud
            response = upload_to_nextcloud(profilePic, encoded_path)
            if response.status_code not in (200, 201, 204):
                return jsonify({
                    'success': False,
                    'message': 'Nextcloud profile picture upload failed.',
                    'status': response.status_code,
                    'details': response.text
                }), 400
            
            profilePicPath = f"{path}/{filename}"  # Save path if uploaded

        # For updates, make validation more flexible
        if is_update:
            # For updates, only validate fields that are provided and not empty
            if first_name and not first_name.strip():
                return jsonify({'success': False, 'message': 'First name cannot be empty if provided'}), 400
            if last_name and not last_name.strip():
                return jsonify({'success': False, 'message': 'Last name cannot be empty if provided'}), 400
            if email and not (re.match(validEmail, email)):
                return jsonify({'success': False, 'message': 'Please enter a valid email'}), 400
            if contactNum and not (re.match(r'^\+63 \d{3} \d{3} \d{4}$', contactNum) or re.match(r'^\d{11}$', contactNum)):
                return jsonify({'success': False, 'message': 'Contact number must be in format +63 XXX XXX XXXX'}), 400
            
            # For updates, programs and areas are optional - only validate if provided
            if programs and len(programs) > 0 and not all(program.strip() for program in programs if isinstance(program, str)):
                return jsonify({'success': False, 'message': 'Invalid program selection'}), 400
            if areas and len(areas) > 0 and not all(area.strip() for area in areas if isinstance(area, str)):
                return jsonify({'success': False, 'message': 'Invalid area selection'}), 400
        else:
            # For new users, all fields are required
            # Validate that programs and areas are provided
            if not programs or len(programs) == 0:
                return jsonify({'success': False, 'message': 'At least one program is required'}), 400
            if not areas or len(areas) == 0:
                return jsonify({'success': False, 'message': 'At least one area is required'}), 400

        if is_update:
            # Update existing user - only update fields that are provided
            if first_name and first_name.strip():
                existing_user.fName = first_name
            if last_name and last_name.strip():
                existing_user.lName = last_name
            if suffix is not None:  # Allow empty suffix
                existing_user.suffix = suffix
            if email and email.strip():
                existing_user.email = email
            if contactNum and contactNum.strip():
                existing_user.contactNum = contactNum
            if profilePicPath:  # Only update if new profile pic was uploaded
                existing_user.profilePic = profilePicPath
            
            # Always update permissions (these are boolean values)
            existing_user.isAdmin = isAdmin
            existing_user.isRating = isRating
            existing_user.isEdit = isEdit
            existing_user.isCoAdmin = isCoAdmin
            existing_user.crudFormsEnable = crudFormsEnable
            existing_user.crudProgramEnable = crudProgramEnable
            existing_user.crudInstituteEnable = crudInstituteEnable

            # Update password only if provided
            if password and password.strip():
                existing_user.password = generate_password_hash(password, method="pbkdf2:sha256")

            user = existing_user
        else:
            # Create new user
            user = Employee(
                employeeID=empID,
                password=generate_password_hash(password, method="pbkdf2:sha256"),
                fName=first_name,
                lName=last_name,
                suffix=suffix,
                email=email,
                contactNum=contactNum,
                profilePic=profilePicPath,
                isAdmin=isAdmin,
                isRating=isRating,
                isEdit=isEdit,
                isCoAdmin=isCoAdmin,
                crudFormsEnable=crudFormsEnable,
                crudProgramEnable=crudProgramEnable,
                crudInstituteEnable=crudInstituteEnable,
                created_at=created_at
            )
        db.session.add(user)
        db.session.flush()  # Flush to get the employeeID for junction tables

        if is_update:
            # For updates, only update junction tables if programs/areas are provided
            if programs and len(programs) > 0:
                # Delete existing EmployeeProgram entries for update
                EmployeeProgram.query.filter_by(employeeID=empID).delete()
                # Create new EmployeeProgram entries
                for program_id in programs:
                    emp_program = EmployeeProgram(
                        employeeID=empID,
                        programID=int(program_id)
                    )
                    db.session.add(emp_program)
            
            if areas and len(areas) > 0:
                # Delete existing EmployeeArea entries for update
                EmployeeArea.query.filter_by(employeeID=empID).delete()
                # Create new EmployeeArea entries
                for area_id in areas:
                    emp_area = EmployeeArea(
                        employeeID=empID,
                        areaID=int(area_id)
                    )
                    db.session.add(emp_area)
        else:
            # For new users, always create junction table entries
            # Create EmployeeProgram entries
            for program_id in programs:
                emp_program = EmployeeProgram(
                    employeeID=empID,
                    programID=int(program_id)
                )
                db.session.add(emp_program)

            # Create EmployeeArea entries
            for area_id in areas:
                emp_area = EmployeeArea(
                    employeeID=empID,
                    areaID=int(area_id)
                )
                db.session.add(emp_area)
            
        # Handle EmployeeFolder entries
        if is_update:
            # For updates, only update folder permissions if provided
            if selected_folders and len(selected_folders) > 0:
                # Delete existing EmployeeFolder entries for update
                EmployeeFolder.query.filter_by(employeeID=empID).delete()
                # Create new EmployeeFolder entries
                for folder_path in selected_folders:
                    emp_folder = EmployeeFolder(
                        employeeID=empID,
                        folderPath=folder_path
                    )
                    db.session.add(emp_folder)
        else:
            # For new users, create folder permissions if provided
            for folder_path in selected_folders:
                emp_folder = EmployeeFolder(
                    employeeID=empID,
                    folderPath=folder_path
                )
                db.session.add(emp_folder)

        # Audit user operation
        action_type = "UPDATED" if is_update else "CREATED NEW"
        new_log = AuditLog(
            employeeID = admin_user.employeeID,
            action = f"{admin_user.lName}, {admin_user.fName} {admin_user.suffix} {action_type} USER {empID}. Admin={isAdmin}, CoAdmin={isCoAdmin}"
        )
        db.session.add(new_log)
        db.session.commit()
        # Invalidate cached users list
        try:
            redis_client.delete('users:list')
        except Exception:
            pass

        message = 'Employee updated successfully!' if is_update else 'Employee created successfully!'
        return jsonify({
            'success': True,
            'message': message,
            'profilePic': profilePicPath,  # Return None if no upload
        }), 200
 
        

    #Reset user password (for fixing invalid password hashes)
    @app.route('/api/user/<string:employeeID>/reset-password', methods=["POST"])
    @jwt_required()
    def reset_user_password(employeeID):
        # admin-only
        current_user_id = get_jwt_identity()
        admin_user = Employee.query.filter_by(employeeID=current_user_id).first()
        if not admin_user or not admin_user.isAdmin:
            return jsonify({'success': False, 'message': 'Admins only'}), 403
        try:
            data = request.get_json()
            new_password = data.get("newPassword")
            
            if not new_password or len(new_password.strip()) == 0:
                return jsonify({'success': False, 'message': 'New password cannot be empty'}), 400
            
            user = Employee.query.filter_by(employeeID=employeeID).first()
            if not user:
                return jsonify({'success': False, 'message': 'Employee not found'}), 404
            
            # Update with properly hashed password
            user.password = generate_password_hash(new_password)
            db.session.commit()
            
            return jsonify({'success': True, 'message': f'Password reset successfully for employee {employeeID}'}), 200
            
        except Exception as e:
            current_app.logger.error(f"Password reset error: {e}")
            return jsonify({'success': False, 'message': 'Failed to reset password'}), 500

    #Delete the user 
    @app.route('/api/user/<string:employeeID>', methods=["DELETE"])
    @jwt_required()
    def delete_user(employeeID):
        # admin-only
        current_user_id = get_jwt_identity()
        admin_user = Employee.query.filter_by(employeeID=current_user_id).first()
        if not admin_user or not admin_user.isAdmin:
            return jsonify({'success': False, 'message': 'Admins only'}), 403
        user = Employee.query.filter_by(employeeID=employeeID).first()

        if not user:
            return jsonify({"success": False, "message": "Employee does not exists"}), 404
        
        db.session.delete(user)

        # Audit deleted user
        new_log = AuditLog(
            employeeID = admin_user.employeeID,
            action = f"{admin_user.lName}, {admin_user.fName} {admin_user.suffix} Deleted a user: {user.lName}, {user.fName} {user.suffix}"
        )
        db.session.add(new_log)
        db.session.commit()
        try:
            redis_client.delete('users:list')
        except Exception:
            pass

        return jsonify({"success": True, "message":"Employee has been deleted successfully!"}), 200

    #Check for users with invalid password hashes
    @app.route('/api/users/check-invalid-passwords', methods=["GET"])
    def check_invalid_passwords():
        try:
            users_with_invalid_passwords = []
            all_users = Employee.query.all()
            
            for user in all_users:
                if not user.password or len(user.password.strip()) == 0:
                    users_with_invalid_passwords.append({
                        'employeeID': user.employeeID,
                        'name': f"{user.fName} {user.lName}",
                        'email': user.email,
                        'issue': 'Empty password hash'
                    })
                else:
                    # Try to validate the hash format by attempting to parse it
                    try:
                        # This will raise ValueError if the hash format is invalid
                        _hash_internal(user.password, 'test')
                    except ValueError:
                        users_with_invalid_passwords.append({
                            'employeeID': user.employeeID,
                            'name': f"{user.fName} {user.lName}",
                            'email': user.email,
                            'issue': 'Invalid hash format'
                        })
                    except Exception:
                        # If we can't even test the hash, it's definitely invalid
                        users_with_invalid_passwords.append({
                            'employeeID': user.employeeID,
                            'name': f"{user.fName} {user.lName}",
                            'email': user.email,
                            'issue': 'Corrupted hash format'
                        })
            
            return jsonify({
                'success': True, 
                'count': len(users_with_invalid_passwords),
                'users': users_with_invalid_passwords
            }), 200
            
        except Exception as e:
            current_app.logger.error(f"Check invalid passwords error: {e}")
            return jsonify({'success': False, 'message': 'Failed to check passwords'}), 500

    #Test specific user's password hash
    @app.route('/api/user/<string:employeeID>/test-password', methods=["GET"])
    def test_user_password(employeeID):
        try:
            user = Employee.query.filter_by(employeeID=employeeID).first()
            if not user:
                return jsonify({'success': False, 'message': 'Employee not found'}), 404
            
            result = {
                'employeeID': user.employeeID,
                'name': f"{user.fName} {user.lName}",
                'email': user.email,
                'hasPassword': bool(user.password),
                'passwordLength': len(user.password) if user.password else 0,
                'passwordPreview': user.password[:20] + '...' if user.password and len(user.password) > 20 else user.password
            }
            
            # Test if the hash format is valid
            if user.password:
                try:
                    _hash_internal(user.password, 'test')
                    result['hashValid'] = True
                    result['hashError'] = None
                except ValueError as e:
                    result['hashValid'] = False
                    result['hashError'] = str(e)
                except Exception as e:
                    result['hashValid'] = False
                    result['hashError'] = f"Unexpected error: {str(e)}"
            else:
                result['hashValid'] = False
                result['hashError'] = 'No password set'
            
            return jsonify({'success': True, 'user': result}), 200
            
        except Exception as e:
            current_app.logger.error(f"Test password error: {e}")
            return jsonify({'success': False, 'message': 'Failed to test password'}), 500



    # ============================================ DATA FETCHING ROUTES ============================================

    # Gets the data count for user, programs, and institutes                                        
    @app.route('/api/count', methods=["GET"])
    def get_count():
        employee_count = (Employee.query.count())                                            
        program_count = (Program.query.count())                                            
        institute_count = (Institute.query.count())      
        deadline_count = (Deadline.query.count())      

        return jsonify({'employees' : employee_count, 'programs' : program_count, 'institutes' : institute_count, 'deadlines' : deadline_count  })                                    
                                                            
    # GET USER PROFILE BY EMPLOYEE ID
    @app.route('/api/profile/<string:employeeID>', methods=["GET"])
    @jwt_required()
    def get_user_profile(employeeID):
        try:
            # Query user
            user = Employee.query.filter_by(employeeID=employeeID).first()
            
            if not user:
                return jsonify({
                    'success': False, 
                    'message': 'Employee not found'
                }), 404
            
            # Get user's programs and areas from junction tables
            user_programs = []
            user_areas = []
            
            for ep in user.employee_programs:
                program = Program.query.get(ep.programID)
                if program:
                    user_programs.append({
                        'programID': program.programID,
                        'programName': program.programName,
                        'programCode': program.programCode
                    })
            
            for ea in user.employee_areas:
                area = Area.query.get(ea.areaID)
                if area:
                    user_areas.append({
                        'areaID': area.areaID,
                        'areaName': area.areaName,
                        'areaNum': area.areaNum
                    })
            
            # Prepare detailed profile data
            profile_data = {
                'employeeID': user.employeeID,
                'firstName': user.fName,
                'lastName': user.lName, 
                'suffix': user.suffix or '',
                'email': user.email,
                'contactNumb': user.contactNum,  # Note: matches your frontend expectation
                'profilePic': user.profilePic,
                'isAdmin': user.isAdmin,
                'role': 'admin' if user.isAdmin else 'user',
            
                'programs': user_programs,
                'areas': user_areas,
  
                'programName': user_programs[0]['programName'] if user_programs else 'Not Assigned',
                'programCode': user_programs[0]['programCode'] if user_programs else 'N/A', 
                'areaName': user_areas[0]['areaName'] if user_areas else 'Not Assigned',
                'areaNum': user_areas[0]['areaNum'] if user_areas else 'N/A'
            }
            
            return jsonify({
                'status': 'success',  # Note: matches your frontend check
                'success': True,
                'data': profile_data
            }), 200
            
        except Exception as e:
            current_app.logger.error(f"Get profile error: {e}")
            return jsonify({
                'success': False, 
                'message': 'Failed to fetch profile'
            }), 500
        
    # Get profile picture
    @app.route('/api/user/profile-pic/<string:employeeID>', methods=["GET"])
    @jwt_required()
    def get_profile_pic(employeeID):
        token = request.args.get("token")

        if token:
            try:
                decoded = decode_token(token) # validate the token manually
            except exceptions.JWTDecodeError:
                return jsonify({"success": False, "message": "Invalid token"}), 401
            
        else:
            verify_jwt_in_request()  # fallback to Authorization header

        NEXTCLOUD_URL = os.getenv("NEXTCLOUD_URL")
        NEXTCLOUD_USER = os.getenv("NEXTCLOUD_USER")
        NEXTCLOUD_PASSWORD = os.getenv("NEXTCLOUD_PASSWORD")
        
        print(f"Nextcloud config - URL: {NEXTCLOUD_URL is not None}, User: {NEXTCLOUD_USER is not None}, Password: {NEXTCLOUD_PASSWORD is not None}")


        if not all([NEXTCLOUD_URL, NEXTCLOUD_USER, NEXTCLOUD_PASSWORD]):
            return jsonify({
                'success': False,
                'message': 'Nextcloud Configuration missing'
            }), 500

        user = Employee.query.filter_by(employeeID=employeeID).first()
        if not user or not user.profilePic:
            print(f"User or profile pic not found for employee: {employeeID}")
            return jsonify({'success': False, 'message': 'Profile Picture not found'}), 404
        
        print(f"Profile pic path: {user.profilePic}")

        # Fetch from nextcloud
        response = preview_from_nextcloud(user.profilePic)  
        print(f"Nextcloud response status: {response.status_code}")        
           
        if response.status_code == 200:
            return Response(
                response.iter_content(chunk_size=8192),
                content_type=response.headers.get("Content-Type", "image/jpeg"),
                headers={
                    "Content-Disposition": f'inline; filename="{employeeID}.jpg"'
                }
            )
        else:
            return jsonify({
                'success': False,
                'status': response.status_code,
                'detail': response.text
            }), response.status_code

    @app.route('/api/profile', methods=['POST'])
    @jwt_required()
    def change_profile():
        current_user = get_jwt_identity()
        user = Employee.query.filter_by(employeeID=current_user).first()

        if not user:
            return jsonify({'success': False, 'message': 'you cannot edit this user.'}), 404
        try:
            data = request.get_json()
            if not data:
                return jsonify({'success': False, 'message': 'no data passed.'}), 400

            suffix = data.get('suffix')
            email = data.get('email')
            contactNum = data.get('contactNum')
            experience = data.get('experience')
            password = data.get('password')

            if email and not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
                return jsonify({'success': False, 'message': 'Invalid email format'}), 400
        
            if password and len(password) < 6:
                return jsonify({'success': False, 'message': 'Password must be at least 6 characters'}), 400
            if suffix is not None:
                user.suffix = suffix
            if email is not None:
                user.email = email
            if contactNum is not None:
                user.contactNum = contactNum
            if experience is not None:
                user.experiences = experience
            if password is not None:
                user.password = generate_password_hash(password, method="pbkdf2:sha256")
            db.session.commit()

            return jsonify({
                'success': True,
                'message': 'Profile updated successfully',
                'updated_user_data': {
                    'firstName': user.fName,
                    'lastName': user.lName,
                    'suffix': user.suffix,
                    'email': user.email,
                    'experience': user.experiences,
                    'contactNum': user.contactNum,
                }
            }), 200
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': 'Failed to update profile.'})

                                                            
    #Get the users 
    @app.route('/api/users', methods=["GET"])
    @jwt_required()
    def get_users():
        # Try cache first for 60s shared list
        try:
            cached = redis_client.get('users:list')
            if cached:
                return jsonify({"users": json.loads(cached.decode())}), 200
        except Exception:
            pass

        users = Employee.query.all()
        user_list = []
        for user in users:
            # Get user's programs and areas from junction tables
            user_programs = []
            user_areas = []
            
            for ep in user.employee_programs:
                program = Program.query.get(ep.programID)
                if program:
                    user_programs.append(program.programName)
            
            for ea in user.employee_areas:
                area = Area.query.get(ea.areaID)
                if area:
                    user_areas.append(f"{area.areaNum}: {area.areaName}")
            
            # Get user's folder permissions
            user_folders = []
            for ef in user.employee_folders:
                user_folders.append(ef.folderPath)
            
            user_data = {
                'employeeID': user.employeeID,
                'fName': user.fName,
                'lName': user.lName,
                'suffix': user.suffix,
                'programs': user_programs,
                'areas': user_areas,
                'folders': user_folders,
                'programName': ', '.join(user_programs) if user_programs else 'Not Assigned',
                'areaName': ', '.join(user_areas) if user_areas else 'Not Assigned',
                'areaNum': user_areas[0].split(':')[0] if user_areas else 'N/A',
                'name': f"{user.fName} {user.lName} {user.suffix or ''}",
                'email': user.email,
                'contactNum': user.contactNum,
                'profilePic': f"/api/user/profile-pic/{user.employeeID}" if user.profilePic else None,
                'isAdmin': user.isAdmin,
                'isCoAdmin': user.isCoAdmin,
                'isRating': user.isRating,
                'isEdit': user.isEdit,
                'crudFormsEnable': user.crudFormsEnable,
                'crudProgramEnable': user.crudProgramEnable,
                'crudInstituteEnable': user.crudInstituteEnable,
                'isOnline': user.isOnline
            } 
        
            user_list.append(user_data)
        # Save to cache
        try:
            redis_client.setex('users:list', 60, json.dumps(user_list))
        except Exception:
            pass
        return jsonify({"users" : user_list}), 200

    # ============================================ INSTITUTES PAGE ROUTES ============================================
    
    #edit institute base on institute 
    
    ALLOWED_EXTENSION = {'jpg', 'jpeg', 'png', 'webp'}
    
    @app.route('/api/institute/<int:instID>', methods=['PUT'])
    @jwt_required()    
    def edit_institute(instID):
    
        # Edit an existing institute by ID
        # Expects JSON data with institute information
        
        try:
            # Check admin permissions
            current_user_id = get_jwt_identity()
            admin_user = Employee.query.filter_by(employeeID=current_user_id).first()
            if not admin_user or not admin_user.isAdmin:
                return jsonify({'success': False, 'message': 'Admins only'}), 403
            
            # Find the institute to edit
            institute = Institute.query.filter_by(instID=instID).first()
            
            if not institute:
                return jsonify({'success': False, 'message': 'Institute not found'}), 
            
            content_type = request.content_type or ''
            
            # If request is multipart/form-data (for file upload)
            if 'multipart/form-data' in request.content_type:
                data = request.form
                inst_code = data.get('instCode')
                inst_name = data.get('instName')
                employee_id = data.get('employeeID')
                inst_pic_file = request.files.get('instPic')  # Optional new logo file
                
                if inst_code: 
                    institute.instCode = inst_code
                if inst_name: 
                    institute.instName = inst_name
                if employee_id is not None:
                    institute.employeeID = employee_id.strip() if employee_id and employee_id.strip() else None
                
                # If user uploaded new logo, push to Nextcloud instead of local
                if inst_pic_file and inst_pic_file.filename:
                    allowed_extensions = {'jpg', 'jpeg','png', 'webp'}
                    if '.' not in inst_pic_file.filename:
                        return jsonify({'success': False, 'message': 'Invalid file format'}), 400
                    
                    file_extension = inst_pic_file.filename.rsplit('.', 1)[1].lower()
                    if file_extension not in allowed_extensions:
                        return jsonify({
                            'success': False, 
                            'message': 'Invalid file format. Only jpg, jpeg, png, webp allowed.'
                        }), 400

                    # Construct filename: always based on instCode
                    filename = secure_filename(f"{institute.instCode}.{file_extension}")
                    
                    # Path inside Nextcloud (example: Institutes/logos/<filename>)
                    nc_path = f"Institutes/logos/{filename}"

                    # Upload/overwrite to Nextcloud
                    response, status = edit_file_nextcloud(nc_path, inst_pic_file.read())
                    if status not in (200, 201, 204):
                        return jsonify({
                            "success": False,
                            "message": f"Failed to upload file to Nextcloud: {response.get_json() if response.is_json else response}"
                        }), status

                    # Store the Nextcloud relative path in DB
                    institute.instPic = nc_path

            else:
                # JSON payload (no file)
                data = request.get_json()
                if 'instCode' in data:
                    institute.instCode = data.get('instCode')
                if 'instName' in data:
                    institute.instName = data.get('instName')
                if 'employeeID' in data:
                    employee_id = data.get('employeeID')
                    institute.employeeID = employee_id.strip() if employee_id and employee_id.strip() else None
            
            # audit edit of institute
            new_log = AuditLog(
                employeeID = admin_user.employeeID,
                action = f"{admin_user.lName}, {admin_user.fName} {admin_user.suffix} Edited the institute {institute.instName}"
            )
            db.session.add(new_log)
            # Save changes
            db.session.commit()
            
            # Get dean info for response
            dean = institute.dean if institute.employeeID else None
            dean_name = f"{dean.fName} {dean.lName} {dean.suffix or ''}".strip() if dean else "N/A"
            
            return jsonify({
                'success': True,
                'message': 'Institute updated successfully',
                'data': {
                    'instID': institute.instID,
                    'instCode': institute.instCode,
                    'instName': institute.instName,
                    'instPic': institute.instPic,  # Now stored as Nextcloud path
                    'instDean': dean_name,
                    'employeeID': institute.employeeID
                }
            }), 200
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Edit institute error: {str(e)}")
            return jsonify({'success': False, 'message': f'Database error: {str(e)}'}), 500


    @app.route('/api/institutes', methods=['POST'])
    @jwt_required()
    def create_institute():
        try:
            data = request.form
            instCode = data.get('instCode')
            instName = data.get("instName")
            instPic = request.files.get('instPic')
            employee_id = data.get('employeeID')

            if not instCode or not instName:
                return jsonify({'success': False, 'message': 'Institute code and name are required'}), 400

            if not instPic:
                return jsonify({'success': False, 'message': 'Institute logo (instPic) is required'}), 400

            if instPic.filename == '':
                return jsonify({'success': False, 'message': 'No file selected'}), 400

            allowed_extensions = {'jpg', 'jpeg', 'png', 'webp'}
            if '.' not in instPic.filename:
                return jsonify({'success': False, 'message': 'Invalid file format'}), 400

            file_extension = instPic.filename.rsplit('.', 1)[1].lower()
            if file_extension not in allowed_extensions:
                return jsonify({'success': False, 'message': 'Invalid file format. Only jpg, jpeg, png, webp allowed.'}), 400

            # Create uploads folder if missing
            upload_folder = os.path.join(current_app.root_path, "uploads")
            os.makedirs(upload_folder, exist_ok=True)

            filename = f"{instCode}.{file_extension}"
            filename = secure_filename(filename)

            save_path = os.path.join(upload_folder, filename)
            instPic.save(save_path)

            # Save just the filename in DB (not full path)
            instPicPath = filename

            new_institute = Institute(
                instCode=instCode,
                instName=instName,
                instPic=instPicPath,
                employeeID=employee_id.strip() if employee_id and employee_id.strip() else None
            )
            db.session.add(new_institute)

            # Audit new institute
            admin_user = Employee.query.filter_by(employeeID=get_jwt_identity()).first()
            new_log = AuditLog(
                employeeID = admin_user.employeeID,
                action = f"{admin_user.lName}, {admin_user.fName} {admin_user.suffix} Created an institute: {instName}"
            )
            db.session.add(new_log)
            db.session.commit()

            dean = new_institute.dean
            dean_name = f"{dean.fName} {dean.lName} {dean.suffix or ''}" if dean else "N/A"

            return jsonify({
                'success': True,
                'message': 'Institute Created Successfully',
                'instID': new_institute.instID,
                'instCode': new_institute.instCode,
                'instName': new_institute.instName,
                'instPic': new_institute.instPic,
                'instDean': dean_name,
                'employeeID': new_institute.employeeID
            })

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Create Institute error: {str(e)}")
            return jsonify({'error': f'Failed to create institute {str(e)}'}), 500



    #Delete institute by ID
    @app.route('/api/institute/<int:instID>', methods=['DELETE'])
    @jwt_required()
    def delete_institute(instID):
        try:
            current_user_id = get_jwt_identity()
            admin_user = Employee.query.filter_by(employeeID=current_user_id).first()
            if not admin_user or not admin_user.isAdmin:
                return jsonify({'success': False, 'message': 'Admins only'}), 403

            institute = Institute.query.filter_by(instID=instID).first()
            if not institute:
                return jsonify({'error': 'Institute not found'}), 404

            updated_counts = {}
            programs_updated = Program.query.filter_by(instID=instID).update({'instID': None})
            updated_counts['programs'] = programs_updated
            
            areas_updated = Area.query.filter_by(instID=instID).update({'instID': None})
            updated_counts['areas'] = areas_updated
            
            deadlines_updated = 0
            if hasattr(Deadline, 'instID'):
                deadlines_updated = Deadline.query.filter_by(instID=instID).update({'instID': None})
            updated_counts['deadlines'] = deadlines_updated
            
            db.session.delete(institute)

            # Audit deleted institute
            new_log = AuditLog(
                employeeID = admin_user.employeeID,
                action = f"{admin_user.lName}, {admin_user.fName} {admin_user.suffix} Deleted the institute {institute.instName}"
            )
            db.session.add(new_log)
            db.session.commit()

            return jsonify({
                'success': True, 
                'message': f'Institute deleted successfully. Related records preserved but unlinked.',
                'deletedID': instID,
                'updated_counts': updated_counts
            }), 200
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Delete institute error: {str(e)}")
            return jsonify({'error': 'Database error occurred'}), 500


    #Get the institute
    @app.route('/api/institute', methods=["GET"])
    @jwt_required()
    def get_institute():
        try:
            current_user_id = get_jwt_identity()
            current_user = Employee.query.filter_by(employeeID=current_user_id).first()
            
            if not current_user:
                return jsonify({'success': False, 'message': 'User not found'}), 404
            
            # All users can see all institutes
            institutes = Institute.query.all()
                    
            institute_list = []

            for institute in institutes:
                dean = institute.dean
                
                # Get program count for this institute
                program_count = Program.query.filter_by(instID=institute.instID).count()

                institute_data = {
                    'instID': institute.instID,
                    'instDean': f"{dean.fName} {dean.lName} {dean.suffix or ''}" if dean else "N/A",
                    'instCode': institute.instCode,
                    'instName': institute.instName,
                    'instPic': institute.instPic,
                    'employeeID': institute.employeeID,
                    'programCount': program_count
                } 
                institute_list.append(institute_data)
                
            return jsonify({
                'success': True,
                'institutes': institute_list,
                'accessLevel': 'full',
                'userPermissions': {
                    'isAdmin': current_user.isAdmin,
                    'isCoAdmin': current_user.isCoAdmin,
                    'crudInstituteEnable': current_user.crudInstituteEnable,
                    'assignedProgramCount': len(current_user.employee_programs)
                }
            }), 200
            
        except Exception as e:
            current_app.logger.error(f"Get institutes error: {e}")
            return jsonify({'success': False, 'message': 'Failed to fetch institutes'}), 500
    

    @app.route('/api/institute/logos/<string:instCode>', methods=["GET"])
    def get_institute_logo(instCode):
        institute = Institute.query.filter_by(instCode=instCode).first()
        if not institute or not institute.instPic:
            return jsonify({"success": False, "message": "Institute logo not found"}), 404

        # Validate Nextcloud configuration
        NEXTCLOUD_URL = os.getenv("NEXTCLOUD_URL")
        NEXTCLOUD_USER = os.getenv("NEXTCLOUD_USER")
        NEXTCLOUD_PASSWORD = os.getenv("NEXTCLOUD_PASSWORD")
        if not all([NEXTCLOUD_URL, NEXTCLOUD_USER, NEXTCLOUD_PASSWORD]):
            return jsonify({
                'success': False,
                'message': 'Nextcloud configuration missing on server'
            }), 500

        raw = (institute.instPic or '').strip()
        # Build candidate paths to match your structure UDMS_Repository/Institutes/Logos
        candidates = []
        if raw:
            filename = os.path.basename(raw)
            name, ext = os.path.splitext(filename)
            if raw.startswith('UDMS_Repository/'):
                # Try exact DB path first
                candidates.append(raw)
                # If it fails, try swapping common image extensions
                if name and ext:
                    dir_prefix = raw[: -len(filename)]
                    for e in ['.png', '.jpg', '.jpeg', '.webp']:
                        if ext.lower() != e:
                            candidates.append(f"{dir_prefix}{name}{e}")
            else:
                if name:
                    exts = [ext] if ext else []
                    for e in ['.png', '.jpg', '.jpeg', '.webp']:
                        if e not in exts:
                            exts.append(e)
                    for e in exts:
                        fname = f"{name}{e}" if e else filename
                        candidates.append(f"UDMS_Repository/Institutes/Logos/{fname}")
                        candidates.append(f"UDMS_Repository/Institutes/logos/{fname}")  
                candidates.append(f"UDMS_Repository/{raw}")

        response = None
        for p in candidates:
            r = preview_from_nextcloud(p)
            if getattr(r, 'status_code', 500) == 200:
                response = r
                break

        if response and response.status_code == 200:
            content_type = response.headers.get("Content-Type", "application/octet-stream")
            return Response(response.content, content_type=content_type)
        else:
            return jsonify({
                "success": False,
                "message": f"Failed to fetch logo for {instCode}",
                "status": getattr(response, 'status_code', 500),
                "detail": getattr(response, "text", "No response text")
            }), getattr(response, 'status_code', 500)            

    # Fetch programs for the institute
    @app.route('/api/institute/programs', methods=["GET"])
    def get_program_for_inst():
        instID = request.args.get('instID', type=int)
        if not instID:
            return jsonify({'programs': []}), 200

        # Try cache first
        cache_key = f'programs:inst:{instID}'
        cached = redis_client.get(cache_key)
        if cached:
            try:
                return jsonify({'programs': json.loads(cached.decode())}), 200
            except Exception:
                pass

        programs = Program.query.filter_by(instID=instID).all()
        program_list = [{
            'programID': p.programID,
            'programCode': p.programCode,
            'programName': p.programName,
        } for p in programs]

        # Save to cache for 30 minutes (programs rarely change)
        try:
            redis_client.setex(cache_key, 1800, json.dumps(program_list))
        except Exception:
            pass

        return jsonify({'programs': program_list}), 200

    
    # ============================================ PROGRAM PAGE ROUTES ============================================
    
    #edit program base on program id
    @app.route('/api/program/<int:programID>', methods=['PUT'])
    @jwt_required()
    def edit_program(programID):
        try:
            # Admin only
            current_user_id = get_jwt_identity()
            admin_user = Employee.query.filter_by(employeeID=current_user_id).first()
            if not admin_user or not admin_user.isAdmin:
                return jsonify({'success': False, 'message': 'Admins only'}), 403

            data = request.get_json() # Get JSON data from frontend
            program = Program.query.filter_by(programID=programID).first()

            if not program:
                return jsonify({'success': False, 'message': 'Program not found'}), 404

            old_inst_id = program.instID
            # Update the database fields with new values
            program.programCode = data.get('programCode', program.programCode)      # Update program code (e.g., "BSIT")
            program.programName = data.get('programName', program.programName)      # Update program name
            program.programColor = data.get('programColor', program.programColor)   # Update program color
            program.employeeID = data.get('employeeID', program.employeeID)         # Handle employeeID - accept string format like "23-45-678"
            program.instID = data.get('instID', program.instID)

            # Audit edited program
            new_log = AuditLog(
                employeeID = admin_user.employeeID,
                action = f"{admin_user.lName}, {admin_user.fName} {admin_user.suffix} Edited the program {program.programName}"
            )
            db.session.add(new_log)
            db.session.commit() # Save changes to database

            # Invalidate program caches for affected institutes
            try:
                if old_inst_id:
                    redis_client.delete(f'programs:inst:{old_inst_id}')
                if program.instID and program.instID != old_inst_id:
                    redis_client.delete(f'programs:inst:{program.instID}')
            except Exception:
                pass

            return jsonify({        
                'success': True,
                'message': 'Program updated successfully',
                'data': {
                    'programID': program.programID,
                    'programCode': program.programCode,
                    'programName': program.programName,
                    'programColor': program.programColor,
                    'employeeID': program.employeeID,
                    'instID': program.instID
                }
            }), 200

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Edit program error: {str(e)}")
            return jsonify({'success': False, 'message': f'Database error: {str(e)}'}), 500

    #Create new program
    @app.route('/api/program', methods=['POST'])
    @jwt_required()
    def create_program():
        try:
            current_user_id = get_jwt_identity()
            admin_user = Employee.query.filter_by(employeeID=current_user_id).first()
            if not admin_user or not admin_user.isAdmin:
                return jsonify({'success': False, 'message': 'Admins only'}), 403
            data = request.get_json()  # Get JSON data from frontend
            
            # Handle employeeID - accept string format like "23-45-678"
            employee_id = data.get('employeeID')
            final_employee_id = employee_id.strip() if employee_id and str(employee_id).strip() else None
            
            # Parse instID and validate it
            inst_id = data.get('instID')
            if inst_id is not None:
                # If provided, ensure institute exists
                inst = Institute.query.filter_by(instID=inst_id).first()
                if not inst:
                    return jsonify({
                        'success': False,
                        'message': 'Institute not found'
                    }), 400
            
            # Create new program object with instID to fetch in College modal
            new_program = Program(
                programCode = data.get('programCode'),
                programName = data.get('programName'),
                programColor = data.get('programColor'),
                employeeID = final_employee_id,
                instID = inst_id # associate program with institute
            )
            
            db.session.add(new_program)  # Add to database

            # Audit new program
            new_log = AuditLog(
                employeeID = admin_user.employeeID,
                action = f"{admin_user.lName}, {admin_user.fName} {admin_user.suffix} Created a new program: {data.get('programName')}"
            )
            db.session.add(new_log)
            db.session.commit()  # Save changes

            # Invalidate cache for this institute's programs
            try:
                if new_program.instID:
                    redis_client.delete(f'programs:inst:{new_program.instID}')
            except Exception:
                pass
            
            # Get the dean info for response (same as edit route)
            dean = new_program.dean
            dean_name = f"{dean.fName} {dean.lName} {dean.suffix or ''}" if dean else "N/A"
            
            return jsonify({
                'success': True,
                'message': 'Program Created Successfully',
                'programID': new_program.programID,
                'programCode': new_program.programCode,
                'programName': new_program.programName,
                'programColor': new_program.programColor,
                'programDean': dean_name,
                'employeeID': new_program.employeeID,
                'instID': new_program.instID
            }), 200
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Create program error: {str(e)}")
            return jsonify({'error': 'Failed to create program'}), 500

    #Delete program by ID
    @app.route('/api/program/<int:programID>', methods=['DELETE'])
    @jwt_required()
    def delete_program(programID):
        try:
            current_user_id = get_jwt_identity()
            admin_user = Employee.query.filter_by(employeeID=current_user_id).first()
            if not admin_user or not admin_user.isAdmin:
                return jsonify({'success': False, 'message': 'Admins only'}), 403

            programs = Program.query.filter_by(programID=programID).first()
            
            if not programs:
                return jsonify({'error': 'Program not found'}), 404
            
            updated_counts = {}
            
            # Delete employee-program relationships instead of updating Employee table
            employees_updated = EmployeeProgram.query.filter_by(programID=programID).delete()
            updated_counts['employees'] = employees_updated
            
            areas_updated = Area.query.filter_by(programID=programID).update({'programID': None})
            updated_counts['areas'] = areas_updated
            
            deadlines_updated = Deadline.query.filter_by(programID=programID).update({'programID': None})
            updated_counts['deadlines'] = deadlines_updated
        
            db.session.delete(programs)

            # Audit deleted program
            new_log = AuditLog(
                employeeID = admin_user.employeeID,
                action = f"{admin_user.lName}, {admin_user.fName} {admin_user.suffix} Deleted a program: {programs.programName}"
            )
            db.session.add(new_log)
            db.session.commit()

            # Invalidate cache for this institute's programs
            try:
                if programs.instID:
                    redis_client.delete(f'programs:inst:{programs.instID}')
            except Exception:
                pass
            
            return jsonify({
                'success': True,
                'message': f'Program deleted successfully. {employees_updated} employees, {areas_updated} areas, and {deadlines_updated} deadlines are now unlinked.',
                'deletedID': programID,
                'updated_counts': updated_counts
            }), 200
                
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Delete program error: {str(e)}")
            return jsonify({'error': 'Database error occurred'}), 500
        
    @app.route('/api/program', methods=['GET', 'OPTIONS'])
    @jwt_required()
    def get_user_program():
        if request.method == 'OPTIONS':
            return ('', 204)
        try:
            current_user_id = get_jwt_identity()
            current_user = Employee.query.filter_by(employeeID=current_user_id).first()
            
            if not current_user:
                return jsonify({'success': False, 'message': 'User not found'}), 404
            
            # Serve from cache if available (short TTL as data is not static)
            cache_key = f'programs:user:{current_user_id}'
            cached = redis_client.get(cache_key)
            if cached:
                try:
                    payload = json.loads(cached.decode())
                    return jsonify({'success': True, **payload}), 200
                except Exception:
                    pass

            # Determine user access level
            is_admin = current_user.isAdmin
            is_co_admin = current_user.isCoAdmin
            has_program_crud = current_user.crudProgramEnable
            
            # Admin: Return all programs
            # Co-Admin with crudProgramEnable: Return all programs
            # Regular user with crudProgramEnable: Return all programs
            # Co-Admin without crudProgramEnable: Return only assigned programs
            # Regular user without crudProgramEnable: Return only assigned programs
            
            if is_admin or has_program_crud:
                # Full access - return all programs
                programs = Program.query.all()
                access_level = 'full'
            else:
                # Limited access - return only assigned programs
                user_program_ids = [ep.programID for ep in current_user.employee_programs]
                if user_program_ids:
                    programs = Program.query.filter(Program.programID.in_(user_program_ids)).all()
                else:
                    programs = []  # No assigned programs
                access_level = 'assigned'
                    
            program_list = []
            for program in programs:
                dean = program.dean
                institute = program.institute
                program_data = {
                    'programID': program.programID,
                    'programDean': f"{dean.fName} {dean.lName} {dean.suffix or ''}" if dean else "N/A",
                    'programCode': program.programCode,
                    'programName': program.programName,
                    'programColor': program.programColor,
                    'employeeID': program.employeeID,
                    'instID': program.instID,
                    'instituteName': institute.instName if institute else "N/A",
                    'instituteCode': institute.instCode if institute else "N/A"
                }
                program_list.append(program_data)

            payload = {
                'programs': program_list,
                'accessLevel': access_level,
                'userPermissions': {
                    'isAdmin': is_admin,
                    'isCoAdmin': is_co_admin,
                    'crudProgramEnable': has_program_crud,
                    'assignedProgramCount': len(current_user.employee_programs)
                }
            }
            try:
                redis_client.setex(cache_key, 60, json.dumps(payload))
            except Exception:
                pass
            return jsonify({'success': True, **payload}), 200
            
        except Exception as e:
            current_app.logger.error(f"Get user program error: {e}")
            return jsonify({'success': False, 'message': 'Failed to fetch programs'}), 500


    # ============================================ Criteria And Area Route ============================================

    # Mark criteria as done or not done
    @app.route('/api/criteria/<int:criteriaID>/done', methods=["PUT"])
    def mark_criteria_done(criteriaID):
        data = request.get_json()
        is_done = data.get('isDone')
        
        criteria = Criteria.query.filter_by(criteriaID=criteriaID).first()

        if not criteria:
            return jsonify({'success': False, 'message': 'Criteria not found'}), 404
        
        criteria.isDone = is_done

        db.session.commit()

        return jsonify({'success': True, 'message': 'Criteria marked as done'}), 200

    @app.route('/api/area/progress', methods=["PUT"])
    def save_area_progress():
        data = request.get_json()
        areaID = data.get("areaID")
        progress = data.get("progress")
        updated_at = datetime.utcnow()
 
        if areaID is None or progress is None:
            return jsonify({'success': False, 'message': 'areaID and progress are required'}), 400
        
        area = Area.query.filter_by(areaID=areaID).first()

        area.progress = progress
        area.updated_at = updated_at


        db.session.commit()

        return jsonify({'success': True, 'message': 'Area progress saved!'}), 200

    @app.route('/api/area/option', methods=["GET"])
    def get_area_option():

        area_options = AreaReference.query.all()

        option_list = []

        for opt in area_options:
            area_data = {
                'areaName': opt.areaName,
                'areaNum': opt.areaNum,
                'title': f'{opt.areaName}: {opt.areaNum}'
            }

            option_list.append(area_data)
        return jsonify(option_list), 200


    # ============================================ Notifications ============================================
    @app.route('/api/notifications', methods=['GET', 'OPTIONS'])
    def notifications_options_handler():
        if request.method == 'OPTIONS':
            return ('', 204)
        return get_notifications()

    @jwt_required()
    def get_notifications():
        try:
            current_user_id = get_jwt_identity()
            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 20, type=int)

            # Cache only first page for 60s
            if page == 1:
                cache_key = f'notif_list:{current_user_id}:1'
                cached = redis_client.get(cache_key)
                if cached:
                    try:
                        data = json.loads(cached.decode())
                        return jsonify({'success': True, **data}), 200
                    except Exception:
                        pass

            notifications = (Notification.query
                              .filter_by(recipientID=current_user_id)
                              .order_by(Notification.createdAt.desc())
                              .paginate(page=page, per_page=per_page, error_out=False))

            notification_list = []
            for notif in notifications.items:
                sender_info = None
                if notif.senderID:
                    sender = Employee.query.get(notif.senderID)
                    if sender:
                        sender_info = {
                            'employeeID': sender.employeeID,
                            'name': f'{sender.fName} {sender.lName}',
                            'profilePic': sender.profilePic if sender.profilePic else None
                        }
                notification_list.append({
                    'notificationID': notif.notificationID,
                    'type': notif.type,
                    'title': notif.title,
                    'content': notif.content,
                    'createdAt': notif.createdAt.isoformat() if notif.createdAt else None,
                    'isRead': notif.isRead,
                    'link': notif.link,
                    'sender': sender_info
                })
            payload = {
                'notifications': notification_list,
                'total': notifications.total,
                'pages': notifications.pages,
                'current_page': page
            }

            if page == 1:
                try:
                    redis_client.setex(cache_key, 60, json.dumps(payload))
                except Exception:
                    pass

            return jsonify({'success': True, **payload}), 200
        except Exception as e:
            return jsonify({'success': False, 'message': f'Failed to fetch notifications: {e}'}), 500
    
    
    @app.route('/api/notifications/<int:notification_id>/read', methods=['PUT', 'OPTIONS'])
    def mark_notification_read_options(notification_id):
        if request.method == 'OPTIONS':
            return ('', 204)
        return mark_notification_read_impl(notification_id)

    @jwt_required()
    def mark_notification_read_impl(notification_id):
        try:
            current_user_id = get_jwt_identity()
            notification = Notification.query.filter_by(
                notificationID=notification_id,
                recipientID=current_user_id
            ).first()
            
            if not notification:
                return jsonify({'success': False, 'message': 'Notification not found'}), 404
            
            notification.isRead = True
            db.session.commit()
            # Invalidate caches
            try:
                redis_client.delete(f'notif_unread:{current_user_id}')
                redis_client.delete(f'notif_list:{current_user_id}:1')
            except Exception:
                pass
            
            return jsonify({'success': True, 'message': 'Notification marked as read'}), 200
            
        except Exception as e:
            current_app.logger.error(f"Mark notification read error: {e}")
            return jsonify({'success': False, 'message': 'Failed to update notification'}), 500

    @app.route('/api/notifications/<int:notification_id>', methods=['DELETE', 'OPTIONS'])
    def delete_notification_options(notification_id):
        if request.method == 'OPTIONS':
            return ('', 204)
        return delete_notification_impl(notification_id)

    @jwt_required()
    def delete_notification_impl(notification_id):
        try:
            current_user_id = get_jwt_identity()
            notification = Notification.query.filter_by(
                notificationID=notification_id,
                recipientID=current_user_id
            ).first()
            
            if not notification:
                return jsonify({'success': False, 'message': 'Notification not found'}), 404
            
            db.session.delete(notification)
            db.session.commit()
            try:
                redis_client.delete(f'notif_unread:{current_user_id}')
                redis_client.delete(f'notif_list:{current_user_id}:1')
            except Exception:
                pass
            
            return jsonify({'success': True, 'message': 'Notification deleted'}), 200
            
        except Exception as e:
            current_app.logger.error(f"Delete notification error: {e}")
            return jsonify({'success': False, 'message': 'Failed to delete notification'}), 500

    @app.route('/api/notifications', methods=['DELETE', 'OPTIONS'])
    def delete_all_notifications_options():
        if request.method == 'OPTIONS':
            return ('', 204)
        return delete_all_notifications_impl()

    @jwt_required()
    def delete_all_notifications_impl():
        try:
            current_user_id = get_jwt_identity()
            Notification.query.filter_by(recipientID=current_user_id).delete()
            db.session.commit()
            try:
                redis_client.delete(f'notif_unread:{current_user_id}')
                redis_client.delete(f'notif_list:{current_user_id}:1')
            except Exception:
                pass
            
            return jsonify({'success': True, 'message': 'All notifications deleted'}), 200
            
        except Exception as e:
            current_app.logger.error(f"Delete all notifications error: {e}")
            return jsonify({'success': False, 'message': 'Failed to delete notifications'}), 500

    @app.route('/api/notifications/mark-all-read', methods=['PUT', 'OPTIONS'])
    def mark_all_notifications_read_options():
        if request.method == 'OPTIONS':
            return ('', 204)
        return mark_all_notifications_read_impl()

    @jwt_required()
    def mark_all_notifications_read_impl():
        try:
            current_user_id = get_jwt_identity()
            Notification.query.filter_by(
                recipientID=current_user_id,
                isRead=False
            ).update({'isRead': True})
            db.session.commit()
            try:
                redis_client.delete(f'notif_unread:{current_user_id}')
                redis_client.delete(f'notif_list:{current_user_id}:1')
            except Exception:
                pass
            
            return jsonify({'success': True, 'message': 'All notifications marked as read'}), 200
            
        except Exception as e:
            current_app.logger.error(f"Mark all notifications read error: {e}")
            return jsonify({'success': False, 'message': 'Failed to mark notifications as read'}), 500

    @app.route('/api/notifications/unread-count', methods=['GET', 'OPTIONS'])
    def get_unread_count_options():
        if request.method == 'OPTIONS':
            return ('', 204)
        return get_unread_count_impl()

    @jwt_required()
    def get_unread_count_impl():
        try:
            current_user_id = get_jwt_identity()
            cache_key = f'notif_unread:{current_user_id}'
            cached = redis_client.get(cache_key)
            if cached:
                try:
                    return jsonify({'success': True, 'count': int(cached.decode())}), 200
                except Exception:
                    pass

            count = Notification.query.filter_by(
                recipientID=current_user_id,
                isRead=False
            ).count()
            try:
                redis_client.setex(cache_key, 60, str(count))
            except Exception:
                pass
            return jsonify({'success': True, 'count': count}), 200
            
        except Exception as e:
            current_app.logger.error(f"Get unread count error: {e}")
            return jsonify({'success': False, 'message': 'Failed to get unread count'}), 500

    # ============================================ Dashboard: Audit Logs & Pending Docs ============================================
    @app.route('/api/auditLogs', methods=['GET', 'OPTIONS'])
    @jwt_required()
    def get_audit_logs():
        if request.method == 'OPTIONS':
            return ('', 204)
        try:
            logs = (AuditLog.query.order_by(AuditLog.createdAt.desc()).limit(100).all())
            results = [{
                'logID': l.logID,
                'employeeID': l.employeeID,
                'action': l.action,
                'createdAt': l.createdAt.isoformat() if l.createdAt else None,
            } for l in logs]
            return jsonify({ 'success': True, 'data': { 'logs': results } }), 200
        except Exception as e:
            current_app.logger.error(f"Get audit logs error: {e}")
            return jsonify({ 'success': False, 'error': 'Failed to fetch logs' }), 500

    @app.route('/api/pendingDocs', methods=['GET', 'OPTIONS'])
    @jwt_required()
    def get_pending_docs():
        if request.method == 'OPTIONS':
            return ('', 204)
        try:
            # Consider pending as documents that are not approved yet (isApproved is NULL)
            pending = Document.query.filter((Document.isApproved.is_(None))).order_by(Document.docID.desc()).limit(100).all()
            def serialize_doc(d: Document):
                # best-effort fields to match frontend expectations
                name = getattr(d, 'docName', None) or getattr(d, 'fileName', None) or 'Document'
                return {
                    'pendingDocID': getattr(d, 'docID', None),
                    'pendingDocName': name,
                }
            return jsonify({ 'success': True, 'data': { 'pendingDocs': [serialize_doc(d) for d in pending] } }), 200
        except Exception as e:
            current_app.logger.error(f"Get pending docs error: {e}")
            return jsonify({ 'success': False, 'error': 'Failed to fetch pending documents' }), 500

    @app.route('/api/program/approve', methods=["PUT"])
    @jwt_required()
    def approve_document():
        data = request.get_json()
        docID = data.get("docID")

        document = Document.query.filter_by(docID=docID).first()

        document.isApproved = True
        document.approvedBy = get_jwt_identity()
        document.evaluate_at = datetime.utcnow()

        db.session.commit()

        return jsonify({'success': True, 'message': 'Document approved!'}), 200


    @app.route('/api/program/reject', methods=["PUT"])
    @jwt_required()
    def reject_document():
        data = request.get_json()
        docID = data.get("docID")

        document = Document.query.filter_by(docID=docID).first()

        document.isApproved = False
        document.approvedBy = get_jwt_identity()
        document.evaluate_at = datetime.utcnow()

        db.session.commit()

        return jsonify({'success': True, 'message': 'Document Rejected!'}), 200


    @app.route('/api/criteria', methods=["GET"])
    def get_criteria(): 

        criteria = Criteria.query.all()

        results = []

        for c in criteria:
            criteria_data ={
                'criteriaID': c.criteriaID,
                'criteriaContent': c.criteriaContent,
                'criteriaName': f"{c.criteriaID}. {c.criteriaContent}",
                'isDone': c.isDone
            }
            results.append(criteria_data)

        return jsonify(results)


    #Get the area for displaying in tasks
    @app.route('/api/area', methods=["GET", "OPTIONS"])
    def get_area():
        if request.method == 'OPTIONS':
            return ('', 204)
        areas = (Area.query
                 .join(Program, Area.programID == Program.programID)
                 .order_by(Area.areaID.asc())               
                 .filter(Area.archived == False)  
                 .outerjoin(Subarea, Area.areaID == Subarea.areaID)                                  
                 .add_columns(
                    Area.areaID,
                    Area.programID,
                    Area.subareaID,
                    Area.templateID,
                    Area.appliedTemplateID,
                    Area.areaBlueprintID,
                    Area.instID,
                    Program.programCode,
                    Program.programColor,
                    Area.areaName,
                    Area.areaNum,
                    Area.progress,
                    Area.rating,
                    Area.archived,
                    Subarea.subareaName,
                    Subarea.subareaID
                )
            ).all()

        area_list = []

        for area in areas:
            area_data = {
                'areaID' : area.areaID,
                'programID': area.programID,
                'subareaID': area.subareaID,    
                'templateID': area.templateID,
                'appliedTemplateID': area.appliedTemplateID,
                'areaBlueprintID': area.areaBlueprintID,
                'instID': area.instID,
                'programCode': area.programCode,
                'programColor': area.programColor,
                'areaTitle': area.areaName,
                'areaNum': area.areaNum,
                'areaName': f"{area.areaNum}: {area.areaName}",
                'progress': area.progress,
                'rating': area.rating,
                'subareaName': area.subareaName,  
                'archived': area.archived,
                'description': area.areaName
            }
            area_list.append(area_data)
        

        return jsonify({"area": area_list}), 200    


    #Create deadline
    @app.route('/api/deadline', methods=["POST"])
    @jwt_required()
    def create_deadline():
        # Support both application/json and form submissions.
        # Use silent=True so get_json() won't raise a 415 when Content-Type != application/json
        try:
            # Build a merged data source: prefer JSON payload when present, otherwise use form
            json_payload = request.get_json(silent=True) or {}
            form_payload = request.form.to_dict() if request.form else {}
            data = {**form_payload, **json_payload}

            # Extract and normalize fields
            def get_field(*names):
                for n in names:
                    if n in data and data[n] not in (None, ''):
                        return data[n]
                return None

            program_raw = get_field("program", "programID", "programId", "program_id")
            area_raw = get_field("area", "areaID", "areaId", "area_id")
            content = get_field("content", "deadlineContent", "description")
            due_date = get_field("due_date", "dueDate", "due")

            # Validate required fields
            if program_raw is None or area_raw is None or content is None or due_date is None:
                return jsonify({'success': False, 'message': 'program, area, content and due_date are required'}), 400

            try:
                programID = int(program_raw)
                areaID = int(area_raw)
            except (TypeError, ValueError):
                return jsonify({'success': False, 'message': 'program and area must be integer IDs'}), 400

            current_user_id = get_jwt_identity()
            admin_user = Employee.query.filter_by(employeeID=current_user_id).first()
            if not admin_user or not admin_user.isAdmin:
                return jsonify({'success': False, 'message': 'Admins only'}), 403

            # 1) Get all subareas under this area
            subareas = Subarea.query.filter_by(areaID=areaID, archived=False).all()
            if not subareas:
                return jsonify({'success': False, 'message': f'No subareas found for areaID={areaID}'}), 404

            # 2) Get all criteria under those subareas
            criteria_list = Criteria.query.filter(Criteria.subareaID.in_([s.subareaID for s in subareas])).all()
            if not criteria_list:
                return jsonify({'success': False, 'message': 'No criteria found for this area'}), 404

            # 3) Create a deadline
            new_deadline = Deadline(
                programID=programID,
                areaID=areaID,
                content=content,
                due_date=due_date
            )
            db.session.add(new_deadline)
            db.session.flush()

            # 4) Link criteria
            for c in criteria_list:
                link = DeadlineCriteria(deadlineID=new_deadline.deadlineID, criteriaID=c.criteriaID)
                db.session.add(link)

            new_log = AuditLog(
                employeeID=admin_user.employeeID,
                action=f"{admin_user.lName}, {admin_user.fName} {admin_user.suffix} created a deadline: {new_deadline.deadlineID}"
            )
            db.session.add(new_log)

            db.session.commit()
            return jsonify({'success': True, 'message': f'Deadline created successfully!'}), 200

        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Failed to create deadline: {str(e)}'}), 500


    # ============================================ Tasks Route ============================================
    
    
    @app.route('/api/deadlines', methods=["GET"])
    def get_deadline():
        deadlines = (Deadline.query
                    .join(Program, Deadline.programID == Program.programID)
                    .join(Area, Deadline.areaID == Area.areaID)
                    .add_columns(
                        Deadline.deadlineID,
                        Program.programName,
                        Program.programCode,
                        Program.programColor,
                        Area.areaName,
                        Area.areaNum,
                        Deadline.due_date,
                        Deadline.content
                    )).all()

        deadline_list = []

        for dl in deadlines:

            # Fetch criteria for this deadline
            criteria_list = []
            criteria_records = (DeadlineCriteria.query
                                .join(Criteria, DeadlineCriteria.criteriaID == Criteria.criteriaID)
                                .filter(DeadlineCriteria.deadlineID == dl.deadlineID)
                                .all())

            for crit in criteria_records:
                criteria_list.append({
                    "criteriaID": crit.criteria.criteriaID                    
                })

            deadline_data = {
                'deadlineID': dl.deadlineID,
                'programName': dl.programName,
                'programColor': dl.programColor,
                'programCode': dl.programCode,
                'areaName': f"{dl.areaNum}: {dl.areaName}",
                'due_date': dl.due_date.strftime('%m-%d-%Y'),
                'content': dl.content,
                'criteria': criteria_list     
            }

            deadline_list.append(deadline_data)

        return jsonify({'deadline': deadline_list})

    
    #get the events for the calendar
    @app.route('/api/events', methods=["GET"])
    def get_events():
    
        events = (Deadline.query
                     .join(Program, Deadline.programID == Program.programID)
                     .join(Area, Deadline.areaID == Area.areaID)
                     .add_columns(
                         Deadline.deadlineID,
                         Program.programName,
                         Program.programColor,
                         Area.areaName,
                         Area.areaNum,
                         Deadline.due_date,
                         Deadline.content
                     )).all()
        
        event_list = []

        for e in events:
            event = {
                'id': e.deadlineID,
                'title': f"{e.areaNum}: {e.areaName}",
                'start': e.due_date.strftime('%Y-%m-%d'),
                'content': e.content,
                'color': e.programColor
            }
     
            event_list.append(event)
        
        return jsonify(event_list)
        


    # ============================================ Accreditation Routes ============================================

    @app.route('/api/accreditation', methods=["GET"])
    def get_areas():
        program_code = request.args.get('programCode')

        # Try Redis cache first for the heavy structure
        try:
            if program_code:
                cache_key = f"accr:program:{program_code}"
                cached = redis_client.get(cache_key)
                if cached:
                    return jsonify(json.loads(cached.decode()))
        except Exception:
            pass

        data = (
            db.session.query(
                Area.areaID,
                Program.programCode,
                Area.areaName,
                Area.areaNum,
                Area.progress,
                Subarea.subareaID,
                Subarea.subareaName,
                Criteria.criteriaID,
                Criteria.criteriaContent,
                Criteria.criteriaType,
                Criteria.rating,
                Document.docID,
                Document.docName,
                Document.docType,
                Document.docPath,
                Document.isApproved,
                Document.predicted_rating,
                Document.predicted_probability,
                Document.similar_docs
            )
            .outerjoin(Program, Area.programID == Program.programID)
            .outerjoin(Subarea, (Area.areaID == Subarea.areaID) & (Subarea.archived == False))
            .outerjoin(Criteria, (Subarea.subareaID == Criteria.subareaID) & (Criteria.archived == False))
            .outerjoin(Document, Criteria.docID == Document.docID)
            .filter(Program.programCode == program_code, Area.archived == False)
            .order_by(Area.areaID.asc(), Subarea.subareaID.asc(), Criteria.criteriaID.asc())
            .all() 
        )


        result = {}
        for row in data:
            area_id = row.areaID
            subarea_id = row.subareaID

            if area_id not in result:
                result[area_id] = {                    
                'areaID': row.areaID,
                'programCode': row.programCode,
                'areaNum': row.areaNum,
                'areaName': row.areaNum + ": " + row.areaName, 
                'subareas': {}                  
            }
                

            if subarea_id and subarea_id not in result[area_id]['subareas']:
                result[area_id]["subareas"][subarea_id] = {
                    'subareaID': subarea_id,
                    'subareaName': row.subareaName,
                    'criteria': {
                        'inputs': [],
                        'processes': [],
                        'outcomes': [],
                },  
                    
            }
            
            if row.criteriaContent:
                criteria_data = {
                    'criteriaID': row.criteriaID ,
                    'content': row.criteriaContent,
                    'docID': row.docID,
                    'docName': row.docName,
                    'docPath': row.docPath,
                    'predicted_rating': row.predicted_rating,
                    'predicted_probability': row.predicted_probability,
                    "similar_docs": row.similar_docs,
                    'isApproved': row.isApproved,
                    'rating': row.rating
                }

            match row.criteriaType:
                case "Inputs":
                    result[area_id]['subareas'][subarea_id]['criteria']['inputs'].append(criteria_data)
                case "Processes":
                    result[area_id]['subareas'][subarea_id]['criteria']['processes'].append(criteria_data)
                case "Outcomes":
                    result[area_id]['subareas'][subarea_id]['criteria']['outcomes'].append(criteria_data)

        for area in result.values():
            area['subareas'] = list(area['subareas'].values())


        payload = list(result.values())
        # Cache for 5 minutes to speed up UI loads
        try:
            if program_code:
                cache_key = f"accr:program:{program_code}"
                redis_client.setex(cache_key, 300, json.dumps(payload))
        except Exception:
            pass
        return jsonify(payload) 
    
    
    
    # ===== Load Models for Document Processing =====

    # Model for genarating embeddings
    embedding_model = SentenceTransformer("all-MiniLM-L6-v2") 
    # Model for predicting document rating
    model_path = os.path.join(os.path.dirname(__file__), "machine_learning", "xgb_best_model.pkl")
    xgb_model = joblib.load(model_path)


    @app.route('/api/accreditation/upload', methods=["POST"])
    @jwt_required()        
    def upload_file():        

       # ==== Get and Validate Form Data ====
        # Get form data
        data = request.form
        file = request.files.get("uploadedFile")
        file_type = request.form.get("fileType")
        file_name = request.form.get("fileName")
        criteria_id = request.form.get("criteriaID")
               
        program_code = data.get("programCode")
        area_name = data.get("areaName")
        subarea_name = data.get("subareaName")
        criteria_type = data.get("criteriaType")
        
        # === Validate the File ===
        if not file:
            return jsonify({'success': False, 'message': 'No file provided'}), 400

        # Make sure filename exists
        if not getattr(file, "filename", None):
            return jsonify({'success': False, 'message': 'Invalid file: no filename detected'}), 400

        # Ensure filename has an extension
        if '.' not in file.filename:
            return jsonify({'success': False, 'message': 'Invalid file name (missing extension)'}), 400

        # Extract extension safely
        file_extension = file.filename.rsplit('.', 1)[-1].lower()
        allowed_extensions = {'pdf'}

        if file_extension not in allowed_extensions:
            return jsonify({'success': False, 'message': 'Invalid file format. Only PDF files are allowed.'}), 400

        # Generate a secure filename
        filename = secure_filename(file.filename)
        if not filename:
            return jsonify({'success': False, 'message': 'Invalid filename'}), 400
        
        # Get uploader info
        try:
            uploader = Employee.query.filter_by(employeeID=get_jwt_identity()).first()
        
            if not uploader:
                return jsonify({'success': False, 'message': 'User not found'}), 400
            
        except Exception as e:
            return jsonify({'success': False, 'message': 'Authentication error'}), 400
        
        # ==== Save File ====

        # Gets the file url
        path = f"UDMS_Repository/Accreditation/Programs/{program_code}/{area_name}/{subarea_name}/{criteria_type}/{criteria_id}"
        normalized_path = normalize_path(path)    

        # Generates a secure filename
        filename = secure_filename(file.filename)

        if not filename:
            return jsonify({'success': False, 'message': 'Invalid filename'}), 400
                       
        try:
            # === Ensures that the directory exists in Nextcloud ===
            print(f"[upload_file] ensure_directories for path: {path}")
            if not ensure_directories(path):
                print("[upload_file] ensure_directories returned False")
                return jsonify({
                    'success': False,
                    'message': 'Failed to create directory structure in Nextcloud'
                }), 400

            # === Save file to Nextcloud ===
            print(f"[upload_file] calling upload_to_nextcloud for: {filename} -> {path}")
            response = upload_to_nextcloud(file, path)
            print(f"[upload_file] upload_to_nextcloud response: {getattr(response, 'status_code', None)}")
            if hasattr(response, 'text'):
                print(f"[upload_file] upload response text: {response.text}")

            if response.status_code not in (200, 201, 204):
                print(f"[upload_file] Nextcloud responded with non-success: {response.status_code}")
                return jsonify({
                    'success': False,
                    'message': 'Nextcloud upload failed.',
                    'status': response.status_code,
                    'details': getattr(response, 'text', '')
                }), 400

            # === Extract the text from file ===
            temp_path = f"/tmp/{filename}"
            print(f"[upload_file] saving temp file -> {temp_path}")
            file.save(temp_path)
            try:
                extracted_text = extract_pdf(temp_path)
                file_size = os.path.getsize(temp_path)
                print(f"[upload_file] extracted_text length: {len(extracted_text)} file_size: {file_size}")
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

            # === Generate Tags ===
            print("[upload_file] generating rule-based tags")
            tags = set(rule_based_tag(extracted_text))

            # Fetch all documents in the DB
            all_docs = [d.content for d in Document.query.with_entities(Document.content).all()]
            all_docs.append(extracted_text)

            tfidf_tags = extract_global_tfid_tags(all_docs, len(all_docs) - 1)
            if tfidf_tags:
                from itertools import chain
                if any(isinstance(tag, list) for tag in tfidf_tags):
                    flat_tags = list(chain.from_iterable(tfidf_tags))
                    tags.update(flat_tags)
                else:
                    tags.update(tfidf_tags)
            print(f"[upload_file] total tags: {len(tags)}")

            # === Generate Embedding ===
            print("[upload_file] generating embedding")
            embedding = embedding_model.encode(extracted_text, normalize_embeddings=True)
            embedding = np.array(embedding, dtype=np.float32).tolist()
            print(f"[upload_file] embedding length: {len(embedding)}")

            # ==== Create or update document record ====
            print(f"[upload_file] looking for existing Document with docName={file_name}")
            doc = Document.query.filter_by(docName=file_name).first()

            if doc:
                print(f"[upload_file] updating existing Document id={doc.docID}")
                doc.docPath = f"{normalized_path}/{filename}"
                doc.docName = file_name
                doc.content = extracted_text
                doc.tags = list(tags)
                doc.embedding = embedding

                new_log = AuditLog(
                    employeeID = uploader.employeeID,
                    action = f"{uploader.lName}, {uploader.fName} {uploader.suffix} Updated a document: {filename}"
                )
                db.session.add(new_log)
            else:
                print("[upload_file] creating new Document record")
                doc = Document(
                    docName=file_name,
                    docType=file_type,
                    docPath=f"{path}/{filename}",
                    content=extracted_text,
                    employeeID=uploader.employeeID,
                    tags=list(tags),
                    embedding=embedding
                )
                db.session.add(doc)
                db.session.flush()  # Assign docID before linking

                new_log = AuditLog(
                    employeeID = uploader.employeeID,
                    action = f"{uploader.lName}, {uploader.fName} {uploader.suffix} Uploaded a new document: {filename}"
                )
                db.session.add(new_log)

            # ==== Link document to criteria ====
            print(f"[upload_file] linking document to criteria id={criteria_id}")
            criteria = Criteria.query.get(criteria_id)
            if not criteria:
                db.session.rollback()
                print(f"[upload_file] criteria not found for id={criteria_id}")
                return jsonify({'success': False, 'message': 'Criteria not found'}), 404

            criteria.docID = doc.docID

            # ==== Update search vector ====
            print(f"[upload_file] updating search vector for docID={doc.docID}")
            db.session.execute(
                text("""
                    UPDATE document
                    SET search_vector = to_tsvector('english', "docName" || ' ' || content)
                    WHERE "docID" = :doc_id
                """),
                {"doc_id": doc.docID}
            )

            # compute features and predict
            print("[upload_file] computing features for rating prediction")
            if not hasattr(criteria, "deadlines") or not criteria.deadlines:
                days_until_deadline = 0
            else:
                nearest_deadline = min(dl.due_date for dl in criteria.deadlines)
                days_until_deadline = (nearest_deadline - datetime.utcnow().date()).days

            criteria_list = Criteria.query.filter_by(subareaID=criteria.subareaID).count()
            completed_criteria = Criteria.query.filter_by(subareaID=criteria.subareaID, isDone=True).count()
            criteria_completion_score = (completed_criteria / criteria_list) * 100 if criteria_list > 0 else 0

            program = Program.query.filter_by(programCode=program_code).first()
            programID = program.programID if program else None

            df_input = pd.DataFrame([{
                "file_size": file_size,
                "Criteria_Completion_Score": criteria_completion_score,
                "Days_Until_Deadline": days_until_deadline,
                "isApproved": False,
                "docType": "application/pdf",
                "programID": programID
            }])

            emb = pd.DataFrame([embedding])
            emb.columns = [f"emb_{i}" for i in range(len(emb.columns))]
            X_new = pd.concat([df_input, emb], axis=1)

            print(f"[upload_file] running model.predict with X_new shape: {X_new.shape}")
            # Diagnostic logs: inspect the model object and its predict attribute
            try:
                print(f"[upload_file] xgb_model type: {type(xgb_model)}")
                print(f"[upload_file] xgb_model has attribute 'predict'? {hasattr(xgb_model, 'predict')}")
                if hasattr(xgb_model, 'predict'):
                    print(f"[upload_file] xgb_model.predict type: {type(xgb_model.predict)}, callable: {callable(xgb_model.predict)}")
                else:
                    print("[upload_file] xgb_model.predict not found")
            except Exception as _log_e:
                print(f"[upload_file] Error inspecting xgb_model: {_log_e}")

            try:
                predicted_rating = float(xgb_model.predict(X_new)[0])
                doc.predicted_rating = predicted_rating
            except Exception as pred_e:
                # Log detailed info about the predict attribute to help debug 'bool' object is not callable
                try:
                    pred_attr = getattr(xgb_model, 'predict', None)
                    print(f"[upload_file] Exception during model.predict: {pred_e}")
                    print(f"[upload_file] type(pred_attr): {type(pred_attr)}")
                    print(f"[upload_file] repr(pred_attr): {repr(pred_attr)}")
                    print(f"[upload_file] callable(pred_attr): {callable(pred_attr)}")
                except Exception as _inner:
                    print(f"[upload_file] Error while logging predict attr: {_inner}")
                # Print full traceback here to capture where the error occurred, then re-raise
                try:
                    import traceback as _tb
                    _tb.print_exc()
                except Exception:
                    pass
                # Re-raise to be handled by outer exception handler (so we still rollback and return 500)
                raise

            # ==== Compare past documents and Predict Probability ====
            past_docs_query = Document.query.with_entities(
                Document.docName, Document.embedding, Document.isApproved
            ).filter(Document.embedding.isnot(None)).all()

            past_docs = pd.DataFrame([
                {"docName": d.docName, "embedding": d.embedding, "isApproved": d.isApproved}
                for d in past_docs_query
            ])

            new_doc_data = {
                "file_size": file_size,
                "Criteria_Completion_Score": criteria_completion_score,
                "Days_Until_Deadline": days_until_deadline,
                "docType": "application/pdf",
                "programID": programID,
                "embedding": embedding
            }

            print(f"[upload_file] past_docs count: {len(past_docs) if hasattr(past_docs, '__len__') else 'unknown'}")
            prob_approval, top_similar_docs = compare_documents(new_doc_data, past_docs, xgb_model)
            
            if prob_approval is None:
                # Fallback: if compare_documents couldn't compute probability (no past docs
                # or model predict failed), derive probability from the model-predicted rating
                try:
                    pr = getattr(doc, 'predicted_rating', None)
                    if pr is None and 'predicted_rating' in locals():
                        pr = predicted_rating
                    if pr is not None:
                        prob_approval = float(1 / (1 + np.exp(-2.0 * (pr - 3))))
                        print(f"[upload_file] Fallback probability from predicted_rating={pr}: {prob_approval}")
                    else:
                        prob_approval = 0.0
                        print("[upload_file] No predicted_rating available; falling back to 0.0")
                except Exception as _pf:
                    print(f"[upload_file] Error computing fallback probability: {_pf}")
                    prob_approval = 0.0

            doc.predicted_probability = float(prob_approval)
            doc.similar_docs = (
                top_similar_docs.to_dict(orient='records')
                if hasattr(top_similar_docs, "to_dict")
                else []
            )

            print(f"[DEBUG] Probability: {doc.predicted_probability}")
            print(f"[DEBUG] Similar Docs count: {len(doc.similar_docs)}")

            # Final commit
            db.session.commit()
            print(f"[upload_file] commit successful for docID={doc.docID}")

            return jsonify({
                'success': True,
                'message': 'File uploaded successfully!',
                'filePath': f"{normalized_path}/{filename}",
                'predict_rating': round(predicted_rating, 2),
                'probability_of_approval': round(prob_approval, 4) if prob_approval is not None else None,
                'status': response.status_code
            }), 200

        except Exception as e:
            import traceback
            traceback.print_exc()
            db.session.rollback()  # Rollback on error
            print(f"[upload_file] Exception: {str(e)}")
            return jsonify({'success': False, 'message': f'Failed to upload file: {str(e)}'}), 500
        

    # Preview file
    @app.route('/api/accreditation/preview/<filename>', methods=["GET"])   
    @jwt_required()   
    def preview_file(filename):                       
        doc = Document.query.filter_by(docName=filename).first()
        if not doc:
            return jsonify({'success': False, 'message': 'File not found.'}), 404    

        # Small-object cache in Redis (<=5MB)
        cache_key = f"preview_cache:{doc.docPath}"
        try:
            cached = redis_client.get(cache_key)
            if cached:
                return Response(cached, content_type="application/pdf", headers={
                    "Content-Disposition": f'inline; filename="{filename}"',
                    "Cache-Control": "public, max-age=300"
                })
        except Exception:
            pass

        # Fetch from Nextcloud using the full docPath
        print(f"[preview_file] Fetching from Nextcloud: {doc.docPath}")
        response = preview_from_nextcloud(doc.docPath)
        
        if response.status_code == 200:
            # Try to cache small files
            try:
                length = response.headers.get("Content-Length")
                content_bytes = response.content if response.content else None
                if content_bytes is not None:
                    if not length:
                        length = len(content_bytes)
                    if int(length) <= 5_000_000:  # 5 MB
                        redis_client.setex(cache_key, 300, content_bytes)
                        return Response(content_bytes, content_type=response.headers.get("Content-Type", "application/pdf"), headers={
                            "Content-Disposition": f'inline; filename="{filename}"',
                            "Cache-Control": "public, max-age=300"
                        })
            except Exception as cache_err:
                print(f"[preview_file] Cache error: {cache_err}")

            # Fallback: stream without caching
            return Response(
                response.iter_content(chunk_size=8192),
                content_type = response.headers.get("Content-Type", "application/octet-stream"),
                headers={
                    "Content-Disposition": f'inline; filename="{filename}"',
                    "Cache-Control": "public, max-age=120"
                }
            ) 
        else:
            print(f"[preview_file] Nextcloud error: {response.status_code} - {getattr(response, 'text', 'No text')}")
            return jsonify({
                'success': False,
                'status': response.status_code,
                'detail': getattr(response, 'text', 'Unknown error')
            }), response.status_code 



       
    # ============================================ Documents Routes ============================================
    
    def filter_folders_by_access(tree, allowed_programs):
        """
        Filter the folder tree to show all Accreditation contents,
        but only Programs that the user has access to.
        """
        import copy
        
        # Navigate to Accreditation if it exists
        if 'folders' in tree and 'Accreditation' in tree['folders']:
            accreditation = copy.deepcopy(tree['folders']['Accreditation'])
            
            # Filter Program folders based on allowed_programs
            if 'folders' in accreditation and 'Programs' in accreditation['folders']:
                programs_folder = accreditation['folders']['Programs']
                if 'folders' in programs_folder:
                    filtered_programs = {
                        program_code: program_data
                        for program_code, program_data in programs_folder['folders'].items()
                        if program_code in allowed_programs
                    }
                    programs_folder['folders'] = filtered_programs
            
            # Return the entire Accreditation folder (includes Programs + other files/folders)
            return accreditation
        
        # If Accreditation folder not found, return empty structure
        return {"files": [], "folders": {}}

    # display all the documents inside nextcloud repo
    @app.route('/api/documents', methods=["GET"])
    @jwt_required()
    def list_files():
        try:
            current_user_id = get_jwt_identity()
            user = Employee.query.filter_by(employeeID=current_user_id).first()
            
            if not user:
                return jsonify({"error": "User not found"}), 404
            
            # Get full folder tree from Nextcloud
            tree = list_files_from_nextcloud()
            
            # If admin, return everything starting from Programs folder
            if user.isAdmin:
                if 'folders' in tree and 'Accreditation' in tree['folders']:
                    return jsonify(tree['folders']['Accreditation'])
                return jsonify(tree)
            
            # Get user's program codes (not names - folder names match program codes like BSIT, BSED)
            user_program_ids = [ep.programID for ep in user.employee_programs]
            user_programs = Program.query.filter(Program.programID.in_(user_program_ids)).all()
            user_program_codes = [p.programCode for p in user_programs]
            
            # Get user's optional folder access
            optional_folder_paths = [ef.folderPath for ef in user.employee_folders]
            
            # Extract program codes from optional folder paths
            # Support both formats: 
            # - UDMS_Repository/Accreditation/Programs/{ProgramCode}
            # - UDMS_Repository/Programs/{ProgramCode}
            optional_program_codes = []
            for path in optional_folder_paths:
                parts = path.split('/')
                if len(parts) >= 3 and parts[0] == 'UDMS_Repository':
                    if len(parts) >= 4 and parts[1] == 'Accreditation' and parts[2] == 'Programs':
                        # Format: UDMS_Repository/Accreditation/Programs/{ProgramCode}
                        optional_program_codes.append(parts[3])
                    elif len(parts) >= 3 and parts[1] == 'Programs':
                        # Format: UDMS_Repository/Programs/{ProgramCode}
                        optional_program_codes.append(parts[2])
            
            # Combine all allowed program codes
            allowed_programs = set(user_program_codes + optional_program_codes)
            
            # Debug logging
            print(f"User {user.employeeID} - Program codes: {user_program_codes}")
            print(f"User {user.employeeID} - Optional folder paths: {optional_folder_paths}")
            print(f"User {user.employeeID} - Optional program codes: {optional_program_codes}")
            print(f"User {user.employeeID} - Allowed programs: {allowed_programs}")
            
            # Filter the folder tree
            filtered_tree = filter_folders_by_access(tree, allowed_programs)
            
            return jsonify(filtered_tree)
            
        except Exception as e:
            return jsonify({"Error": str(e)}), 500

    @app.route('/api/documents/preview/', defaults={'file_path': None}, methods=["GET"])
    @app.route('/api/documents/preview/<path:file_path>', methods=["GET"])
    def preview_file_documents(file_path):
        if not file_path:
            return {"error": "File path required"}, 400
        return preview_file_nextcloud(file_path)

    
    @app.route('/api/documents/download/<path:file_path>', methods=["GET"])
    @jwt_required()
    def download_file_documents(file_path):
        # Audit downloaded file
        user = Employee.query.filter_by(employeeID=get_jwt_identity()).first()
        file_name = file_path.split("/")[-1]
        new_log = AuditLog(
            employeeID = user.employeeID,
            action = f"{user.lName}, {user.fName} {user.suffix} Downloaded {file_name}"
        )
        db.session.add(new_log)
        db.session.commit()

        return download_file_nextcloud(file_path)
    
    
    @app.route('/api/documents/delete_file/<int:docID>', methods=["DELETE"])
    @jwt_required()
    def delete_file(docID):
        current_user_id = get_jwt_identity()
        admin_user = Employee.query.filter_by(employeeID=current_user_id).first()
        if not admin_user or not admin_user.isAdmin:
            return jsonify({'success': False, 'message': 'Admins only'}), 403
        try:
            # Check if metadata exists first
            doc = Document.query.get(docID)
            if not doc:
                return jsonify({
                    'success': False,
                    'message': 'Document not found.'
                }), 404

            file_path = doc.docPath
            print(f"Deleting docID = {docID}, path = {file_path}")
            if file_path.startswith('UDMS_Repository'):
                file_path = file_path.replace("UDMS_Repository", "", 1)

            # Delete from Nextcloud
            response = delete_from_nextcloud(file_path)

            if response.status_code not in (200, 204):
                return jsonify({
                    'success': False,
                    'message': 'Nextcloud deletion failed.',
                    'status': response.status_code,
                    'details': response.text
                }), 400

            # Delete metadata from DB only if Nextcloud deletion succeeded
            db.session.delete(doc)

            # Audit deleted doc
            new_log = AuditLog(
                employeeID = admin_user.employeeID,
                action = f"{admin_user.lName}, {admin_user.fName} {admin_user.suffix} Deleted a file: {doc.docName}"
            )
            db.session.add(new_log)
            db.session.commit()

            return jsonify({
                'success': True,
                'message': 'File deleted successfully.'
            }), 200

        except Exception as e:
            db.session.rollback()
            return jsonify({
                'success': False,
                'message': f'Failed to delete document: {str(e)}'
            }), 500



    @app.route('/api/documents/rename', methods=["PUT"])
    @jwt_required()
    def rename_file():
        data = request.get_json()
        old_path = data.get("oldPath")
        new_path = data.get("newPath")

        try:
            response = rename_file_nextcloud(old_path, new_path)

            if response.status_code in (200, 201, 204, 207):
                # Skip folders                
                if os.path.splitext(new_path)[1] == "":
                    return jsonify({
                        'success': True,
                        'message': 'Folder renamed in Nextcloud but not tracked in DB.'
                    }), 200
                
                display_name = unquote(new_path)
                # Update DB only if it's a file
                doc = Document.query.filter_by(docPath=old_path).first()
                if doc:
                    doc.docPath = display_name
                    user = Employee.query.filter_by(employeeID=get_jwt_identity()).first()
                    # Audit rename path
                    new_log = AuditLog(
                        employeeID = user.employeeID,
                        action = f"{user.lName}, {user.fName} {user.suffix} Renamed a file {doc.docName}"
                    )
                    db.session.add(new_log)
                    db.session.commit()
                else:                 
                    return jsonify({'success': True, 'message': 'File renamed successfully.'}), 200
                
            else:
                return jsonify({
                    'success': False,
                    'message': 'Nextcloud rename failed. Please try again.',
                    'status': response.status_code,
                    'details': response.text
                }), 400
        except Exception as e:
            return jsonify({'success': False, 'message': f'Failed to rename document {str(e)}'}), 500

    @app.route('/api/documents/upload', methods=["POST"])
    @jwt_required()
    def upload_documents():
        file = request.files.get('uploadedFile')
        data = request.form
        file_type = data.get("fileType")
        file_name = data.get("fileName")
        directory = data.get("directory", "").strip('/')

        base_path = "UDMS_Repository/Accreditation"

        if not directory:
            directory = base_path
        else:
            directory = f"{base_path}/{directory}"

        if not file:
            return jsonify({'success': False, 'message': 'No file provided'}), 400        

        if not file.filename or '.' not in file.filename:
            return jsonify({'success': False, 'message': 'Invalid file name'}), 400

        # Get uploader info
        uploader = Employee.query.filter_by(employeeID=get_jwt_identity()).first()
        if not uploader:
            return jsonify({'success': False, 'message': 'User not found'}), 400
        
        filename = secure_filename(file.filename)

        try:
            print(f"Ensuring directory exists: {directory}")
            # Make sure the directory exists before uploading
            ensure_result = ensure_directories(directory)
            if not ensure_result:
                return jsonify({
                    "success": False,
                    "message": "Failed to create directory structure in Nextcloud"
                }), 500
                
            print(f"Starting Nextcloud upload for file: {filename}")
            print(f"Directory path: {directory}")
            
            # Upload to Nextcloud
            response = upload_to_nextcloud(file, directory)
            print(f"Nextcloud upload response: {response.status_code}")
            print(f"Nextcloud response text: {response.text}")

            # Only create audit log if upload was successful
            if response.status_code in (200, 201, 204):
                new_log = AuditLog(
                    employeeID = uploader.employeeID,
                    action = f"{uploader.lName}, {uploader.fName} {uploader.suffix} Uploaded a file: {filename}"
                )
                db.session.add(new_log)
                db.session.commit()
                print("Audit log created successfully")
            else:
                print(f"Nextcloud upload failed with status code: {response.status_code}")
                print(f"Response text: {response.text}")
                return jsonify({
                    "success": False,
                    "message": f"Upload failed: {response.status_code} - {response.text}"
                }), 500
        except Exception as e:
            print(f"Error in upload/audit process: {str(e)}")
            return jsonify({
                "success": False,
                "message": f"Upload process failed: {str(e)}"
            }), 500

        # === Extract text ===
        extracted_text = ""
        file_size = 0
        temp_path = f"/tmp/{filename}"
        try:
            file.save(temp_path) 
            file_size = os.path.getsize(temp_path)

            file_extension = filename.rsplit('.', 1)[-1].lower()
            if file_extension == 'pdf':
                extracted_text = extract_pdf(temp_path)
            elif file_extension in ('docx', 'doc'):
                extracted_text = extract_docs(temp_path)
            elif file_extension in ('xls', 'xlsx'):
                extracted_text = extract_excel(temp_path)
            elif file_extension in ('jpg', 'png', 'jpeg'):
                extracted_text = extract_image(temp_path) 
            else:
                extracted_text = ""
            
            print(f"[upload_documents] Extracted text length: {len(extracted_text)}, file_size: {file_size}")

        except Exception as e:
            print(f"[upload_documents] Text extraction failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return jsonify({'success': False, 'message': f'Text extraction failed: {str(e)}'}), 500
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        
        # === Generate Tags === 
        print("[upload_documents] Generating rule-based tags")
        tags = set(rule_based_tag(extracted_text))
        
        # Fetch all documents in the DB
        all_docs = [d.content for d in Document.query.with_entities(Document.content).all()]
        all_docs.append(extracted_text)

        tfidf_tags = extract_global_tfid_tags(all_docs, len(all_docs) - 1)
        if tfidf_tags:
            from itertools import chain
            if any(isinstance(tag, list) for tag in tfidf_tags):
                flat_tags = list(chain.from_iterable(tfidf_tags))
                tags.update(flat_tags)
            else:
                tags.update(tfidf_tags)
        print(f"[upload_documents] Total tags: {len(tags)}")

        # === Generate Embedding ===
        print("[upload_documents] Generating embedding")
        embedding = embedding_model.encode(extracted_text, normalize_embeddings=True)
        embedding = np.array(embedding, dtype=np.float32).tolist()
        print(f"[upload_documents] Embedding length: {len(embedding)}")
        
        # === Save record to DB ===
        try:
            print(f"[upload_documents] Creating document record: name={file_name}, type={file_type}, path={directory}/{filename}")
            
            doc = Document(
                docName=file_name,
                docType=file_type,
                docPath=f"{directory}/{filename}",
                content=extracted_text,
                employeeID=uploader.employeeID,
                tags=list(tags),
                embedding=embedding
            )
            
            db.session.add(doc)
            db.session.flush()  # Assign docID
            print(f"[upload_documents] Got docID: {doc.docID}")

            # ==== Update search vector ====
            print("[upload_documents] Updating search vector")
            db.session.execute(
                text("""
                    UPDATE document
                    SET search_vector = to_tsvector('english', "docName" || ' ' || content)
                    WHERE "docID" = :doc_id
                """), 
                {"doc_id": doc.docID}
            )

            # ==== Compute predicted rating and probability ====
            print("[upload_documents] Computing model predictions")
            
            # Build feature dataframe for rating prediction
            df_input = pd.DataFrame([{
                "file_size": file_size,
                "Criteria_Completion_Score": 0,  # Not available in documents endpoint
                "Days_Until_Deadline": 0,
                "isApproved": False,
                "docType": file_type,
                "programID": None
            }])

            emb = pd.DataFrame([embedding])
            emb.columns = [f"emb_{i}" for i in range(len(emb.columns))]
            X_new = pd.concat([df_input, emb], axis=1)

            predicted_rating = None
            try:
                predicted_rating = float(xgb_model.predict(X_new)[0])
                doc.predicted_rating = predicted_rating
                print(f"[upload_documents] Predicted rating: {predicted_rating}")
            except Exception as pred_e:
                print(f"[upload_documents] Warning: model prediction failed: {pred_e}")
                predicted_rating = None

            # ==== Compare past documents and compute probability ====
            past_docs_query = Document.query.with_entities(
                Document.docName, Document.embedding, Document.isApproved
            ).filter(Document.embedding.isnot(None)).all()

            past_docs = pd.DataFrame([
                {"docName": d.docName, "embedding": d.embedding, "isApproved": d.isApproved}
                for d in past_docs_query
            ])

            new_doc_data = {
                "file_size": file_size,
                "Criteria_Completion_Score": 0,
                "Days_Until_Deadline": 0,
                "docType": file_type,
                "programID": None,
                "embedding": embedding
            }

            print(f"[upload_documents] past_docs count: {len(past_docs) if hasattr(past_docs, '__len__') else 'unknown'}")
            prob_approval, top_similar_docs = compare_documents(new_doc_data, past_docs, xgb_model)
            
            if prob_approval is None:
                # Fallback: derive probability from predicted rating if available
                try:
                    pr = predicted_rating
                    if pr is not None:
                        prob_approval = float(1 / (1 + np.exp(-2.0 * (pr - 3))))
                        print(f"[upload_documents] Fallback probability from predicted_rating={pr}: {prob_approval}")
                    else:
                        prob_approval = 0.0
                        print("[upload_documents] No predicted_rating available; falling back to 0.0")
                except Exception as _pf:
                    print(f"[upload_documents] Error computing fallback probability: {_pf}")
                    prob_approval = 0.0

            doc.predicted_probability = float(prob_approval)
            doc.similar_docs = (
                top_similar_docs.to_dict(orient='records')
                if hasattr(top_similar_docs, "to_dict")
                else []
            )

            print(f"[upload_documents] Probability: {doc.predicted_probability}")
            print(f"[upload_documents] Similar Docs count: {len(doc.similar_docs)}")

            # Create audit log for successful upload
            new_log = AuditLog(
                employeeID=uploader.employeeID,
                action=f"{uploader.lName}, {uploader.fName} {uploader.suffix} Uploaded a file: {filename}"
            )
            db.session.add(new_log)
            
            # Commit all changes
            db.session.commit()
            print("[upload_documents] Database transaction committed successfully")

            return jsonify({
                'success': True,
                'message': 'File uploaded successfully!',
                'docPath': f"{directory}/{filename}",
                'predicted_rating': round(predicted_rating, 2) if predicted_rating else None,
                'probability_of_approval': round(prob_approval, 4) if prob_approval else None
            }), 200

        except Exception as e:
            print(f"[upload_documents] Database error: {str(e)}")
            import traceback
            traceback.print_exc()
            db.session.rollback()
            return jsonify({
                'success': False, 
                'message': f'Database save failed: {str(e)}'
            }), 500

    @app.route('/api/documents/tags', methods=["GET"])
    def get_tags():

        tags = Document.query.with_entities(Document.tags).all()

        unique_tags = set()

        for tag_list, in tags:
            if tag_list:
                unique_tags.update(tag_list)
        
        sorted_tags = sorted(unique_tags)
        return jsonify(sorted_tags), 200


    @app.route('/api/documents/filter', methods=["GET"])
    def filter_by_tags():
        tag = request.args.get('tag', "").strip()

        if not tag:
            return jsonify({"error": "Tag is required"}), 400
        
        search_tag = tag.lower()

        documents = Document.query.filter(Document.tags.any(search_tag)).all()


        result = []

        for doc in documents:  
            doc_data = {
                    "docID": doc.docID,
                    "docName": doc.docName,
                    "docTags": doc.tags,
                    "docPath": doc.docPath,
                }
            
            result.append(doc_data)

        return jsonify(result), 200
            


    # Smart Searching Feature
    @app.route('/api/search', methods=["GET"])
    def search_document():
        query = request.args.get('q', '').strip()
        if not query:
            return jsonify([])

        tsquery = ' & '.join([f"{word}:*" for word in query.split()])
        query_embedding = embedding_model.encode(query).tolist()

        sql = text(""" 
            SELECT 
                d."docID", 
                d."docName", 
                d."docPath",
                ts_rank_cd(d.search_vector, to_tsquery('english', :tsquery)) as keyword_rank,
                1 - (d.embedding <=> CAST(:embedding AS vector)) AS semantic_score,
                (0.3 * ts_rank_cd(d.search_vector, to_tsquery('english', :tsquery)) +
                0.7 * (1 - (d.embedding <=> CAST(:embedding AS vector)))) AS hybrid_score,
                ts_headline('english', d.content, to_tsquery('english', :tsquery)) AS file_snippet
            FROM document d
            WHERE d.search_vector @@ to_tsquery('english', :tsquery) 
                OR d.embedding IS NOT NULL
            ORDER BY hybrid_score DESC
            LIMIT 10
        """)

        results = db.session.execute(
            sql,             
            {
                "tsquery": tsquery,
                "embedding": query_embedding
            }
        ).mappings().all()

        output = []
        for row in results:
            output.append({
                "docID": row.docID,
                "docName": row.docName,
                "docPath": row.docPath,
                "directory": row.docPath,
                'file_snippet': row.file_snippet,
                "keyword_rank": float(row.keyword_rank) if row.keyword_rank else 0,
                "semantic_score": float(row.semantic_score) if row.semantic_score else 0,
                "hybrid_score": float(row.hybrid_score) if row.hybrid_score else 0
            })

        return jsonify(output)


    # ============================================ Rating Routes ============================================
    
    @app.route('/api/accreditation/rate/criteria', methods=["POST"])
    @jwt_required()
    def save_rating():
        current_user_id = get_jwt_identity()
        admin_user = Employee.query.filter_by(employeeID=current_user_id).first()
        if not admin_user or not admin_user.isAdmin:
            return jsonify({'success': False, 'message': 'Admins only'}), 403
        data = request.get_json()    
        ratings = data.get("ratings", {})        

        for criteriaID, rating in ratings.items():     
            rating = float(rating)       
            criteria = Criteria.query.get(criteriaID)
            if not criteria:
                return jsonify({'success': False, 'message': f'Criteria ID {criteriaID} not found'}), 404
            criteria.rating = rating
            db.session.add(criteria)

            # Audit rated criteria
            new_log = AuditLog(
                employeeID = admin_user.employeeID,
                action = f"{admin_user.lName}, {admin_user.fName} {admin_user.suffix} Rated the criteria {criteria.criteriaType}"
            )
            db.session.commit()

        return jsonify({'success': True, 'message': 'Criteria Rated Successfully!' }), 200
    
    # Get criteria ratings by program code and subarea ID
    @app.route('/api/accreditation/rate/criteria/<string:programCode>/<string:subareaID>', methods=["GET"])
    def get_criteria_ratings(programCode, subareaID):
        criteria = (
            db.session.query(
                Criteria.criteriaID,
                Criteria.criteriaContent,
                Criteria.criteriaType,
                Criteria.rating,
                Document.docID,
                Document.docName,
                Document.docPath,
                Document.predicted_rating,
                Document.predicted_probability,
                Document.similar_docs
            )
            .outerjoin(Document, Criteria.docID == Document.docID)
            .join(Subarea, Criteria.subareaID == Subarea.subareaID)
            .join(Area, Subarea.areaID == Area.areaID)
            .join(Program, Area.programID == Program.programID)
            .filter(Program.programCode == programCode, Subarea.subareaID == subareaID)
            .all()
        )

        grouped = {
            "inputs": [],
            "processes": [],
            "outcomes": []
        }

        for c in criteria:
            criteria_data = {
                "criteriaID": c.criteriaID,
                "content": c.criteriaContent,
                "docID": c.docID,
                "docName": c.docName,
                "docPath": c.docPath,
                'predicted_rating': c.predicted_rating,
                "predicted_probability": c.predicted_probability,
                "similar_docs": c.similar_docs,
                "rating": c.rating
            }

            match c.criteriaType:
                case "Inputs":
                    grouped["inputs"].append(criteria_data)
                case "Processes":
                    grouped["processes"].append(criteria_data)
                case "Outcomes":
                    grouped["outcomes"].append(criteria_data)

        return jsonify(grouped), 200

    # Save subarea rating
    
    @app.route('/api/accreditation/rate/subarea', methods=["POST"])
    @jwt_required()
    def save_subarea_rate():
        current_user_id = get_jwt_identity()
        admin_user = Employee.query.filter_by(employeeID=current_user_id).first()
        if not admin_user or not admin_user.isAdmin:
            return jsonify({'success': False, 'message': 'Admins only'}), 403
        data = request.get_json()        
        subareaID = data.get("subareaID")
        rating = float(data.get("rating"))

        subarea = Subarea.query.get(subareaID)
        if not subarea: 
            return jsonify({'success': False, 'message': 'Subarea not found'}), 404

        subarea.rating = rating

        db.session.add(subarea)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Subarea rating saved!' }), 200


    # Get subarea ratings by program code and area ID
    @app.route('/api/accreditation/rate/subarea/<string:programCode>/<string:areaID>', methods=["GET"])
    def get_subarea_ratings(programCode, areaID):
        subareas = (
            db.session.query(
                Subarea.subareaID,
                Subarea.subareaName,
                Subarea.rating            
            )
            .join(Area, Subarea.areaID == Area.areaID)
            .join(Program, Area.programID == Program.programID)
            .filter(Program.programCode == programCode, Area.areaID == areaID)
            .all()
        )
        subarea_list = []

        for sa in subareas:
            subarea_data = {
                'subareaID': sa.subareaID,
                'subareaName': sa.subareaName,
                'rating': sa.rating,
            }
            subarea_list.append(subarea_data)        

        return jsonify(subarea_list), 200

    
    @app.route('/api/accreditation/rate/area', methods=["POST"])
    @jwt_required()
    def save_area_rate():
        current_user_id = get_jwt_identity()
        admin_user = Employee.query.filter_by(employeeID=current_user_id).first()
        if not admin_user or not admin_user.isAdmin:
            return jsonify({'success': False, 'message': 'Admins only'}), 403
        data = request.get_json()        
        areaID = data.get("areaID")
        rating = float(data.get("rating"))

        area = Area.query.get(areaID)
        if not area: 
            return jsonify({'success': False, 'message': 'Area not found'}), 404

        area.rating = rating
        db.session.add(area)

        # Audit rated area
        new_log = AuditLog(
            employeeID = admin_user.employeeID,
            action = f"{admin_user.lName}, {admin_user.fName} {admin_user.suffix} Rated the area {area.areaName}"
        )
        db.session.add(new_log)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Area rating saved!' }), 200



    # ============================================ Messages Routes ============================================


    @app.route('/api/users/online-status', methods=['GET'])
    @jwt_required()
    def get_users_with_status():
        empID = get_jwt_identity()
        users = Employee.query.all()
        online_users = {user.decode('utf-8') for user in redis_client.smembers('online_users')}
        users_data = []
        for user in users:
            status = redis_client.hget('user_status', user.employeeID)
            status_str = status.decode('utf-8') if status else 'active'
            users_data.append({
                'employeeID': user.employeeID,
                'fName': user.fName,
                'lName': user.lName,
                'profilePic': user.profilePic,
                'online_status': user.employeeID in online_users,
                'status': status_str
            })
        
        return jsonify({
            'success': True,
            'users': users_data
        })

    @app.route('/api/conversations', methods=['GET'])
    @jwt_required()
    def get_conversations():
        current_user_id = get_jwt_identity()
        
        # Get conversations where current user participates
        
        user_conversation_ids = db.session.query(
            ConversationParticipant.conversationID
        ).filter(
            ConversationParticipant.employeeID == current_user_id
        ).subquery()
        
        # Get other participants in those conversations
        conversations = db.session.query(
            Conversation.conversationID,
            Conversation.conversationType,
            Conversation.createdAt,
            ConversationParticipant.employeeID.label('other_participant_id'),
            Employee.fName,
            Employee.lName,
            Employee.profilePic
        ).join(
            ConversationParticipant, 
            Conversation.conversationID == ConversationParticipant.conversationID
        ).join(
            Employee, 
            ConversationParticipant.employeeID == Employee.employeeID
        ).filter(
            Conversation.conversationID.in_(user_conversation_ids),
            ConversationParticipant.employeeID != current_user_id
        ).all()
        
        # Format results (same as before)
        conversations_data = []
        for conv in conversations:
            conversations_data.append({
                'conversationID': conv.conversationID,
                'otherParticipant': {
                    'employeeID': conv.other_participant_id,
                    'name': f"{conv.fName} {conv.lName}",
                    'profilePic': conv.profilePic
                },
                'conversationType': conv.conversationType,
                'createdAt': conv.createdAt.isoformat() if conv.createdAt else None
            })
        
        return jsonify({
            'success': True,
            'conversations': conversations_data
        }), 200

            
    @app.route('/api/conversations/<int:conversation_id>/message', methods =['GET'])
    @jwt_required()
    def get_messages(conversation_id):
        current_user_id = get_jwt_identity()

        participants = ConversationParticipant.query.filter_by(
            conversationID=conversation_id,
            employeeID=current_user_id
        ).first()

        if not participants:
            return jsonify({'success': False, 'message': 'Access Denied.'}), 403

        # Exclude messages the current user chose to hide
        hidden_ids_subq = db.session.query(MessageDeletion.messageID).filter(
            MessageDeletion.employeeID == str(current_user_id)
        ).subquery()

        messages = db.session.query(Message).filter(
            Message.conversationID == conversation_id,
            ~Message.messageID.in_(hidden_ids_subq)
        ).order_by(Message.sentAt.asc()).all()

        messages_data = []
        for msg in messages:
            messages_data.append({
                'id': msg.messageID,
                'content': msg.messageContent,
                'senderID': msg.senderID,
                'createdAt': msg.sentAt.isoformat() if msg.sentAt else None,
                'isOwn': msg.senderID == current_user_id
            })

        return jsonify({
            'success': True,
            'messages': messages_data
        }), 200

    

    @app.route('/api/conversations/start', methods=['POST'])
    @jwt_required()
    def conversations_start():
        try:
            current_user_id = get_jwt_identity()
            data = request.get_json() or {}
            participant_id = data.get('participantID')

            if not participant_id:
                return jsonify({'success': False, 'message': 'participantID is required'}), 400
            # Accept IDs that may contain non-digits (e.g., formatted IDs like 22-16-075)
            raw_pid = str(participant_id).strip()
            normalized_pid = re.sub(r'\D', '', raw_pid)
            if not raw_pid:
                return jsonify({'success': False, 'message': 'participantID is required'}), 400
            # Prevent self-conversation (compare after stripping non-digits)
            if re.sub(r'\D', '', str(current_user_id).strip()) == normalized_pid:
                return jsonify({'success': False, 'message': 'Cannot start a conversation with yourself'}), 400

            # Validate participant exists
            # Try exact string match, or match on digits-only using regexp_replace
            target_user = db.session.query(Employee).filter(
                (cast(Employee.employeeID, String) == raw_pid) |
                (func.regexp_replace(cast(Employee.employeeID, String), '[^0-9]', '', 'g') == normalized_pid)
            ).first()
            if not target_user:
                return jsonify({'success': False, 'message': 'Participant not found'}), 404
            
            # Find existing direct conversation between both users
            current_user_id_str = str(current_user_id).strip()
            participant_id_str = raw_pid

            user_conv_ids = db.session.query(
                ConversationParticipant.conversationID
            ).filter(
                ConversationParticipant.employeeID == current_user_id_str
            ).subquery()

            other_conv_ids = db.session.query(
                ConversationParticipant.conversationID
            ).filter(
                ConversationParticipant.employeeID == participant_id_str
            ).subquery()

            existing_conv = db.session.query(Conversation).filter(
                Conversation.conversationType == 'direct',
                Conversation.conversationID.in_(user_conv_ids),
                Conversation.conversationID.in_(other_conv_ids)
            ).first()

            if existing_conv:
                return jsonify({
                    'success': True,
                    'conversationID': existing_conv.conversationID,
                    'conversationType': existing_conv.conversationType,
                    'createdAt': existing_conv.createdAt.isoformat() if existing_conv.createdAt else None,
                    'otherParticipant': {
                        'employeeID': str(target_user.employeeID),
                        'name': f"{target_user.fName} {target_user.lName}",
                        'profilePic': target_user.profilePic
                    }
                }), 200

            # Create new direct conversation
            new_conv = Conversation(
                conversationType='direct',
                createdBy=current_user_id_str
            )
            db.session.add(new_conv)
            db.session.flush()

            # Add both participants
            db.session.add_all([
                ConversationParticipant(conversationID=new_conv.conversationID, employeeID=current_user_id_str),
                ConversationParticipant(conversationID=new_conv.conversationID, employeeID=participant_id_str)
            ])
            db.session.commit()

            return jsonify({
                'success': True,
                'conversationID': new_conv.conversationID,
                'conversationType': new_conv.conversationType,
                'createdAt': new_conv.createdAt.isoformat() if new_conv.createdAt else None,
                'otherParticipant': {
                    'employeeID': str(target_user.employeeID),
                    'name': f"{target_user.fName} {target_user.lName}",
                    'profilePic': target_user.profilePic
                }
            }), 201
        except Exception as e:
            current_app.logger.error(f"Start conversation error: {e}")
            return jsonify({'success': False, 'message': 'Internal server error'}), 500

    @app.route('/api/conversations/<int:conversation_id>/message', methods=['POST'])
    @jwt_required()
    def send_message(conversation_id):
        current_user_id = get_jwt_identity()
        data = request.get_json()

        participant = ConversationParticipant.query.filter_by(
            conversationID=conversation_id,
            employeeID=current_user_id
        ).first()

        if not participant:
            return jsonify({'success': False, 'message': 'Access Denied'}), 403

        content = data.get('content', '').strip()
        if not content:
            return jsonify({'success': False, 'message': 'Message cannot be empty'}), 400

        new_message = Message(
            conversationID=conversation_id,
            senderID=current_user_id,
            messageContent=content
        )

        db.session.add(new_message)
        db.session.commit()

        socketio.emit('new_message', {
            'conversationID': conversation_id,
            'message': {
                'id': new_message.messageID,
                'content': new_message.messageContent,
                'senderID': new_message.senderID,
                'createdAt': new_message.sentAt.isoformat(),
                'isOwn': False
            }
        }, room=f'conversation:{conversation_id}') 
        
        return jsonify({
            'success': True,
            'message': 'Message sent successfully'
        }), 201

    @app.route('/api/messages/<int:message_id>', methods=['DELETE'])
    @jwt_required()
    def hide_message_for_user(message_id):
        try:
            current_user_id = get_jwt_identity()
            # Ensure the message exists and user is a participant of the conversation
            msg = Message.query.filter_by(messageID=message_id).first()
            if not msg:
                return jsonify({'success': False, 'message': 'Message not found'}), 404

            is_participant = ConversationParticipant.query.filter_by(
                conversationID=msg.conversationID,
                employeeID=str(current_user_id)
            ).first() is not None
            if not is_participant:
                return jsonify({'success': False, 'message': 'Forbidden'}), 403

            # Idempotent insert: if already hidden, return success
            already = MessageDeletion.query.filter_by(
                messageID=message_id,
                employeeID=str(current_user_id)
            ).first()
            if already:
                return jsonify({'success': True}), 200

            deletion = MessageDeletion(
                messageID=message_id,
                employeeID=str(current_user_id)
            )
            db.session.add(deletion)
            db.session.commit()
            return jsonify({'success': True}), 200
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Hide message error: {e}")
            return jsonify({'success': False, 'message': 'Internal server error'}), 500
                    
    @app.route('/api/conversations/<int:conversation_id>', methods=['DELETE'])
    @jwt_required()
    def delete_conversation(conversation_id):
        current_user_id = get_jwt_identity()

        conv = Conversation.query.filter_by(conversationID=conversation_id).first()
        if not conv:
            return jsonify({'success': False, 'message': 'Not found'}), 404

        is_participant = ConversationParticipant.query.filter_by(
            conversationID=conversation_id, employeeID=current_user_id
        ).first() is not None
        if not (is_participant or current_user_id == conv.createdBy):
            return jsonify({'success': False, 'message': 'Forbidden'}), 403

        db.session.delete(conv)
        db.session.commit()

        socketio.emit('conversation_deleted', {'conversationID': conversation_id}, room=f'conversation:{conversation_id}')
        return jsonify({'success': True}), 200

    
    
    # ================ Create Routes ================

    @app.route('/api/accreditation/create_area', methods=["POST"])
    @jwt_required()
    def create_area():
        current_user_id = get_jwt_identity()
        admin_user = Employee.query.filter_by(employeeID=current_user_id).first()
        if not admin_user or not admin_user.isAdmin:
            return jsonify({'success': False, 'message': 'Admins only'}), 403
        data = request.form
        programID = data.get("programID")
        areaNum = data.get("areaNum")
        areaName = data.get("areaName")

    # create new area

        new_area = Area(
            programID = programID,
            areaName = areaName,
            areaNum = areaNum
        )
        db.session.add(new_area)

        # Audit new area
        new_log = AuditLog(
            employeeID = admin_user.employeeID,
            action = f"{admin_user.lName}, {admin_user.fName} {admin_user.suffix} Created a new area: {areaName}"
        )
        db.session.add(new_log)
        db.session.commit()

        return jsonify({'message' : 'Area created successfully!'}), 200


    @app.route('/api/accreditation/create_subarea', methods=["POST"])
    @jwt_required()
    def create_sub_area():
        current_user_id = get_jwt_identity()
        admin_user = Employee.query.filter_by(employeeID=current_user_id).first()
        if not admin_user or not admin_user.isAdmin:
            return jsonify({'success': False, 'message': 'Admins only'}), 403
        data = request.form
        areaID = data.get("selectedAreaID")
        subareaName = data.get("subAreaName")
        area = Area.query.get(areaID)
        # Check if the area exists
        if not area:
            return jsonify({'error': 'Area not found'}), 404

        new_subArea = Subarea(subareaName = subareaName)
        area.subareas.append(new_subArea)

        db.session.add(new_subArea)

        # Audit new subarea
        new_log = AuditLog(
            employeeID = admin_user.employeeID,
            action = f"{admin_user.lName}, {admin_user.fName} {admin_user.suffix} Created a new subarea: {subareaName}"
        )
        db.session.add(new_log)
        db.session.commit()

        return jsonify({'message': 'Sub-Area created successfully!'}), 200
        
    @app.route('/api/accreditation/create_criteria', methods=["POST"])
    @jwt_required()
    def create_criteria():
        current_user_id = get_jwt_identity()
        admin_user = Employee.query.filter_by(employeeID=current_user_id).first()
        if not admin_user or not admin_user.isAdmin:
            return jsonify({'success': False, 'message': 'Admins only'}), 403
        data = request.form
        subareaID = data.get("selectedSubAreaID")
        criteriaContent = data.get("criteria")
        criteriaType = data.get("criteriaType")
        subarea = Subarea.query.get(subareaID)
        if not subarea:
            return jsonify({'error': 'Subarea not found'}), 404
        
        new_criteria = Criteria(
            subareaID = subareaID,
            criteriaContent = criteriaContent,
            criteriaType = criteriaType
        )

        subarea.criteria.append(new_criteria)

        db.session.add(new_criteria)

        # Audit new criteria
        new_log = AuditLog(
            employeeID = admin_user.employeeID,
            action = f"{admin_user.lName}, {admin_user.fName} {admin_user.suffix} Created a new criteria: {criteriaType} in {subarea.subareaName}"
        )
        db.session.add(new_log)
        db.session.commit()

        return jsonify({'message': 'Criteria created successfully!'}), 200
    # ================ Update Routes ================
    # Update area
    @app.route('/api/areas/<int:areaID>/edit', methods=["PUT"])
    @jwt_required()
    def update_area(areaID):
        data = request.get_json()
        try:
            area = Area.query.get(areaID)
            if not area:
                return jsonify({'success': False, 'message': 'Area not found.'}), 404
            area.areaName = data.get("areaName")
            area.areaNum = data.get("areaNum")
            db.session.commit()
            return jsonify({"success": True, "message": "Area updated"})
        except Exception as e:
            db.session.rollback()
            return jsonify({"success": False, "message": f"Failed to update: {str(e)}"}), 500
        
    # Update subarea   
    @app.route('/api/subareas/<int:subareaID>/edit', methods=["PUT"])
    @jwt_required()
    def update_subarea(subareaID):
        data = request.get_json()
        try:
            subarea = Subarea.query.get(subareaID)
            if not subarea:
                return jsonify({'success': False, 'message': 'Subarea not found.'}), 404
            subarea.subareaName = data.get("subareaName")            
            db.session.commit()
            return jsonify({"success": True, "message": "Subarea updated"})
        except Exception as e:
            db.session.rollback()
            return jsonify({"success": False, "message": f"Failed to update: {str(e)}"}), 500
   # Update criteria 
    @app.route('/api/criterias/<int:criteriaID>/edit', methods=["PUT"])
    @jwt_required()
    def update_criteria(criteriaID):
        data = request.get_json()
        try:
            criteria = Criteria.query.get(criteriaID)
            if not criteria:
                return jsonify({'success': False, 'message': 'Criteria not found.'}), 404
            criteria.criteriaContent = data.get("criteriaContent")            
            db.session.commit()
            return jsonify({"success": True, "message": "Criteria updated"})
        except Exception as e:
            db.session.rollback()
            return jsonify({"success": False, "message": f"Failed to update: {str(e)}"}), 500
          
    # ================ Delete Routes ================
    # Delete Area
    @app.route('/api/areas/<int:areaID>/delete', methods=["DELETE"])
    @jwt_required()
    def delete_area(areaID):        
        area = Area.query.get(areaID)
        if not area:
            return jsonify({"success": False, "message": "Area not found"}), 404    
    
        db.session.delete(area)
        db.session.commit()
        return jsonify({"success": True, "message": "Area Deleted"})
    
    # Delete Subarea
    @app.route('/api/subareas/<int:subareaID>/delete', methods=["DELETE"])
    @jwt_required()
    def delete_subarea(subareaID):
        subarea = Subarea.query.get(subareaID)
        if not subarea:
            return jsonify({"success": False, "message": "Subarea not found"}), 404    
    
        db.session.delete(subarea)
        db.session.commit()
        return jsonify({"success": True, "message": "Subarea Deleted"})
    
    # Delete Criteria
    @app.route('/api/criterias/<int:criteriaID>/delete', methods=["DELETE"])
    @jwt_required()
    def delete_criteria(criteriaID):        
        criteria = Criteria.query.get(criteriaID)
        if not criteria:
            return jsonify({"success": False, "message": "Criteri not found"}), 404    
    
        db.session.delete(criteria)
        db.session.commit()
        return jsonify({"success": True, "message": "Criteria Deleted"})
           

    
    
    # ============================================ Template Routes ============================================

    @app.route('/api/templates', methods=["GET"])
    @jwt_required()
    def get_templates():
        data = (
            db.session.query(
                Template.templateID,
                Template.templateName,
                Template.description,
                Template.createdBy,
                Template.createdAt,
                Template.isApplied,
                Employee.employeeID,
                Employee.fName,
                Employee.lName,
                Employee.suffix,
                AreaBlueprint.areaBlueprintID,
                AreaBlueprint.areaName,
                AreaBlueprint.areaNum,
                SubareaBlueprint.subareaBlueprintID,
                SubareaBlueprint.subareaName,
                CriteriaBlueprint.criteriaBlueprintID,
                CriteriaBlueprint.criteriaContent,
                CriteriaBlueprint.criteriaType,
                Program.programID,
                Program.programName,
                Program.programCode
            )
            .outerjoin(Employee, Template.createdBy == Employee.employeeID)
            .outerjoin(AreaBlueprint, AreaBlueprint.templateID == Template.templateID)
            .outerjoin(SubareaBlueprint, SubareaBlueprint.areaBlueprintID == AreaBlueprint.areaBlueprintID)
            .outerjoin(CriteriaBlueprint, CriteriaBlueprint.subareaBlueprintID == SubareaBlueprint.subareaBlueprintID)
            .outerjoin(Program, Program.templateID == Template.templateID)
            .filter(Template.archived == False)
            .group_by(  # Group to eliminate duplicates
                Template.templateID,
                Employee.employeeID,
                AreaBlueprint.areaBlueprintID,
                SubareaBlueprint.subareaBlueprintID,
                CriteriaBlueprint.criteriaBlueprintID,
                Program.programID
            )
            .order_by(
                AreaBlueprint.areaBlueprintID.asc(),
                SubareaBlueprint.subareaBlueprintID.asc(),
                CriteriaBlueprint.criteriaBlueprintID.asc(),
            )
            .all()
        )

        template_dict = {}

        for row in data:
            if row.templateID not in template_dict:
                template_dict[row.templateID] = {
                    "templateID": row.templateID,
                    "templateName": row.templateName,
                    "description": row.description,
                    "createdBy": f"{row.fName} {row.lName}{row.suffix or ''}",
                    "createdAt": row.createdAt,
                    "isApplied": "Applied" if row.isApplied == True else "Inactive",                                          
                    "areas": {},
                    "programs": []
                }

            template = template_dict[row.templateID]

            # --- Programs ---
            if row.programID and not any(p["programID"] == row.programID for p in template["programs"]):
                template["programs"].append({
                    "programID": row.programID,
                    "programName": row.programName,
                    "programCode": row.programCode
                })

            # --- Areas ---
            if row.areaBlueprintID and row.areaBlueprintID not in template["areas"]:
                template["areas"][row.areaBlueprintID] = {
                    "areaID": row.areaBlueprintID,
                    "areaName": row.areaName,
                    "areaNum": row.areaNum,
                    "subareas": {},
                }

            area = template["areas"].get(row.areaBlueprintID)
            if not area:
                continue

            # --- Subareas ---
            if row.subareaBlueprintID and row.subareaBlueprintID not in area["subareas"]:
                area["subareas"][row.subareaBlueprintID] = {
                    "subareaID": row.subareaBlueprintID,
                    "subareaName": row.subareaName,
                    "criteria": {
                        "inputs": [],
                        "processes": [],
                        "outcomes": [],
                    },
                }

            subarea = area["subareas"].get(row.subareaBlueprintID)
            if not subarea:
                continue

            # --- Group criteria ---
            if row.criteriaBlueprintID and row.criteriaType:
                crit_type = row.criteriaType.lower()
                criteria_entry = {
                    "criteriaID": row.criteriaBlueprintID,
                    "criteriaContent": row.criteriaContent,
                    "criteriaType": row.criteriaType,
                }
                
                def add_unique_criteria(array):
                    # Only add if criteriaID not already in array
                    if not any(c["criteriaID"] == row.criteriaBlueprintID for c in array):
                        array.append(criteria_entry)
                
                if "input" in crit_type:
                    add_unique_criteria(subarea["criteria"]["inputs"])
                elif "process" in crit_type:
                    add_unique_criteria(subarea["criteria"]["processes"])
                elif "outcome" in crit_type:
                    add_unique_criteria(subarea["criteria"]["outcomes"])
                else:
                    # fallback for undefined types
                    add_unique_criteria(subarea["criteria"]["inputs"])

        # --- Convert nested dicts to lists ---
        template_list = []
        for temp in template_dict.values():
            temp["areas"] = list(temp["areas"].values())
            for area in temp["areas"]:
                area["subareas"] = list(area["subareas"].values())
            template_list.append(temp)

        return jsonify(template_list), 200



    @app.route('/api/templates/create', methods=["POST"])
    @jwt_required()
    def create_template():
        import traceback

        data = request.get_json()
        
        templateName = data.get("templateName")
        description = data.get("description", "")
        createdBy = get_jwt_identity()
        areas = data.get("areas", [])

        print("DEBUG incoming data:", data)
        

        try:
            new_template = Template(                
                templateName=templateName,
                description=description,
                createdBy=createdBy,
                createdAt=datetime.utcnow(),
                isApplied=False
            )   

            db.session.add(new_template)
            db.session.flush()

            created_areas = []

            for area in areas:
                # Parse the area name                                
            
                area_bp = AreaBlueprint(
                    templateID=new_template.templateID,
                    areaName=area.get("areaName"),
                    areaNum=area.get("areaNum")            
                )

                db.session.add(area_bp)
                db.session.flush()

                created_subareas = []

                for sub in area.get("subareas", []):
                    subarea_bp = SubareaBlueprint(
                        areaBlueprintID=area_bp.areaBlueprintID,
                        subareaName=sub.get("subareaName")
                    )
                    db.session.add(subarea_bp)
                    db.session.flush()

                    created_criteria = []

                    for crit in sub.get("criteria", []):
                        criteria_bp = CriteriaBlueprint(
                            subareaBlueprintID=subarea_bp.subareaBlueprintID,
                            criteriaContent=crit.get("criteriaContent", ""),
                            criteriaType=crit.get("criteriaType", ""),                            
                        )
                        db.session.add(criteria_bp)
                        db.session.flush()

                        created_criteria.append({
                            "criteriaBlueprintID": criteria_bp.criteriaBlueprintID,
                            "criteriaContent": criteria_bp.criteriaContent,
                            "criteriaType": criteria_bp.criteriaType,                            
                        })

                    created_subareas.append({
                        'subareaBlueprintID': subarea_bp.subareaBlueprintID,
                        'subareaName': subarea_bp.subareaName,
                        'criteria': created_criteria
                    })
                
                created_areas.append({
                    "areaBlueprintID": area_bp.areaBlueprintID,
                    "areaNum": area_bp.areaNum,
                    "areaName": area_bp.areaName,
                    "subareas": created_subareas
                })
            
            db.session.commit()
            
            return jsonify({
                "success": True,
                "message": "Template saved successfully!",
                "template": {
                    "templateID": new_template.templateID,
                    "templateName": new_template.templateName,
                    "description": new_template.description,
                    "createdBy": new_template.createdBy,
                    "createdAt": new_template.createdAt,
                    "areas": created_areas,
                    "isApplied": new_template.isApplied
                }
            }), 201
        
            
        except Exception as e:
            db.session.rollback()
            print("Save template error:", str(e))
            traceback.print_exc()
            return jsonify({"success": False, "message": f"Failed to save template: {str(e)}"}), 500


    @app.route('/api/programs/apply-template/<int:templateID>', methods=["POST"])
    @jwt_required()
    def apply_template(templateID): 
        userID = get_jwt_identity()

        try:
            data = request.get_json()
            programIDs = data.get("programIDs", [])
            
            if not programIDs:
                return jsonify({"success": False, "message": "No programs selected"}), 400

            # Get the template
            template = Template.query.filter_by(templateID=templateID).first()
            if not template:
                return jsonify({"success": False, "message": "Template not found"}), 404
            
            for programID in programIDs:
                # === Archive existing areas ===
                active_areas = Area.query.filter_by(programID=programID, archived=False).all()
                for area in active_areas:
                    area.archived = True
                    for sub in area.subareas:
                        sub.archived = True
                        for crit in sub.criteria:
                            crit.archived = True

                # === Create Applied Template for this program ===
                applied_template = AppliedTemplate(
                    programID=programID,
                    templateID=template.templateID,
                    templateName=template.templateName,
                    description=template.description,
                    appliedBy=get_jwt_identity()
                )
                db.session.add(applied_template)
                db.session.flush()

                # === Copy Areas, Subareas, Criteria ===
                area_blueprints = AreaBlueprint.query.filter_by(templateID=templateID).all()
                for ab in area_blueprints:
                    area = Area(
                        appliedTemplateID=applied_template.appliedTemplateID,
                        programID=programID,                        
                        areaBlueprintID=ab.areaBlueprintID,
                        areaName=ab.areaName,
                        areaNum=ab.areaNum,
                        archived=False
                    )
                    db.session.add(area)
                    db.session.flush()

                    subarea_blueprints = SubareaBlueprint.query.filter_by(areaBlueprintID=ab.areaBlueprintID).all()
                    for sb in subarea_blueprints:
                        subarea = Subarea(
                            areaID=area.areaID,                            
                            subareaBlueprintID=sb.subareaBlueprintID,
                            subareaName=sb.subareaName,
                            archived=False
                        )
                        db.session.add(subarea)
                        db.session.flush()

                        criteria_blueprints = CriteriaBlueprint.query.filter_by(subareaBlueprintID=sb.subareaBlueprintID).all()
                        for cb in criteria_blueprints:
                            criteria = Criteria(
                                subareaID=subarea.subareaID,                                
                                criteriaBlueprintID=cb.criteriaBlueprintID,
                                criteriaContent=cb.criteriaContent,
                                criteriaType=cb.criteriaType,
                                archived=False
                            )
                            db.session.add(criteria)

                # Link program to template
                program = Program.query.get(programID)
                if program:
                    program.templateID = template.templateID

            # Mark template as applied
            template.isApplied = True

            
            currentUser = Employee.query.filter_by(employeeID=userID).first()
            new_log = AuditLog(
                employeeID = currentUser.employeeID,
                action = f"{currentUser.lName}, {currentUser.fName} {currentUser.suffix} APPLIED the template {template.templateName} to {program.programName}"
            )
            db.session.add(new_log)            
            db.session.commit()

            return jsonify({'success': True, 'message': 'Template applied to all selected programs successfully!'}), 201

        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f"Failed to apply template: {str(e)}"}), 500



    @app.route("/api/templates/edit/<int:templateID>", methods=["PUT"])
    @jwt_required()
    def edit_template(templateID):
        data = request.get_json()
        userID = get_jwt_identity()

        try:
            template = Template.query.get(templateID)
            if not template:
                return jsonify({"message": "Template not found"}), 404

            # ===== Update Template Info =====
            template.templateName = data.get("templateName", template.templateName)
            template.description = data.get("description", template.description)

            # ===== Track Existing Areas =====
            existing_area_bps = {
                a.areaBlueprintID: a for a in AreaBlueprint.query.filter_by(templateID=templateID).all()
            }
            incoming_area_ids = {
                a.get("areaBlueprintID") for a in data.get("areas", []) if a.get("areaBlueprintID")
            }

            # ===== Delete Removed Areas =====
            for abp_id, abp in existing_area_bps.items():
                if abp_id not in incoming_area_ids:
                    # unlink dependent records first
                    Area.query.filter_by(areaBlueprintID=abp_id).update({"areaBlueprintID": None})
                    SubareaBlueprint.query.filter_by(areaBlueprintID=abp_id).update({"areaBlueprintID": None})
                    db.session.delete(abp)

            # ===== Update/Add Areas =====
            for area_data in data.get("areas", []):
                area_bp = existing_area_bps.get(area_data.get("areaBlueprintID")) if area_data.get("areaBlueprintID") else None

                if area_bp:
                    area_bp.areaName = area_data.get("areaName", area_bp.areaName)
                    area_bp.areaNum = area_data.get("areaNum", area_bp.areaNum)
                else:
                    area_bp = AreaBlueprint(
                        templateID=templateID,
                        areaName=area_data.get("areaName"),
                        areaNum=area_data.get("areaNum")
                    )
                    db.session.add(area_bp)
                    db.session.flush()

                # ===== Handle Subareas =====
                existing_sub_bps = {
                    s.subareaBlueprintID: s for s in SubareaBlueprint.query.filter_by(areaBlueprintID=area_bp.areaBlueprintID).all()
                }
                incoming_sub_ids = {
                    s.get("subareaBlueprintID") for s in area_data.get("subareas", []) if s.get("subareaBlueprintID")
                }

                # Delete removed subareas
                for sb_id, sb in existing_sub_bps.items():
                    if sb_id not in incoming_sub_ids:
                        Subarea.query.filter_by(subareaBlueprintID=sb_id).update({"subareaBlueprintID": None})
                        db.session.delete(sb)

                # Update/add subareas
                for sub_data in area_data.get("subareas", []):
                    sub_bp = existing_sub_bps.get(sub_data.get("subareaBlueprintID"))
                    if sub_bp:
                        sub_bp.subareaName = sub_data.get("subareaName", sub_bp.subareaName)
                    else:
                        sub_bp = SubareaBlueprint(
                            areaBlueprintID=area_bp.areaBlueprintID,
                            subareaName=sub_data.get("subareaName")
                        )
                        db.session.add(sub_bp)
                        db.session.flush()

                    # ===== Handle Criteria =====
                    existing_crit_bps = {
                        c.criteriaBlueprintID: c for c in CriteriaBlueprint.query.filter_by(subareaBlueprintID=sub_bp.subareaBlueprintID).all()
                    }
                    incoming_crit_ids = {
                        c.get("criteriaBlueprintID") for c in sub_data.get("criteria", []) if c.get("criteriaBlueprintID")
                    }

                    # Delete removed criteria
                    for cb_id, cb in existing_crit_bps.items():
                        if cb_id not in incoming_crit_ids:
                            Criteria.query.filter_by(criteriaBlueprintID=cb_id).update({"criteriaBlueprintID": None})
                            db.session.delete(cb)

                    # Add/update criteria
                    for crit in sub_data.get("criteria", []):
                        crit_id = crit.get("criteriaBlueprintID")
                        c_bp = existing_crit_bps.get(crit_id) if crit_id else None
                        
                        # Normalize content and type
                        content = (crit.get("criteriaContent") or "").strip()
                        crit_type = (crit.get("criteriaType") or "").strip()
                        
                        if c_bp:
                            # Update existing blueprint with normalized content
                            c_bp.criteriaContent = content
                            c_bp.criteriaType = crit_type
                        else:
                            # try to reuse an existing blueprint with same content for this subarea
                            c_bp = CriteriaBlueprint.query.filter_by(
                                subareaBlueprintID=sub_bp.subareaBlueprintID,
                                criteriaContent=content,
                                criteriaType=crit_type  # Also check type match
                            ).first()
                            
                            if not c_bp:
                                # Check for content match with different casing/whitespace
                                similar_content = (
                                    CriteriaBlueprint.query
                                    .filter_by(subareaBlueprintID=sub_bp.subareaBlueprintID)
                                    .filter(
                                        func.lower(func.trim(CriteriaBlueprint.criteriaContent)) == 
                                        func.lower(content)
                                    )
                                    .first()
                                )
                                if similar_content:
                                    c_bp = similar_content
                                    c_bp.criteriaContent = content  # Update to normalized version
                                    c_bp.criteriaType = crit_type
                                
                            if c_bp:
                                # reuse found blueprint
                                existing_crit_bps[c_bp.criteriaBlueprintID] = c_bp
                            else:
                                # Create new only if truly unique
                                c_bp = CriteriaBlueprint(
                                    subareaBlueprintID=sub_bp.subareaBlueprintID,
                                    criteriaContent=content,
                                    criteriaType=crit_type
                                )
                                db.session.add(c_bp)
                                db.session.flush()
                                existing_crit_bps[c_bp.criteriaBlueprintID] = c_bp

            # Commit template + blueprints first
            db.session.commit()

            # ===== Reapply template updates to all linked programs =====
            programs = Program.query.filter_by(templateID=templateID).all()
            for program in programs:
                applied_template = AppliedTemplate.query.filter_by(programID=program.programID).first()
                if not applied_template:
                    applied_template = AppliedTemplate(programID=program.programID, templateID=templateID)
                    db.session.add(applied_template)
                    db.session.flush()

                reapply_template(templateID, applied_template)
        
            db.session.commit()

            currentUser = Employee.query.filter_by(employeeID=userID).first()
            new_log = AuditLog(
                employeeID = currentUser.employeeID,
                action = f"{currentUser.lName}, {currentUser.fName} {currentUser.suffix} EDITED TEMPLATE {template.templateName}"
            )
            db.session.add(new_log)
            db.session.commit()

            return jsonify({"success": True, "message": "Template and all linked programs updated successfully"}), 200

        except Exception as e:
            db.session.rollback()
            print("❌ Template update error:", e)
            return jsonify({"error": f"Failed to update template: {str(e)}"}), 500




    @app.route('/api/templates/delete/<int:templateID>', methods=["DELETE"])
    @jwt_required()
    def delete_template(templateID):
        userID = get_jwt_identity()

        try:
            template = Template.query.filter_by(templateID=templateID).first()
            if not template:
                return jsonify({"success": False, "message": "Template not found"}), 404

            # ================ Delete Blueprint Data ================

            # 1. Delete CriteriaBlueprints linked to this template
            criteriaBP = (
                CriteriaBlueprint.query
                .join(SubareaBlueprint)
                .join(AreaBlueprint)
                .filter(AreaBlueprint.templateID == templateID)
                .all()
            )
            for crit in criteriaBP:
                db.session.delete(crit)

            # 2. Delete SubareaBlueprints linked to this template
            subareaBP = (
                SubareaBlueprint.query
                .join(AreaBlueprint)
                .filter(AreaBlueprint.templateID == templateID)
                .all()
            )
            for sub in subareaBP:
                db.session.delete(sub)

            # 3. Delete AreaBlueprints linked to this template
            areaBP = AreaBlueprint.query.filter_by(templateID=templateID).all()
            for area in areaBP:
                db.session.delete(area)

            # ================ Delete AppliedTemplate records ================
            applied_templates = AppliedTemplate.query.filter_by(templateID=templateID).all()
            for applied in applied_templates:
                db.session.delete(applied)

            # 4. Finally delete the Template itself
            db.session.delete(template)

            
            currentUser = Employee.query.filter_by(employeeID=userID).first()
            new_log = AuditLog(
                employeeID = currentUser.employeeID,
                action = f"{currentUser.lName}, {currentUser.fName} {currentUser.suffix} DELETED TEMPLATE {template.templateName}"
            )
            db.session.add(new_log)            
            db.session.commit()

            return jsonify({"success": True, "message": "Template deleted successfully"}), 200
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Failed to delete template: {str(e)}'}), 400

    # =================================== SECURITY DASHBOARD ROUTES ===================================
    
    @app.route('/api/security/dashboard', methods=['GET'])
    @jwt_required()
    def security_dashboard():
        """Get security dashboard data - Admin only"""
        try:
            from app.security.security_monitor import SecurityMonitor
            
            # Get current user
            emp_id = get_jwt_identity()
            user = Employee.query.filter_by(employeeID=emp_id).first()
            
            if not user or not user.isAdmin:
                return jsonify({
                    'success': False,
                    'message': 'Unauthorized. Admin access required.'
                }), 403
            
            # Get security statistics
            threat_level = SecurityMonitor.check_threat_level()
            recent_events = SecurityMonitor.get_recent_events(limit=50)
            blocked_ips = SecurityMonitor.get_blocked_ips()
            
            return jsonify({
                'success': True,
                'data': {
                    'threat_level': threat_level,
                    'recent_events': recent_events,
                    'blocked_ips': blocked_ips,
                    'total_blocked_ips': len(blocked_ips)
                }
            }), 200
            
        except Exception as e:
            current_app.logger.error(f"Security dashboard error: {e}")
            return jsonify({
                'success': False,
                'message': 'Failed to load security dashboard'
            }), 500
    
    @app.route('/api/security/unblock-ip', methods=['POST'])
    @jwt_required()
    def unblock_ip():
        """Manually unblock an IP address - Admin only"""
        try:
            # Get current user
            emp_id = get_jwt_identity()
            user = Employee.query.filter_by(employeeID=emp_id).first()
            
            if not user or not user.isAdmin:
                return jsonify({
                    'success': False,
                    'message': 'Unauthorized. Admin access required.'
                }), 403
            
            data = request.get_json()
            ip_to_unblock = data.get('ip_address')
            
            if not ip_to_unblock:
                return jsonify({
                    'success': False,
                    'message': 'IP address is required'
                }), 400
            
            # Remove the block
            block_key = f"ip_blocked:{ip_to_unblock}"
            result = redis_client.delete(block_key)
            
            if result > 0:
                # Log the action
                new_log = AuditLog(
                    employeeID=user.employeeID,
                    action=f"Admin {user.lName}, {user.fName} manually unblocked IP: {ip_to_unblock}"
                )
                db.session.add(new_log)
                db.session.commit()
                
                return jsonify({
                    'success': True,
                    'message': f'IP {ip_to_unblock} has been unblocked'
                }), 200
            else:
                return jsonify({
                    'success': False,
                    'message': 'IP was not blocked or already expired'
                }), 404
                
        except Exception as e:
            current_app.logger.error(f"Unblock IP error: {e}")
            return jsonify({
                'success': False,
                'message': 'Failed to unblock IP'
            }), 500

    @app.route('/api/upload/chunked', methods=['POST'])
    @jwt_required()
    def upload_chunked():
        empID = get_jwt_identity()
        from app.models import Employee
        user = Employee.query.filter_by(employeeID=empID).first()

        if 'file' not in request.files:
            return jsonify({'success': False, 'message': 'No file part in request'}), 400
        file = request.files['file']
        final_path = request.form.get('final_path')
        if not final_path:
            return jsonify({'success': False, 'message': 'Missing final_path'}), 400

        try:
            move_resp = upload_to_nextcloud_chunked(
                file,
                final_path,
                empID=empID,
                redis_client=redis_client
            )

            # Minimal metadata save to DB to enable links in accreditation view
            try:
                from app.models import Document, Criteria, Program
                file_name = request.form.get('fileName') or file.filename
                file_type = request.form.get('fileType') or 'application/pdf'
                criteria_id = request.form.get('criteriaID')

                # Fallback: extract criteriaID from final_path (…/<criteriaID>/<filename>)
                if not criteria_id:
                    try:
                        import re
                        m = re.search(r"/(\d+)/[^/]+$", final_path)
                        if m:
                            criteria_id = m.group(1)
                    except Exception:
                        pass

                # Normalize stored path identical to final_path
                doc_path = final_path

                # Always create a new Document record for chunked uploads
                doc = Document(
                    docName=file_name,
                    docType=file_type,
                    docPath=doc_path,
                    employeeID=empID
                )
                db.session.add(doc)
                db.session.flush()

                # Link to criteria if provided
                affected_program_code = None
                if criteria_id:
                    crit = Criteria.query.get(int(criteria_id))
                    if crit:
                        crit.docID = doc.docID
                        try:
                            # Join to get program code for cache invalidation
                            from app.models import Subarea, Area, Program
                            sub = Subarea.query.get(crit.subareaID)
                            if sub:
                                area = Area.query.get(sub.areaID)
                                if area and area.programID:
                                    prog = Program.query.get(area.programID)
                                    if prog:
                                        affected_program_code = prog.programCode
                        except Exception:
                            pass
                db.session.commit()

                # Invalidate accreditation cache for this program and preview cache for file
                try:
                    if affected_program_code:
                        redis_client.delete(f"accr:program:{affected_program_code}")
                    redis_client.delete(f"preview_cache:{doc.docPath}")
                except Exception:
                    pass
            except Exception as meta_err:
                current_app.logger.error(f"Post-upload metadata save failed: {meta_err}")

            return jsonify({
                'success': True,
                'message': 'Upload complete',
                'progress_key': f'upload_status:{empID}:{file.filename}',
                'result': move_resp.status_code
            }), 200
        except Exception as e:
            import traceback
            traceback.print_exc()
            current_app.logger.error(f"upload_chunked failed: {e}")
            return jsonify({'success': False, 'message': 'Upload failed', 'details': str(e)}), 500

    @app.route('/api/upload/progress', methods=['GET'])
    @jwt_required()
    def upload_progress():
        empID = get_jwt_identity()
        filename = request.args.get('filename')
        key = f'upload_status:{empID}:{filename}'
        prog = redis_client.get(key)
        if prog is None:
            return jsonify({'progress': None}), 200
        try:
            value = int(prog)
            return jsonify({'progress': value}), 200
        except Exception:
            return jsonify({'progress': prog.decode()}), 200

