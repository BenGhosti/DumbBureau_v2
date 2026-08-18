from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-crypto-tests-32-bytes")
os.environ.setdefault("ENCRYPTION_KEY", "dedicated-encryption-key-for-tests")

from app.crypto import decrypt, encrypt  # noqa: E402


class CryptoTest(unittest.TestCase):
    def test_round_trip(self):
        for text in [
            "hello",
            "Tätigkeit <script>alert(1)</script>",
            "",
            "emoji 🎯 and umlauts äöü",
        ]:
            self.assertEqual(decrypt(encrypt(text)), text)

    def test_ciphertext_obscures_plaintext(self):
        text = "super-secret-description"
        ciphertext = encrypt(text)
        self.assertTrue(ciphertext.startswith("enc:v1:"))
        self.assertNotIn(text, ciphertext)

    def test_non_deterministic(self):
        self.assertNotEqual(encrypt("x"), encrypt("x"))

    def test_passthrough_plaintext(self):
        self.assertEqual(decrypt("legacy plain"), "legacy plain")

    def test_decrypt_none(self):
        self.assertIsNone(decrypt(None))

    def test_decrypt_failure_is_visible_not_silent_garbage(self):
        # Simulates a SECRET_KEY/ENCRYPTION_KEY rotation: previously encrypted
        # data must never come back out looking like a plausible plaintext
        # description (raw base64 ciphertext silently shown as "the task
        # text" is a real data-integrity bug, not just cosmetic).
        import app.crypto as crypto_module

        ciphertext = encrypt("some real task description")
        original_key = crypto_module._master_key
        try:
            crypto_module._master_key = b"0" * 16  # wrong key, same length
            result = decrypt(ciphertext)
            self.assertNotEqual(result, ciphertext)
            self.assertIn("fehlgeschlagen", result)
        finally:
            crypto_module._master_key = original_key


if __name__ == "__main__":
    unittest.main()
