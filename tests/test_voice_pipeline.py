import json
import unittest
from unittest.mock import patch

import numpy as np

from src.pipelines import voice_pipeline


class FakeVoiceEncoder:
    def embed_utterance(self, _audio):
        return np.array([3.0, 4.0], dtype=np.float32)


class VoicePipelineTests(unittest.TestCase):
    def test_voice_enrollment_returns_normalized_json_compatible_embedding(self):
        audio = np.ones(voice_pipeline.SAMPLE_RATE, dtype=np.float32)

        with (
            patch.object(
                voice_pipeline,
                "load_voice_encoder",
                return_value=FakeVoiceEncoder()
            ),
            patch.object(voice_pipeline, "load_audio", return_value=audio),
            patch.object(
                voice_pipeline,
                "preprocess_wav",
                side_effect=lambda samples, source_sr: samples
            )
        ):
            embedding = voice_pipeline.get_voice_embedding(b"audio")

        self.assertIsInstance(embedding, list)
        self.assertEqual(len(embedding), 2)
        np.testing.assert_allclose(embedding, [0.6, 0.8])
        self.assertIsInstance(json.dumps(embedding), str)


if __name__ == "__main__":
    unittest.main()
