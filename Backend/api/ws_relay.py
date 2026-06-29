"""
WebSocket Relay — WebSocket endpoint + client pool + broadcast.

Messages:
  Frontend -> Backend: {"type":"food_upload", "foods":[...]}
  Backend -> Frontend: {"type":"food_update", "foodItems":[...], "isSnapshot":true, "timestamp":"ISO8601"}
  Backend -> Frontend: {"type":"upload_status", "upload_id":"...", "status":"done|retrying"}
  Backend -> Frontend: {"type":"upload_failed", "upload_id":"...", "error":"..."}
"""
import json
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()

_clients: set[WebSocket] = set()
_on_upload = None
_on_connect_cb = None


def set_upload_handler(handler):
    """handler(foods) -> upload_id"""
    global _on_upload
    _on_upload = handler


def set_on_connect_handler(handler):
    global _on_connect_cb
    _on_connect_cb = handler


async def ws_fridge(websocket: WebSocket):
    await websocket.accept()
    _clients.add(websocket)
    logger.info(f"[WS Relay] Client connected, total={len(_clients)}")
    if _on_connect_cb:
        try:
            await _on_connect_cb(websocket)
        except Exception as e:
            logger.warning(f"[WS Relay] on_connect callback error: {e}")

    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
            elif data == '{"type":"request_sync"}':
                if _on_connect_cb:
                    await _on_connect_cb(websocket)
            elif data.startswith("{") and _on_upload:
                try:
                    msg = json.loads(data)
                    if msg.get("type") == "food_upload" and msg.get("foods") is not None:
                        upload_id = await _on_upload(msg["foods"])
                        await websocket.send_text(json.dumps({
                            "type": "ack", "ok": True,
                            "upload_id": upload_id, "status": "queued",
                        }, ensure_ascii=False))
                except Exception as e:
                    logger.warning(f"[WS Relay] Upload error: {e}")
                    try:
                        await websocket.send_text('{"type":"ack","ok":false}')
                    except Exception:
                        pass
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"[WS Relay] Client error: {e}")
    finally:
        _clients.discard(websocket)
        logger.info(f"[WS Relay] Client disconnected, total={len(_clients)}")


async def broadcast(data: dict):
    if not _clients:
        logger.warning("[WS Relay] broadcast skipped: no clients connected")
        return

    data.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    payload = json.dumps(data, ensure_ascii=False)
    dead = set()

    for ws in _clients.copy():
        try:
            await ws.send_text(payload)
        except Exception:
            dead.add(ws)

    for ws in dead:
        _clients.discard(ws)

    if dead:
        logger.info(f"[WS Relay] Cleaned {len(dead)} dead clients, remaining={len(_clients)}")


async def send_upload_status(upload_id: str, status: str, **extra):
    """发送上传状态通知给所有客户端"""
    payload = {
        "type": "upload_status",
        "upload_id": upload_id,
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    payload.update(extra)
    await broadcast(payload)


async def send_upload_failed(upload_id: str, error: str):
    """发送上传最终失败通知给所有客户端"""
    payload = {
        "type": "upload_failed",
        "upload_id": upload_id,
        "status": "dead",
        "error": error,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await broadcast(payload)
