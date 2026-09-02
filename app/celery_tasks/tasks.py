import os
from typing import Optional
from fastapi import BackgroundTasks
from app.core import database
from app.services.ml_service import retrain_model
from app.services.scoring_service import refresh_leaderboard
from app.ledger.reader import daily_pnl

try:
    from celery import Celery
    celery_app = Celery("polymarket", broker=os.getenv("CELERY_BROKER_URL")) if os.getenv("CELERY_BROKER_URL") else None
except ImportError:
    celery_app = None


def refresh_leaderboard_job():
    with database.SessionLocal() as db:
        return refresh_leaderboard(db)


def retrain_model_job():
    return retrain_model()


def health_check_job():
    with database.SessionLocal() as db:
        from app.services.risk_service import check_circuit_breaker
        return {"ok": True, "daily_pnl": daily_pnl(), "circuit_breaker": check_circuit_breaker(1, db).status}


def enqueue(job, background_tasks: Optional[BackgroundTasks]) -> str:
    if celery_app:
        celery_app.task(job).delay()
        return "celery"
    if background_tasks:
        background_tasks.add_task(job)
        return "background"
    job()
    return "inline"


if celery_app:
    refresh_leaderboard_job = celery_app.task(refresh_leaderboard_job)
    retrain_model_job = celery_app.task(retrain_model_job)
    health_check_job = celery_app.task(health_check_job)
