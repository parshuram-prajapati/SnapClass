from src.database.config import supabase
import bcrypt
import hashlib
import secrets
import re
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, Dict, Any

# In-memory fallback token store if Supabase table is not yet migrated
_MEMORY_RESET_TOKENS: Dict[str, Dict[str, Any]] = {}


def hash_pass(pwd: str) -> str:
    return bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode()

def check_pass(pwd: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pwd.encode(), hashed.encode())
    except Exception:
        return False

def hash_token(token: str) -> str:
    """Computes SHA-256 hash of a reset token for secure storage."""
    return hashlib.sha256(token.strip().encode('utf-8')).hexdigest()

def validate_password_strength(pwd: str) -> Tuple[bool, str]:
    """Validates password strength: minimum 8 chars, at least one letter and one number."""
    if not pwd or len(pwd) < 8:
        return False, "Password must be at least 8 characters long."
    if not re.search(r"[A-Za-z]", pwd):
        return False, "Password must contain at least one letter."
    if not re.search(r"\d", pwd):
        return False, "Password must contain at least one number."
    return True, ""


def check_teacher_exists(username: str) -> bool:
    # Check for unique username, returns false when username is already taken
    response = supabase.table("teachers").select("username").eq("username", username).execute()
    return len(response.data) > 0 


def find_teacher_by_email_or_username(identifier: str) -> Optional[Dict[str, Any]]:
    """Looks up teacher by email or username (case-insensitive and whitespace-tolerant)."""
    if not identifier:
        return None
    ident = identifier.strip()
    if not ident:
        return None

    # 1. Lookup by email if '@' is in identifier
    if "@" in ident:
        try:
            res = supabase.table("teachers").select("*").ilike("email", ident).execute()
            if res.data:
                return res.data[0]
        except Exception:
            pass

    # 2. Case-insensitive lookup by username
    try:
        res = supabase.table("teachers").select("*").ilike("username", ident).execute()
        if res.data:
            return res.data[0]
    except Exception:
        pass

    # 3. Fallback check across all teachers (handles trimmed/lower variations)
    try:
        res = supabase.table("teachers").select("*").execute()
        for t in res.data or []:
            if t.get("email") and t["email"].strip().lower() == ident.lower():
                return t
            if t.get("username") and t["username"].strip().lower() == ident.lower():
                return t
    except Exception:
        pass

    return None


def create_teacher(username: str, password: str, name: str, email: Optional[str] = None):
    data = { "username" : username.strip(), "password": hash_pass(password.strip()), "name": name.strip()}
    if email and email.strip():
        data["email"] = email.strip()

    try:
        response = supabase.table("teachers").insert(data).execute()
        return response.data
    except Exception as e:
        # If insertion failed because email column does not exist yet, retry without email
        if email and "email" in str(e).lower():
            del data["email"]
            response = supabase.table("teachers").insert(data).execute()
            return response.data
        raise e


def teacher_login(username_or_email, password):
    if not username_or_email or not password:
        return None
    teacher = find_teacher_by_email_or_username(username_or_email)
    if teacher:
        stored_hash = teacher.get('password', '')
        if check_pass(password, stored_hash) or check_pass(password.strip(), stored_hash):
            return teacher
    return None


# =============================================================================
# PASSWORD RESET FUNCTIONALITY (Custom Authentication)
# =============================================================================

def request_password_reset(identifier: str, expiry_minutes: int = 15, send_email: bool = True) -> Tuple[bool, str, Optional[str], Dict[str, Any]]:
    """
    Initiates a password reset for a teacher.
    - Generates a cryptographically secure single-use token.
    - Stores only the SHA-256 hash.
    - Never reveals whether an email is registered to prevent user enumeration.
    - Optionally sends an automated HTML reset email if SMTP is configured.
    Returns: (success: bool, user_message: str, raw_token_for_link: Optional[str], email_status: dict)
    """
    from src.services.email_service import send_password_reset_email, is_smtp_configured

    raw_token = secrets.token_urlsafe(32)
    token_hash_val = hash_token(raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=expiry_minutes)

    teacher = find_teacher_by_email_or_username(identifier)
    
    # Generic message to prevent email enumeration
    generic_msg = (
        "If the entered email/username is registered in our system, "
        "a password reset link has been generated."
    )

    email_status = {
        "sent": False,
        "message": "No account matched or email not provided.",
        "target_email": None
    }

    if not teacher:
        # Do not store anything, return generic message with None token
        return True, generic_msg, None, email_status

    teacher_id = teacher["teacher_id"]
    target_email = teacher.get("email") or (identifier.strip() if "@" in identifier else None)
    teacher_name = teacher.get("name", "Teacher")
    email_status["target_email"] = target_email

    # Try persisting token hash to Supabase
    saved_to_db = False
    try:
        supabase.table("password_resets").insert({
            "teacher_id": teacher_id,
            "token_hash": token_hash_val,
            "expires_at": expires_at.isoformat(),
            "used": False
        }).execute()
        saved_to_db = True
    except Exception:
        # Fallback to secure in-memory cache if table doesn't exist yet
        saved_to_db = False

    # Always keep in memory store as fallback / backup
    _MEMORY_RESET_TOKENS[token_hash_val] = {
        "teacher_id": teacher_id,
        "expires_at": expires_at,
        "used": False,
        "created_at": datetime.now(timezone.utc)
    }

    # Attempt to send email via SMTP if configured and target_email exists
    if send_email and target_email:
        if is_smtp_configured():
            sent, send_msg = send_password_reset_email(target_email, raw_token, recipient_name=teacher_name)
            email_status["sent"] = sent
            email_status["message"] = send_msg
        else:
            email_status["sent"] = False
            email_status["message"] = "SMTP credentials not yet configured in .streamlit/secrets.toml."
    elif not target_email:
        email_status["sent"] = False
        email_status["message"] = "No email address on file for this teacher profile."

    return True, generic_msg, raw_token, email_status



