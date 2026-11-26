import re


DEFAULT_USN_PATTERN = r"^[0-9][A-Z]{2}[0-9]{2}[A-Z]{2}[0-9]{3}$"
USN_UNIQUE_INDEX = "students_usn_normalized_unique_idx"


def normalize_usn(usn, pattern=DEFAULT_USN_PATTERN):
    if not isinstance(usn, str) or not usn.strip():
        raise ValueError("USN is required.")

    normalized = usn.strip().upper()

    try:
        matches_pattern = re.fullmatch(pattern, normalized) is not None
    except re.error as exc:
        raise RuntimeError("The configured USN pattern is invalid.") from exc

    if not matches_pattern:
        raise ValueError("Invalid USN format. Check the example shown.")

    return normalized


def student_usn_exists(client, usn, pattern=DEFAULT_USN_PATTERN):
    normalized = normalize_usn(usn, pattern)
    response = (
        client.table("students")
        .select("student_id")
        .eq("usn", normalized)
        .limit(1)
        .execute()
    )
    return bool(response.data)


def _is_usn_unique_violation(error):
    constraint = str(getattr(error, "constraint", "")).lower()
    details = str(getattr(error, "details", "")).lower()
    message = str(error).lower()
    diagnostic = " ".join((constraint, details, message))

    return (
        "23505" in str(getattr(error, "code", ""))
        and (
            USN_UNIQUE_INDEX in diagnostic
            or "usn" in diagnostic
        )
    )


def create_student_record(
    client,
    new_name,
    usn,
    voice_embedding=None,
    usn_pattern=DEFAULT_USN_PATTERN
):
    if not isinstance(new_name, str) or not new_name.strip():
        raise ValueError("Student name is required.")

    normalized_usn = normalize_usn(usn, usn_pattern)

    if student_usn_exists(client, normalized_usn, usn_pattern):
        raise ValueError("This USN is already registered.")

    data = {
        "name": new_name.strip(),
        "usn": normalized_usn,
        "voice_embedding": voice_embedding
    }

    try:
        response = client.table("students").insert(data).execute()
    except Exception as exc:
        if _is_usn_unique_violation(exc):
            raise ValueError("This USN is already registered.") from exc
        raise

    return response.data
