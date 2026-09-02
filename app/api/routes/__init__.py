from fastapi import APIRouter

api_router = APIRouter(prefix="/api")
from . import status, risk, sizing, leaders, trades, strategies, ml  # noqa: E402,F401
