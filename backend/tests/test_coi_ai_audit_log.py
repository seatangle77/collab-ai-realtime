"""Isolated tests for the dedicated CoI AI coding audit log."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from backend.app.analysis import coi_ai_audit_log


def test_audit_log_writes_jsonl_and_protects_permissions(monkeypatch, tmp_path) -> None:
    log_dir = tmp_path / "coi-ai-coding"
    monkeypatch.setenv("COI_AI_AUDIT_LOG_DIR", str(log_dir))
    monkeypatch.setenv("COI_AI_AUDIT_LOG_ENABLED", "true")

    assert coi_ai_audit_log.write_coi_ai_audit({
        "request_id": "coia-test",
        "session_id": "session-test",
        "operation": "coding",
        "stage": "request",
        "units": [{"id": "u9", "content": "要不大家都说一下对应的字母。"}],
    })
    assert coi_ai_audit_log.write_coi_ai_audit({
        "request_id": "coia-test",
        "session_id": "session-test",
        "operation": "coding",
        "stage": "model_response",
        "raw_response": '{"results":[]}',
    })

    files = list(log_dir.glob("coi-ai-coding-*.jsonl"))
    assert len(files) == 1
    records = [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines()]
    assert [record["stage"] for record in records] == ["request", "model_response"]
    assert records[0]["units"][0]["content"] == "要不大家都说一下对应的字母。"
    assert files[0].stat().st_mode & 0o777 == 0o600
    assert log_dir.stat().st_mode & 0o777 == 0o700


def test_audit_log_rotates_every_four_hours_by_default(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("COI_AI_AUDIT_ROTATION_HOURS", raising=False)
    log_dir = tmp_path / "coi-ai-coding"
    timezone = ZoneInfo("Asia/Shanghai")

    before_boundary = coi_ai_audit_log._log_file_path(
        log_dir, datetime(2026, 8, 21, 7, 59, tzinfo=timezone),
    )
    after_boundary = coi_ai_audit_log._log_file_path(
        log_dir, datetime(2026, 8, 21, 8, 0, tzinfo=timezone),
    )

    assert before_boundary.name == "coi-ai-coding-20260821-04.jsonl"
    assert after_boundary.name == "coi-ai-coding-20260821-08.jsonl"


def test_audit_log_rotation_hours_can_be_configured(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("COI_AI_AUDIT_ROTATION_HOURS", "6")
    log_dir = tmp_path / "coi-ai-coding"
    now = datetime(2026, 8, 21, 17, 30, tzinfo=ZoneInfo("Asia/Shanghai"))

    assert coi_ai_audit_log._log_file_path(log_dir, now).name == (
        "coi-ai-coding-20260821-12.jsonl"
    )


def test_audit_log_removes_expired_files(monkeypatch, tmp_path) -> None:
    log_dir = tmp_path / "coi-ai-coding"
    log_dir.mkdir()
    expired = log_dir / "coi-ai-coding-20200101.jsonl"
    expired.write_text("{}\n", encoding="utf-8")
    old_time = time.time() - 3 * 24 * 60 * 60
    os.utime(expired, (old_time, old_time))

    monkeypatch.setenv("COI_AI_AUDIT_LOG_DIR", str(log_dir))
    monkeypatch.setenv("COI_AI_AUDIT_RETENTION_DAYS", "1")
    monkeypatch.setenv("COI_AI_AUDIT_LOG_ENABLED", "true")

    assert coi_ai_audit_log.write_coi_ai_audit({"stage": "request"})
    assert not expired.exists()


def test_audit_log_can_be_disabled(monkeypatch, tmp_path) -> None:
    log_dir = tmp_path / "coi-ai-coding"
    monkeypatch.setenv("COI_AI_AUDIT_LOG_DIR", str(log_dir))
    monkeypatch.setenv("COI_AI_AUDIT_LOG_ENABLED", "false")

    assert not coi_ai_audit_log.write_coi_ai_audit({"stage": "request"})
    assert not log_dir.exists()