def verify_password_reset_token(raw_token: str) -> Tuple[bool, Optional[int], str]:
    """
    Verifies a reset token:
    - Checks that token exists and is valid.
    - Checks that token has not expired.
    - Checks that token has not already been used.
    Returns: (is_valid: bool, teacher_id: Optional[int], message: str)
    """
    if not raw_token or not raw_token.strip():
        return False, None, "Invalid reset token."

    token_hash_val = hash_token(raw_token.strip())
    now_utc = datetime.now(timezone.utc)

    # 1. Check Supabase password_resets table first
    try:
        res = supabase.table("password_resets").select("*").eq("token_hash", token_hash_val).execute()
        if res.data:
            entry = res.data[0]
            if entry.get("used"):
                return False, None, "This password reset link has already been used."

            expires_str = entry.get("expires_at", "")
            if expires_str:
                exp_dt = datetime.fromisoformat(expires_str.replace("Z", "+00:00"))
                if now_utc > exp_dt:
                    return False, None, "This password reset link has expired."

            return True, entry.get("teacher_id"), "Token is valid."
    except Exception:
        # PostgREST error or table not yet migrated, fall back to memory
        pass

    # 2. Check in-memory token storage
    if token_hash_val in _MEMORY_RESET_TOKENS:
        entry = _MEMORY_RESET_TOKENS[token_hash_val]
        if entry["used"]:
            return False, None, "This password reset link has already been used."
        if now_utc > entry["expires_at"]:
            return False, None, "This password reset link has expired."
        return True, entry["teacher_id"], "Token is valid."

    return False, None, "Invalid or unrecognized reset token."


def reset_teacher_password(raw_token: str, new_password: str) -> Tuple[bool, str]:
    """
    Resets the teacher's password using a valid single-use token:
    - Validates token validity and single-use status.
    - Validates password strength.
    - Hashes password using bcrypt.
    - Updates teacher's password in database.
    - Marks token as used (invalidated).
    """
    is_valid, teacher_id, msg = verify_password_reset_token(raw_token)
    if not is_valid or not teacher_id:
        return False, msg

    strong, reason = validate_password_strength(new_password)
    if not strong:
        return False, reason

    token_hash_val = hash_token(raw_token.strip())
    hashed_pwd = hash_pass(new_password)

    # Update teacher password in Supabase
    try:
        supabase.table("teachers").update({"password": hashed_pwd}).eq("teacher_id", teacher_id).execute()
    except Exception as e:
        return False, f"Failed to update password: {str(e)}"

    # Invalidate token in Supabase
    try:
        supabase.table("password_resets").update({"used": True}).eq("token_hash", token_hash_val).execute()
    except Exception:
        pass

    # Invalidate token in memory
    if token_hash_val in _MEMORY_RESET_TOKENS:
        _MEMORY_RESET_TOKENS[token_hash_val]["used"] = True

    return True, "Your password has been successfully updated! You can now log in."



def get_all_students():
    response = supabase.table('students').select("*").execute()
    return response.data

def create_student(new_name, face_embedding=None, voice_embedding=None):
    data = {'name': new_name, 'face_embedding':face_embedding, "voice_embedding": voice_embedding}
    response = supabase.table('students').insert(data).execute()
    return response.data


def create_subject(subject_code, name, section, teacher_id):
    data = {"subject_code": subject_code, "name": name, "section": section, "teacher_id": teacher_id}
    response = supabase.table("subjects").insert(data).execute()
    return response.data

def get_teacher_subjects(teacher_id):
    response = supabase.table('subjects').select("*, subject_students(count), attendance_logs(timestamp)").eq("teacher_id", teacher_id).execute()
    subjects = response.data


    for sub in subjects:
        sub['total_students'] = sub.get("subject_students", [{}])[0].get('count', 0) if sub.get('subject_students') else 0
        attendance = sub.get('attendance_logs', [])
        unique_sessions = len(set(log['timestamp'] for log in attendance))
        sub['total_classes'] = unique_sessions


        sub.pop('subject_student', None)
        sub.pop('attendance_logs', None)

    return subjects


def  enroll_student_to_subject(student_id, subject_id):
    data = {'student_id': student_id, "subject_id": subject_id}
    response= supabase.table('subject_students').insert(data).execute()
    return response.data


def  unenroll_student_to_subject(student_id, subject_id):
    response= supabase.table('subject_students').delete().eq('student_id', student_id).eq('subject_id', subject_id).execute()
    return response.data



def get_student_subjects(student_id):
    response = supabase.table('subject_students').select('*, subjects(*)').eq('student_id', student_id).execute()
    return response.data


def get_student_attendance(student_id):
    response = supabase.table('attendance_logs').select('*, subjects(*)').eq('student_id', student_id).execute()
    return response.data


def create_attendance(logs):
    response = supabase.table('attendance_logs').insert(logs).execute()
    return response.data

def get_attendance_for_teacher(teacher_id):
    response = supabase.table('attendance_logs').select("*, subjects!inner(*), students(*)").eq('subjects.teacher_id', teacher_id).execute()
    return response.data

