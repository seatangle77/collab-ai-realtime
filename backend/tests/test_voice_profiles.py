from __future__ import annotations

import io
import math
import struct
import uuid
from typing import Any, Dict, Tuple

import requests

BASE_URL = "http://127.0.0.1:8000"
RUN_ID = uuid.uuid4().hex[:6]


def _log(ok: bool, message: str, extra: Any | None = None) -> bool:
    prefix = "✅" if ok else "❌"
    print(f"{prefix} {message}")
    if not ok and extra is not None:
        print("   详情:", extra)
    return ok


def register_dummy_user_with_token(label: str) -> Tuple[Dict[str, Any], str]:
    """通过业务接口注册一个普通用户，并返回 (用户 JSON, access_token)。"""
    email = f"voice_profile_{label}_{uuid.uuid4().hex[:6]}@example.com"
    password = "1234"

    # 注册
    r = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={
            "name": f"Voice User {label} {RUN_ID}",
            "email": email,
            "password": password,
            "device_token": f"device-{label}-{uuid.uuid4().hex[:8]}",
        },
    )
    r.raise_for_status()
    user = r.json()

    # 登录获取 token
    r_login = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
    )
    r_login.raise_for_status()
    token = r_login.json()["access_token"]
    return user, token


def _auth_headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _make_minimal_wav(duration_secs: float = 1.5, sample_rate: int = 16000) -> bytes:
    """生成最小有效 WAV（单声道 440Hz 正弦波），供 Resemblyzer 可以真实处理。"""
    n_samples = int(duration_secs * sample_rate)
    samples = bytearray()
    for i in range(n_samples):
        val = int(16000 * math.sin(2 * math.pi * 440 * i / sample_rate))
        samples += struct.pack("<h", val)
    data = bytes(samples)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(data), b"WAVE",
        b"fmt ", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16,
        b"data", len(data),
    )
    return header + data


def _upload_real_wav_and_save(token: str) -> bool:
    """上传真实 WAV 并保存到样本列表，返回是否成功。"""
    wav_bytes = _make_minimal_wav()
    r_upload = requests.post(
        f"{BASE_URL}/api/voice-profile/me/upload-audio",
        headers=_auth_headers(token),
        files={"file": ("sample.wav", io.BytesIO(wav_bytes), "audio/wav")},
    )
    if r_upload.status_code != 200:
        return False
    url = r_upload.json()["url"]
    r_put = requests.put(
        f"{BASE_URL}/api/voice-profile/me/samples",
        headers=_auth_headers(token),
        json={"sample_audio_urls": [url]},
    )
    return r_put.status_code == 200


# ---------- 场景：GET /api/voice-profile/me ----------


def scenario_get_me_creates_profile_if_not_exists() -> bool:
    user, token = register_dummy_user_with_token("GetMeNew")

    r = requests.get(f"{BASE_URL}/api/voice-profile/me", headers=_auth_headers(token))
    if r.status_code != 200:
        return _log(False, "首次调用 /me 期望 200", {"status_code": r.status_code, "body": r.text})

    data = r.json()
    ok = True
    ok &= isinstance(data.get("id"), str)
    ok &= data.get("user_id") == user["id"]
    ok &= isinstance(data.get("sample_audio_urls"), list) and data.get("sample_audio_urls") == []
    ok &= data.get("voice_embedding") is None

    return _log(ok, "首次调用 /api/voice-profile/me 自动创建空配置场景", data)


def scenario_get_me_requires_auth() -> bool:
    r = requests.get(f"{BASE_URL}/api/voice-profile/me")
    ok = r.status_code in (401, 403)
    return _log(ok, "未带 token 调 /api/voice-profile/me 被拒绝场景", {"status_code": r.status_code, "body": r.text})


# ---------- 场景：PUT /api/voice-profile/me/samples ----------


