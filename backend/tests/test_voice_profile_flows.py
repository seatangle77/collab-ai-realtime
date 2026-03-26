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


def _register_and_login(label: str) -> Tuple[Dict[str, Any], str]:
    email = f"vp_{label}_{uuid.uuid4().hex[:6]}@example.com"
    password = "1234"
    r = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={
            "name": f"VP User {label} {RUN_ID}",
            "email": email,
            "password": password,
            "device_token": f"device-vp-{uuid.uuid4().hex[:8]}",
        },
    )
    r.raise_for_status()
    user = r.json()
    r_login = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password})
    r_login.raise_for_status()
    token = r_login.json()["access_token"]
    return user, token


def _auth(token: str) -> Dict[str, str]:
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
        headers=_auth(token),
        files={"file": ("sample.wav", io.BytesIO(wav_bytes), "audio/wav")},
    )
    if r_upload.status_code != 200:
        return False
    url = r_upload.json()["url"]
    r_put = requests.put(
        f"{BASE_URL}/api/voice-profile/me/samples",
        headers=_auth(token),
        json={"sample_audio_urls": [url]},
    )
    return r_put.status_code == 200


# ──────────────────────────────────────────────────────────────────
# A. GET /api/voice-profile/me
# ──────────────────────────────────────────────────────────────────

def scenario_get_me_unauth() -> bool:
    r = requests.get(f"{BASE_URL}/api/voice-profile/me")
    return _log(r.status_code == 401, "GET /me 未登录返回 401", {"status": r.status_code})


def scenario_get_me_autocreate() -> bool:
    """首次调用自动创建空档案，字段初始值正确。"""
    _, token = _register_and_login("GetMeCreate")
    r = requests.get(f"{BASE_URL}/api/voice-profile/me", headers=_auth(token))
    if r.status_code != 200:
        return _log(False, "GET /me 首次调用失败（期望 200）", {"status": r.status_code, "body": r.text})
    data = r.json()
    ok = True
    ok &= data.get("id", "").startswith("vp")
    ok &= isinstance(data.get("sample_audio_urls"), list) and len(data["sample_audio_urls"]) == 0
    ok &= data.get("voice_embedding") is None
    ok &= data.get("embedding_status") == "not_generated"
    ok &= "embedding_updated_at" in data
    ok &= data.get("embedding_updated_at") is None
    ok &= "created_at" in data
    return _log(ok, "GET /me 首次调用自动创建，初始字段值正确场景", data)


def scenario_get_me_idempotent() -> bool:
    """二次调用返回同一 id，不重复创建。"""
    _, token = _register_and_login("GetMeIdem")
    r1 = requests.get(f"{BASE_URL}/api/voice-profile/me", headers=_auth(token))
    r2 = requests.get(f"{BASE_URL}/api/voice-profile/me", headers=_auth(token))
    r1.raise_for_status(); r2.raise_for_status()
    ok = r1.json()["id"] == r2.json()["id"]
    return _log(ok, "GET /me 幂等，二次调用返回同一 id 场景", {"id1": r1.json()["id"], "id2": r2.json()["id"]})


def scenario_get_me_fields_complete() -> bool:
    """验证所有 VoiceProfileOut 字段都存在。"""
    _, token = _register_and_login("GetMeFields")
    r = requests.get(f"{BASE_URL}/api/voice-profile/me", headers=_auth(token))
    r.raise_for_status()
    data = r.json()
    required_fields = ["id", "user_id", "sample_audio_urls", "voice_embedding",
                       "embedding_status", "embedding_updated_at", "created_at"]
    ok = all(f in data for f in required_fields)
    return _log(ok, "GET /me 返回字段完整性验证场景", {f: (f in data) for f in required_fields})


# ──────────────────────────────────────────────────────────────────
# B. PUT /api/voice-profile/me/samples
# ──────────────────────────────────────────────────────────────────

