from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import DictLoader
from jinja2.sandbox import SandboxedEnvironment

DEFAULT_TEMPLATE = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<title>Berichtsheft {{ month }}</title>
<style>
  body { font-family: sans-serif; font-size: 11pt; color: #222; }
  h1 { color: #333; }
  .meta { margin-bottom: 1em; color: #555; }
  table { width: 100%; border-collapse: collapse; margin-top: 1em; }
  th, td { border: 1px solid #ccc; padding: 6px; text-align: left; vertical-align: top; }
  th { background: #f0f0f0; }
</style>
</head>
<body>
  <h1>Berichtsheft - {{ month }}</h1>
  <div class="meta">
    <strong>{{ user.username }}</strong>{% if user.email %} &lt;{{ user.email }}&gt;{% endif %}
  </div>
  <table>
    <thead>
      <tr>
        <th>Datum</th>
        <th>Kategorie</th>
        <th>Beschreibung</th>
        <th>FiSi-Bereich</th>
      </tr>
    </thead>
    <tbody>
      {% for t in tasks %}
      <tr>
        <td>{{ t.date }}</td>
        <td>{{ t.category or "" }}</td>
        <td>{{ t.description }}</td>
        <td>{{ t.fisi_area or "" }}</td>
      </tr>
      {% else %}
      <tr><td colspan="4">Keine Eintr&auml;ge in diesem Monat.</td></tr>
      {% endfor %}
    </tbody>
  </table>
</body>
</html>
"""


def _sandbox() -> SandboxedEnvironment:
    # Empty loader blocks {% include %}/{% extends %}/{% import %} file access.
    return SandboxedEnvironment(autoescape=True, loader=DictLoader({}))


def render_template(html: str, context: dict[str, Any]) -> str:
    template = _sandbox().from_string(html)
    return template.render(**context)


def generate_pdf(html: str, output_path: Path) -> None:
    import weasyprint
    from weasyprint.urls import URLFetcher

    # Only data: URIs are allowed; external/file resources are blocked (SSRF guard).
    fetcher = URLFetcher(allowed_protocols=["data"])
    weasyprint.HTML(string=html, url_fetcher=fetcher).write_pdf(str(output_path))
