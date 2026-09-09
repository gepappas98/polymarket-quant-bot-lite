import os
import ipaddress
from typing import Optional

from fastapi import Header, HTTPException

from bot.config import cfg


def _token_is_mandatory() -> bool:
    """
    Return True when the process is in an environment where an unauthenticated
    mutating request would be reachable by untrusted callers:
      - MODE=live
      - ENV=production (or ENVIRONMENT=production)
      - API_HOST binds beyond the loopback range (anything other than 127.x or ::1)

    Paper mode on 127.0.0.1 / ::1 does NOT require a token so that local dev
    works out of the box without additional configuration.
    """
    if cfg.mode == "live":
        return True
    env = (os.getenv("ENV") or os.getenv("ENVIRONMENT") or "").lower()
    if env == "production":
        return True
    host = os.getenv("API_HOST", "127.0.0.1")
    try:
        addr = ipaddress.ip_address(host)
        if addr.is_loopback:
            return False
    except ValueError:
        # hostname (e.g. "0.0.0.0" parsed fine, but guard against DNS names)
        if host in ("localhost",):
            return False
    # 0.0.0.0, ::, any external address, or an unresolvable hostname → mandatory
    return True


def require_api_token(
    authorization: Optional[str] = Header(default=None),
    x_api_key: Optional[str] = Header(default=None),
):
    """
    Dependency injected on every mutating route.

    Token resolution order:
      1. X-Api-Key header
      2. Authorization: Bearer <token>

    Fail-closed rules:
      - If API_TOKEN is set: any mismatch → 401.
      - If API_TOKEN is not set and the route requires a token: → 503.
      - If API_TOKEN is not set and the route does NOT require a token: pass through.
    """
    expected = os.getenv("API_TOKEN", "")
    supplied: Optional[str] = x_api_key
    if supplied is None and authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer":
            supplied = value

    if expected:
        if supplied != expected:
            raise HTTPException(401, "invalid API token")
        return expected

    # No token configured — decide by environment.
    if _token_is_mandatory():
        raise HTTPException(
            503,
            "API_TOKEN must be set when MODE=live, ENV=production, "
            "or API_HOST binds beyond loopback",
        )
    return None
