from fastapi import APIRouter

api_router = APIRouter(prefix="/api")
from . import status, risk, sizing, leaders, trades, strategies, ml, metrics, analytics  # noqa: E402,F401
