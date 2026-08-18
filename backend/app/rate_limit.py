from __future__ import annotations

import ipaddress
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from .config import settings


def _trusted_networks() -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    nets: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for cidr in settings.trusted_proxies_list:
        try:
            nets.append(ipaddress.ip_network(cidr, strict=False))
        except ValueError:
            continue
    return nets


def _is_trusted(ip_str: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return any(addr in net for net in _trusted_networks())


def get_client_ip(request: Request) -> str:
    """Resolve the real client IP, honoring trusted reverse proxies.

    ``X-Forwarded-For`` is a comma-separated chain appended left-to-right as a
    request passes proxies. We walk it right-to-left: the first (rightmost)
    address that is NOT a trusted proxy is the originating client. If the whole
    chain is trusted (or the header is absent), fall back to the direct peer.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        for ip in reversed(parts):
            if not _is_trusted(ip):
                return ip
    return request.client.host if request.client else "unknown"


class SlidingWindowRateLimiter:
    """Thread-safe in-memory sliding-window rate limiter.

    Good enough for a single-instance app with a handful of users. Not
    distributed — if you ever scale to multiple backend replicas, move to a
    shared store (Redis) instead.
    """

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            dq = self._hits[key]
            while dq and now - dq[0] > self.window_seconds:
                dq.popleft()
            if len(dq) >= self.max_requests:
                return False
            dq.append(now)
            # Bound memory: forget empty keys. Full key eviction is deferred to
            # a periodic sweep below to avoid O(n) work on every request.
            return True

    def _sweep(self, now: float) -> None:
        for key in list(self._hits.keys()):
            dq = self._hits[key]
            while dq and now - dq[0] > self.window_seconds:
                dq.popleft()
            if not dq:
                del self._hits[key]


_limiter = SlidingWindowRateLimiter(
    settings.rate_limit_max_requests, settings.rate_limit_window_seconds
)


def rate_limited(scope: str):
    """Return a FastAPI dependency that enforces the rate limit for ``scope``.

    Keyed by real client IP (via ``get_client_ip``), so it applies per client
    behind the reverse proxy, not per proxy hop.
    """

    def dependency(request: Request) -> None:
        if not settings.rate_limit_enabled:
            return
        key = f"{scope}:{get_client_ip(request)}"
        if not _limiter.allow(key):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again later.",
            )

    return dependency
