from __future__ import annotations

import base64
import logging
import os

from argon2.low_level import Type, hash_secret_raw
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger("dumbbureau.crypto")

_PREFIX = "enc:v1:"
_NONCE_LEN = 12
_KEY_LEN = 16  # AES-128
_DECRYPT_FAILURE_MARKER = "\u26a0 [Entschlüsselung fehlgeschlagen / decryption failed]"

# Argon2id cost parameters. Low cost is acceptable here because the password
# (ENCRYPTION_KEY / SECRET_KEY) is a high-entropy secret, not a user password.
_TIME_COST = 3
_MEMORY_COST = 65536  # 64 MiB
_PARALLELISM = 4

# Fixed salt for the master-key derivation (key is derived once, then cached).
_SALT = b"dumbbureau-kdf-v1"

_master_key: bytes | None = None


def _derive(password: bytes) -> bytes:
    return hash_secret_raw(
        secret=password,
        salt=_SALT,
        time_cost=_TIME_COST,
        memory_cost=_MEMORY_COST,
        parallelism=_PARALLELISM,
        hash_len=_KEY_LEN,
        type=Type.ID,
    )


def _get_key() -> bytes:
    global _master_key
    if _master_key is None:
        from .config import settings

        password = settings.encryption_key or settings.secret_key
        _master_key = _derive(password.encode("utf-8"))
    return _master_key


def encrypt(plaintext: str) -> str:
    nonce = os.urandom(_NONCE_LEN)
    ciphertext = AESGCM(_get_key()).encrypt(nonce, plaintext.encode("utf-8"), None)
    return _PREFIX + base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def decrypt(value: str | None) -> str | None:
    if value is None:
        return None
    if not value.startswith(_PREFIX):
        # Plaintext (legacy/unencrypted) value — pass through unchanged.
        return value
    try:
        raw = base64.urlsafe_b64decode(value[len(_PREFIX):].encode("ascii"))
        nonce, ciphertext = raw[:_NONCE_LEN], raw[_NONCE_LEN:]
        return AESGCM(_get_key()).decrypt(nonce, ciphertext, None).decode("utf-8")
    except Exception:
        # Decryption failure almost always means SECRET_KEY/ENCRYPTION_KEY was
        # rotated or is misconfigured. Returning the raw ciphertext here would
        # silently show base64 garbage to the user as if it were their real
        # task description, with no way to tell anything went wrong. Log it
        # loudly (server-side, no secret material) and surface an honest
        # placeholder instead so the failure is visible, not silent data loss.
        logger.error(
            "Decryption failed for a stored value (%d bytes). This usually means "
            "SECRET_KEY/ENCRYPTION_KEY changed since the value was written. "
            "The affected value cannot be recovered without the original key.",
            len(value),
        )
        return _DECRYPT_FAILURE_MARKER
