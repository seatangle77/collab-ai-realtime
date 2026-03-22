from __future__ import annotations

from typing import Any

from fastapi import WebSocket


class SessionWebSocketManager:
    """Session-scoped websocket connection manager."""

    def __init__(self) -> None:
        self.session_connections: dict[str, set[WebSocket]] = {}

    async def connect_session(self, session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        if session_id not in self.session_connections:
            self.session_connections[session_id] = set()
        self.session_connections[session_id].add(websocket)

    async def disconnect_session(self, session_id: str, websocket: WebSocket) -> None:
        conns = self.session_connections.get(session_id)
        if not conns:
            return
        conns.discard(websocket)
        if not conns:
            self.session_connections.pop(session_id, None)

    async def broadcast_to_session(self, session_id: str, message: dict[str, Any]) -> None:
        conns = self.session_connections.get(session_id)
        if not conns:
            return
        stale: list[WebSocket] = []
        for conn in list(conns):
            try:
                await conn.send_json(message)
            except Exception:
                stale.append(conn)
        for conn in stale:
            conns.discard(conn)
        if not conns:
            self.session_connections.pop(session_id, None)

    async def close_session_connections(self, session_id: str, *, code: int, reason: str) -> None:
        conns = self.session_connections.get(session_id)
        if not conns:
            return
        for conn in list(conns):
            try:
                await conn.close(code=code, reason=reason)
            except Exception:
                # Closing a dead connection may raise; ignore and continue cleanup.
                pass
        self.session_connections.pop(session_id, None)


ws_manager = SessionWebSocketManager()
