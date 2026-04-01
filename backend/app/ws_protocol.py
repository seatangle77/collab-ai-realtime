from __future__ import annotations

from typing import Any


def build_connected(session_id: str) -> dict[str, Any]:
    return {
        "type": "connected",
        "data": {
            "session_id": session_id,
        },
    }


def build_pong() -> dict[str, Any]:
    return {
        "type": "pong",
        "data": {},
    }


def build_error(error_code: str, message: str) -> dict[str, Any]:
    return {
        "type": "error",
        "data": {
            "error_code": error_code,
            "message": message,
        },
    }


def build_audio_chunk_ack(seq: int) -> dict[str, Any]:
    return {
        "type": "audio_chunk_ack",
        "data": {
            "seq": seq,
            "accepted": True,
        },
    }


def build_transcript(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "transcript",
        "data": data,
    }


def build_engagement_alert(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "engagement_alert",
        "data": data,
    }


def build_session_ended(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "session_ended",
        "data": data,
    }


def build_push_notification(content: str, target_user_id: str) -> dict[str, Any]:
    return {
        "type": "push_notification",
        "data": {
            "content": content,
            "target_user_id": target_user_id,
        },
    }


def build_info_gap_button(buttons: list[dict[str, Any]]) -> dict[str, Any]:
    """
    buttons 每项格式：
    { "id": str, "keyword": str, "skw_score": float }
    """
    return {
        "type": "info_gap_button",
        "data": {
            "buttons": buttons,
        },
    }