def scenario_put_samples_unauth() -> bool:
    r = requests.put(
        f"{BASE_URL}/api/voice-profile/me/samples",
        json={"sample_audio_urls": ["https://example.com/a.wav"]},
    )
    return _log(r.status_code == 401, "PUT /me/samples 未登录返回 401", {"status": r.status_code})


def scenario_put_samples_normal() -> bool:
    _, token = _register_and_login("PutSamplesOk")
    urls = [f"https://example.com/{uuid.uuid4().hex[:6]}.wav" for _ in range(3)]
    r = requests.put(
        f"{BASE_URL}/api/voice-profile/me/samples",
        headers=_auth(token),
        json={"sample_audio_urls": urls},
    )
    if r.status_code != 200:
        return _log(False, "PUT /me/samples 正常更新失败（期望 200）", {"status": r.status_code, "body": r.text})
    data = r.json()
    ok = data.get("sample_audio_urls") == urls
    ok &= "embedding_status" in data
    ok &= "embedding_updated_at" in data
    return _log(ok, "PUT /me/samples 正常更新场景，返回字段完整", data)


def scenario_put_samples_empty_list() -> bool:
    """空列表全量清空样本，应返回 200。"""
    _, token = _register_and_login("PutSamplesEmpty")
    # 先写入 2 条
    requests.put(
        f"{BASE_URL}/api/voice-profile/me/samples",
        headers=_auth(token),
        json={"sample_audio_urls": ["https://example.com/a.wav", "https://example.com/b.wav"]},
    ).raise_for_status()
    # 清空
    r = requests.put(
        f"{BASE_URL}/api/voice-profile/me/samples",
        headers=_auth(token),
        json={"sample_audio_urls": []},
    )
    if r.status_code != 200:
        return _log(False, "PUT /me/samples 空列表清空失败（期望 200）", {"status": r.status_code, "body": r.text})
    ok = r.json().get("sample_audio_urls") == []
    return _log(ok, "PUT /me/samples 空列表全量清空场景", r.json())


def scenario_put_samples_exactly_five() -> bool:
    """恰好 5 条（边界值），应返回 200。"""
    _, token = _register_and_login("PutSamplesFive")
    urls = [f"https://example.com/s{i}.wav" for i in range(5)]
    r = requests.put(
        f"{BASE_URL}/api/voice-profile/me/samples",
        headers=_auth(token),
        json={"sample_audio_urls": urls},
    )
    ok = r.status_code == 200 and r.json().get("sample_audio_urls") == urls
    return _log(ok, "PUT /me/samples 恰好 5 条边界值场景", {"status": r.status_code})


def scenario_put_samples_too_many() -> bool:
    """6 条超限，应返回 400/422。"""
    _, token = _register_and_login("PutSamplesTooMany")
    urls = [f"https://example.com/x{i}.wav" for i in range(6)]
    r = requests.put(
        f"{BASE_URL}/api/voice-profile/me/samples",
        headers=_auth(token),
        json={"sample_audio_urls": urls},
    )
    ok = r.status_code in (400, 422)
    return _log(ok, "PUT /me/samples 超 5 条被拒绝场景", {"status": r.status_code})


# ──────────────────────────────────────────────────────────────────
# C. POST /api/voice-profile/me/generate-embedding
# ──────────────────────────────────────────────────────────────────

def scenario_generate_embedding_unauth() -> bool:
    r = requests.post(f"{BASE_URL}/api/voice-profile/me/generate-embedding")
    return _log(r.status_code == 401, "POST /me/generate-embedding 未登录返回 401", {"status": r.status_code})


def scenario_generate_embedding_no_samples() -> bool:
    _, token = _register_and_login("GenEmbNoSamples")
    # 确保档案存在但无样本
    requests.get(f"{BASE_URL}/api/voice-profile/me", headers=_auth(token)).raise_for_status()
    r = requests.post(f"{BASE_URL}/api/voice-profile/me/generate-embedding", headers=_auth(token))
    ok = r.status_code == 400
    return _log(ok, "POST /me/generate-embedding 无样本返回 400 场景", {"status": r.status_code, "body": r.text})


