from __future__ import annotations

import io

import requests

from .test_voice_profiles import (
    BASE_URL,
    _auth_headers,
    _log,
    register_dummy_user_with_token,
)


def scenario_upload_audio_success() -> bool:
    user, token = register_dummy_user_with_token("UploadOk")

    dummy_audio = io.BytesIO(b"RIFF....fakewav")
    files = {
        "file": ("sample.wav", dummy_audio, "audio/wav"),
    }

    r = requests.post(
        f"{BASE_URL}/api/voice-profile/me/upload-audio",
        headers=_auth_headers(token),
        files=files,
    )
    if r.status_code != 200:
        return _log(
            False,
            "上传音频失败（期望 200）",
            {"status_code": r.status_code, "body": r.text},
        )

    data = r.json()
    url = data.get("url")

    ok = True
    ok &= isinstance(url, str) and len(url) > 0
    ok &= "/audio/voice-profiles/" in url
    ok &= user["id"] in url

    if not ok:
        return _log(False, "上传音频返回的 URL 不符合预期", data)

    # 使用返回的 URL 更新样本列表，并验证写入成功
    r_put = requests.put(
        f"{BASE_URL}/api/voice-profile/me/samples",
        headers=_auth_headers(token),
        json={"sample_audio_urls": [url]},
    )
    if r_put.status_code != 200:
        return _log(
            False,
            "使用上传 URL 更新样本失败（期望 200）",
            {"status_code": r_put.status_code, "body": r_put.text},
        )

    r_me = requests.get(
        f"{BASE_URL}/api/voice-profile/me",
        headers=_auth_headers(token),
    )
    if r_me.status_code != 200:
        return _log(
            False,
            "读取声纹配置失败（期望 200）",
            {"status_code": r_me.status_code, "body": r_me.text},
        )

    data_me = r_me.json()
    ok &= data_me.get("sample_audio_urls") == [url]

    # 通过后端提供的静态文件映射访问该 URL，验证本地环境下可直接播放
    r_file = requests.get(url)
    ok &= r_file.status_code == 200

    return _log(ok, "成功上传音频并将 URL 写入样本列表且可直接访问场景", {"profile": data_me, "file_status": r_file.status_code})


def scenario_upload_audio_creates_profile_if_missing() -> bool:
    """
    上传接口在用户尚无声纹配置时，也能正常工作并完成 profile 初始化。
    """
    user, token = register_dummy_user_with_token("UploadCreateProfile")

    dummy_audio = io.BytesIO(b"RIFF....fakewav")
    files = {
        "file": ("sample.wav", dummy_audio, "audio/wav"),
    }

    # 不预先调用 /me 或 /me/samples，直接上传
    r = requests.post(
        f"{BASE_URL}/api/voice-profile/me/upload-audio",
        headers=_auth_headers(token),
        files=files,
    )
    if r.status_code != 200:
        return _log(
            False,
            "在未显式创建声纹配置时上传音频失败（期望 200）",
            {"status_code": r.status_code, "body": r.text},
        )

    data = r.json()
    url = data.get("url")
    ok = isinstance(url, str) and len(url) > 0 and user["id"] in url

    # 此时 profile 应该已经存在，但样本列表仍为空（上传接口本身不写库）
    r_me = requests.get(
        f"{BASE_URL}/api/voice-profile/me",
        headers=_auth_headers(token),
    )
    if r_me.status_code != 200:
        return _log(
            False,
            "上传后读取声纹配置失败（期望 200）",
            {"status_code": r_me.status_code, "body": r_me.text},
        )

    data_me = r_me.json()
    ok &= data_me.get("user_id") == user["id"]
    ok &= isinstance(data_me.get("sample_audio_urls"), list)

    return _log(ok, "上传音频可触发自动创建声纹配置场景", {"upload": data, "me": data_me})


def scenario_upload_audio_multiple_under_limit() -> bool:
    """
    多次上传但总样本数低于上限时，upload 接口仍可正常使用。
    """
    _, token = register_dummy_user_with_token("UploadMulti")

    urls: list[str] = []
    for idx in range(2):
        dummy_audio = io.BytesIO(b"RIFF....fakewav")
        files = {
            "file": (f"sample{idx}.wav", dummy_audio, "audio/wav"),
        }
        r = requests.post(
            f"{BASE_URL}/api/voice-profile/me/upload-audio",
            headers=_auth_headers(token),
            files=files,
        )
        if r.status_code != 200:
            return _log(
                False,
                f"第 {idx + 1} 次上传音频失败（期望 200）",
                {"status_code": r.status_code, "body": r.text},
            )
        data = r.json()
        url = data.get("url")
        if not isinstance(url, str) or not url:
            return _log(False, "多次上传返回的 URL 非字符串或为空", data)
        urls.append(url)

    # 将两条 URL 一次性写入 samples
    r_put = requests.put(
        f"{BASE_URL}/api/voice-profile/me/samples",
        headers=_auth_headers(token),
        json={"sample_audio_urls": urls},
    )
    if r_put.status_code != 200:
        return _log(
            False,
            "多次上传后的样本列表写入失败（期望 200）",
            {"status_code": r_put.status_code, "body": r_put.text},
        )

    r_me = requests.get(
        f"{BASE_URL}/api/voice-profile/me",
        headers=_auth_headers(token),
    )
    if r_me.status_code != 200:
        return _log(
            False,
            "多次上传后读取声纹配置失败（期望 200）",
            {"status_code": r_me.status_code, "body": r_me.text},
        )

    data_me = r_me.json()
    ok = data_me.get("sample_audio_urls") == urls
    return _log(ok, "多次上传音频且总样本数未超限场景", data_me)


