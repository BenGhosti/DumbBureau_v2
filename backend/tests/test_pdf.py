from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.helpers import check, make_temp_env  # noqa: E402

test_dir = make_temp_env("pdf")

from fastapi.testclient import TestClient  # noqa: E402

from app import pdf_generator  # noqa: E402
from app.auth_utils import create_access_token  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.init_db import init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Category, Task, Template, User  # noqa: E402

init_db()

# ---- mock weasyprint (needs Pango, unavailable outside the Docker image) ----
captured = {}


def fake_generate_pdf(html, output_path):
    captured["html"] = html
    captured["path"] = str(output_path)
    Path(output_path).write_bytes(b"%PDF-1.4 fake-bytes")


pdf_generator.generate_pdf = fake_generate_pdf

db = SessionLocal()
admin = User(username="admin", is_admin=True)
ben = User(username="ben")
db.add_all([admin, ben])
db.flush()
admin_id = admin.id
ben_id = ben.id
cat = Category(user_id=ben_id, name="FiSi")
db.add(cat)
db.flush()
cat_id = cat.id
for d in [date(2026, 8, 3), date(2026, 8, 10)]:
    db.add(Task(user_id=ben_id, date=d, category_id=cat_id, description=f"Work on {d}"))
db.add(Task(user_id=ben_id, date=date(2026, 7, 30), category_id=cat_id, description="July task"))
db.commit()

tpl_dir = Path(os.environ["APPDATA_DIR"]) / "templates" / ben_id
tpl_dir.mkdir(parents=True, exist_ok=True)
tpl_file = tpl_dir / "mytemplate.html"
tpl_file.write_text(
    "<html><body><h1>{{ month }}</h1>{% for t in tasks %}<p>{{ t.description }}</p>{% endfor %}</body></html>",
    encoding="utf-8",
)
mal_file = tpl_dir / "malicious.html"
mal_file.write_text("<p>{{ ''.__class__.__mro__ }}</p>", encoding="utf-8")
tpl = Template(id="tmpl1", user_id=ben_id, name="M", html_file=str(tpl_file), is_default=True)
mal = Template(id="mal1", user_id=ben_id, name="Mal", html_file=str(mal_file), is_default=False)
db.add_all([tpl, mal])
db.commit()

admin_token = create_access_token(admin)
ben_token = create_access_token(ben)
db.close()

client = TestClient(app)
AH = {"Authorization": f"Bearer {admin_token}"}
BH = {"Authorization": f"Bearer {ben_token}"}


# --- unit: render default template ---
html = pdf_generator.render_template(
    pdf_generator.DEFAULT_TEMPLATE,
    {
        "user": {"username": "ben"},
        "month": "2026-08",
        "tasks": [{"date": "2026-08-03", "category": "FiSi", "description": "<script>x</script>", "fisi_area": None}],
        "generated_at": "x",
    },
)
check("default template renders month", "2026-08" in html)
check("default template renders username", "ben" in html)
check("autoescape escapes injected html", "&lt;script&gt;" in html and "<script>" not in html)

try:
    pdf_generator.render_template("<p>{{ ''.__class__.__mro__ }}</p>", {})
    check("sandbox blocks SSTI chain", False)
except Exception:
    check("sandbox blocks SSTI chain", True)

out = pdf_generator.render_template("<p>{{ config }}</p>", {})
check("sandbox does not leak config", out.strip() == "<p></p>")

# --- export with default template ---
r = client.post("/api/pdf/export", json={"month": "2026-08"}, headers=BH)
check("export (default template) -> 200", r.status_code == 200)
pdf_id = r.json()["pdf_id"]
check("pdf_url correct", r.json()["pdf_url"] == f"/api/pdf/{pdf_id}")
check("fake pdf written", Path(captured["path"]).exists())
check("rendered html has 2 aug tasks", captured["html"].count("<td>") >= 2 or "Work on" in captured["html"])

# --- export with explicit template ---
r = client.post("/api/pdf/export", json={"month": "2026-08", "template_id": "tmpl1"}, headers=BH)
check("export (explicit template) -> 200", r.status_code == 200)
check("custom template rendered", "<h1>2026-08</h1>" in captured["html"])

# --- export with malicious template -> 400 (SSTI blocked) ---
r = client.post("/api/pdf/export", json={"month": "2026-08", "template_id": "mal1"}, headers=BH)
check("malicious template -> 400", r.status_code == 400)

# --- bad month ---
r = client.post("/api/pdf/export", json={"month": "bogus"}, headers=BH)
check("bad month -> 400", r.status_code == 400)

# --- nonexistent template ---
r = client.post("/api/pdf/export", json={"month": "2026-08", "template_id": "nope"}, headers=BH)
check("missing template -> 404", r.status_code == 404)

# --- download ---
r = client.get(f"/api/pdf/{pdf_id}", headers=BH)
check("download own pdf -> 200", r.status_code == 200 and r.content == b"%PDF-1.4 fake-bytes")

r = client.get(f"/api/pdf/{pdf_id}", headers=AH)
check("admin can download ben's pdf -> 200", r.status_code == 200)

# admin export for ben (with user_id)
r = client.post("/api/pdf/export", json={"month": "2026-08", "user_id": ben_id}, headers=AH)
check("admin export for ben -> 200", r.status_code == 200)

# non-admin cannot export for other
r = client.post("/api/pdf/export", json={"month": "2026-08", "user_id": admin_id}, headers=BH)
check("ben cannot export for other -> 403", r.status_code == 403)

# --- DB row exists but the file was removed from disk (volume issue, manual
# cleanup, ...) -> must be an honest 404, not an unhandled 500 ---
from app.models import PdfExport  # noqa: E402

db2 = SessionLocal()
export_row = db2.get(PdfExport, pdf_id)
Path(export_row.pdf_file).unlink()
db2.close()

r = client.get(f"/api/pdf/{pdf_id}", headers=BH)
check("missing pdf file on disk -> 404 (not 500)", r.status_code == 404)

print("\nALL PDF TESTS PASSED")
