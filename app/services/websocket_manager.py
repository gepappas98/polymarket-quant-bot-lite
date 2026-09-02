import asyncio


class ConnectionManager:
    def __init__(self):
        self.active_connections = []
        self.loop = None

    async def connect(self, websocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, payload):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(payload)
            except Exception:
                self.disconnect(connection)

    def broadcast_sync(self, payload):
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self.broadcast(payload), self.loop)


manager = ConnectionManager()
set_loop = lambda loop: setattr(manager, "loop", loop)