def scenario_upload_audio_requires_auth() -> bool:
    dummy_audio = io.BytesIO(b"RIFF....fakewav")
    files = {
        "file": ("sample.wav", dummy_audio, "audio/wav"),
    }

    r = requests.post(
        f"{BASE_URL}/api/voice-profile/me/upload-audio",
        files=files,
    )
    ok = r.status_code in (401, 403)
    return _log(
        ok,
        "未带 token 上传音频被拒绝场景",
        {"status_code": r.status_code, "body": r.text},
    )


def scenario_upload_audio_too_many_samples() -> bool:
    _, token = register_dummy_user_with_token("UploadTooMany")

    # 先写入 5 条样本
    urls = [f"https://example.com/{i}.wav" for i in range(5)]
    r_put = requests.put(
        f"{BASE_URL}/api/voice-profile/me/samples",
        headers=_auth_headers(token),
        json={"sample_audio_urls": urls},
    )
    if r_put.status_code != 200:
        return _log(
            False,
            "预写入 5 条样本失败（期望 200）",
            {"status_code": r_put.status_code, "body": r_put.text},
        )

    dummy_audio = io.BytesIO(b"RIFF....fakewav")
    files = {
        "file": ("sample.wav", dummy_audio, "audio/wav"),
    }

    r = requests.post(
        f"{BASE_URL}/api/voice-profile/me/upload-audio",
        headers=_auth_headers(token),
        files=files,
    )
    ok = r.status_code == 400
    return _log(
        ok,
        "已有 5 条样本时上传音频被拒绝场景",
        {"status_code": r.status_code, "body": r.text},
    )


def scenario_upload_audio_invalid_mime() -> bool:
    _, token = register_dummy_user_with_token("UploadBadMime")

    dummy = io.BytesIO(b"hello")
    files = {
        "file": ("note.txt", dummy, "text/plain"),
    }

    r = requests.post(
        f"{BASE_URL}/api/voice-profile/me/upload-audio",
        headers=_auth_headers(token),
        files=files,
    )
    ok = r.status_code == 400
    return _log(
        ok,
        "上传不支持的文件类型被拒绝场景",
        {"status_code": r.status_code, "body": r.text},
    )


def scenario_upload_audio_other_allowed_mime() -> bool:
    """
    使用允许的其它 MIME 类型（如 audio/mpeg）上传应当成功。
    """
    _, token = register_dummy_user_with_token("UploadMpeg")

    dummy_audio = io.BytesIO(b"ID3....fake-mp3")
    files = {
        "file": ("sample.mp3", dummy_audio, "audio/mpeg"),
    }

    r = requests.post(
        f"{BASE_URL}/api/voice-profile/me/upload-audio",
        headers=_auth_headers(token),
        files=files,
    )
    if r.status_code != 200:
        return _log(
            False,
            "使用 audio/mpeg 上传音频失败（期望 200）",
            {"status_code": r.status_code, "body": r.text},
        )

    data = r.json()
    url = data.get("url")
    ok = isinstance(url, str) and url.endswith(".mp3")
    return _log(ok, "使用 audio/mpeg 上传音频成功场景", data)


def scenario_upload_audio_missing_file_field() -> bool:
    """
    未提供 file 字段时，FastAPI 应返回 422。
    """
    _, token = register_dummy_user_with_token("UploadNoFile")

    r = requests.post(
        f"{BASE_URL}/api/voice-profile/me/upload-audio",
        headers=_auth_headers(token),
    )
    ok = r.status_code == 422
    return _log(
        ok,
        "未提供 file 字段上传音频返回 422 场景",
        {"status_code": r.status_code, "body": r.text},
    )


def run_all() -> bool:
    print("=== 开始 Voice Profiles 录音上传接口测试 ===")

    ok = True
    ok &= scenario_upload_audio_success()
    ok &= scenario_upload_audio_creates_profile_if_missing()
    ok &= scenario_upload_audio_multiple_under_limit()
    ok &= scenario_upload_audio_requires_auth()
    ok &= scenario_upload_audio_too_many_samples()
    ok &= scenario_upload_audio_invalid_mime()
    ok &= scenario_upload_audio_other_allowed_mime()
    ok &= scenario_upload_audio_missing_file_field()

    print(
        "\n=== Voice Profiles 录音上传测试结果: {} ===".format(
            "全部通过 ✅" if ok else "有失败 ❌"
        )
    )
    return ok


if __name__ == "__main__":
    import sys

    sys.exit(0 if run_all() else 1)

