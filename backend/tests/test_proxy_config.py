from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.helpers import check  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def load_compose() -> dict:
    with (ROOT / "docker-compose.yml").open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# --- docker-compose.yml -----------------------------------------------------
compose = load_compose()
services = compose["services"]

# Caddy must be gone: TLS is handled by the operator's own reverse proxy.
check("no caddy service", "caddy" not in services)
check("no caddy volumes", "caddy_data" not in compose.get("volumes", {}))
check("Caddyfile removed", not (ROOT / "Caddyfile").exists())

check("frontend publishes 8360", "${FRONTEND_PORT:-8360}:80" in services["frontend"].get("ports", []))
check("backend publishes 8361", "${BACKEND_PORT:-8361}:8000" in services["backend"].get("ports", []))

backend_env = {e.split("=", 1)[0]: e.split("=", 1)[1] for e in services["backend"].get("environment", []) if "=" in e}
check("backend TRUSTED_PROXY_IPS defaults to docker range", "172.16.0.0/12" in backend_env["TRUSTED_PROXY_IPS"])
check("backend has RATE_LIMIT_* env", all(k in backend_env for k in ("RATE_LIMIT_ENABLED", "RATE_LIMIT_MAX_REQUESTS", "RATE_LIMIT_WINDOW_SECONDS")))

# No custom/fixed docker subnet: standard bridge network, host ports only.
check("no fixed docker subnet configured", "networks" not in compose)

check("log rotation set on backend", services["backend"].get("logging", {}).get("driver") == "json-file")
check("log rotation max-size set", services["backend"]["logging"]["options"].get("max-size") == "10m")

# --- frontend nginx.conf ----------------------------------------------------
nginx_conf = (ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")
check("nginx preserves X-Real-IP (no $remote_addr overwrite)",
      "proxy_set_header X-Real-IP $http_x_real_ip;" in nginx_conf)
check("nginx proxies /api to backend", "proxy_pass http://backend:8000;" in nginx_conf)

# --- .env.example -----------------------------------------------------------
env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
check("env template uses placeholder domain (no real domain)",
      "dumbbureau.example.com" in env_example and "WEBAUTHN_RP_ID=dumbbureau.example.com" in env_example)
check("env template no Caddy hostname var", "DUMBBUREAU_HOSTNAME" not in env_example)
check("env template documents proxy IP + docker range",
      "TRUSTED_PROXY_IPS=" in env_example and "172.16.0.0/12" in env_example)

print("\nALL PROXY CONFIG TESTS PASSED")
