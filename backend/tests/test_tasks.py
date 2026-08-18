from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.helpers import check, make_temp_env  # noqa: E402

make_temp_env("tasks")

from fastapi.testclient import TestClient  # noqa: E402

from app.auth_utils import create_access_token  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.init_db import init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Category, User  # noqa: E402

init_db()

db = SessionLocal()
admin = User(username="admin", is_admin=True)
ben = User(username="ben")
db.add_all([admin, ben])
db.flush()
admin_id = admin.id
ben_id = ben.id
cat = Category(user_id=ben_id, name="FiSi", color="#123456")
admin_cat = Category(user_id=admin_id, name="Admin Cat")
db.add_all([cat, admin_cat])
db.flush()
cat_id = cat.id
admin_cat_id = admin_cat.id
admin_token = create_access_token(admin)
ben_token = create_access_token(ben)
db.commit()
db.close()

client = TestClient(app)
AH = {"Authorization": f"Bearer {admin_token}"}
BH = {"Authorization": f"Bearer {ben_token}"}


# create as ben
r = client.post("/api/tasks", json={"date": "2026-08-10", "category_id": cat_id, "description": "Server konfiguriert", "fisi_area": "Systemintegration"}, headers=BH)
check("create task -> 200", r.status_code == 200)
task_id = r.json()["task_id"]

r = client.post("/api/tasks", json={"date": "2026-08-11", "description": "No category"}, headers=BH)
check("create task without category -> 200", r.status_code == 200)

r = client.post("/api/tasks", json={"date": "2026-08-12", "description": "   "}, headers=BH)
check("empty description -> 400", r.status_code == 400)

r = client.post("/api/tasks", json={"date": "2026-08-12", "category_id": admin_cat_id, "description": "x"}, headers=BH)
check("foreign category -> 400", r.status_code == 400)

# list own
r = client.get("/api/tasks", headers=BH)
check("ben sees 2 tasks", len(r.json()["tasks"]) == 2)

# month filter
r = client.get("/api/tasks?month=2026-08", headers=BH)
check("ben august -> 2 tasks", len(r.json()["tasks"]) == 2)
r = client.get("/api/tasks?month=2026-09", headers=BH)
check("ben september -> 0 tasks", len(r.json()["tasks"]) == 0)
r = client.get("/api/tasks?month=bogus", headers=BH)
check("bad month -> 400", r.status_code == 400)

# admin sees own (none yet), then all via user_id
r = client.get("/api/tasks", headers=AH)
check("admin sees 0 own tasks", len(r.json()["tasks"]) == 0)
r = client.get(f"/api/tasks?user_id={ben_id}", headers=AH)
check("admin sees ben's 2 tasks", len(r.json()["tasks"]) == 2)

# non-admin cannot use user_id
r = client.get(f"/api/tasks?user_id={admin_id}", headers=BH)
check("ben cannot filter by other user -> 403", r.status_code == 403)

# update own
r = client.put(f"/api/tasks/{task_id}", json={"description": "Updated desc"}, headers=BH)
check("ben update own -> 200", r.status_code == 200)

# admin update ben's task (override)
r = client.put(f"/api/tasks/{task_id}", json={"description": "Admin edited"}, headers=AH)
check("admin update ben's task -> 200", r.status_code == 200)

# cross-user forbidden: create admin task, ben tries to edit
r = client.post("/api/tasks", json={"date": "2026-08-15", "description": "admin task"}, headers=AH)
admin_task_id = r.json()["task_id"]
r = client.put(f"/api/tasks/{admin_task_id}", json={"description": "hax"}, headers=BH)
check("ben cannot edit admin task -> 403", r.status_code == 403)

# delete own
r = client.delete(f"/api/tasks/{task_id}", headers=BH)
check("ben delete own -> 200", r.status_code == 200)
r = client.get("/api/tasks?month=2026-08", headers=BH)
check("ben has 1 remaining task", len(r.json()["tasks"]) == 1)

# delete already deleted
r = client.delete(f"/api/tasks/{task_id}", headers=BH)
check("delete again -> 404", r.status_code == 404)

print("\nALL TASK TESTS PASSED")
