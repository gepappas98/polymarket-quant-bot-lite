import asyncio
import os
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.core.database import init_db
from app.services.websocket_manager import manager, set_loop
from app.services.price_feed_service import CLOBPriceFeed
import app.models  # noqa: F401

app = FastAPI(title="polymarket-quant-bot-lite API", version="0.4.4")
_price_feed_task = None
origins = [x.strip() for x in os.getenv("API_CORS_ORIGINS", "*").split(",")]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=origins != ["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(api_router)


@app.get("/health")
def health():
    return {"ok": True}


@app.websocket("/api/ws")
async def websocket(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.on_event("startup")
async def startup():
    global _price_feed_task
    init_db()
    set_loop(asyncio.get_running_loop())
    if os.getenv("CLOB_PRICE_FEED_ENABLED", "false").lower() in {"1", "true", "yes", "on"}:
        _price_feed_task = asyncio.create_task(CLOBPriceFeed().run())


@app.on_event("shutdown")
async def shutdown():
    global _price_feed_task
    if _price_feed_task is not None:
        _price_feed_task.cancel()
        try:
            await _price_feed_task
        except asyncio.CancelledError:
            pass
        _price_feed_task = None


if __name__ == "__main__":
    uvicorn.run(app, host=os.getenv("API_HOST", "127.0.0.1"), port=int(os.getenv("API_PORT", "8000")))