def scenario_generate_embedding_success() -> bool:
    _, token = _register_and_login("GenEmbOk")
    # 上传真实 WAV（Resemblyzer 需要可读取的本地文件，假 URL 会导致 400）
    if not _upload_real_wav_and_save(token):
        return _log(False, "准备真实音频样本失败", None)

    r = requests.post(f"{BASE_URL}/api/voice-profile/me/generate-embedding", headers=_auth(token))
    if r.status_code != 200:
        return _log(False, "POST /me/generate-embedding 失败（期望 200）", {"status": r.status_code, "body": r.text})
    data = r.json()
    ok = True
    ok &= data.get("embedding_status") == "ready"
    ok &= data.get("embedding_updated_at") is not None
    emb = data.get("voice_embedding")
    # voice_embedding 现在是 list[float]（256 维），不再是占位 dict
    ok &= isinstance(emb, list) and len(emb) == 256
    return _log(ok, "POST /me/generate-embedding 成功场景，字段验证", {
        "embedding_status": data.get("embedding_status"),
        "embedding_updated_at": data.get("embedding_updated_at"),
        "emb_len": len(emb) if isinstance(emb, list) else None,
    })


def scenario_generate_embedding_twice_updates_timestamp() -> bool:
    """连续调用两次，embedding_updated_at 应刷新（不同值）。"""
    import time
    _, token = _register_and_login("GenEmbTwice")
    # 上传真实 WAV（假 URL 会导致 400）
    if not _upload_real_wav_and_save(token):
        return _log(False, "准备真实音频样本失败", None)

    r1 = requests.post(f"{BASE_URL}/api/voice-profile/me/generate-embedding", headers=_auth(token))
    r1.raise_for_status()
    ts1 = r1.json().get("embedding_updated_at")

    time.sleep(1)  # 确保时间戳不同

    r2 = requests.post(f"{BASE_URL}/api/voice-profile/me/generate-embedding", headers=_auth(token))
    r2.raise_for_status()
    ts2 = r2.json().get("embedding_updated_at")

    ok = ts1 is not None and ts2 is not None and ts1 != ts2
    return _log(ok, "POST /me/generate-embedding 第二次调用 embedding_updated_at 刷新场景", {"ts1": ts1, "ts2": ts2})


# ──────────────────────────────────────────────────────────────────
# D. POST /api/voice-profile/me/upload-audio
# ──────────────────────────────────────────────────────────────────

def scenario_upload_audio_unauth() -> bool:
    dummy = io.BytesIO(b"RIFF....fakewav")
    r = requests.post(
        f"{BASE_URL}/api/voice-profile/me/upload-audio",
        files={"file": ("a.wav", dummy, "audio/wav")},
    )
    return _log(r.status_code == 401, "POST /me/upload-audio 未登录返回 401", {"status": r.status_code})


def scenario_upload_audio_invalid_mime() -> bool:
    _, token = _register_and_login("UploadBadMime")
    dummy = io.BytesIO(b"hello text")
    r = requests.post(
        f"{BASE_URL}/api/voice-profile/me/upload-audio",
        headers=_auth(token),
        files={"file": ("note.txt", dummy, "text/plain")},
    )
    ok = r.status_code == 400
    return _log(ok, "POST /me/upload-audio 不支持格式被拒绝场景", {"status": r.status_code})


