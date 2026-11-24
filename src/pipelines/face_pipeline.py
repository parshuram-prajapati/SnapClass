

import gc
import logging
import dlib
import numpy as np
import face_recognition_models
from sklearn.svm import SVC
import streamlit as st

from src.database.db import get_all_students

logger = logging.getLogger(__name__)

# Configurable default face matching threshold (Euclidean distance on 128D embeddings)
DEFAULT_CONFIDENCE_THRESHOLD = 0.6


@st.cache_resource
def load_dlib_models():
    detector = dlib.get_frontal_face_detector() 

    sp = dlib.shape_predictor(
        face_recognition_models.pose_predictor_model_location()
    )

    facerec = dlib.face_recognition_model_v1(
        face_recognition_models.face_recognition_model_location()
    )

    return detector, sp, facerec


def get_face_embeddings(image_np: np.ndarray) -> list:
    """
    Extracts 128-dimensional face embeddings for all faces detected in the image.
    - Optimized for large group photographs and high resolutions.
    - Uses adaptive upsampling (avoids memory-exploding upsampling on high-res images).
    - Safely handles edge faces and bounding box errors without crashing.
    """
    if image_np is None or image_np.size == 0:
        return []

    detector, sp, facerec = load_dlib_models()

    h, w = image_np.shape[:2]
    max_dim = max(h, w)

    # Adaptive upsample:
    # On images with max dimension > 1200, upsampling causes massive RAM spikes (OOM/crash).
    # detector(..., 0) detects normal and group faces cleanly without RAM explosion.
    # On smaller images (<= 1024px), upsample=1 helps detect smaller faces safely.
    upsample = 1 if max_dim <= 1024 else 0

    try:
        faces = detector(image_np, upsample)
    except Exception as e:
        logger.warning(f"dlib face detection error with upsample={upsample}: {e}")
        try:
            # Fallback with no upsampling
            faces = detector(image_np, 0)
        except Exception:
            return []

    # If 0 faces found on moderate-size image (between 1024 and 1600), try upsampling once as fallback
    if len(faces) == 0 and 1024 < max_dim <= 1600:
        try:
            faces = detector(image_np, 1)
        except Exception:
            pass

    encodings = []

    for face in faces:
        try:
            shape = sp(image_np, face)
            # Compute 128D face descriptor (num_jitters=1 for performance and stability)
            face_descriptor = facerec.compute_face_descriptor(image_np, shape, 1)
            encodings.append(np.array(face_descriptor))
        except Exception as e:
            # Individual face failure (e.g. face near image boundary) should not crash the app
            logger.debug(f"Failed to extract face descriptor for a bounding box: {e}")
            continue

    return encodings


@st.cache_resource
def get_trained_model():
    X = []
    y = []

    try:
        student_db = get_all_students()
    except Exception as e:
        logger.error(f"Failed to fetch students for model training: {e}")
        student_db = None

    if not student_db:
        return None
    
    for student in student_db:
        embedding = student.get('face_embedding')
        if embedding:
            X.append(np.array(embedding))
            y.append(student.get('student_id'))

    if len(X) == 0:
        return None
    
    all_unique_students = list(set(y))
    clf = None

    # Train SVM classifier only if there are at least 2 distinct student classes
    if len(all_unique_students) >= 2:
        try:
            clf = SVC(kernel='linear', probability=True, class_weight='balanced')
            clf.fit(X, y)
        except Exception as e:
            logger.warning(f"SVM training skipped: {e}")
            clf = None

    return {'clf': clf, 'X': X, 'y': y}


def train_classifier():
    st.cache_resource.clear()
    model_data = get_trained_model()
    return bool(model_data)


def predict_attendance(
    class_image_np: np.ndarray,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD
):
    """
    Scans a classroom photo and predicts present students:
    - Extracts face encodings safely for all detected people.
    - Matches detected faces against enrolled student embeddings.
    - Strictly rejects unknown people (does NOT mark unknown people as students).
    - Preserves existing matching logic and IDs.
    Returns: (detected_student: dict, all_students: list, num_faces_detected: int)
    """
    encodings = get_face_embeddings(class_image_np)
    detected_student = {}

    if not encodings:
        return detected_student, [], 0

    model_data = get_trained_model()

    if not model_data:
        return detected_student, [], len(encodings)
    
    clf = model_data.get('clf')
    X_train = model_data.get('X', [])
    y_train = model_data.get('y', [])

    if not X_train or not y_train:
        return detected_student, [], len(encodings)

    all_students = sorted(list(set(y_train)))

    for encoding in encodings:
        # 1. Direct Euclidean distance verification against all registered embeddings
        best_id = None
        min_distance = float('inf')

        # Check candidate using SVM if available
        if clf is not None and len(all_students) >= 2:
            try:
                svm_pred_id = int(clf.predict([encoding])[0])
                # Check distance to that student's registered embeddings
                for emb, sid in zip(X_train, y_train):
                    if sid == svm_pred_id:
                        dist = float(np.linalg.norm(emb - encoding))
                        if dist < min_distance:
                            min_distance = dist
                            best_id = sid
            except Exception:
                pass

        # Also check all embeddings to ensure global minimum distance
        for emb, sid in zip(X_train, y_train):
            dist = float(np.linalg.norm(emb - encoding))
            if dist < min_distance:
                min_distance = dist
                best_id = sid

        # Strict thresholding: Only accept if resemblance is within confidence threshold
        # Rejects unknown faces so random people are never marked as registered students
        if best_id is not None and min_distance <= confidence_threshold:
            detected_student[int(best_id)] = True

    # Memory cleanup
    gc.collect()

    return detected_student, all_students, len(encodings)


