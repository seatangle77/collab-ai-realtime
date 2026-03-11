from __future__ import annotations

import io
import uuid
from typing import Any, Dict, Tuple

import requests

BASE_URL = "http://127.0.0.1:8000"

ADMIN_KEY = "TestAdminKey123"
ADMIN_HEADERS = {"X-Admin-Token": ADMIN_KEY}


def _log(ok: bool, message: str, extra: Any | None = None) -> bool:
    prefix = "✅" if ok else "❌"
    print(f"{prefix} {message}")
    if not ok and extra is not None:
        print("   详情:", extra)
    return ok


def register_user_with_token(label: str) -> Tuple[Dict[str, Any], str]:
    email = f"admin_voice_{label}_{uuid.uuid4().hex[:6]}@example.com"
    password = "1234"

    r = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={
            "name": f"声纹用户-{label}",
            "email": email,
            "password": password,
            "device_token": f"device-{label}",
        },
    )
    r.raise_for_status()
    user = r.json()

    r_login = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
    )
    r_login.raise_for_status()
    token = r_login.json()["access_token"]
    return user, token


def _auth_headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_profile_with_samples(label: str, sample_count: int = 2) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    user, token = register_user_with_token(label)
    urls = [f"https://example.com/{uuid.uuid4().hex[:6]}.wav" for _ in range(sample_count)]

    r = requests.put(
        f"{BASE_URL}/api/voice-profile/me/samples",
        headers=_auth_headers(token),
        json={"sample_audio_urls": urls},
    )
    r.raise_for_status()
    profile = r.json()
    return user, profile


def scenario_admin_list_voice_profiles_basic() -> bool:
    user, profile = _create_profile_with_samples("ListBasic", sample_count=2)

    r = requests.get(
        f"{BASE_URL}/api/admin/voice-profiles",
        headers=ADMIN_HEADERS,
        params={"page": 1, "page_size": 20},
    )
    if r.status_code != 200:
        return _log(False, "admin 列出声纹配置失败（期望 200）", {"status_code": r.status_code, "body": r.text})

    data = r.json()
    items = data.get("items", [])
    meta = data.get("meta", {})

    found = None
    for item in items:
        if item.get("id") == profile["id"]:
            found = item
            break

    ok = True
    ok &= isinstance(items, list) and isinstance(meta, dict)
    ok &= found is not None
    if found:
        ok &= found.get("user_id") == user["id"]
        ok &= found.get("sample_count") == len(profile.get("sample_audio_urls", []))
        ok &= found.get("has_embedding") is False
        # 新增字段：用户名 / 邮箱 / 当前小组字段存在且类型合理（当前可能为空）
        ok &= "user_name" in found and "user_email" in found
        ok &= "primary_group_id" in found and "primary_group_name" in found

    return _log(ok, "admin 基础分页列出声纹配置场景", data)


def scenario_admin_filters_and_detail() -> bool:
    user, profile = _create_profile_with_samples("FilterDetail", sample_count=1)

    r = requests.get(
        f"{BASE_URL}/api/admin/voice-profiles",
        headers=ADMIN_HEADERS,
        params={"page": 1, "page_size": 20, "user_id": user["id"], "has_samples": True, "has_embedding": False},
    )
    if r.status_code != 200:
        return _log(False, "admin 按条件过滤声纹配置失败（期望 200）", {"status_code": r.status_code, "body": r.text})

    data = r.json()
    ids = {item["id"] for item in data.get("items", [])}
    ok = profile["id"] in ids
    ok &= _log(ok, "admin 按 user_id/has_samples/has_embedding 过滤声纹配置场景", data)

    r_detail = requests.get(
        f"{BASE_URL}/api/admin/voice-profiles/{profile['id']}",
        headers=ADMIN_HEADERS,
    )
    if r_detail.status_code != 200:
        return _log(False, "admin 获取声纹配置详情失败（期望 200）", {"status_code": r_detail.status_code, "body": r_detail.text})
    detail = r_detail.json()

    ok &= detail.get("profile", {}).get("id") == profile["id"]
    ok &= detail.get("profile", {}).get("user_id") == user["id"]
    ok &= isinstance(detail.get("profile", {}).get("sample_audio_urls"), list) and len(
        detail.get("profile", {}).get("sample_audio_urls") or []
    ) == 1
    # 详情中也应返回用户名称/邮箱字段
    ok &= detail.get("user_name") is not None or detail.get("user_email") is not None

    return _log(ok, "admin 获取声纹配置详情场景", detail)


