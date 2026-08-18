from __future__ import annotations

import ipaddress
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from .config import settings


def _trusted_networks() -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    networks = []
    for entry in settings.trusted_proxies_list:
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            continue
    return networks


_TRUSTED_NETWORKS = _trusted_networks()


def client_ip(request: Request) -> str:
    """Best-effort real client IP.

    Only trusts X-Forwarded-For / X-Real-IP when the direct peer is a
    configured trusted proxy (TRUSTED_PROXY_IPS) - otherwise any client could
    simply send a spoofed X-Forwarded-For header and dodge rate limiting or
    poison audit-relevant IP data entirely. Falls back to the direct peer
    address, which is what you get when the app is reached without a proxy
    (e.g. BACKEND_PORT exposed directly).

    Deployment note: in a chained setup (Cloudflare -> your nginx -> this
    app's frontend container -> backend), only the LAST hop needs to be in
    TRUSTED_PROXY_IPS - that's your nginx's fixed IP, since it's the only
    peer this process ever sees directly. X-Forwarded-For may contain a
    comma-separated chain built up by every hop in between (Cloudflare
    appends the original client, your nginx passes it through); we take the
    first entry, which is the original client as long as every hop after it
    appends rather than overwrites the header - which is exactly what
    Cloudflare and stock nginx `proxy_set_header X-Forwarded-For
    $proxy_add_x_forwarded_for` both do.
    """
    direct = request.client.host if request.client else None
    is_trusted_peer = False
    if direct and _TRUSTED_NETWORKS:
        try:
            direct_addr = ipaddress.ip_address(direct)
            is_trusted_peer = any(direct_addr in net for net in _TRUSTED_NETWORKS)
        except ValueError:
            is_trusted_peer = False

    if is_trusted_peer:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()

    return direct or "unknown"


class _SlidingWindowLimiter:
    """Small dependency-free fixed-key sliding-window rate limiter.

    Deliberately in-process rather than backed by Redis/etc: this app is a
    single-backend-instance self-hosted deployment (see docker-compose.yml -
    one `backend` service, SQLite database), so an external rate-limit store
    would be pure added operational complexity for zero benefit here. If this
    is ever scaled to multiple backend replicas behind a shared load
    balancer, this in-memory limiter would need to move to a shared store.
    """

    def __init__(self, max_events: int, window_seconds: float):
        self.max_events = max_events
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def hit(self, key: str) -> bool:
        """Records one event for `key`. Returns True if within limit."""
        now = time.monotonic()
        bucket = self._hits[key]
        cutoff = now - self.window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= self.max_events:
            return False
        bucket.append(now)
        return True


# Auth endpoints are the sensitive surface: unauthenticated, and each attempt
# triggers DB writes (AuthChallenge rows) and WebAuthn challenge generation.
# Note this does NOT protect against credential brute-forcing in the
# traditional sense - WebAuthn has no password to guess, the private key
# never leaves the authenticator, so guessing is cryptographically
# infeasible regardless of rate limit. What this actually guards against is
# resource exhaustion (a script flooding AuthChallenge rows) and drive-by
# scripted abuse. 30 attempts / 5 minutes per client IP comfortably covers
# a real admin onboarding several household members in one sitting (each
# registration/login is 1-2 calls) while still capping sustained automated
# abuse to a few thousand requests/day from a single source.
_auth_limiter = _SlidingWindowLimiter(max_events=30, window_seconds=300)


def enforce_auth_rate_limit(request: Request) -> None:
    ip = client_ip(request)
    if not _auth_limiter.hit(ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please wait a few minutes and try again.",
        )
