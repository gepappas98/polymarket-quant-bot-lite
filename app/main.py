import asyncio
import os
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.core.database import init_db
from app.services.websocket_manager import manager, set_loop
import app.models  # noqa: F401

app = FastAPI(title="polymarket-quant-bot-lite API", version="0.4.0")
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
    init_db()
    set_loop(asyncio.get_running_loop())


if __name__ == "__main__":
    uvicorn.run(app, host=os.getenv("API_HOST", "127.0.0.1"), port=int(os.getenv("API_PORT", "8000")))