def scenario_admin_update_samples_and_generate_embedding() -> bool:
    user, profile = _create_profile_with_samples("UpdateGen", sample_count=1)

    new_urls = [
        f"https://example.com/{uuid.uuid4().hex[:6]}_1.wav",
        f"https://example.com/{uuid.uuid4().hex[:6]}_2.wav",
    ]
    r_update = requests.put(
        f"{BASE_URL}/api/admin/voice-profiles/{profile['id']}/samples",
        headers=ADMIN_HEADERS,
        json={"sample_audio_urls": new_urls},
    )
    if r_update.status_code != 200:
        return _log(False, "admin 更新声纹样本列表失败（期望 200）", {"status_code": r_update.status_code, "body": r_update.text})
    updated = r_update.json()

    ok = updated.get("sample_audio_urls") == new_urls

    r_gen = requests.post(
        f"{BASE_URL}/api/admin/voice-profiles/{profile['id']}/generate-embedding",
        headers=ADMIN_HEADERS,
    )
    if r_gen.status_code != 200:
        return _log(False, "admin 触发生成声纹失败（期望 200）", {"status_code": r_gen.status_code, "body": r_gen.text})
    gen = r_gen.json()

    emb = gen.get("voice_embedding") or {}
    ok &= isinstance(emb, dict) and emb.get("generated_at") is not None

    return _log(ok, "admin 更新样本并生成声纹场景", {"updated": updated, "generated": gen})


def scenario_admin_update_samples_too_many() -> bool:
  """
  管理端通过 samples 接口一次性写入超过 5 条样本时应被拒绝。
  """
  _, profile = _create_profile_with_samples("AdminTooManySamples", sample_count=0)

  urls = [f"https://example.com/admin-too-many-{i}.wav" for i in range(6)]
  r_update = requests.put(
      f"{BASE_URL}/api/admin/voice-profiles/{profile['id']}/samples",
      headers=ADMIN_HEADERS,
      json={"sample_audio_urls": urls},
  )
  ok = r_update.status_code in (400, 422)
  return _log(
      ok,
      "admin 一次性写入超过 5 条样本被拒绝场景",
      {"status_code": r_update.status_code, "body": r_update.text},
  )


def scenario_admin_generate_embedding_without_samples() -> bool:
    user, token = register_user_with_token("GenNoSamplesAdmin")

    # 先确保 profile 存在但 sample_audio_urls 为空
    r_me = requests.get(
        f"{BASE_URL}/api/voice-profile/me",
        headers=_auth_headers(token),
    )
    r_me.raise_for_status()
    profile = r_me.json()

    r_admin = requests.post(
        f"{BASE_URL}/api/admin/voice-profiles/{profile['id']}/generate-embedding",
        headers=ADMIN_HEADERS,
    )
    ok = r_admin.status_code == 400
    return _log(ok, "admin 无样本生成声纹返回 400 场景", {"status_code": r_admin.status_code, "body": r_admin.text})


def scenario_admin_list_voice_profiles_no_results() -> bool:
    # 使用一个绝对不存在的 user_id 进行过滤，预期不返回任何记录
    r = requests.get(
        f"{BASE_URL}/api/admin/voice-profiles",
        headers=ADMIN_HEADERS,
        params={"page": 1, "page_size": 10, "user_id": "non-existent-user-id-xyz"},
    )
    if r.status_code != 200:
        return _log(False, "admin 过滤不存在 user_id 的声纹配置失败（期望 200）", {"status_code": r.status_code, "body": r.text})
    data = r.json()
    ok = data.get("meta", {}).get("total", -1) in (0, len(data.get("items", []))) and len(data.get("items", [])) == 0
    return _log(ok, "admin 按不存在 user_id 过滤声纹配置返回空结果场景", data)


