
from pathlib import Path
import cv2
import numpy as np
import streamlit as st
import logging

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parents[2]
MODEL_PATH = ROOT_DIR / "models" / "sface.onnx"


@st.cache_resource
def load_face_recognizer():
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"SFace model not found: {MODEL_PATH}"
        )

    return cv2.FaceRecognizerSF.create(
        str(MODEL_PATH),
        ""
    )


def get_face_embedding(image_rgb, face):
    """
    Extract a normalized SFace embedding.

    image_rgb: Original RGB image.
    face: One YuNet detection row (15 values).
    """

    if image_rgb is None or image_rgb.size == 0:
        raise ValueError("Invalid input image.")

    recognizer = load_face_recognizer()

    image_bgr = cv2.cvtColor(
        image_rgb,
        cv2.COLOR_RGB2BGR
    )

    try:
        aligned_face = recognizer.alignCrop(
            image_bgr,
            face.astype(np.float32)
        )

        feature = recognizer.feature(aligned_face)

        embedding = np.asarray(
            feature,
            dtype=np.float32
        ).flatten()

        norm = np.linalg.norm(embedding)

        if norm == 0:
            raise ValueError("Invalid face embedding.")

        return embedding / norm

    except cv2.error as exc:
        logger.exception("SFace embedding extraction failed")
        raise RuntimeError(
            "Could not extract face embedding."
        ) from exc
