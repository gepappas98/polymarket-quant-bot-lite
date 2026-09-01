from datetime import datetime, timezone
from fastapi import BackgroundTasks, Depends
from app.api.routes import api_router
from app.core.database import get_db
from app.schemas.v04_schemas import LeaderOut
from app.services.scoring_service import get_leaders, refresh_leaderboard
from app.celery_tasks.tasks import enqueue, refresh_leaderboard_job


@api_router.get("/leaders", response_model=list[LeaderOut])
def leaders(limit=50, db=Depends(get_db)):
    return get_leaders(db, min(int(limit), 200))


@api_router.post("/leaders/refresh")
def refresh(sync=False, background_tasks: BackgroundTasks = None, db=Depends(get_db)):
    if str(sync).lower() in ("1", "true", "yes"):
        return {"status": "refreshed", "leaders": refresh_leaderboard(db)}
    return {"status": "queued", "via": enqueue(refresh_leaderboard_job, background_tasks)}