def scenario_admin_flags_filters() -> bool:
    # 准备三类 profile：无样本 / 有样本但无 embedding / 有样本且已有 embedding
    _, profile_empty = _create_profile_with_samples("FlagEmpty", sample_count=0)
    user_no_emb, profile_no_emb = _create_profile_with_samples("FlagNoEmb", sample_count=1)
    user_with_emb, profile_with_emb = _create_profile_with_samples("FlagWithEmb", sample_count=1)

    # 为第三个配置先生成 embedding（走 app 端接口）
    r_login = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": user_with_emb["email"], "password": "1234"},
    )
    r_login.raise_for_status()
    token = r_login.json()["access_token"]
    r_generate = requests.post(
        f"{BASE_URL}/api/voice-profile/me/generate-embedding",
        headers=_auth_headers(token),
    )
    r_generate.raise_for_status()

    ok = True

    # has_samples=true 应至少包含 profile_no_emb 和 profile_with_emb，不包含 empty
    r_has_samples = requests.get(
        f"{BASE_URL}/api/admin/voice-profiles",
        headers=ADMIN_HEADERS,
        params={"page": 1, "page_size": 50, "has_samples": True},
    )
    if r_has_samples.status_code != 200:
        return _log(
            False,
            "admin 使用 has_samples=true 过滤声纹配置失败（期望 200）",
            {"status_code": r_has_samples.status_code, "body": r_has_samples.text},
        )
    data_samples = r_has_samples.json()
    ids_samples = {item["id"] for item in data_samples.get("items", [])}
    ok &= _log(
        profile_no_emb["id"] in ids_samples and profile_with_emb["id"] in ids_samples and profile_empty["id"] not in ids_samples,
        "admin has_samples=true 过滤场景",
        data_samples,
    )

    # has_samples=false 应至少包含 empty，不包含另外两个
    r_no_samples = requests.get(
        f"{BASE_URL}/api/admin/voice-profiles",
        headers=ADMIN_HEADERS,
        params={"page": 1, "page_size": 50, "has_samples": False},
    )
    if r_no_samples.status_code != 200:
        return _log(
            False,
            "admin 使用 has_samples=false 过滤声纹配置失败（期望 200）",
            {"status_code": r_no_samples.status_code, "body": r_no_samples.text},
        )
    data_no_samples = r_no_samples.json()
    ids_no_samples = {item["id"] for item in data_no_samples.get("items", [])}
    ok &= _log(
        profile_empty["id"] in ids_no_samples
        and profile_no_emb["id"] not in ids_no_samples
        and profile_with_emb["id"] not in ids_no_samples,
        "admin has_samples=false 过滤场景",
        data_no_samples,
    )

    # has_embedding=true 应至少包含 profile_with_emb，不包含前两个
    r_has_emb = requests.get(
        f"{BASE_URL}/api/admin/voice-profiles",
        headers=ADMIN_HEADERS,
        params={"page": 1, "page_size": 50, "has_embedding": True},
    )
    if r_has_emb.status_code != 200:
        return _log(
            False,
            "admin 使用 has_embedding=true 过滤声纹配置失败（期望 200）",
            {"status_code": r_has_emb.status_code, "body": r_has_emb.text},
        )
    data_has_emb = r_has_emb.json()
    ids_has_emb = {item["id"] for item in data_has_emb.get("items", [])}
    ok &= _log(
        profile_with_emb["id"] in ids_has_emb
        and profile_empty["id"] not in ids_has_emb
        and profile_no_emb["id"] not in ids_has_emb,
        "admin has_embedding=true 过滤场景",
        data_has_emb,
    )

    # has_embedding=false 应至少包含 empty 和 no_emb，不包含 with_emb
    r_no_emb = requests.get(
        f"{BASE_URL}/api/admin/voice-profiles",
        headers=ADMIN_HEADERS,
        params={"page": 1, "page_size": 50, "has_embedding": False},
    )
    if r_no_emb.status_code != 200:
        return _log(
            False,
            "admin 使用 has_embedding=false 过滤声纹配置失败（期望 200）",
            {"status_code": r_no_emb.status_code, "body": r_no_emb.text},
        )
    data_no_emb = r_no_emb.json()
    ids_no_emb = {item["id"] for item in data_no_emb.get("items", [])}
    ok &= _log(
        profile_empty["id"] in ids_no_emb
        and profile_no_emb["id"] in ids_no_emb
        and profile_with_emb["id"] not in ids_no_emb,
        "admin has_embedding=false 过滤场景",
        data_no_emb,
    )

    return ok


