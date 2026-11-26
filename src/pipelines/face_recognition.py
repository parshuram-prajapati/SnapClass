
import logging
import numpy as np

from src.database.db import (
    get_all_students,
    get_all_face_embeddings
)

logger = logging.getLogger(__name__)

# Initial threshold for testing only.
# We will calibrate this using genuine test images.
DEFAULT_THRESHOLD = 0.40


def normalize_embedding(embedding):
    """Validate and normalize an SFace embedding."""

    vector = np.asarray(embedding, dtype=np.float32).reshape(-1)

    if vector.shape[0] != 128:
        raise ValueError("Expected a 128-dimensional SFace embedding.")

    if not np.all(np.isfinite(vector)):
        raise ValueError("Embedding contains invalid values.")

    norm = np.linalg.norm(vector)

    if norm == 0:
        raise ValueError("Embedding norm cannot be zero.")

    return vector / norm


def load_face_database():
    """Load registered students and their SFace embeddings."""

    students = get_all_students()
    stored_embeddings = get_all_face_embeddings()

    student_names = {
        int(student["student_id"]): student["name"]
        for student in students
    }

    database = {}

    for row in stored_embeddings:
        student_id = int(row["student_id"])

        if student_id not in student_names:
            logger.warning(
                "Ignoring embeddings for missing student ID %s",
                student_id
            )
            continue

        try:
            embedding = normalize_embedding(row["embedding"])
        except (ValueError, TypeError):
            logger.warning("Invalid embedding for student %s", student_id)
            continue

        database.setdefault(student_id, []).append(embedding)

    return database, student_names


def recognize_face(
    query_embedding,
    threshold=DEFAULT_THRESHOLD
):
    """
    Recognize a face using cosine similarity.

    Returns:
        {
            "student_id": int or None,
            "name": str,
            "similarity": float,
            "status": "recognized" or "unknown"
        }
    """

    query = normalize_embedding(query_embedding)

    database, student_names = load_face_database()

    if not database:
        return {
            "student_id": None,
            "name": "Unknown",
            "similarity": 0.0,
            "status": "unknown"
        }

    best_student_id = None
    best_similarity = -1.0

    for student_id, embeddings in database.items():

        similarities = [
            float(np.dot(query, stored))
            for stored in embeddings
        ]

        # Average the two highest similarities when available.
        similarities.sort(reverse=True)
        top_scores = similarities[:2]

        student_score = float(np.mean(top_scores))

        if student_score > best_similarity:
            best_similarity = student_score
            best_student_id = student_id

    if best_similarity < threshold:
        return {
            "student_id": None,
            "name": "Unknown",
            "similarity": best_similarity,
            "status": "unknown"
        }

    return {
        "student_id": best_student_id,
        "name": student_names[best_student_id],
        "similarity": best_similarity,
        "status": "recognized"
    }
