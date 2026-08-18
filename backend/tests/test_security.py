from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.helpers import check, make_temp_env  # noqa: E402

make_temp_env("security")

from fastapi.testclient import TestClient  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.init_db import init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402
from app.rate_limit import SlidingWindowRateLimiter, get_client_ip  # noqa: E402

init_db()

# --- 1. Sliding-window rate limiter (unit) ---------------------------------
rl = SlidingWindowRateLimiter(max_requests=3, window_seconds=60)
check("limiter allows up to max", all(rl.allow("k") for _ in range(3)))
check("limiter blocks beyond max", rl.allow("k") is False)
check("limiter keeps keys independent", rl.allow("other") is True)

# --- 2. Client IP extraction behind trusted proxies ------------------------
def _req(xff: str | None, peer: str = "172.28.1.6", x_real_ip: str | None = None) -> SimpleNamespace:
    headers: dict = {}
    if xff is not None:
        headers["x-forwarded-for"] = xff
    if x_real_ip is not None:
        headers["x-real-ip"] = x_real_ip
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=peer))

check(
    "xff: rightmost untrusted is the client",
    get_client_ip(_req("203.0.113.7, 172.28.1.5")) == "203.0.113.7",
)
check(
    "xff: all trusted falls back to peer",
    get_client_ip(_req("172.28.1.2, 172.28.1.5")) == "172.28.1.6",
)
check("no xff uses direct peer", get_client_ip(_req(None, peer="203.0.113.9")) == "203.0.113.9")
check(
    "x-real-ip honored from trusted peer",
    get_client_ip(_req(None, x_real_ip="203.0.113.99")) == "203.0.113.99",
)
check(
    "x-real-ip ignored from untrusted peer",
    get_client_ip(_req(None, peer="203.0.113.5", x_real_ip="1.2.3.4")) == "203.0.113.5",
)

# --- 3. User enumeration: unknown username must not 404 --------------------
db = SessionLocal()
db.add(User(username="admin", is_admin=True))
db.commit()
db.close()

client = TestClient(app)

r = client.post("/api/auth/login/options", json={"username": "admin"})
check("login/options existing user -> 200", r.status_code == 200)

r = client.post("/api/auth/login/options", json={"username": "does-not-exist"})
check("login/options unknown user -> 200 (no enumeration)", r.status_code == 200)
body = r.json()
check("unknown user gets usernameless options", "challenge" in body["options"])

print("\nALL SECURITY TESTS PASSED")
