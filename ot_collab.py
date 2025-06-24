import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import List, Dict

app = FastAPI()

class ConnectionManager:
    def __init__(self):
        self.active: List[WebSocket] = []
        self.version = 0  # document version
        self.document = ""  # shared document state

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)
        # send full document and version to new client
        await ws.send_json({
            "type": "init",
            "version": self.version,
            "document": self.document,
            "clients": len(self.active)
        })

    def disconnect(self, ws: WebSocket):
        self.active.remove(ws)

    async def broadcast(self, msg: Dict):
        for conn in self.active:
            await conn.send_json(msg)

    def apply_op(self, op: Dict):
        """
        Simplified operational transform:
        op = {type: "insert"|"delete", pos: int, text: str}
        """
        t = op["type"]
        p = op["pos"]
        txt = op.get("text", "")
        if t == "insert":
            self.document = self.document[:p] + txt + self.document[p:]
        elif t == "delete":
            length = op.get("length", 1)
            self.document = self.document[:p] + self.document[p+length:]
        self.version += 1
        op["version"] = self.version

manager = ConnectionManager()

@app.websocket("/ws/ot")
async def ot_ws(ws: WebSocket):
    await manager.connect(ws)
    await manager.broadcast({"type": "presence", "count": len(manager.active)})
    try:
        while True:
            msg = await ws.receive_json()
            if msg["type"] == "op":
                client_ver = msg.get("version", 0)
                # ignore stale ops
                if client_ver != manager.version:
                    # TODO: implement proper OT transform here
                    await ws.send_json({
                        "type": "error",
                        "message": "Version mismatch",
                        "currentVersion": manager.version
                    })
                    continue
                manager.apply_op(msg)
                await manager.broadcast(msg)
    except WebSocketDisconnect:
        manager.disconnect(ws)
        await manager.broadcast({"type": "presence", "count": len(manager.active)})
if __name__ == "__main__":
    uvicorn.run("collab_app:app", host="127.0.0.1", port=8004, reload=True)
