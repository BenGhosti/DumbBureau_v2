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


def load_caddyfile() -> str:
    return (ROOT / "Caddyfile").read_text(encoding="utf-8")


# --- docker-compose.yml -----------------------------------------------------
compose = load_compose()
services = compose["services"]

check("caddy service exists", "caddy" in services)
caddy = services.get("caddy", {})
check("caddy uses the `caddy` profile", "caddy" in caddy.get("profiles", []))
caddy_ports = caddy.get("ports", [])
check("caddy exposes 8360", "8360:8360" in caddy_ports)
check("caddy exposes 8361", "8361:8361" in caddy_ports)
check("caddy mounts Caddyfile read-only", "./Caddyfile:/etc/caddy/Caddyfile:ro" in caddy.get("volumes", []))

backend_env = {e.split("=", 1)[0]: e.split("=", 1)[1] for e in services["backend"].get("environment", []) if "=" in e}
check("backend TRUSTED_PROXY_IPS defaults to docker subnet", "172.28.1.0/24" in backend_env["TRUSTED_PROXY_IPS"])
check("backend has RATE_LIMIT_* env", all(k in backend_env for k in ("RATE_LIMIT_ENABLED", "RATE_LIMIT_MAX_REQUESTS", "RATE_LIMIT_WINDOW_SECONDS")))

networks = compose.get("networks", {})
check("fixed subnet 172.28.1.0/24 configured", networks["dumbbureau"]["ipam"]["config"][0]["subnet"] == "172.28.1.0/24")

check("log rotation set on backend", services["backend"].get("logging", {}).get("driver") == "json-file")
check("log rotation max-size set", services["backend"]["logging"]["options"].get("max-size") == "10m")

# backend/frontend must not be reachable from the host directly: all external
# traffic should go through Caddy (which is the only service publishing ports).
check("backend publishes no host port", "ports" not in services["backend"])
check("frontend publishes no host port", "ports" not in services["frontend"])

# --- Caddyfile --------------------------------------------------------------
caddyfile = load_caddyfile()
check("Caddyfile uses DUMBBUREAU_HOSTNAME env var", "{$DUMBBUREAU_HOSTNAME}" in caddyfile)
check("Caddyfile enables tls internal", "tls internal" in caddyfile)
check("Caddyfile proxies to frontend:80", "reverse_proxy frontend:80" in caddyfile)
check("Caddyfile binds HTTP port 8361", "http_port 8361" in caddyfile)
check("Caddyfile binds HTTPS port 8360", "https_port 8360" in caddyfile)
check("Caddyfile disables admin API", "admin off" in caddyfile)
check("no on-demand TLS", "on_demand" not in caddyfile)
check("no catch-all site block", "{:443}" not in caddyfile and "{:80}" not in caddyfile)

print("\nALL PROXY CONFIG TESTS PASSED")
