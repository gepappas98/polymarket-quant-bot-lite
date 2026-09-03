from typing import Optional

from fastapi import Depends, Query

from app.api.routes import api_router
from app.core.database import get_db
from app.services.metrics_service import markets_snapshot, metrics_summary


@api_router.get("/metrics/summary")
def summary(db=Depends(get_db)):
    return metrics_summary(db)


@api_router.get("/markets/snapshot")
def snapshot(category: Optional[str] = Query(default=None), db=Depends(get_db)):
    return markets_snapshot(db, category)
