import logging
import hmac
import hashlib
import secrets
import re
import math
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, Dict, Any

from src.database.config import get_secret, supabase_admin
from src.services.student_registration import (
    DEFAULT_USN_PATTERN,
    create_student_record,
    normalize_usn,
    student_usn_exists as check_student_usn_exists
)
import bcrypt

logger = logging.getLogger(__name__)
USN_PATTERN = get_secret("USN_PATTERN", DEFAULT_USN_PATTERN)


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


def _get_teacher_admin_client():
    """Return the trusted server-side Supabase client for teacher auth operations."""
    if supabase_admin is None:
        raise RuntimeError(
            "Supabase admin client is not configured. Check the server-side service-role secret."
        )
    return supabase_admin


def check_teacher_exists(username: str) -> bool:
    """Check for an existing username using the server-side client (RLS-safe)."""
    if not username or not username.strip():
        return False

    response = (
        _get_teacher_admin_client()
        .table("teachers")
        .select("teacher_id")
        .ilike("username", username.strip())
        .limit(1)
        .execute()
    )
    return bool(response.data)


def find_teacher_by_email_or_username(identifier: str) -> Optional[Dict[str, Any]]:
    """Find a teacher by email or username using the trusted server-side client."""
    if not identifier or not identifier.strip():
        return None

    ident = identifier.strip()
    client = _get_teacher_admin_client()

    # Search email first when the identifier looks like an email address.
    if "@" in ident:
        response = (
            client.table("teachers")
            .select("*")
            .ilike("email", ident)
            .limit(1)
            .execute()
        )
        if response.data:
            return response.data[0]

    # Otherwise, or if no email matched, search by username.
    response = (
        client.table("teachers")
        .select("*")
        .ilike("username", ident)
        .limit(1)
        .execute()
    )
    if response.data:
        return response.data[0]

    return None


def create_teacher(
    username: str,
    password: str,
    name: str,
    email: Optional[str] = None
):
    """Create a teacher account using the trusted server-side client."""
    if not username or not username.strip():
        raise ValueError("Username is required.")
    if not password or not password.strip():
        raise ValueError("Password is required.")
    if not name or not name.strip():
        raise ValueError("Teacher name is required.")

    data = {
        "username": username.strip(),
        "password": hash_pass(password.strip()),
        "name": name.strip(),
    }
    if email and email.strip():
        data["email"] = email.strip()

    client = _get_teacher_admin_client()
    try:
        response = client.table("teachers").insert(data).execute()
        return response.data
    except Exception as exc:
        # Keep compatibility with deployments where the optional email column
        # has not yet been added. Do not hide unrelated database errors.
        if "email" in data and "email" in str(exc).lower():
            data_without_email = {key: value for key, value in data.items() if key != "email"}
            response = client.table("teachers").insert(data_without_email).execute()
            return response.data
        raise


def teacher_login(username_or_email: str, password: str) -> Optional[Dict[str, Any]]:
    """Authenticate a teacher and return profile data without the password hash."""
    if not username_or_email or not username_or_email.strip() or not password:
        return None

    try:
        teacher = find_teacher_by_email_or_username(username_or_email)
        if not teacher:
            logger.warning("Teacher login failed: account not found.")
            return None

        stored_hash = teacher.get("password") or ""
        # Registration stores password.strip(), so verify using the same rule.
        candidate = password.strip()
        legacy_password_match = (
            bool(stored_hash)
            and not stored_hash.startswith("$2")
            and hmac.compare_digest(
                candidate.encode("utf-8"),
                stored_hash.encode("utf-8")
            )
        )
        if not check_pass(candidate, stored_hash) and not legacy_password_match:
            logger.warning("Teacher login failed: password verification failed.")
            return None

        if legacy_password_match:
            # Migrate legacy manually-created plaintext credentials on successful login.
            response = (
                _get_teacher_admin_client()
                .table("teachers")
                .update({"password": hash_pass(candidate)})
                .eq("teacher_id", teacher["teacher_id"])
                .select("teacher_id")
                .execute()
            )
            if not response.data:
                logger.error("Legacy teacher password upgrade did not update an account.")
                return None

        # Never put the password hash into Streamlit session state.
        return {key: value for key, value in teacher.items() if key != "password"}

    except Exception:
        logger.exception("Teacher authentication database operation failed.")
        return None


# =============================================================================
# PASSWORD RESET FUNCTIONALITY (Custom Authentication)
# =============================================================================

