"""
极光推送客户端
- 使用官方 jpush SDK（已在 requirements.txt）
- send_push_to_registration_id：向单个设备 registration_id 发推送
- 从 async FastAPI 调用时请用 asyncio.to_thread() 包裹
"""
from __future__ import annotations

import logging

import jpush as jpush_sdk

from .settings import jpush_settings

logger = logging.getLogger(__name__)


def _get_push_client() -> jpush_sdk.JPush:
    if not jpush_settings.app_key or not jpush_settings.master_secret:
        raise RuntimeError("JPUSH_APP_KEY 或 JPUSH_MASTER_SECRET 未配置")
    return jpush_sdk.JPush(jpush_settings.app_key, jpush_settings.master_secret)


def send_push_to_registration_id(
    registration_id: str,
    content: str,
    title: str = "",
) -> dict:
    """
    向指定 registration_id 的设备发送极光推送通知。

    :param registration_id: 设备注册 ID（存储在 users_info.device_token）
    :param content: 推送正文（≤30字）
    :param title: 推送标题，默认空字符串
    :return: JPush API 响应 dict
    """
    client = _get_push_client()
    push = client.create_push()

    push.platform = jpush_sdk.platform("android")
    push.audience = jpush_sdk.audience(
        jpush_sdk.registration_id(registration_id)
    )
    push.notification = jpush_sdk.notification(
        android=jpush_sdk.android(alert=content, title=title),
    )
    push.options = {"time_to_live": 60}

    try:
        response = push.send()
        logger.info("JPush sent", extra={"registration_id": registration_id, "response": response})
        return response if isinstance(response, dict) else {"status": "ok"}
    except Exception as exc:
        logger.error("JPush failed", extra={"registration_id": registration_id, "error": str(exc)})
        raise
