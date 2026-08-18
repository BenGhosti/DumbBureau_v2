from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.helpers import VirtualAuthenticator, check, make_temp_env  # noqa: E402

make_temp_env("auth")

from fastapi.testclient import TestClient  # noqa: E402

from app.auth_utils import generate_token, hash_token  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.init_db import init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import InviteToken  # noqa: E402

init_db()

client = TestClient(app)


# --- 1. bootstrap guard ---
r = client.post("/api/auth/register/options", json={"username": "admin"})
check("register/options without secret -> 403", r.status_code == 403)

r = client.post("/api/auth/register/options", json={"username": "admin", "admin_secret": "wrong"})
check("register/options wrong secret -> 403", r.status_code == 403)

r = client.post(
    "/api/auth/register/options",
    json={"username": "admin", "email": "admin@example.com", "admin_secret": "test-admin-secret"},
)
check("register/options correct secret -> 200", r.status_code == 200)
reg = r.json()
check("options has challenge", "challenge" in reg["options"])
check("options has user", reg["options"]["user"]["name"] == "admin")

authn = VirtualAuthenticator()
cred = authn.register(reg["options"]["challenge"])
r = client.post(
    "/api/auth/register/verify",
    json={"challenge_id": reg["challenge_id"], "credential": cred},
)
check("register/verify -> 200", r.status_code == 200)
admin_session = r.json()
check("first user is admin", admin_session["is_admin"] is True)
check("session_token present", bool(admin_session["session_token"]))

admin_headers = {"Authorization": f"Bearer {admin_session['session_token']}"}

# --- 2. login flow ---
r = client.post("/api/auth/login/options", json={"username": "admin"})
check("login/options -> 200", r.status_code == 200)
login = r.json()

cred = authn.authenticate(login["options"]["challenge"])
r = client.post(
    "/api/auth/login/verify",
    json={"challenge_id": login["challenge_id"], "credential": cred},
)
check("login/verify -> 200", r.status_code == 200)
login_resp = r.json()
check("login returns is_admin", login_resp["is_admin"] is True)

r = client.post(
    "/api/auth/login/verify",
    json={"challenge_id": login["challenge_id"], "credential": cred},
)
check("login/verify replay -> 400", r.status_code == 400)

# --- 3. recovery flow ---
r = client.post(
    "/api/auth/recovery",
    json={"target_user_id": admin_session["user_id"]},
    headers=admin_headers,
)
check("recovery (admin) -> 200", r.status_code == 200)
rec = r.json()
check("recovery_token present", bool(rec["recovery_token"]))

new_authn = VirtualAuthenticator()
r = client.post("/api/auth/recovery/options", json={"recovery_token": rec["recovery_token"]})
check("recovery/options -> 200", r.status_code == 200)
rec_opts = r.json()

cred = new_authn.register(rec_opts["options"]["challenge"])
r = client.post(
    "/api/auth/recovery/verify",
    json={
        "recovery_token": rec["recovery_token"],
        "challenge_id": rec_opts["challenge_id"],
        "credential": cred,
    },
)
check("recovery/verify -> 200", r.status_code == 200)

r = client.post("/api/auth/recovery/options", json={"recovery_token": rec["recovery_token"]})
check("recovery token single-use -> 403", r.status_code == 403)

# --- 4. invite flow (user 2) ---
db = SessionLocal()
raw_invite = generate_token()
db.add(InviteToken(token_hash=hash_token(raw_invite), created_by=admin_session["user_id"]))
db.commit()
db.close()

r = client.post(
    "/api/auth/register/options",
    json={"username": "ben", "email": "ben@example.com", "invite_token": raw_invite},
)
check("register/options via invite -> 200", r.status_code == 200)
reg2 = r.json()

authn2 = VirtualAuthenticator()
cred = authn2.register(reg2["options"]["challenge"])
r = client.post(
    "/api/auth/register/verify",
    json={"challenge_id": reg2["challenge_id"], "credential": cred},
)
check("register/verify user2 -> 200", r.status_code == 200)
user2 = r.json()
check("user2 is not admin", user2["is_admin"] is False)

r = client.post(
    "/api/auth/register/options",
    json={"username": "charlie", "invite_token": raw_invite},
)
check("invite token single-use -> 403", r.status_code == 403)

# --- 5. username uniqueness (with a valid invite token) ---
db = SessionLocal()
raw_invite2 = generate_token()
db.add(InviteToken(token_hash=hash_token(raw_invite2), created_by=admin_session["user_id"]))
db.commit()
db.close()

r = client.post(
    "/api/auth/register/options",
    json={"username": "admin", "invite_token": raw_invite2},
)
check("duplicate username -> 409", r.status_code == 409)

# --- 6. protected route auth check (recovery requires admin) ---
r = client.post("/api/auth/recovery", json={"target_user_id": user2["user_id"]})
check("recovery without token -> 401", r.status_code == 401)

print("\nALL AUTH TESTS PASSED")
