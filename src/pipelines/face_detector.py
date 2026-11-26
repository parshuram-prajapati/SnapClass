
from pathlib import Path
import cv2
import numpy as np
import streamlit as st
import logging

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parents[2]
MODEL_PATH = ROOT_DIR / "models" / "yunet.onnx"

@st.cache_resource
def load_face_detector():
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"YuNet model not found: {MODEL_PATH}"
        )

    return cv2.FaceDetectorYN.create(
        str(MODEL_PATH),
        "",
        (320, 320),
        0.8,
        0.3,
        5000,
        cv2.dnn.DNN_BACKEND_OPENCV,
        cv2.dnn.DNN_TARGET_CPU
    )


def detect_faces(image: np.ndarray):
    if image is None or image.size == 0:
        return []

    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("Expected an RGB image.")

    h, w = image.shape[:2]
    detector = load_face_detector()

    detector.setInputSize((w, h))

    # OpenCV YuNet expects BGR input.
    bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

    try:
        _, faces = detector.detect(bgr)
    except cv2.error as exc:
        logger.exception("YuNet detection failed")
        raise RuntimeError("Face detection failed.") from exc

    if faces is None:
        return []

    return faces
