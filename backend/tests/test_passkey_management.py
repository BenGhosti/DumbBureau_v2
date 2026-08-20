from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.helpers import VirtualAuthenticator, check, make_temp_env  # noqa: E402

make_temp_env("passkeys")

from fastapi.testclient import TestClient  # noqa: E402

from app.init_db import init_db  # noqa: E402
from app.main import app  # noqa: E402

init_db()

client = TestClient(app)

# --- Bootstrap: register the first (admin) user with one passkey ---
auth1 = VirtualAuthenticator()

r = client.post(
    "/api/auth/register/options",
    json={"username": "multiben", "email": "ben@example.com", "admin_secret": "test-admin-secret"},
)
check("register/options -> 200", r.status_code == 200)
opts = r.json()
cred = auth1.register(opts["options"]["challenge"])

r = client.post(
    "/api/auth/register/verify",
    json={"challenge_id": opts["challenge_id"], "credential": cred, "passkey_name": "First Device"},
)
check("register/verify -> 200", r.status_code == 200)
token = r.json()["session_token"]
AH = {"Authorization": f"Bearer {token}"}

# --- List passkeys: should show exactly one, named as requested ---
r = client.get("/api/auth/passkeys", headers=AH)
check("list passkeys -> 200", r.status_code == 200)
passkeys = r.json()
check("exactly 1 passkey after registration", len(passkeys) == 1)
check("passkey name matches what was requested", passkeys[0]["name"] == "First Device")
first_passkey_id = passkeys[0]["id"]

# --- Add a second passkey to the same account ---
auth2 = VirtualAuthenticator()

r = client.post("/api/auth/passkeys/add/options", headers=AH)
check("passkeys/add/options -> 200", r.status_code == 200)
add_opts = r.json()
cred2 = auth2.register(add_opts["options"]["challenge"])

r = client.post(
    "/api/auth/passkeys/add/verify",
    json={"challenge_id": add_opts["challenge_id"], "credential": cred2, "passkey_name": "Second Device"},
    headers=AH,
)
check("passkeys/add/verify -> 200", r.status_code == 200)
second_passkey_id = r.json()["id"]

r = client.get("/api/auth/passkeys", headers=AH)
check("exactly 2 passkeys after adding one", len(r.json()) == 2)

# --- Usernameless login: no username given, browser gets a discoverable-
# credential challenge, EITHER registered authenticator should be able to
# complete it (this is the core "usernameless" behavior). ---
r = client.post("/api/auth/login/options", json={})
check("login/options with no username -> 200", r.status_code == 200)
login_opts = r.json()
check("no username -> allowCredentials is empty (discoverable)", login_opts["options"]["allowCredentials"] == [])

login_cred = auth2.authenticate(login_opts["options"]["challenge"])
r = client.post(
    "/api/auth/login/verify",
    json={"challenge_id": login_opts["challenge_id"], "credential": login_cred},
)
check("usernameless login with 2nd passkey -> 200", r.status_code == 200)
check("usernameless login resolves to the right user", r.json()["username"] == "multiben")

# --- Removing a passkey requires authenticating with THAT credential ---
# Wrong-credential attempt: try to remove passkey #1 by authenticating with
# passkey #2 - must be rejected.
r = client.post(f"/api/auth/passkeys/{first_passkey_id}/remove/options", headers=AH)
check("remove/options -> 200", r.status_code == 200)
remove_opts = r.json()
wrong_cred = auth2.authenticate(remove_opts["options"]["challenge"])
r = client.post(
    f"/api/auth/passkeys/{first_passkey_id}/remove/verify",
    json={"challenge_id": remove_opts["challenge_id"], "credential": wrong_cred},
    headers=AH,
)
check("removing with the WRONG passkey is rejected (403)", r.status_code == 403)

r = client.get("/api/auth/passkeys", headers=AH)
check("still 2 passkeys after rejected removal", len(r.json()) == 2)

# Correct-credential attempt: authenticate with passkey #1 itself to remove it.
r = client.post(f"/api/auth/passkeys/{first_passkey_id}/remove/options", headers=AH)
remove_opts2 = r.json()
right_cred = auth1.authenticate(remove_opts2["options"]["challenge"])
r = client.post(
    f"/api/auth/passkeys/{first_passkey_id}/remove/verify",
    json={"challenge_id": remove_opts2["challenge_id"], "credential": right_cred},
    headers=AH,
)
check("removing with the CORRECT passkey succeeds", r.status_code == 200)

r = client.get("/api/auth/passkeys", headers=AH)
check("exactly 1 passkey remains after removal", len(r.json()) == 1)
check("the remaining passkey is the second one", r.json()[0]["id"] == second_passkey_id)

# --- Cannot remove the LAST remaining passkey (would lock the user out) ---
r = client.post(f"/api/auth/passkeys/{second_passkey_id}/remove/options", headers=AH)
last_opts = r.json()
last_cred = auth2.authenticate(last_opts["options"]["challenge"])
r = client.post(
    f"/api/auth/passkeys/{second_passkey_id}/remove/verify",
    json={"challenge_id": last_opts["challenge_id"], "credential": last_cred},
    headers=AH,
)
check("cannot remove the last passkey (400)", r.status_code == 400)

r = client.get("/api/auth/passkeys", headers=AH)
check("last passkey survives the rejected removal", len(r.json()) == 1)

# --- Rename ---
r = client.patch(f"/api/auth/passkeys/{second_passkey_id}", json={"name": "Renamed"}, headers=AH)
check("rename passkey -> 200", r.status_code == 200)
r = client.get("/api/auth/passkeys", headers=AH)
check("name actually changed", r.json()[0]["name"] == "Renamed")

print("\nALL MULTI-PASSKEY TESTS PASSED")