def _get_password_reset_client():
    if supabase_admin is None:
        raise RuntimeError("Server-side Supabase service role is not configured.")
    return supabase_admin


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

    # Generic message to prevent email enumeration
    generic_msg = (
        "If the entered email/username is registered in our system, "
        "a password reset link has been generated."
    )
    email_status = {
        "sent": False,
        "message": "Password reset could not be completed.",
        "target_email": None
    }

    try:
        reset_client = _get_password_reset_client()
    except RuntimeError as exc:
        logger.error("Password reset unavailable (%s)", type(exc).__name__)
        return False, "Password reset is temporarily unavailable.", None, email_status

    raw_token = secrets.token_urlsafe(32)
    token_hash_val = hash_token(raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=expiry_minutes)

    teacher = find_teacher_by_email_or_username(identifier)

    if not teacher:
        return True, generic_msg, None, email_status

    teacher_id = teacher["teacher_id"]
    target_email = teacher.get("email") or (identifier.strip() if "@" in identifier else None)
    teacher_name = teacher.get("name", "Teacher")
    email_status["target_email"] = target_email

    try:
        reset_client.table("password_resets").insert({
            "teacher_id": teacher_id,
            "token_hash": token_hash_val,
            "expires_at": expires_at.isoformat(),
            "used": False
        }).execute()
    except Exception as exc:
        database_code = getattr(exc, "code", None)
        if not isinstance(database_code, str) or not re.fullmatch(
            r"[A-Za-z0-9_-]{1,32}",
            database_code
        ):
            database_code = "unavailable"
        logger.error(
            "Could not save password reset token "
            "(exception=%s, database_code=%s)",
            type(exc).__name__,
            database_code
        )
        return False, "Password reset is temporarily unavailable.", None, email_status

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

    try:
        reset_client = _get_password_reset_client()
        response = (
            reset_client.table("password_resets")
            .select("teacher_id, token_hash, expires_at, used")
            .eq("token_hash", token_hash_val)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        logger.error("Could not verify password reset token (%s)", type(exc).__name__)
        return False, None, "Password reset verification is temporarily unavailable."

    if response.data:
        entry = response.data[0]
        if entry.get("used"):
            return False, None, "This password reset link has already been used."

        expires_str = entry.get("expires_at", "")
        if expires_str:
            exp_dt = datetime.fromisoformat(expires_str.replace("Z", "+00:00"))
            if now_utc > exp_dt:
                return False, None, "This password reset link has expired."

        return True, entry.get("teacher_id"), "Token is valid."

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

    try:
        reset_client = _get_password_reset_client()
        response = reset_client.rpc(
            "redeem_teacher_password_reset",
            {
                "p_token_hash": token_hash_val,
                "p_password_hash": hashed_pwd
            }
        ).execute()
    except Exception as exc:
        logger.error("Could not complete password reset (%s)", type(exc).__name__)
        return False, "Password reset could not be completed. Please try again."

    redeemed = response.data
    if isinstance(redeemed, list) and len(redeemed) == 1:
        redeemed = redeemed[0]
    if redeemed is not True:
        return False, "This password reset link is invalid, expired, or already used."

    return True, "Your password has been successfully updated! You can now log in."



def get_all_students():
    response = (
        _get_teacher_admin_client()
        .table("students")
        .select("student_id, name, usn")
        .execute()
    )
    return response.data or []


def normalize_student_usn(usn):
    return normalize_usn(usn, USN_PATTERN)


def student_usn_exists(usn):
    return check_student_usn_exists(
        _get_teacher_admin_client(),
        usn,
        USN_PATTERN
    )


def create_student(new_name, usn, voice_embedding=None):
    return create_student_record(
        _get_teacher_admin_client(),
        new_name,
        usn,
        voice_embedding=voice_embedding,
        usn_pattern=USN_PATTERN
    )


def create_subject(subject_code, name, section, teacher_id):
    values = (subject_code, name, section)
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError("Subject code, name, and section are required.")

    client = _get_teacher_admin_client()
    teacher = (
        client.table("teachers")
        .select("teacher_id")
        .eq("teacher_id", teacher_id)
        .limit(1)
        .execute()
    )
    if not teacher.data:
        raise ValueError("Teacher account was not found.")

    data = {
        "subject_code": subject_code.strip(),
        "name": name.strip(),
        "section": section.strip(),
        "teacher_id": teacher_id
    }
    response = client.table("subjects").insert(data).execute()
    return response.data


def get_teacher_subjects(teacher_id):
    if supabase_admin is None:
        raise RuntimeError("Supabase admin client is not configured.")

    response = (
        supabase_admin.table("subjects")
        .select("*, subject_students(count), attendance_logs(timestamp)")
        .eq("teacher_id", teacher_id)
        .execute()
    )

    subjects = response.data or []

    for sub in subjects:
        sub["total_students"] = (
            sub.get("subject_students", [{}])[0].get("count", 0)
            if sub.get("subject_students")
            else 0
        )

        attendance = sub.get("attendance_logs", [])
        unique_sessions = len(
            set(log["timestamp"] for log in attendance)
        )

        sub["total_classes"] = unique_sessions

        sub.pop("subject_students", None)
        sub.pop("attendance_logs", None)

    return subjects


def get_enrolled_students_for_teacher(teacher_id, subject_id):
    client = _get_teacher_admin_client()

    owned_subject = (
        client.table("subjects")
        .select("subject_id")
        .eq("subject_id", subject_id)
        .eq("teacher_id", teacher_id)
        .limit(1)
        .execute()
    )
    if not owned_subject.data:
        raise PermissionError("Teacher is not authorized to access this subject.")

    response = (
        client.table("subject_students")
        .select("student_id, students!inner(*)")
        .eq("subject_id", subject_id)
        .execute()
    )
    return response.data or []


def get_subject_by_code(subject_code):
    if not subject_code or not subject_code.strip():
        return None

    response = (
        _get_teacher_admin_client()
        .table("subjects")
        .select("subject_id, name, subject_code")
        .eq("subject_code", subject_code.strip())
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


def student_is_enrolled(student_id, subject_id):
    response = (
        _get_teacher_admin_client()
        .table("subject_students")
        .select("student_id")
        .eq("student_id", student_id)
        .eq("subject_id", subject_id)
        .limit(1)
        .execute()
    )
    return bool(response.data)


def enroll_student_to_subject(student_id, subject_id):
    client = _get_teacher_admin_client()

    student = (
        client.table("students")
        .select("student_id")
        .eq("student_id", student_id)
        .limit(1)
        .execute()
    )
    if not student.data:
        raise ValueError("Student account was not found.")

    subject = (
        client.table("subjects")
        .select("subject_id")
        .eq("subject_id", subject_id)
        .limit(1)
        .execute()
    )
    if not subject.data:
        raise ValueError("Subject was not found.")

    enrollment = (
        client.table("subject_students")
        .select("student_id")
        .eq("student_id", student_id)
        .eq("subject_id", subject_id)
        .limit(1)
        .execute()
    )
    if enrollment.data:
        return False

    data = {"student_id": student_id, "subject_id": subject_id}
    client.table("subject_students").insert(data).execute()
    return True


def unenroll_student_to_subject(student_id, subject_id):
    response = (
        _get_teacher_admin_client()
        .table("subject_students")
        .delete()
        .eq("student_id", student_id)
        .eq("subject_id", subject_id)
        .execute()
    )
    return response.data



def get_student_subjects(student_id):
    response = (
        _get_teacher_admin_client()
        .table("subject_students")
        .select("*, subjects(*)")
        .eq("student_id", student_id)
        .execute()
    )
    return response.data or []


def get_student_attendance(student_id):
    response = (
        _get_teacher_admin_client()
        .table("attendance_logs")
        .select("*, subjects(*)")
        .eq("student_id", student_id)
        .execute()
    )
    return response.data or []


def create_attendance(logs, teacher_id):
    if not logs:
        raise ValueError("Attendance records are required.")

    subject_ids = {log.get("subject_id") for log in logs}
    if len(subject_ids) != 1 or None in subject_ids:
        raise ValueError("Attendance records must belong to one subject.")

    student_ids = {log.get("student_id") for log in logs}
    if None in student_ids:
        raise ValueError("Every attendance record must include a student.")

    subject_id = next(iter(subject_ids))
    client = _get_teacher_admin_client()

    owned_subject = (
        client.table("subjects")
        .select("subject_id")
        .eq("subject_id", subject_id)
        .eq("teacher_id", teacher_id)
        .limit(1)
        .execute()
    )
    if not owned_subject.data:
        raise PermissionError("Teacher is not authorized to save attendance for this subject.")

    enrolled = (
        client.table("subject_students")
        .select("student_id")
        .eq("subject_id", subject_id)
        .in_("student_id", list(student_ids))
        .execute()
    )
    enrolled_ids = {row["student_id"] for row in enrolled.data or []}
    if enrolled_ids != student_ids:
        raise ValueError("Attendance includes students not enrolled in this subject.")

    try:
        response = (
            client.table("attendance_logs")
            .insert(logs)
            .execute()
        )
    except Exception as exc:
        database_code = getattr(exc, "code", None)
        if not isinstance(database_code, str) or not re.fullmatch(
            r"[A-Za-z0-9_-]{1,32}",
            database_code
        ):
            database_code = "unavailable"
        logger.error(
            "Could not save attendance "
            "(exception=%s, database_code=%s)",
            type(exc).__name__,
            database_code
        )
        raise

    return response.data


def get_attendance_for_teacher(teacher_id):
    if supabase_admin is None:
        raise RuntimeError("Supabase admin client is not configured.")

    response = (
        supabase_admin.table("attendance_logs")
        .select("*, subjects!inner(*), students(*)")
        .eq("subjects.teacher_id", teacher_id)
        .execute()
    )

    return response.data or []



# =============================================================================
# SFace FACE EMBEDDING DATABASE FUNCTIONS
# =============================================================================
def get_biometric_client():
    if supabase_admin is None:
        raise RuntimeError(
            "SUPABASE_SERVICE_ROLE_KEY is not configured. "
            "Biometric database operations require a trusted "
            "server-side Supabase client."
        )

    return supabase_admin

def _validate_face_embedding(embedding):
    """
    Validate and convert an SFace embedding into a JSON-compatible list.
    SFace embeddings must contain exactly 128 finite values.
    """

    if hasattr(embedding, "tolist"):
        embedding = embedding.tolist()

    if not isinstance(embedding, (list, tuple)):
        raise ValueError("Embedding must be a list or array.")

    if len(embedding) != 128:
        raise ValueError(
            f"Expected 128 embedding values, received {len(embedding)}."
        )

    try:
        values = [float(value) for value in embedding]
    except (TypeError, ValueError):
        raise ValueError("Embedding contains invalid values.")

    if not all(math.isfinite(value) for value in values):
        raise ValueError("Embedding contains non-finite values.")

    return values


def save_face_embedding(student_id, embedding):
    """
    Save one SFace embedding in the separate student_face_embeddings table.
    """

    embedding_values = _validate_face_embedding(embedding)

    data = {
        "student_id": int(student_id),
        "embedding": embedding_values
    }

    response = (
        get_biometric_client().table("student_face_embeddings")
        .insert(data)
        .execute()
    )

    return response.data



def save_face_embeddings(student_id, embeddings):
    if not embeddings:
        raise ValueError("No face embeddings provided.")

    data = [
        {
            "student_id": int(student_id),
            "embedding": _validate_face_embedding(embedding)
        }
        for embedding in embeddings
    ]

    response = (
        get_biometric_client()
        .table("student_face_embeddings")
        .insert(data)
        .execute()
    )

    return response.data


def get_student_face_embeddings(student_id):
    response = (
        get_biometric_client()
        .table("student_face_embeddings")
        .select("id, student_id, embedding, created_at")
        .eq("student_id", int(student_id))
        .execute()
    )

    return response.data or []


def get_all_face_embeddings():
    all_embeddings = []
    page_size = 1000
    start = 0

    while True:
        response = (
            get_biometric_client()
            .table("student_face_embeddings")
            .select("id, student_id, embedding, created_at")
            .order("id")
            .range(start, start + page_size - 1)
            .execute()
        )

        rows = response.data or []
        all_embeddings.extend(rows)

        if len(rows) < page_size:
            break

        start += page_size

    return all_embeddings


def get_student_face_embeddings(student_id):
    """
    Retrieve all SFace embeddings belonging to one student.
    """

    response = (
       get_biometric_client().table("student_face_embeddings")
        .select("id, student_id, embedding, created_at")
        .eq("student_id", int(student_id))
        .execute()
    )

    return response.data or []


def get_all_face_embeddings():
    """
    Retrieve all SFace embeddings for classifier training.
    Uses pagination to avoid the default 1000-row response limit.
    """

    all_embeddings = []
    page_size = 1000
    start = 0

    while True:
        response = (
            get_biometric_client().table("student_face_embeddings")
            .select("id, student_id, embedding, created_at")
            .order("id")
            .range(start, start + page_size - 1)
            .execute()
        )

        rows = response.data or []
        all_embeddings.extend(rows)

        if len(rows) < page_size:
            break

        start += page_size

    return all_embeddings
