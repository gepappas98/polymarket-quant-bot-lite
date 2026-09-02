import os
from typing import Optional

from fastapi import Header, HTTPException

from bot.config import cfg


def require_api_token(
    authorization: Optional[str] = Header(default=None),
    x_api_key: Optional[str] = Header(default=None),
):
    expected = os.getenv("API_TOKEN", "")
    if expected:
        supplied = x_api_key
        if supplied is None and authorization:
            scheme, _, value = authorization.partition(" ")
            if scheme.lower() == "bearer":
                supplied = value
        if supplied != expected:
            raise HTTPException(401, "invalid API token")
        return expected
    if cfg.mode != "live":
        return None
    raise HTTPException(503, "API_TOKEN required in live mode")
