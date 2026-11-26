
import io
import logging

import librosa
import numpy as np
import streamlit as st

from resemblyzer import VoiceEncoder, preprocess_wav

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
MIN_SEGMENT_SECONDS = 1.0


@st.cache_resource
def load_voice_encoder():
    return VoiceEncoder()


def normalize_embedding(embedding):
    """Validate and L2-normalize a speaker embedding."""
    try:
        vector = np.asarray(embedding, dtype=np.float32).reshape(-1)

        if vector.size == 0 or not np.all(np.isfinite(vector)):
            return None

        norm = np.linalg.norm(vector)

        if norm < 1e-8:
            return None

        return vector / norm

    except (TypeError, ValueError):
        return None


def load_audio(audio_bytes):
    """Decode uploaded or recorded audio into mono 16 kHz audio."""
    if not audio_bytes:
        raise ValueError("No audio was provided.")

    audio, sr = librosa.load(
        io.BytesIO(audio_bytes),
        sr=SAMPLE_RATE,
        mono=True
    )

    if audio.size == 0:
        raise ValueError("Audio is empty.")

    if not np.all(np.isfinite(audio)):
        raise ValueError("Audio contains invalid values.")

    duration = len(audio) / SAMPLE_RATE

    if duration < MIN_SEGMENT_SECONDS:
        raise ValueError("Recording is too short.")

    return audio.astype(np.float32)


def get_voice_embedding(audio_bytes):
    try:
        encoder = load_voice_encoder()
        audio = load_audio(audio_bytes)

        wav = preprocess_wav(audio, source_sr=SAMPLE_RATE)

        if len(wav) < SAMPLE_RATE:
            return None

        embedding = encoder.embed_utterance(wav)

        normalized_embedding = normalize_embedding(embedding)
        return (
            normalized_embedding.tolist()
            if normalized_embedding is not None
            else None
        )

    except Exception:
        logger.exception("Voice embedding extraction failed.")
        return None


def prepare_candidates(candidates_dict):
    """Validate and normalize stored student embeddings."""
    candidates = {}

    for student_id, stored_embedding in candidates_dict.items():
        vector = normalize_embedding(stored_embedding)

        if vector is not None:
            candidates[student_id] = vector

    return candidates


def identify_speaker(
    new_embedding,
    candidates_dict,
    threshold=0.65
):
    if new_embedding is None or not candidates_dict:
        return None, 0.0

    query = normalize_embedding(new_embedding)

    if query is None:
        return None, 0.0

    best_sid = None
    best_score = -1.0

    for sid, stored_embedding in candidates_dict.items():

        candidate = normalize_embedding(stored_embedding)

        if candidate is None:
            continue

        if candidate.shape != query.shape:
            continue

        similarity = float(np.dot(query, candidate))

        if similarity > best_score:
            best_score = similarity
            best_sid = sid

    if best_sid is not None and best_score >= threshold:
        return best_sid, best_score

    return None, max(best_score, 0.0)


def process_bulk_audio(
    audio_bytes,
    candidates_dict,
    threshold=0.65
):
    try:
        encoder = load_voice_encoder()

        audio = load_audio(audio_bytes)

        candidates = prepare_candidates(candidates_dict)

        if not candidates:
            return {}

        # Split non-silent audio regions.
        # This does NOT perform speaker diarization.
        segments = librosa.effects.split(
            audio,
            top_db=30
        )

        identified_results = {}

        for start, end in segments:

            segment_audio = audio[start:end]

            duration = len(segment_audio) / SAMPLE_RATE

            if duration < MIN_SEGMENT_SECONDS:
                continue

            wav = preprocess_wav(
                segment_audio,
                source_sr=SAMPLE_RATE
            )

            if len(wav) < SAMPLE_RATE:
                continue

            embedding = normalize_embedding(
                encoder.embed_utterance(wav)
            )

            if embedding is None:
                continue

            sid, score = identify_speaker(
                embedding,
                candidates,
                threshold
            )

            if sid is not None:

                if (
                    sid not in identified_results
                    or score > identified_results[sid]
                ):
                    identified_results[sid] = score

        return identified_results

    except Exception:
        logger.exception("Bulk voice attendance processing failed.")
        return {}
