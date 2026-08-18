from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.helpers import check, make_temp_env  # noqa: E402

make_temp_env("admin")

from fastapi.testclient import TestClient  # noqa: E402

from app import maintenance  # noqa: E402
from app.auth_utils import create_access_token  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.init_db import init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Task, User  # noqa: E402

init_db()

db = SessionLocal()
admin = User(username="admin", is_admin=True)
ben = User(username="ben")
db.add_all([admin, ben])
db.flush()
admin_id = admin.id
ben_id = ben.id
db.add(Task(user_id=ben_id, date=date(2026, 8, 1), description="recent task"))
db.add(Task(user_id=ben_id, date=date(2020, 1, 1), description="ancient task"))
db.commit()
admin_token = create_access_token(admin)
ben_token = create_access_token(ben)
db.close()

client = TestClient(app)
AH = {"Authorization": f"Bearer {admin_token}"}
BH = {"Authorization": f"Bearer {ben_token}"}


# --- users ---
r = client.get("/api/admin/users", headers=AH)
check("admin list users -> 200", r.status_code == 200)
users = {u["username"]: u for u in r.json()["users"]}
check("users has admin + ben", "admin" in users and "ben" in users)
check("ben task_count == 2", users["ben"]["task_count"] == 2)

r = client.get("/api/admin/users", headers=BH)
check("non-admin list users -> 403", r.status_code == 403)

# --- audit log ---
r = client.get("/api/admin/audit-log", headers=AH)
check("audit-log -> 200", r.status_code == 200)
check("audit-log has entries", isinstance(r.json()["logs"], list))

# --- admin view tasks ---
r = client.get(f"/api/admin/user/{ben_id}/tasks?month=2026-08", headers=AH)
check("admin view ben's tasks -> 200", r.status_code == 200)
check("admin sees 1 aug task", len(r.json()["tasks"]) == 1)

# --- invites ---
r = client.post("/api/admin/invites", headers=AH)
check("create invite -> 200", r.status_code == 200)
invite_token = r.json()["invite_token"]
check("invite token non-empty", bool(invite_token))

r = client.get("/api/admin/invites", headers=AH)
check("list invites -> 200", r.status_code == 200)
check("one invite listed", len(r.json()["invites"]) == 1)

# --- archive / unarchive ---
r = client.post(f"/api/admin/user/{ben_id}/archive", json={"reason": "left company"}, headers=AH)
check("archive ben -> 200", r.status_code == 200)

r = client.get("/api/tasks", headers=BH)
check("archived ben -> 401 on tasks", r.status_code == 401)

r = client.post(f"/api/admin/user/{admin_id}/archive", json={}, headers=AH)
check("cannot archive self -> 400", r.status_code == 400)

r = client.post(f"/api/admin/user/{ben_id}/unarchive", headers=AH)
check("unarchive ben -> 200", r.status_code == 200)
r = client.get("/api/tasks", headers=BH)
check("unarchived ben -> 200 on tasks", r.status_code == 200)

# --- maintenance: archive old tasks ---
db = SessionLocal()
n = maintenance.archive_old_tasks(db)
db.close()
check("archive_old_tasks archives 1 old task", n == 1)

db = SessionLocal()
active = db.query(Task).filter(Task.user_id == ben_id, Task.archived_at.is_(None)).count()
db.close()
check("only recent task remains active", active == 1)

print("\nALL ADMIN TESTS PASSED")