def scenario_admin_not_found_cases() -> bool:
    ok = True

    # 详情不存在
    r_detail = requests.get(
        f"{BASE_URL}/api/admin/voice-profiles/non-existent-profile-id-123",
        headers=ADMIN_HEADERS,
    )
    ok &= _log(r_detail.status_code == 404, "admin 获取不存在声纹配置详情返回 404 场景", {"status_code": r_detail.status_code, "body": r_detail.text})

    # 更新不存在
    r_update = requests.put(
        f"{BASE_URL}/api/admin/voice-profiles/non-existent-profile-id-456/samples",
        headers=ADMIN_HEADERS,
        json={"sample_audio_urls": ["https://example.com/a.wav"]},
    )
    ok &= _log(r_update.status_code == 404, "admin 更新不存在声纹配置样本返回 404 场景", {"status_code": r_update.status_code, "body": r_update.text})

    # 生成不存在
    r_gen = requests.post(
        f"{BASE_URL}/api/admin/voice-profiles/non-existent-profile-id-789/generate-embedding",
        headers=ADMIN_HEADERS,
    )
    ok &= _log(r_gen.status_code == 404, "admin 为不存在声纹配置生成 embedding 返回 404 场景", {"status_code": r_gen.status_code, "body": r_gen.text})

    return ok

def scenario_admin_missing_or_wrong_token() -> bool:
    ok = True

    r = requests.get(f"{BASE_URL}/api/admin/voice-profiles")
    ok &= _log(r.status_code == 403, "缺少 X-Admin-Token 访问声纹后台被禁止场景", {"status_code": r.status_code, "body": r.text})

    r2 = requests.get(
        f"{BASE_URL}/api/admin/voice-profiles",
        headers={"X-Admin-Token": "WrongKey"},
    )
    ok &= _log(r2.status_code == 403, "错误 X-Admin-Token 访问声纹后台被禁止场景", {"status_code": r2.status_code, "body": r2.text})

    return ok


def scenario_admin_upload_audio_success() -> bool:
    """
    管理端为已有声纹配置上传音频成功场景。
    """
    user, profile = _create_profile_with_samples("AdminUploadOk", sample_count=1)

    dummy_audio = io.BytesIO(b"RIFF....fakewav")
    files = {
        "file": ("sample.wav", dummy_audio, "audio/wav"),
    }

    r = requests.post(
        f"{BASE_URL}/api/admin/voice-profiles/{profile['id']}/upload-audio",
        headers=ADMIN_HEADERS,
        files=files,
    )
    if r.status_code != 200:
        return _log(
            False,
            "admin 上传音频失败（期望 200）",
            {"status_code": r.status_code, "body": r.text},
        )

    data = r.json()
    url = data.get("url")

    ok = True
    ok &= isinstance(url, str) and len(url) > 0
    ok &= "/audio/voice-profiles/" in url
    ok &= user["id"] in url

    # 验证 upload 接口本身不会修改样本列表，需要单独调用 samples 接口
    r_detail_before = requests.get(
        f"{BASE_URL}/api/admin/voice-profiles/{profile['id']}",
        headers=ADMIN_HEADERS,
    )
    r_detail_before.raise_for_status()
    profile_before = r_detail_before.json()["profile"]

    r_update = requests.put(
        f"{BASE_URL}/api/admin/voice-profiles/{profile['id']}/samples",
        headers=ADMIN_HEADERS,
        json={"sample_audio_urls": profile_before["sample_audio_urls"] + [url]},
    )
    if r_update.status_code != 200:
        return _log(
            False,
            "admin 使用上传 URL 更新样本失败（期望 200）",
            {"status_code": r_update.status_code, "body": r_update.text},
        )

    r_detail_after = requests.get(
        f"{BASE_URL}/api/admin/voice-profiles/{profile['id']}",
        headers=ADMIN_HEADERS,
    )
    r_detail_after.raise_for_status()
    profile_after = r_detail_after.json()["profile"]

    ok &= len(profile_after["sample_audio_urls"]) == len(profile_before["sample_audio_urls"]) + 1
    ok &= url in profile_after["sample_audio_urls"]

    return _log(ok, "admin 上传音频并通过 samples 接口写入样本列表场景", {"upload": data, "after": profile_after})


