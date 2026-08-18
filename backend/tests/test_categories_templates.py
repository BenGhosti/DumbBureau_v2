from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.helpers import check, make_temp_env  # noqa: E402

make_temp_env("cat-tpl")

from fastapi.testclient import TestClient  # noqa: E402

from app.auth_utils import create_access_token  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.init_db import init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402

init_db()

db = SessionLocal()
admin = User(username="admin", is_admin=True)
ben = User(username="ben")
db.add_all([admin, ben])
db.flush()
admin_token = create_access_token(admin)
ben_token = create_access_token(ben)
db.commit()
db.close()

client = TestClient(app)
AH = {"Authorization": f"Bearer {admin_token}"}
BH = {"Authorization": f"Bearer {ben_token}"}


# --- categories ---
r = client.post("/api/categories", json={"name": "FiSi", "description": "desc", "color": "#FF0000"}, headers=BH)
check("create category -> 200", r.status_code == 200)
cat_id = r.json()["category_id"]

r = client.post("/api/categories", json={"name": "x", "color": "red"}, headers=BH)
check("invalid color -> 400", r.status_code == 400)

r = client.post("/api/categories", json={"name": "   "}, headers=BH)
check("empty name -> 400", r.status_code == 400)

r = client.get("/api/categories", headers=BH)
check("ben has 1 category", len(r.json()["categories"]) == 1)

r = client.put(f"/api/categories/{cat_id}", json={"name": "FiSi Admin", "color": "#00FF00"}, headers=AH)
check("admin update ben's category -> 200", r.status_code == 200)

r = client.put(f"/api/categories/{cat_id}", json={"name": "FiSi", "color": "#123456"}, headers=BH)
check("ben update own -> 200", r.status_code == 200)

r = client.post("/api/categories", json={"name": "AdminCat"}, headers=AH)
admin_cat_id = r.json()["category_id"]
r = client.put(f"/api/categories/{admin_cat_id}", json={"name": "hax"}, headers=BH)
check("ben cannot edit admin category -> 403", r.status_code == 403)

r = client.delete(f"/api/categories/{cat_id}", headers=BH)
check("ben delete own category -> 200", r.status_code == 200)
r = client.delete(f"/api/categories/{cat_id}", headers=BH)
check("delete again -> 404", r.status_code == 404)

# --- templates ---
template_html = (
    "<html><head><style>body{color:red}</style></head><body>"
    "<h1>{{ user_name }}</h1>"
    "<ul>{% for t in tasks %}<li>{{ t.description }}</li>{% endfor %}</ul>"
    "<script>alert('xss')</script>"
    "<img src=\"javascript:alert(1)\">"
    "</body></html>"
)

files = {"html_file": ("t.html", template_html.encode("utf-8"), "text/html")}
data = {"name": "Berichtsheft", "description": "Default template", "is_default": "true"}
r = client.post("/api/templates", data=data, files=files, headers=BH)
check("upload template -> 200", r.status_code == 200)
tpl_id = r.json()["template_id"]
tpl_path = r.json()["file_path"]

saved = Path(tpl_path).read_text(encoding="utf-8")
check("sanitized: no <script>", "<script>" not in saved)
check("sanitized: no javascript:", "javascript:" not in saved)
check("sanitized: jinja preserved", "{{ user_name }}" in saved and "{% for t in tasks %}" in saved)
check("sanitized: style kept", "<style>" in saved)
check("file exists on disk", Path(tpl_path).exists())

r = client.get("/api/templates", headers=BH)
tpls = r.json()["templates"]
check("ben has 1 template", len(tpls) == 1)
check("template is default", tpls[0]["is_default"] is True)

files2 = {"html_file": ("t2.html", b"<p>second</p>", "text/html")}
r = client.post("/api/templates", data={"name": "Second", "is_default": "true"}, files=files2, headers=BH)
check("upload second template -> 200", r.status_code == 200)

r = client.get("/api/templates", headers=BH)
defaults = [t for t in r.json()["templates"] if t["is_default"]]
check("exactly one default", len(defaults) == 1)

r = client.put(f"/api/templates/{tpl_id}", data={"name": "Renamed"}, headers=BH)
check("update template name -> 200", r.status_code == 200)

r = client.put(f"/api/templates/{tpl_id}", data={"name": "hax"}, headers=AH)
check("admin CAN edit ben's template -> 200", r.status_code == 200)

r = client.post("/api/templates", data={"name": "AdminTpl"}, files={"html_file": ("a.html", b"<p>admin</p>", "text/html")}, headers=AH)
admin_tpl_id = r.json()["template_id"]
r = client.put(f"/api/templates/{admin_tpl_id}", data={"name": "hax"}, headers=BH)
check("ben cannot edit admin template -> 403", r.status_code == 403)

r = client.delete(f"/api/templates/{tpl_id}", headers=BH)
check("delete template -> 200", r.status_code == 200)
check("file removed from disk", not Path(tpl_path).exists())
r = client.delete(f"/api/templates/{tpl_id}", headers=BH)
check("delete again -> 404", r.status_code == 404)

print("\nALL CATEGORY/TEMPLATE TESTS PASSED")
