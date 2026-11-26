
import logging
import numpy as np

from src.pipelines.face_detector import detect_faces
from src.pipelines.face_embedder import get_face_embedding

from src.pipelines.face_recognition import (
    normalize_embedding,
    load_face_database,
    DEFAULT_THRESHOLD
)

logger = logging.getLogger(__name__)


def match_embedding(
    query_embedding,
    database,
    student_names,
    threshold=DEFAULT_THRESHOLD
):
    """Match one face against the already-loaded database."""

    query = normalize_embedding(query_embedding)

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
        scores = [
            float(np.dot(query, stored))
            for stored in embeddings
        ]

        scores.sort(reverse=True)
        student_score = float(np.mean(scores[:2]))

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


def recognize_multiple_faces(
    image_rgb,
    threshold=DEFAULT_THRESHOLD
):
    """
    Detect and recognize every face in an RGB image.

    Returns a list containing each face's bounding box
    and recognition result.
    """

    if image_rgb is None or image_rgb.size == 0:
        raise ValueError("Invalid input image.")

    faces = detect_faces(image_rgb)

    # Load database once, not once per detected face.
    database, student_names = load_face_database()

    results = []

    for index, face in enumerate(faces):

        try:
            embedding = get_face_embedding(image_rgb, face)

            recognition = match_embedding(
                embedding,
                database,
                student_names,
                threshold
            )

            # YuNet format: x, y, width, height, landmarks..., score
            x, y, width, height = [
                int(round(value)) for value in face[:4]
            ]

            results.append({
                "face_number": index + 1,
                "bbox": {
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height
                },
                **recognition
            })

        except Exception:
            logger.exception(
                "Recognition failed for face number %s",
                index + 1
            )

            results.append({
                "face_number": index + 1,
                "bbox": {
                    "x": int(round(face[0])),
                    "y": int(round(face[1])),
                    "width": int(round(face[2])),
                    "height": int(round(face[3]))
                },
                "student_id": None,
                "name": "Processing Error",
                "similarity": 0.0,
                "status": "error"
            })

    return results



def get_unique_recognized_students(results):
    """
    Keep only the strongest match for each student.
    Keep unknown faces separately.
    """

    best_matches = {}
    unknown_faces = []

    for result in results:

        if result.get("status") == "recognized":
            student_id = result.get("student_id")

            if student_id is None:
                unknown_faces.append(result)
                continue

            current = best_matches.get(student_id)

            if (
                current is None
                or result["similarity"] > current["similarity"]
            ):
                best_matches[student_id] = result

        else:
            unknown_faces.append(result)

    return {
        "recognized_students": list(best_matches.values()),
        "unknown_faces": unknown_faces
    }
