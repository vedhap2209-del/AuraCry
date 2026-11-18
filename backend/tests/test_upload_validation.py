"""Phase 9: server-side upload validation. A file is not trusted because it ends in .wav.
Run from backend/:  python -m unittest tests.test_upload_validation -v"""
import os
import tempfile
import unittest

import numpy as np
import soundfile as sf

from ml import upload_validation as V
from ml.audio_io import AudioError


class Validate(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def write(self, name, data):
        p = os.path.join(self.d, name)
        open(p, "wb").write(data)
        return p

    def wav(self, name, y, sr=16000):
        p = os.path.join(self.d, name); sf.write(p, y.astype("float32"), sr); return p

    def test_disguised_non_audio_is_rejected(self):
        cases = {"img.wav": b"\xff\xd8\xff\xe0" + b"0" * 2000, "doc.wav": b"%PDF-1.4\n" + b"0" * 2000,
                 "zip.wav": b"PK\x03\x04" + b"0" * 2000, "png.wav": b"\x89PNG\r\n" + b"0" * 2000}
        for name, data in cases.items():
            p = self.write(name, data)
            with self.assertRaises(AudioError) as cm:
                V.validate_file(p, os.path.getsize(p), 15)
            self.assertEqual(cm.exception.code, "not_audio", name)

    def test_empty_and_oversize(self):
        p = self.write("e.wav", b"")
        with self.assertRaises(AudioError) as cm:
            V.validate_file(p, 0, 15)
        self.assertEqual(cm.exception.code, "empty_file")
        big = self.wav("big.wav", np.zeros(16000 * 3))
        with self.assertRaises(AudioError) as cm:
            V.validate_file(big, 20 * 1024 * 1024, 15)
        self.assertEqual(cm.exception.code, "too_large")

    def test_random_bytes_rejected(self):
        p = self.write("r.wav", os.urandom(4000))
        with self.assertRaises(AudioError):
            V.validate_file(p, 4000, 15)

    def test_too_short(self):
        p = self.wav("s.wav", np.random.randn(8000) * 0.1)   # 0.5 s
        with self.assertRaises(AudioError) as cm:
            V.validate_file(p, os.path.getsize(p), 15)
        self.assertEqual(cm.exception.code, "too_short")

    def test_real_wav_accepted(self):
        t = np.linspace(0, 2, 32000, endpoint=False)
        p = self.wav("ok.wav", 0.3 * np.sin(2 * np.pi * 400 * t))
        info = V.validate_file(p, os.path.getsize(p), 15)
        self.assertAlmostEqual(info["duration"], 2.0, delta=0.1)

    def test_quality_flags(self):
        sr = 16000
        self.assertIn("silent", [w["code"] for w in V.quality_warnings(np.zeros(sr, "float32"), sr)])
        t = np.linspace(0, 2, 2 * sr, endpoint=False)
        self.assertIn("clipped", [w["code"] for w in V.quality_warnings(np.clip(np.sin(2 * np.pi * 400 * t) * 5, -1, 1), sr)])
        self.assertIn("maybe_not_cry", [w["code"] for w in V.quality_warnings((0.3 * np.sin(2 * np.pi * 60 * t)).astype("float32"), sr)])


if __name__ == "__main__":
    unittest.main()
