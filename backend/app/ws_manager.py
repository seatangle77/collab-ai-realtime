from __future__ import annotations

from typing import Any

from fastapi import WebSocket


class SessionWebSocketManager:
    """Session-scoped websocket connection manager."""

    def __init__(self) -> None:
        # session_id → set of all WebSocket connections (for broadcast)
        self.session_connections: dict[str, set[WebSocket]] = {}
        # session_id → user_id → WebSocket (for targeted send)
        self._user_connections: dict[str, dict[str, WebSocket]] = {}

    async def connect_session(self, session_id: str, websocket: WebSocket, user_id: str = "") -> None:
        await websocket.accept()
        if session_id not in self.session_connections:
            self.session_connections[session_id] = set()
        self.session_connections[session_id].add(websocket)
        if user_id:
            if session_id not in self._user_connections:
                self._user_connections[session_id] = {}
            self._user_connections[session_id][user_id] = websocket

    async def disconnect_session(self, session_id: str, websocket: WebSocket) -> None:
        conns = self.session_connections.get(session_id)
        if conns:
            conns.discard(websocket)
            if not conns:
                self.session_connections.pop(session_id, None)
        # 同步清理 user 映射
        user_conns = self._user_connections.get(session_id)
        if user_conns:
            stale_users = [uid for uid, ws in user_conns.items() if ws is websocket]
            for uid in stale_users:
                user_conns.pop(uid, None)
            if not user_conns:
                self._user_connections.pop(session_id, None)

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

    async def send_to_user(self, session_id: str, user_id: str, message: dict[str, Any]) -> bool:
        """向会话内指定用户发送消息，返回是否发送成功。"""
        user_conns = self._user_connections.get(session_id, {})
        ws = user_conns.get(user_id)
        if ws is None:
            return False
        try:
            await ws.send_json(message)
            return True
        except Exception:
            # 连接已断开，清理
            user_conns.pop(user_id, None)
            self.session_connections.get(session_id, set()).discard(ws)
            return False

    def get_online_user_ids(self, session_id: str) -> list[str]:
        return list(self._user_connections.get(session_id, {}).keys())

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
        self._user_connections.pop(session_id, None)


ws_manager = SessionWebSocketManager()
