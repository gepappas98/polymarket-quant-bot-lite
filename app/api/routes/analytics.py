from typing import Optional

from fastapi import Query

from app.api.routes import api_router
from app.services.metrics_service import (
    feature_importance,
    leader_sparklines,
    volatility_series,
)


@api_router.get("/analytics/feature_importance")
def analytics_feature_importance(
    top_n: int = Query(default=10, ge=1, le=50),
    model: Optional[str] = Query(default=None),
):
    return feature_importance(top_n, model)


@api_router.get("/analytics/volatility/{market_slug}")
def analytics_volatility(market_slug: str, days: int = Query(default=7, ge=1, le=90)):
    return volatility_series(market_slug, days)


@api_router.get("/analytics/leader_sparklines")
def analytics_leader_sparklines(days: int = Query(default=7, ge=1, le=90)):
    return leader_sparklines(days)