def scenario_update_samples_creates_and_overwrites() -> bool:
    user, token = register_dummy_user_with_token("UpdateSamples")

    urls_first = [f"https://example.com/{uuid.uuid4().hex[:6]}.wav"]
    r1 = requests.put(
        f"{BASE_URL}/api/voice-profile/me/samples",
        headers=_auth_headers(token),
        json={"sample_audio_urls": urls_first},
    )
    if r1.status_code != 200:
        return _log(False, "首次更新样本失败（期望 200）", {"status_code": r1.status_code, "body": r1.text})
    data1 = r1.json()

    ok = True
    ok &= data1.get("user_id") == user["id"]
    ok &= data1.get("sample_audio_urls") == urls_first

    urls_second = [
        f"https://example.com/{uuid.uuid4().hex[:6]}_a.wav",
        f"https://example.com/{uuid.uuid4().hex[:6]}_b.wav",
    ]
    r2 = requests.put(
        f"{BASE_URL}/api/voice-profile/me/samples",
        headers=_auth_headers(token),
        json={"sample_audio_urls": urls_second},
    )
    if r2.status_code != 200:
        return _log(False, "第二次更新样本失败（期望 200）", {"status_code": r2.status_code, "body": r2.text})
    data2 = r2.json()

    ok &= data2.get("sample_audio_urls") == urls_second

    return _log(ok, "更新样本自动创建并全量覆盖场景", {"first": data1, "second": data2})


def scenario_update_samples_clear_list() -> bool:
    _, token = register_dummy_user_with_token("ClearSamples")

    urls = [f"https://example.com/{uuid.uuid4().hex[:6]}.wav"]
    r1 = requests.put(
        f"{BASE_URL}/api/voice-profile/me/samples",
        headers=_auth_headers(token),
        json={"sample_audio_urls": urls},
    )
    if r1.status_code != 200:
        return _log(False, "预先写入样本失败（期望 200）", {"status_code": r1.status_code, "body": r1.text})

    r2 = requests.put(
        f"{BASE_URL}/api/voice-profile/me/samples",
        headers=_auth_headers(token),
        json={"sample_audio_urls": []},
    )
    if r2.status_code != 200:
        return _log(False, "清空样本失败（期望 200）", {"status_code": r2.status_code, "body": r2.text})

    data = r2.json()
    ok = isinstance(data.get("sample_audio_urls"), list) and data.get("sample_audio_urls") == []
    return _log(ok, "清空样本列表场景", data)


def scenario_update_samples_too_many() -> bool:
    _, token = register_dummy_user_with_token("TooMany")

    urls = [f"https://example.com/{i}.wav" for i in range(11)]
    r = requests.put(
        f"{BASE_URL}/api/voice-profile/me/samples",
        headers=_auth_headers(token),
        json={"sample_audio_urls": urls},
    )
    ok = r.status_code in (400, 422)
    return _log(ok, "更新样本超过 10 条被拒绝场景", {"status_code": r.status_code, "body": r.text})


def scenario_update_samples_requires_auth() -> bool:
    r = requests.put(
        f"{BASE_URL}/api/voice-profile/me/samples",
        json={"sample_audio_urls": ["https://example.com/a.wav"]},
    )
    ok = r.status_code in (401, 403)
    return _log(ok, "未带 token 更新样本被拒绝场景", {"status_code": r.status_code, "body": r.text})


# ---------- 场景：POST /api/voice-profile/me/generate-embedding ----------


def scenario_generate_embedding_requires_samples() -> bool:
    _, token = register_dummy_user_with_token("GenNoSamples")

    r = requests.post(
        f"{BASE_URL}/api/voice-profile/me/generate-embedding",
        headers=_auth_headers(token),
    )
    ok = r.status_code == 400
    return _log(ok, "无样本直接生成声纹返回 400 场景", {"status_code": r.status_code, "body": r.text})


