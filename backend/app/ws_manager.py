from __future__ import annotations

import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)
WS_TRACE = "[WS_TRACE]"


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
            logger.warning(
                "%s [ws_send_to_user_miss] session_id=%s user_id=%s session_conn_count=%s user_conn_count=%s online_user_ids=%s",
                WS_TRACE,
                session_id,
                user_id,
                self.get_session_connection_count(session_id),
                self.get_user_connection_count(session_id),
                list(user_conns.keys()),
            )
            return False
        try:
            await ws.send_json(message)
            logger.info(
                "%s [ws_send_to_user_ok] session_id=%s user_id=%s message_type=%s",
                WS_TRACE,
                session_id,
                user_id,
                message.get("type"),
            )
            return True
        except Exception as exc:
            # 连接已断开，清理
            user_conns.pop(user_id, None)
            self.session_connections.get(session_id, set()).discard(ws)
            logger.warning(
                "%s [ws_send_to_user_error] session_id=%s user_id=%s message_type=%s error=%s",
                WS_TRACE,
                session_id,
                user_id,
                message.get("type"),
                str(exc),
            )
            return False

    def get_online_user_ids(self, session_id: str) -> list[str]:
        return list(self._user_connections.get(session_id, {}).keys())

    def get_session_connection_count(self, session_id: str) -> int:
        return len(self.session_connections.get(session_id, set()))

    def get_user_connection_count(self, session_id: str) -> int:
        return len(self._user_connections.get(session_id, {}))

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
