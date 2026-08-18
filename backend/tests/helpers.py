from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

RP_ID = "localhost"
ORIGIN = "http://localhost:8600"

DEFAULT_ENV = {
    "ADMIN_RECOVERY_SECRET": "test-admin-secret",
    "SECRET_KEY": "a-very-long-secret-key-for-testing-purposes-32",
    "ENCRYPTION_KEY": "a-dedicated-encryption-key-for-tests",
    "WEBAUTHN_RP_ID": RP_ID,
    "WEBAUTHN_ORIGIN": ORIGIN,
}


def make_temp_env(prefix: str) -> str:
    """Create an isolated temp dir and point DATABASE_URL/APPDATA_DIR at it.

    Must be called *before* importing ``app`` modules (settings are read at
    import time).
    """
    test_dir = tempfile.mkdtemp(prefix=f"dumbbureau-{prefix}-")
    os.environ["DATABASE_URL"] = f"sqlite:///{test_dir}/db.sqlite"
    os.environ["APPDATA_DIR"] = test_dir
    for key, value in DEFAULT_ENV.items():
        os.environ[key] = value
    return test_dir


def b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


class VirtualAuthenticator:
    """Minimal software authenticator that produces valid WebAuthn responses.

    Uses an ES256 keypair and "none" (self) attestation, matching what real
    roaming authenticators emit. Signatures are ASN.1 DER (per WebAuthn spec
    §6.5.5).
    """

    def __init__(self):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.cred_id = os.urandom(16)
        self.sign_count = 0
        pub = self.key.public_key().public_numbers()
        self.cose_key = cbor2.dumps(
            {
                1: 2,
                3: -7,
                -1: 1,
                -2: pub.x.to_bytes(32, "big"),
                -3: pub.y.to_bytes(32, "big"),
            }
        )

    def _client_data(self, type_: str, challenge_b64: str) -> bytes:
        return json.dumps(
            {
                "type": type_,
                "challenge": challenge_b64,
                "origin": ORIGIN,
                "crossOrigin": False,
            }
        ).encode()

    def register(self, challenge_b64: str) -> dict:
        rp_id_hash = hashlib.sha256(RP_ID.encode()).digest()
        flags = 0x45  # UP | UV | AT
        attested = (
            b"\x00" * 16
            + len(self.cred_id).to_bytes(2, "big")
            + self.cred_id
            + self.cose_key
        )
        auth_data = (
            rp_id_hash + bytes([flags]) + self.sign_count.to_bytes(4, "big") + attested
        )
        att_obj = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        cd = self._client_data("webauthn.create", challenge_b64)
        return {
            "id": b64url(self.cred_id),
            "rawId": b64url(self.cred_id),
            "response": {"clientDataJSON": b64url(cd), "attestationObject": b64url(att_obj)},
            "type": "public-key",
        }

    def authenticate(self, challenge_b64: str) -> dict:
        self.sign_count += 1
        rp_id_hash = hashlib.sha256(RP_ID.encode()).digest()
        auth_data = rp_id_hash + bytes([0x05]) + self.sign_count.to_bytes(4, "big")
        cd = self._client_data("webauthn.get", challenge_b64)
        sig_input = auth_data + hashlib.sha256(cd).digest()
        der_sig = self.key.sign(sig_input, ec.ECDSA(hashes.SHA256()))
        return {
            "id": b64url(self.cred_id),
            "rawId": b64url(self.cred_id),
            "response": {
                "clientDataJSON": b64url(cd),
                "authenticatorData": b64url(auth_data),
                "signature": b64url(der_sig),
                "userHandle": None,
            },
            "type": "public-key",
        }


def check(name: str, cond: bool) -> None:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}")
    if not cond:
        raise SystemExit(f"FAILED: {name}")
