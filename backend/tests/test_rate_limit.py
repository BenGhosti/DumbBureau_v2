from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.helpers import check, make_temp_env  # noqa: E402

make_temp_env("rate_limit")

from fastapi.testclient import TestClient  # noqa: E402

from app.init_db import init_db  # noqa: E402
from app.main import app  # noqa: E402

init_db()

client = TestClient(app)


# --- Username enumeration: unknown username must NOT be distinguishable
# from a valid one via status code. Both return 200 with a generic,
# discoverable-credential-style challenge. ---
r_unknown = client.post("/api/auth/login/options", json={"username": "does-not-exist-abcxyz"})
check("login/options unknown user -> 200 (not 404)", r_unknown.status_code == 200)
check("login/options unknown user has empty allowCredentials", r_unknown.json()["options"]["allowCredentials"] == [])

r_no_username = client.post("/api/auth/login/options", json={"username": None})
check("login/options no username -> 200", r_no_username.status_code == 200)
check(
    "unknown-user and no-username responses have the same shape",
    set(r_unknown.json()["options"].keys()) == set(r_no_username.json()["options"].keys()),
)


# --- Rate limiting: requests beyond the configured window limit must be
# rejected with 429. The two enumeration checks above already counted
# against this same client's limit, so we account for that here instead of
# guessing a magic number - the real assertion is "some requests succeed,
# then it starts rejecting them", not a specific index.
statuses = []
for i in range(35):
    r = client.post("/api/auth/login/options", json={"username": f"probe-{i}"})
    statuses.append(r.status_code)

check("some requests succeed before the limit kicks in", statuses.count(200) > 0)
check("requests are rate-limited (429) once the window fills", statuses.count(429) > 0)
check("once limited, it stays limited for the rest of the burst", statuses[-1] == 429)

print("\nALL RATE-LIMIT TESTS PASSED")