def scenario_upload_audio_success() -> bool:
    user, token = _register_and_login("UploadOk")
    dummy = io.BytesIO(b"RIFF....fakewav")
    r = requests.post(
        f"{BASE_URL}/api/voice-profile/me/upload-audio",
        headers=_auth(token),
        files={"file": ("sample.wav", dummy, "audio/wav")},
    )
    if r.status_code != 200:
        return _log(False, "POST /me/upload-audio 成功上传失败（期望 200）", {"status": r.status_code, "body": r.text})
    data = r.json()
    url = data.get("url", "")
    ok = isinstance(url, str) and len(url) > 0
    ok &= "/audio/voice-profiles/" in url
    ok &= user["id"] in url
    return _log(ok, "POST /me/upload-audio 成功上传，url 含 user_id 场景", data)


def scenario_upload_audio_does_not_update_samples() -> bool:
    """上传成功后，GET /me 的 sample_audio_urls 不自动增加。"""
    _, token = _register_and_login("UploadNoAutoSample")
    # 先记录当前样本数
    r_before = requests.get(f"{BASE_URL}/api/voice-profile/me", headers=_auth(token))
    r_before.raise_for_status()
    count_before = len(r_before.json().get("sample_audio_urls", []))

    dummy = io.BytesIO(b"RIFF....fakewav")
    requests.post(
        f"{BASE_URL}/api/voice-profile/me/upload-audio",
        headers=_auth(token),
        files={"file": ("sample.wav", dummy, "audio/wav")},
    ).raise_for_status()

    r_after = requests.get(f"{BASE_URL}/api/voice-profile/me", headers=_auth(token))
    r_after.raise_for_status()
    count_after = len(r_after.json().get("sample_audio_urls", []))

    ok = count_before == count_after
    return _log(ok, "POST /me/upload-audio 上传后不自动更新 sample_audio_urls 场景", {"before": count_before, "after": count_after})


def scenario_upload_audio_full_samples() -> bool:
    """样本已满 5 条时上传被拒绝。"""
    _, token = _register_and_login("UploadFull")
    urls = [f"https://example.com/full{i}.wav" for i in range(5)]
    requests.put(
        f"{BASE_URL}/api/voice-profile/me/samples",
        headers=_auth(token),
        json={"sample_audio_urls": urls},
    ).raise_for_status()

    dummy = io.BytesIO(b"RIFF....fakewav")
    r = requests.post(
        f"{BASE_URL}/api/voice-profile/me/upload-audio",
        headers=_auth(token),
        files={"file": ("sample.wav", dummy, "audio/wav")},
    )
    ok = r.status_code == 400
    return _log(ok, "POST /me/upload-audio 样本已满 5 条被拒绝场景", {"status": r.status_code})


# ──────────────────────────────────────────────────────────────────
# Run all
# ──────────────────────────────────────────────────────────────────

def run_all() -> bool:
    print("=== 开始 Voice Profile 用户端接口测试 ===")

    ok = True
    # A. GET /me
    ok &= scenario_get_me_unauth()
    ok &= scenario_get_me_autocreate()
    ok &= scenario_get_me_idempotent()
    ok &= scenario_get_me_fields_complete()
    # B. PUT /me/samples
    ok &= scenario_put_samples_unauth()
    ok &= scenario_put_samples_normal()
    ok &= scenario_put_samples_empty_list()
    ok &= scenario_put_samples_exactly_five()
    ok &= scenario_put_samples_too_many()
    # C. POST /me/generate-embedding
    ok &= scenario_generate_embedding_unauth()
    ok &= scenario_generate_embedding_no_samples()
    ok &= scenario_generate_embedding_success()
    ok &= scenario_generate_embedding_twice_updates_timestamp()
    # D. POST /me/upload-audio
    ok &= scenario_upload_audio_unauth()
    ok &= scenario_upload_audio_invalid_mime()
    ok &= scenario_upload_audio_success()
    ok &= scenario_upload_audio_does_not_update_samples()
    ok &= scenario_upload_audio_full_samples()

    print("\n=== Voice Profile 用户端测试结果: {} ===".format("全部通过 ✅" if ok else "有失败 ❌"))
    return ok


if __name__ == "__main__":
    import sys
    sys.exit(0 if run_all() else 1)