def scenario_generate_embedding_success_and_overwrite() -> bool:
    _, token = register_dummy_user_with_token("GenOk")

    # 上传真实 WAV（Resemblyzer 需要可读取的本地文件）
    if not _upload_real_wav_and_save(token):
        return _log(False, "准备真实音频样本失败", None)

    r1 = requests.post(
        f"{BASE_URL}/api/voice-profile/me/generate-embedding",
        headers=_auth_headers(token),
    )
    if r1.status_code != 200:
        return _log(False, "第一次生成声纹失败（期望 200）", {"status_code": r1.status_code, "body": r1.text})
    data1 = r1.json()
    emb1 = data1.get("voice_embedding")

    r2 = requests.post(
        f"{BASE_URL}/api/voice-profile/me/generate-embedding",
        headers=_auth_headers(token),
    )
    if r2.status_code != 200:
        return _log(False, "第二次生成声纹失败（期望 200）", {"status_code": r2.status_code, "body": r2.text})
    data2 = r2.json()
    emb2 = data2.get("voice_embedding")

    ok = True
    ok &= isinstance(emb1, list) and len(emb1) == 256
    ok &= isinstance(emb2, list) and len(emb2) == 256
    ok &= data1.get("embedding_status") == "ready"
    ok &= data2.get("embedding_status") == "ready"
    ok &= data1.get("embedding_updated_at") is not None
    ok &= data2.get("embedding_updated_at") is not None

    return _log(
        ok,
        "有样本成功生成并可覆盖更新声纹场景",
        {"emb1_len": len(emb1) if isinstance(emb1, list) else None,
         "emb2_len": len(emb2) if isinstance(emb2, list) else None},
    )


def scenario_generate_embedding_requires_auth() -> bool:
    r = requests.post(f"{BASE_URL}/api/voice-profile/me/generate-embedding")
    ok = r.status_code in (401, 403)
    return _log(ok, "未带 token 生成声纹被拒绝场景", {"status_code": r.status_code, "body": r.text})


# ---------- 场景：多用户隔离 ----------


def scenario_multi_user_isolation() -> bool:
    user_a, token_a = register_dummy_user_with_token("IsoA")
    user_b, token_b = register_dummy_user_with_token("IsoB")

    urls_a = [f"https://example.com/{uuid.uuid4().hex[:6]}_a.wav"]
    urls_b = [f"https://example.com/{uuid.uuid4().hex[:6]}_b.wav"]

    r_a = requests.put(
        f"{BASE_URL}/api/voice-profile/me/samples",
        headers=_auth_headers(token_a),
        json={"sample_audio_urls": urls_a},
    )
    r_b = requests.put(
        f"{BASE_URL}/api/voice-profile/me/samples",
        headers=_auth_headers(token_b),
        json={"sample_audio_urls": urls_b},
    )
    if r_a.status_code != 200 or r_b.status_code != 200:
        return _log(
            False,
            "多用户写入样本失败（期望均为 200）",
            {"a": {"status": r_a.status_code, "body": r_a.text}, "b": {"status": r_b.status_code, "body": r_b.text}},
        )

    m_a = requests.get(f"{BASE_URL}/api/voice-profile/me", headers=_auth_headers(token_a))
    m_b = requests.get(f"{BASE_URL}/api/voice-profile/me", headers=_auth_headers(token_b))
    if m_a.status_code != 200 or m_b.status_code != 200:
        return _log(
            False,
            "多用户读取样本失败（期望均为 200）",
            {"a": {"status": m_a.status_code, "body": m_a.text}, "b": {"status": m_b.status_code, "body": m_b.text}},
        )

    data_a = m_a.json()
    data_b = m_b.json()

    ok = True
    ok &= data_a.get("user_id") == user_a["id"]
    ok &= data_b.get("user_id") == user_b["id"]
    ok &= data_a.get("sample_audio_urls") == urls_a
    ok &= data_b.get("sample_audio_urls") == urls_b

    return _log(ok, "多用户声纹配置数据隔离场景", {"a": data_a, "b": data_b})


# ---------- 总入口 ----------


def run_all() -> bool:
    print("=== 开始 Voice Profiles 声纹配置接口测试 ===")

    ok = True
    ok &= scenario_get_me_creates_profile_if_not_exists()
    ok &= scenario_get_me_requires_auth()

    ok &= scenario_update_samples_creates_and_overwrites()
    ok &= scenario_update_samples_clear_list()
    ok &= scenario_update_samples_too_many()
    ok &= scenario_update_samples_requires_auth()

    ok &= scenario_generate_embedding_requires_samples()
    ok &= scenario_generate_embedding_success_and_overwrite()
    ok &= scenario_generate_embedding_requires_auth()

    ok &= scenario_multi_user_isolation()

    print("\n=== Voice Profiles 测试结果: {} ===".format("全部通过 ✅" if ok else "有失败 ❌"))
    return ok


if __name__ == "__main__":
    import sys

    sys.exit(0 if run_all() else 1)

