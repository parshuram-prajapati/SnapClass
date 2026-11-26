
import gc
import logging
import numpy as np
import streamlit as st

from src.pipelines.face_detector import detect_faces
from src.pipelines.face_embedder import get_face_embedding
from src.database.db import get_all_face_embeddings

logger = logging.getLogger(__name__)

# Initial testing threshold. Calibrate using your own face samples.
DEFAULT_CONFIDENCE_THRESHOLD = 0.45


@st.cache_resource
def get_face_database():
    """
    Load registered SFace embeddings from the database.
    Old Dlib embeddings are not used here.
    """
    try:
        records = get_all_face_embeddings()
    except Exception:
        logger.exception("Failed to load SFace database")
        return {"X": [], "y": []}

    embeddings = []
    student_ids = []

    for record in records or []:
        try:
            student_id = int(record["student_id"])

            embedding = np.asarray(
                record["embedding"],
                dtype=np.float32
            ).reshape(-1)

            if embedding.shape != (128,):
                logger.warning(
                    "Invalid embedding dimension for student %s",
                    student_id
                )
                continue

            norm = np.linalg.norm(embedding)

            if not np.isfinite(norm) or norm == 0:
                continue

            embeddings.append(embedding / norm)
            student_ids.append(student_id)

        except (KeyError, TypeError, ValueError):
            logger.warning("Skipping invalid SFace database record")

    logger.info(
        "Loaded %d SFace embeddings for %d students",
        len(embeddings),
        len(set(student_ids))
    )

    return {
        "X": embeddings,
        "y": student_ids
    }


def get_face_embeddings(image_np: np.ndarray) -> list:
    """
    Extract SFace embeddings for every face in an RGB image.

    Maintains compatibility with the existing student registration screen.
    Returns a list of normalized 128-dimensional embeddings.
    """
    if image_np is None or image_np.size == 0:
        return []

    try:
        faces = detect_faces(image_np)
    except Exception:
        logger.exception("YuNet detection failed during enrollment")
        return []

    embeddings = []

    for face in faces:
        try:
            embedding = get_face_embedding(image_np, face)

            embedding = np.asarray(
                embedding,
                dtype=np.float32
            ).reshape(-1)

            if embedding.shape != (128,):
                logger.warning("Invalid SFace embedding dimension")
                continue

            norm = np.linalg.norm(embedding)

            if not np.isfinite(norm) or norm == 0:
                continue

            embeddings.append(embedding / norm)

        except Exception:
            logger.exception(
                "Failed to extract an individual enrollment embedding"
            )

    return embeddings


def train_classifier():
    """
    Refresh the cached SFace database.

    Retains the old function name for compatibility.
    No SVM classifier is trained.
    """
    get_face_database.clear()

    database = get_face_database()

    return bool(database["X"])


def predict_attendance(
    class_image_np: np.ndarray,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD
):
    """
    Recognize multiple students in an RGB classroom image.

    Returns:
        detected_student: {student_id: True}
        all_students: list of registered student IDs
        num_faces_detected: number of detected faces
    """
    detected_student = {}

    if class_image_np is None or class_image_np.size == 0:
        return detected_student, [], 0

    try:
        faces = detect_faces(class_image_np)

    except Exception:
        logger.exception("YuNet face detection failed")
        return detected_student, [], 0

    num_faces = len(faces)

    if num_faces == 0:
        return detected_student, [], 0

    database = get_face_database()

    X_train = database["X"]
    y_train = database["y"]

    all_students = sorted(set(y_train))

    if not X_train:
        logger.warning("No registered SFace embeddings found")
        return detected_student, all_students, num_faces

    for face in faces:
        try:
            embedding = get_face_embedding(
                class_image_np,
                face
            )

            embedding = np.asarray(
                embedding,
                dtype=np.float32
            ).reshape(-1)

            if embedding.shape != (128,):
                continue

            norm = np.linalg.norm(embedding)

            if not np.isfinite(norm) or norm == 0:
                continue

            embedding = embedding / norm

            # Compare against every registered SFace embedding.
            similarities = np.asarray(
                [
                    np.dot(embedding, registered)
                    for registered in X_train
                ],
                dtype=np.float32
            )

            best_index = int(np.argmax(similarities))
            best_similarity = float(similarities[best_index])

            # Accept only matches above the configured threshold.
            if best_similarity >= confidence_threshold:
                student_id = int(y_train[best_index])

                # Prevent duplicate recognition in the same image.
                detected_student[student_id] = True

        except Exception:
            logger.exception(
                "Failed to recognize an individual classroom face"
            )
            continue

    gc.collect()

    return detected_student, all_students, num_faces