def scenario_admin_upload_audio_too_many_samples() -> bool:
    """
    管理端为已有 5 条样本的配置上传音频会被拒绝。
    """
    _, profile = _create_profile_with_samples("AdminUploadTooMany", sample_count=5)

    dummy_audio = io.BytesIO(b"RIFF....fakewav")
    files = {
        "file": ("sample.wav", dummy_audio, "audio/wav"),
    }

    r = requests.post(
        f"{BASE_URL}/api/admin/voice-profiles/{profile['id']}/upload-audio",
        headers=ADMIN_HEADERS,
        files=files,
    )
    ok = r.status_code == 400
    return _log(
        ok,
        "admin 为已满 5 条样本的配置上传音频被拒绝场景",
        {"status_code": r.status_code, "body": r.text},
    )


def scenario_admin_upload_audio_invalid_mime() -> bool:
    """
    管理端上传不支持的文件类型将被拒绝。
    """
    _, profile = _create_profile_with_samples("AdminUploadBadMime", sample_count=0)

    dummy = io.BytesIO(b"hello")
    files = {
        "file": ("note.txt", dummy, "text/plain"),
    }

    r = requests.post(
        f"{BASE_URL}/api/admin/voice-profiles/{profile['id']}/upload-audio",
        headers=ADMIN_HEADERS,
        files=files,
    )
    ok = r.status_code == 400
    return _log(
        ok,
        "admin 上传不支持的文件类型被拒绝场景",
        {"status_code": r.status_code, "body": r.text},
    )


def scenario_admin_upload_audio_not_found_or_unauthorized() -> bool:
    """
    管理端上传音频时，404 与鉴权错误的边界场景。
    """
    dummy_audio = io.BytesIO(b"RIFF....fakewav")
    files = {
        "file": ("sample.wav", dummy_audio, "audio/wav"),
    }

    ok = True

    # 不存在的 profile_id
    r_not_found = requests.post(
        f"{BASE_URL}/api/admin/voice-profiles/non-existent-profile-id-999/upload-audio",
        headers=ADMIN_HEADERS,
        files=files,
    )
    ok &= _log(
        r_not_found.status_code == 404,
        "admin 为不存在的声纹配置上传音频返回 404 场景",
        {"status_code": r_not_found.status_code, "body": r_not_found.text},
    )

    # 缺少 admin token
    r_no_token = requests.post(
        f"{BASE_URL}/api/admin/voice-profiles/non-existent-profile-id-999/upload-audio",
        files=files,
    )
    ok &= _log(
        r_no_token.status_code == 403,
        "缺少 X-Admin-Token 上传音频被禁止场景",
        {"status_code": r_no_token.status_code, "body": r_no_token.text},
    )

    # 错误 admin token
    r_bad_token = requests.post(
        f"{BASE_URL}/api/admin/voice-profiles/non-existent-profile-id-999/upload-audio",
        headers={"X-Admin-Token": "WrongKey"},
        files=files,
    )
    ok &= _log(
        r_bad_token.status_code == 403,
        "错误 X-Admin-Token 上传音频被禁止场景",
        {"status_code": r_bad_token.status_code, "body": r_bad_token.text},
    )

    return ok


def run_all() -> bool:
    print("=== 开始 Admin Voice Profiles 后台接口测试 ===")

    ok = True
    ok &= scenario_admin_list_voice_profiles_basic()
    ok &= scenario_admin_filters_and_detail()
    ok &= scenario_admin_update_samples_and_generate_embedding()
    ok &= scenario_admin_update_samples_too_many()
    ok &= scenario_admin_generate_embedding_without_samples()
    ok &= scenario_admin_list_voice_profiles_no_results()
    ok &= scenario_admin_flags_filters()
    ok &= scenario_admin_not_found_cases()
    ok &= scenario_admin_missing_or_wrong_token()
    ok &= scenario_admin_upload_audio_success()
    ok &= scenario_admin_upload_audio_too_many_samples()
    ok &= scenario_admin_upload_audio_invalid_mime()
    ok &= scenario_admin_upload_audio_not_found_or_unauthorized()

    print("\n=== Admin Voice Profiles 测试结果: {} ===".format("全部通过 ✅" if ok else "有失败 ❌"))
    return ok


if __name__ == "__main__":
    import sys

    sys.exit(0 if run_all() else 1)

