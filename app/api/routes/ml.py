from fastapi import BackgroundTasks
from app.api.routes import api_router
from app.celery_tasks.tasks import enqueue, retrain_model_job


@api_router.post("/ml/retrain")
def retrain(sync=False, background_tasks: BackgroundTasks = None):
    if str(sync).lower() in ("1", "true", "yes"):
        return retrain_model_job()
    return {"status": "queued", "via": enqueue(retrain_model_job, background_tasks)}
