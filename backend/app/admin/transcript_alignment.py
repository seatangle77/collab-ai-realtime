"""AI-assisted alignment for the transcript-corrections admin page.

``coi_utterances`` and ``speech_transcripts`` are strictly read-only here.  AI
results are kept in Redis (with an in-process fallback) until an administrator
explicitly saves selected suggestions into the existing correction tables.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import re
import uuid
from datetime import datetime, timezone
from difflib import SequenceMatcher
from statistics import median
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from openai import AsyncOpenAI
from pydantic import Field, field_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..api_model import ApiModel
from ..db import get_db
from ..redis_client import get_redis_client
from ..settings import QWEN_CHAT_EXTRA_BODY, nlp_settings
from .deps import require_admin
from .transcript_final_scope import final_scope_exclusions, scope_reason


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/admin/transcript-corrections",
    tags=["admin-transcript-alignment"],
    dependencies=[Depends(require_admin)],
)

ASSISTED_CONDITIONS = {"glasses", "app_notification"}
ALIGNMENT_RUN_TTL_SECONDS = 2 * 60 * 60
REFERENCE_CHUNK_SIZE = 20
MAX_LIVE_CANDIDATES_PER_CHUNK = 80
TIME_MARGIN_SECONDS = 20.0
AI_CORRECTION_REASON_PREFIX = "AI 整场匹配"
ALIGNMENT_LOGIC_VERSION = 5
_RUN_KEY_PREFIX = "admin:transcript-alignment:"
_LOCAL_RUNS: dict[str, dict[str, Any]] = {}
_LOCAL_RUNS_LOCK = asyncio.Lock()

RunStatus = Literal["queued", "running", "completed", "completed_with_errors", "failed"]
ConfidenceLevel = Literal["high", "medium", "low"]


class AlignmentAnchorIn(ApiModel):
    transcript_id: str = Field(min_length=1)
    transcript_relative_seconds: float
    reference_order: int
    reference_start_time: float


class StartAlignmentRunIn(ApiModel):
    anchor: AlignmentAnchorIn


class AiAlignmentMatchOut(ApiModel):
    match_id: str
    reference_orders: list[int]
    transcript_ids: list[str]
    reference_text: str
    transcript_text: str
    corrected_text: str
    confidence: float
    confidence_level: ConfidenceLevel
    time_distance_seconds: float | None = None
    reason: str = ""
    saved: bool = False
    review_required: bool = False
    review_reason: str = ""


class AlignmentRunSummaryOut(ApiModel):
    high: int = 0
    medium: int = 0
    low: int = 0
    unmatched_references: int = 0
    unmatched_transcripts: int = 0
    skipped_corrected_transcripts: int = 0
    replaceable_ai_transcripts: int = 0
    organized_transcripts: int = 0
    total_target_transcripts: int = 0
    review_required: int = 0
    out_of_scope_transcripts: int = 0


class AlignmentRunOut(ApiModel):
    run_id: str
    session_id: str
    model: str
    status: RunStatus
    completed_chunks: int
    total_chunks: int
    matches: list[AiAlignmentMatchOut] = Field(default_factory=list)
    summary: AlignmentRunSummaryOut = Field(default_factory=AlignmentRunSummaryOut)
    failed_chunks: list[int] = Field(default_factory=list)
    message: str = ""
    total_tokens: int = 0
    created_at: str
    out_of_scope_transcript_ids: list[str] = Field(default_factory=list)
    unmatched_transcript_ids: list[str] = Field(default_factory=list)
    unmatched_reference_orders: list[int] = Field(default_factory=list)
    excluded_transcript_ids: list[str] = Field(default_factory=list)


class SaveAlignmentRunIn(ApiModel):
    match_ids: list[str] = Field(min_length=1, max_length=2000)
    corrected_by: str | None = None

    @field_validator("match_ids")
    @classmethod
    def validate_match_ids(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if item.strip()]
        if not normalized:
            raise ValueError("至少选择一条 AI 匹配建议")
        if len(set(normalized)) != len(normalized):
            raise ValueError("AI 匹配建议不能重复")
        return normalized


class ResolveAlignmentBoundaryIn(ApiModel):
    match_id: str = Field(min_length=1)
    action: Literal["previous", "next", "keep"]


class SkippedAlignmentMatchOut(ApiModel):
    match_id: str
    reason: str


class SaveAlignmentRunOut(ApiModel):
    saved_matches: int
    saved_transcripts: int
    saved_match_ids: list[str]
    skipped: list[SkippedAlignmentMatchOut]


class UndoAlignmentRunOut(ApiModel):
    removed_matches: int
    removed_corrections: int


def _run_key(run_id: str) -> str:
    return f"{_RUN_KEY_PREFIX}{run_id}"


async def _store_run(run: dict[str, Any]) -> None:
    snapshot = json.loads(json.dumps(run, ensure_ascii=False))
    async with _LOCAL_RUNS_LOCK:
        _LOCAL_RUNS[run["run_id"]] = snapshot
    redis = get_redis_client()
    if redis is None:
        return
    try:
        await redis.set(
            _run_key(run["run_id"]),
            json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")),
            ex=ALIGNMENT_RUN_TTL_SECONDS,
        )
    except Exception as exc:  # pragma: no cover - cache fallback is intentional
        logger.warning("[transcript-alignment] Redis 写入失败，使用进程内缓存: %s", exc)


async def _load_run(run_id: str) -> dict[str, Any] | None:
    redis = get_redis_client()
    if redis is not None:
        try:
            raw = await redis.get(_run_key(run_id))
            if raw:
                return json.loads(raw)
        except Exception as exc:  # pragma: no cover - cache fallback is intentional
            logger.warning("[transcript-alignment] Redis 读取失败，使用进程内缓存: %s", exc)
    async with _LOCAL_RUNS_LOCK:
        run = _LOCAL_RUNS.get(run_id)
        return json.loads(json.dumps(run, ensure_ascii=False)) if run else None


def _strip_json_fence(raw: str) -> str:
    value = raw.strip()
    if value.startswith("```"):
        lines = value.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        value = "\n".join(lines).strip()
    return value


def _normalize_text(value: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]", "", value.lower())


def _is_ai_correction_reason(value: Any) -> bool:
    return str(value or "").startswith(AI_CORRECTION_REASON_PREFIX)


def _partition_existing_corrections(
    rows: list[dict[str, Any]],
) -> tuple[set[str], set[str]]:
    """Return replaceable AI correction IDs and blocking manual transcript IDs."""
    replaceable_ids: set[str] = set()
    blocking_transcript_ids: set[str] = set()
    for row in rows:
        correction_id = str(row.get("correction_id") or "").strip()
        transcript_id = str(row.get("transcript_id") or "").strip()
        if not correction_id or not transcript_id:
            continue
        if _is_ai_correction_reason(row.get("correction_reason")):
            replaceable_ids.add(correction_id)
        else:
            blocking_transcript_ids.add(transcript_id)
    return replaceable_ids, blocking_transcript_ids


def _are_consecutive(positions: list[int]) -> bool:
    ordered = sorted(set(positions))
    return bool(ordered) and ordered == list(range(ordered[0], ordered[-1] + 1))


def _relative_seconds(value: datetime | None, base: datetime | None) -> float | None:
    if value is None or base is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    return (value - base).total_seconds()


def _calibrate_live_times(references, live_items, alignment_offset_seconds):
    """Use corroborated, distinctive text anchors to account for clock drift.

    Only temporary matching coordinates change; source timestamps and the
    user's paired start anchor remain intact. Short/repeated phrases cannot
    establish a new offset, nor can an isolated coincidental text match.
    """
    candidates = []
    for ref in references:
        target = _normalize_text(ref["content"])
        if len(target) < 10 or ref["start_time"] is None:
            continue
        scored = sorted([
            (SequenceMatcher(None, target, _normalize_text(item["text"])).ratio(), item)
            for item in live_items
            if not item["is_corrected"] and item["relative_seconds"] is not None
            and abs(item["relative_seconds"] + alignment_offset_seconds - ref["start_time"]) <= 180
        ], key=lambda pair: pair[0], reverse=True)
        if not scored or scored[0][0] < .72:
            continue
        if len(scored) > 1 and scored[0][0] - scored[1][0] < .12:
            continue
        item = scored[0][1]
        candidates.append((item["relative_seconds"], ref["start_time"] - alignment_offset_seconds))
    anchors = []
    for source, target in sorted(candidates):
        if not any(0 < abs(other_source - source) <= 240
                   and abs((other_source - other_target) - (source - target)) <= 15
                   for other_source, other_target in candidates):
            continue
        if anchors and (source <= anchors[-1][0] or target <= anchors[-1][1]):
            continue
        anchors.append((source, target))
    if len(anchors) < 2:
        return [dict(item) for item in live_items]
    first_time = next((item["relative_seconds"] for item in live_items if item["relative_seconds"] is not None), None)
    if first_time is not None and first_time < anchors[0][0] and first_time < anchors[0][1]:
        anchors.insert(0, (first_time, first_time))
    result = []
    for item in live_items:
        copy = dict(item)
        copy["original_relative_seconds"] = item["relative_seconds"]
        time = item["relative_seconds"]
        if time is not None and not item["is_corrected"]:
            left = next((pair for pair in reversed(anchors) if pair[0] <= time), None)
            right = next((pair for pair in anchors if pair[0] >= time), None)
            if left and right and left[0] != right[0]:
                copy["relative_seconds"] = left[1] + (time - left[0]) * (right[1] - left[1]) / (right[0] - left[0])
            elif left:
                copy["relative_seconds"] = time - left[0] + left[1]
        result.append(copy)
    return result


def _build_chunks(
    references: list[dict[str, Any]],
    live_items: list[dict[str, Any]],
    alignment_offset_seconds: float,
    time_margin_seconds: float = TIME_MARGIN_SECONDS,
) -> list[dict[str, Any]]:
    available_live = [item for item in live_items if not item["is_corrected"]]
    chunks: list[dict[str, Any]] = []
    for start in range(0, len(references), REFERENCE_CHUNK_SIZE):
        chunk_refs = references[start:start + REFERENCE_CHUNK_SIZE]
        timed_refs = [item for item in chunk_refs if item["start_time"] is not None]
        candidates: list[dict[str, Any]] = []
        if timed_refs:
            expected_start = min(item["start_time"] for item in timed_refs) - alignment_offset_seconds
            expected_end = max(item["start_time"] for item in timed_refs) - alignment_offset_seconds
            candidates = [
                item for item in available_live
                if any(value is not None and expected_start - time_margin_seconds
                       <= value <= expected_end + time_margin_seconds
                       for value in (item["relative_seconds"], item.get("original_relative_seconds")))
            ]
        if not timed_refs and available_live:
            proportional_start = math.floor(start / max(len(references), 1) * len(available_live))
            candidates = available_live[
                max(0, proportional_start - 10):proportional_start + MAX_LIVE_CANDIDATES_PER_CHUNK
            ]
        if len(candidates) > MAX_LIVE_CANDIDATES_PER_CHUNK:
            midpoint = (
                sum(item["start_time"] for item in timed_refs) / len(timed_refs)
                - alignment_offset_seconds
            )
            candidates = sorted(
                candidates,
                key=lambda item: abs((item["relative_seconds"] or midpoint) - midpoint),
            )[:MAX_LIVE_CANDIDATES_PER_CHUNK]
            candidates.sort(key=lambda item: item["position"])
        chunks.append({"references": chunk_refs, "live_items": candidates})
    return chunks


def _partition_manual_sections(
    references: list[dict[str, Any]],
    live_items: list[dict[str, Any]],
    alignment_offset_seconds: float,
) -> list[dict[str, Any]]:
    """Separate AI work at verified manual ranges; never infer missing text.

    Manual corrections have no stored recording IDs. Only a unique, complete
    text match near the anchored time can establish their recording range.
    Ambiguous/edited text must be resolved by choosing a new paired anchor.
    """
    sections: list[dict[str, Any]] = []
    reference_cursor = live_cursor = index = 0
    seen: set[str] = set()
    error = (
        "无法明确确定人工修订对应的录音范围。请将实时转写和录音的对齐起点"
        "一起选在该人工修订之后，再重新整理；当前修订不会改变。"
    )
    normalized = [_normalize_text(item["content"]) for item in references]
    while index < len(live_items):
        item = live_items[index]
        if not item["is_corrected"]:
            index += 1
            continue
        correction_id = item.get("existing_correction_id")
        if not correction_id or correction_id in seen:
            raise ValueError(error)
        seen.add(correction_id)
        end = index + 1
        while end < len(live_items) and live_items[end].get("existing_correction_id") == correction_id:
            end += 1
        target = _normalize_text(item.get("manual_corrected_text") or "")
        candidates: list[tuple[int, int]] = []
        if target and item["relative_seconds"] is not None:
            for start in range(reference_cursor, len(references)):
                time = references[start]["start_time"]
                if time is None or abs(time - alignment_offset_seconds - item["relative_seconds"]) > TIME_MARGIN_SECONDS:
                    continue
                combined = ""
                for stop in range(start, len(references)):
                    combined += normalized[stop]
                    if combined == target:
                        candidates.append((start, stop + 1))
                    if len(combined) >= len(target):
                        break
        if len(candidates) != 1:
            raise ValueError(error)
        start, stop = candidates[0]
        section_refs = references[reference_cursor:start]
        section_live = live_items[live_cursor:index]
        if bool(section_refs) != bool(section_live):
            raise ValueError(error)
        if section_refs:
            sections.append({"references": section_refs, "live_items": section_live})
        reference_cursor, live_cursor, index = stop, end, end
    section_refs = references[reference_cursor:]
    section_live = live_items[live_cursor:]
    if section_refs and not section_live:
        raise ValueError(error)
    if section_live:
        sections.append({"references": section_refs, "live_items": section_live})
    return sections


def _score_match(
    references: list[dict[str, Any]],
    live_items: list[dict[str, Any]],
    model_confidence: float,
    alignment_offset_seconds: float,
) -> tuple[float, ConfidenceLevel, float | None]:
    reference_text = "".join(item["content"] for item in references)
    live_text = "".join(item["text"] for item in live_items)
    normalized_reference = _normalize_text(reference_text)
    normalized_live = _normalize_text(live_text)
    similarity = SequenceMatcher(None, normalized_reference, normalized_live).ratio()

    reference_time = next((item["start_time"] for item in references if item["start_time"] is not None), None)
    live_time = next((item["relative_seconds"] for item in live_items if item["relative_seconds"] is not None), None)
    distance: float | None = None
    time_score = 0.5
    if reference_time is not None and live_time is not None:
        distance = abs((reference_time - alignment_offset_seconds) - live_time)
        time_score = max(0.0, 1.0 - distance / 30.0)

    model_score = max(0.0, min(1.0, model_confidence))
    score = round(0.55 * model_score + 0.30 * similarity + 0.15 * time_score, 3)
    if score >= 0.82 and model_score >= 0.80 and (distance is None or distance <= 12.0):
        level: ConfidenceLevel = "high"
    elif score >= 0.60:
        level = "medium"
    else:
        level = "low"
    return score, level, round(distance, 2) if distance is not None else None


def _validate_model_matches(
    raw_matches: Any,
    chunk: dict[str, Any],
    all_references: list[dict[str, Any]],
    all_live_items: list[dict[str, Any]],
    alignment_offset_seconds: float,
    time_margin_seconds: float = TIME_MARGIN_SECONDS,
) -> list[dict[str, Any]]:
    if not isinstance(raw_matches, list):
        raise ValueError("模型未返回 matches 数组")
    references_by_order = {item["order_index"]: item for item in all_references}
    live_by_id = {item["transcript_id"]: item for item in all_live_items}
    allowed_reference_orders = {item["order_index"] for item in chunk["references"]}
    allowed_transcript_ids = {item["transcript_id"] for item in chunk["live_items"]}
    validated: list[dict[str, Any]] = []

    for raw in raw_matches:
        if not isinstance(raw, dict):
            continue
        try:
            reference_orders = [int(value) for value in raw.get("reference_orders", [])]
            transcript_ids = [str(value) for value in raw.get("transcript_ids", [])]
        except (TypeError, ValueError):
            continue
        reference_orders = list(dict.fromkeys(reference_orders))
        transcript_ids = list(dict.fromkeys(transcript_ids))
        if not reference_orders or not transcript_ids:
            continue
        if not set(reference_orders).issubset(allowed_reference_orders):
            continue
        if not set(transcript_ids).issubset(allowed_transcript_ids):
            continue
        selected_references = [references_by_order[value] for value in reference_orders]
        selected_live = [live_by_id[value] for value in transcript_ids]
        if any(item["is_corrected"] for item in selected_live):
            continue
        # These are provisional correspondence groups. Recording rows can
        # contain multiple speakers; split them before final validation/save.
        if not _are_consecutive([item["position"] for item in selected_references]):
            continue
        if not _are_consecutive([item["position"] for item in selected_live]):
            continue
        if any(
            ref["start_time"] is not None and not any(
                value is not None
                and abs(ref["start_time"] - alignment_offset_seconds - value) <= time_margin_seconds
                for item in selected_live
                for value in (item["relative_seconds"], item.get("original_relative_seconds"))
            )
            for ref in selected_references
        ):
            continue
        selected_references.sort(key=lambda item: item["position"])
        selected_live.sort(key=lambda item: item["position"])
        try:
            model_confidence = float(raw.get("confidence", 0.5))
        except (TypeError, ValueError):
            model_confidence = 0.5
        confidence, confidence_level, distance = _score_match(
            selected_references,
            selected_live,
            model_confidence,
            alignment_offset_seconds,
        )
        reference_orders = [item["order_index"] for item in selected_references]
        transcript_ids = [item["transcript_id"] for item in selected_live]
        reference_text = " ".join(item["content"].strip() for item in selected_references).strip()
        transcript_text = " ".join(item["text"].strip() for item in selected_live).strip()
        signature = json.dumps([reference_orders, transcript_ids], ensure_ascii=False)
        validated.append({
            "match_id": "aim" + hashlib.sha1(signature.encode("utf-8")).hexdigest()[:14],
            "reference_orders": reference_orders,
            "transcript_ids": transcript_ids,
            "reference_text": reference_text,
            "transcript_text": transcript_text,
            "corrected_text": reference_text,
            "confidence": confidence,
            "confidence_level": confidence_level,
            "time_distance_seconds": distance,
            "reason": str(raw.get("reason") or "").strip()[:300],
            "saved": False,
            "review_required": confidence_level == "low",
            "review_reason": "AI 对这处分组边界不够确定" if confidence_level == "low" else "",
            "_reference_position": selected_references[0]["position"],
            "_transcript_position": selected_live[0]["position"],
        })
    return validated


def _deduplicate_matches(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(
        matches,
        key=lambda item: (
            item["_reference_position"],
            item["_transcript_position"],
            -item["confidence"],
        ),
    )
    accepted: list[dict[str, Any]] = []
    used_references: set[int] = set()
    used_transcripts: set[str] = set()
    last_reference_position = -1
    last_transcript_position = -1
    for item in ordered:
        if used_references.intersection(item["reference_orders"]):
            continue
        if used_transcripts.intersection(item["transcript_ids"]):
            continue
        if item["_reference_position"] < last_reference_position:
            continue
        if item["_transcript_position"] < last_transcript_position:
            continue
        accepted.append({key: value for key, value in item.items() if not key.startswith("_")})
        used_references.update(item["reference_orders"])
        used_transcripts.update(item["transcript_ids"])
        last_reference_position = item["_reference_position"]
        last_transcript_position = item["_transcript_position"]
    return accepted


def _match_id(reference_orders: list[int], transcript_ids: list[str]) -> str:
    signature = json.dumps([reference_orders, transcript_ids], ensure_ascii=False)
    return "aim" + hashlib.sha1(signature.encode("utf-8")).hexdigest()[:14]


def _refresh_match_text(
    match: dict[str, Any],
    references_by_order: dict[int, dict[str, Any]],
    live_by_id: dict[str, dict[str, Any]],
) -> None:
    match["reference_orders"] = list(dict.fromkeys(match["reference_orders"]))
    match["transcript_ids"] = list(dict.fromkeys(match["transcript_ids"]))
    match["reference_text"] = "\n".join(
        references_by_order[order]["content"].strip()
        for order in match["reference_orders"]
        if order in references_by_order
    ).strip()
    match["transcript_text"] = " ".join(
        live_by_id[transcript_id]["text"].strip()
        for transcript_id in match["transcript_ids"]
        if transcript_id in live_by_id
    ).strip()
    match["corrected_text"] = match["reference_text"]
    match["match_id"] = _match_id(match["reference_orders"], match["transcript_ids"])
    speakers = {
        _speaker_key(live_by_id[transcript_id])
        for transcript_id in match["transcript_ids"]
        if transcript_id in live_by_id
    }
    if len(speakers) > 1:
        match["review_required"] = True
        match["review_reason"] = "这组跨越了说话人边界，请确认分组"


def _speaker_key(item: dict[str, Any]) -> str:
    return str(
        item.get("speaker_key") or item.get("speaker_name") or "未知说话人"
    ).strip() or "未知说话人"


def _has_single_speaker(
    transcript_ids: list[str],
    live_by_id: dict[str, dict[str, Any]],
) -> bool:
    return len({
        _speaker_key(live_by_id[transcript_id])
        for transcript_id in transcript_ids
        if transcript_id in live_by_id
    }) <= 1


def _estimated_live_recording_end(
    references: list[dict[str, Any]],
    alignment_offset_seconds: float,
) -> float | None:
    timed = [float(item["start_time"]) for item in references if item["start_time"] is not None]
    if not timed:
        return None
    gaps = [right - left for left, right in zip(timed, timed[1:]) if 0 < right - left <= 60]
    tail_allowance = max(30.0, min(90.0, (median(gaps) * 3) if gaps else 30.0))
    return timed[-1] - alignment_offset_seconds + tail_allowance


def _complete_alignment(
    matches: list[dict[str, Any]],
    references: list[dict[str, Any]],
    live_items: list[dict[str, Any]],
    alignment_offset_seconds: float,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Complete local timed gaps inside a section with no manual corrections."""
    if any(item["is_corrected"] for item in live_items):
        raise ValueError("必须先按人工修订边界分段，再补齐 AI 匹配")
    references_by_order = {item["order_index"]: item for item in references}
    live_by_id = {item["transcript_id"]: item for item in live_items}
    reference_positions = {item["order_index"]: item["position"] for item in references}
    live_positions = {item["transcript_id"]: item["position"] for item in live_items}
    available_live = [item for item in live_items if not item["is_corrected"]]

    recording_end = _estimated_live_recording_end(references, alignment_offset_seconds)
    matched_ids = {transcript_id for match in matches for transcript_id in match["transcript_ids"]}
    out_of_scope_ids = {
        item["transcript_id"]
        for item in available_live
        if item["transcript_id"] not in matched_ids
        and recording_end is not None
        and item["relative_seconds"] is not None
        and item["relative_seconds"] > recording_end
    }
    target_live = [item for item in available_live if item["transcript_id"] not in out_of_scope_ids]
    if not matches:
        return [], sorted(out_of_scope_ids, key=lambda item: live_positions[item])

    seeds: list[dict[str, Any]] = []
    for raw in matches:
        match = dict(raw)
        match.setdefault("review_required", match.get("confidence_level") == "low")
        match.setdefault("review_reason", "")
        match["_reference_start"] = min(reference_positions[order] for order in match["reference_orders"])
        match["_reference_end"] = max(reference_positions[order] for order in match["reference_orders"])
        match["_live_start"] = min(live_positions[item] for item in match["transcript_ids"])
        match["_live_end"] = max(live_positions[item] for item in match["transcript_ids"])
        seeds.append(match)
    seeds.sort(key=lambda item: (item["_reference_start"], item["_live_start"]))

    completed: list[dict[str, Any]] = []

    def new_gap(reference_gap: list[dict[str, Any]], live_gap: list[dict[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {
            "reference_orders": [item["order_index"] for item in reference_gap],
            "transcript_ids": [item["transcript_id"] for item in live_gap],
            "confidence": 0.5,
            "confidence_level": "medium",
            "time_distance_seconds": None,
            "reason": "系统已连续收拢 AI 遗漏的内容",
            "saved": False,
            "review_required": True,
            "review_reason": "AI 没有明确给出这处分界，请确认当前分组或并入相邻段",
        }
        _refresh_match_text(result, references_by_order, live_by_id)
        return result

    def absorb_gap(
        reference_gap: list[dict[str, Any]],
        live_gap: list[dict[str, Any]],
        next_seed: dict[str, Any] | None,
    ) -> None:
        if reference_gap and live_gap:
            if all(
                ref["start_time"] is not None and any(
                    item["relative_seconds"] is not None
                    and abs(ref["start_time"] - alignment_offset_seconds - item["relative_seconds"]) <= TIME_MARGIN_SECONDS
                    for item in live_gap
                )
                for ref in reference_gap
            ) and all(
                item["relative_seconds"] is not None and any(
                    ref["start_time"] is not None
                    and abs(ref["start_time"] - alignment_offset_seconds - item["relative_seconds"]) <= TIME_MARGIN_SECONDS
                    for ref in reference_gap
                )
                for item in live_gap
            ):
                completed.append(new_gap(reference_gap, live_gap))
            return
        if not reference_gap and not live_gap:
            return
        target = completed[-1] if completed else next_seed
        if target is None:
            return
        # A recording-only gap can be previously corrected text or a wrong
        # boundary. Keep it unmatched rather than appending it to another row.
        if reference_gap:
            return
        if live_gap:
            times = [references_by_order[order]["start_time"] for order in target["reference_orders"]]
            if any(
                item["relative_seconds"] is None or not any(
                    time is not None and abs(time - alignment_offset_seconds - item["relative_seconds"]) <= TIME_MARGIN_SECONDS
                    for time in times
                )
                for item in live_gap
            ):
                return
            ids = [item["transcript_id"] for item in live_gap]
            target["transcript_ids"] = (
                target["transcript_ids"] + ids if completed else ids + target["transcript_ids"]
            )
        target["review_required"] = True
        target["review_reason"] = "这里包含 AI 遗漏的残句或边界内容，请确认归属"
        _refresh_match_text(target, references_by_order, live_by_id)

    reference_cursor = 0
    live_cursor = 0
    for seed in seeds:
        reference_gap = [
            item for item in references
            if reference_cursor <= item["position"] < seed["_reference_start"]
        ]
        live_gap = [
            item for item in target_live
            if live_cursor <= item["position"] < seed["_live_start"]
        ]
        absorb_gap(reference_gap, live_gap, seed)
        for key in ("_reference_start", "_reference_end", "_live_start", "_live_end"):
            seed.pop(key, None)
        _refresh_match_text(seed, references_by_order, live_by_id)
        completed.append(seed)
        reference_cursor = max(reference_positions[order] for order in seed["reference_orders"]) + 1
        live_cursor = max(live_positions[item] for item in seed["transcript_ids"]) + 1

    reference_gap = [item for item in references if item["position"] >= reference_cursor]
    live_gap = [item for item in target_live if item["position"] >= live_cursor]
    absorb_gap(reference_gap, live_gap, None)

    return completed, sorted(out_of_scope_ids, key=lambda item: live_positions[item])


def _split_alignment_groups_by_reference(
    matches: list[dict[str, Any]],
    references: list[dict[str, Any]],
    live_items: list[dict[str, Any]],
    alignment_offset_seconds: float,
) -> list[dict[str, Any]]:
    """Keep the final revision segmented like the accurate recording text.

    A single accurate utterance may absorb multiple broken live ASR rows. When
    a coarse AI/gap group contains multiple accurate utterances and enough live
    rows, split it back into smaller monotonic groups using time (or position
    when timestamps are tied). A single live row cannot be split by the current
    correction schema, so that rare case keeps line breaks between references.
    """
    references_by_order = {item["order_index"]: item for item in references}
    live_by_id = {item["transcript_id"]: item for item in live_items}
    reference_position = {item["order_index"]: item["position"] for item in references}
    result: list[dict[str, Any]] = []

    for original in matches:
        reference_orders = sorted(
            original["reference_orders"],
            key=lambda order: reference_position.get(order, 0),
        )
        transcript_ids = original["transcript_ids"]
        if len(reference_orders) <= 1 or len(transcript_ids) <= 1:
            match = dict(original)
            _refresh_match_text(match, references_by_order, live_by_id)
            result.append(match)
            continue

        reference_times = [
            references_by_order[order]["start_time"] - alignment_offset_seconds
            if references_by_order[order]["start_time"] is not None else None
            for order in reference_orders
        ]
        live_times = [live_by_id[item]["relative_seconds"] for item in transcript_ids]
        usable_time = (
            all(value is not None for value in reference_times)
            and all(value is not None for value in live_times)
            and max(reference_times) - min(reference_times) > 0.5
            and max(live_times) - min(live_times) > 0.5
        )

        live_buckets: list[list[str]] = [[] for _ in reference_orders]
        previous_bucket = 0
        for index, transcript_id in enumerate(transcript_ids):
            if usable_time:
                live_time = float(live_times[index])
                bucket = min(
                    range(len(reference_orders)),
                    key=lambda value: abs(float(reference_times[value]) - live_time),
                )
            else:
                bucket = min(
                    len(reference_orders) - 1,
                    int((index + 0.5) * len(reference_orders) / len(transcript_ids)),
                )
            bucket = max(previous_bucket, bucket)
            live_buckets[bucket].append(transcript_id)
            previous_bucket = bucket

        reference_buckets: list[list[int]] = [[] for _ in reference_orders]
        populated = [index for index, bucket in enumerate(live_buckets) if bucket]
        for index, order in enumerate(reference_orders):
            target = index if live_buckets[index] else min(populated, key=lambda value: abs(value - index))
            reference_buckets[target].append(order)

        for index in populated:
            match = dict(original)
            match["reference_orders"] = reference_buckets[index]
            match["transcript_ids"] = live_buckets[index]
            if len(reference_buckets[index]) > 1:
                match["review_required"] = True
                match["review_reason"] = "多条录音句只对应到同一条实时转写，已保留原文换行"
            _refresh_match_text(match, references_by_order, live_by_id)
            result.append(match)

    result.sort(key=lambda item: reference_position.get(item["reference_orders"][0], 0))
    return result


def _map_live_boundary_to_reference(
    live_text: str,
    reference_text: str,
    live_boundary: int,
) -> int | None:
    """Map a normalized live-text boundary onto the normalized reference text."""
    if not live_text or not reference_text:
        return None
    matcher = SequenceMatcher(None, live_text, reference_text, autojunk=False)
    blocks = [block for block in matcher.get_matching_blocks() if block.size]
    if not blocks:
        return None
    for block in blocks:
        if block.a <= live_boundary <= block.a + block.size:
            return block.b + (live_boundary - block.a)
    previous = next(
        (block for block in reversed(blocks) if block.a + block.size < live_boundary),
        None,
    )
    following = next((block for block in blocks if block.a > live_boundary), None)
    if previous and following:
        live_gap = following.a - (previous.a + previous.size)
        reference_gap = following.b - (previous.b + previous.size)
        offset = live_boundary - (previous.a + previous.size)
        ratio = offset / live_gap if live_gap > 0 else 0.0
        return round(previous.b + previous.size + reference_gap * ratio)
    if previous:
        return min(
            len(reference_text),
            previous.b + previous.size + live_boundary - (previous.a + previous.size),
        )
    if following:
        return max(0, following.b - (following.a - live_boundary))
    return None


def _split_text_by_weights(
    value: str,
    weights: list[int],
    live_texts: list[str] | None = None,
) -> list[str]:
    """Split one exact text stream into ordered slices near natural boundaries."""
    if not weights:
        return []
    text_value = value.strip()
    if len(weights) == 1:
        return [text_value]
    if not text_value:
        return [""] * len(weights)

    normalized_weights = [max(1, int(weight)) for weight in weights]
    total_weight = sum(normalized_weights)
    normalized_reference = _normalize_text(text_value)
    normalized_live_parts = [_normalize_text(item) for item in (live_texts or [])]
    normalized_live = "".join(normalized_live_parts)
    reference_character_ends = [
        index + 1
        for index, character in enumerate(text_value)
        if _normalize_text(character)
    ]
    boundaries = [0]
    consumed_weight = 0
    consumed_live_characters = 0
    text_length = len(text_value)
    non_whitespace_positions = [
        position for position, character in enumerate(text_value) if not character.isspace()
    ]
    can_make_every_slice_nonblank = len(non_whitespace_positions) >= len(normalized_weights)
    strong_boundaries = set("。！？!?；;\n")
    soft_boundaries = set("，,、：: ")

    for index, weight in enumerate(normalized_weights[:-1]):
        consumed_weight += weight
        proportional_target = round(text_length * consumed_weight / total_weight)
        if len(normalized_live_parts) == len(normalized_weights):
            consumed_live_characters += len(normalized_live_parts[index])
        mapped_normalized = _map_live_boundary_to_reference(
            normalized_live,
            normalized_reference,
            consumed_live_characters,
        ) if normalized_live and consumed_live_characters else None
        if mapped_normalized is None or not reference_character_ends:
            target = proportional_target
        elif mapped_normalized <= 0:
            target = 0
        elif mapped_normalized >= len(reference_character_ends):
            target = text_length
        else:
            target = reference_character_ends[mapped_normalized - 1]
        remaining_parts = len(normalized_weights) - index - 1
        if can_make_every_slice_nonblank:
            first_available_character = next(
                position
                for position in non_whitespace_positions
                if position >= boundaries[-1]
            )
            minimum = first_available_character + 1
            maximum = non_whitespace_positions[-remaining_parts]
        else:
            minimum = boundaries[-1] + (1 if text_length >= len(normalized_weights) else 0)
            maximum = text_length - (remaining_parts if text_length >= len(normalized_weights) else 0)
        target = max(minimum, min(maximum, target))

        radius = max(6, min(24, text_length // 8))
        candidates = range(max(minimum, target - radius), min(maximum, target + radius) + 1)

        def boundary_score(position: int) -> tuple[int, int]:
            previous = text_value[position - 1] if position > 0 else ""
            following = text_value[position] if position < text_length else ""
            boundary_bonus = 0
            if previous in strong_boundaries:
                boundary_bonus = 12
            elif previous in soft_boundaries or following.isspace():
                boundary_bonus = 6
            elif previous.isalnum() and following.isalnum():
                boundary_bonus = -4
            return (abs(position - target) - boundary_bonus, position)

        boundaries.append(min(candidates, key=boundary_score))

    boundaries.append(text_length)
    return [
        text_value[left:right].strip()
        for left, right in zip(boundaries, boundaries[1:])
    ]


def _split_alignment_groups_by_speaker(
    matches: list[dict[str, Any]],
    references: list[dict[str, Any]],
    live_items: list[dict[str, Any]],
    alignment_offset_seconds: float,
) -> list[dict[str, Any]]:
    """Split accurate text at live speaker boundaries without losing coverage.

    The recording transcript is treated as an accurate ordered text stream, not
    as a source of speaker boundaries.  Each contiguous live-speaker run gets an
    exact slice of that stream.  The slices are later verified together before
    saving, so no source words can be silently dropped or duplicated.
    """
    references_by_order = {item["order_index"]: item for item in references}
    live_by_id = {item["transcript_id"]: item for item in live_items}
    result: list[dict[str, Any]] = []

    for original in matches:
        transcript_ids = [
            transcript_id
            for transcript_id in original["transcript_ids"]
            if transcript_id in live_by_id
        ]
        if not transcript_ids:
            continue
        if _has_single_speaker(transcript_ids, live_by_id):
            match = dict(original)
            if match.get("review_reason") == "这组跨越了说话人边界，请确认分组":
                match["review_required"] = False
                match["review_reason"] = ""
                match["reason"] = "系统已按实时说话人边界拆分"
            _refresh_match_text(match, references_by_order, live_by_id)
            result.append(match)
            continue

        speaker_runs: list[list[str]] = []
        for transcript_id in transcript_ids:
            if (
                not speaker_runs
                or _speaker_key(live_by_id[speaker_runs[-1][-1]])
                != _speaker_key(live_by_id[transcript_id])
            ):
                speaker_runs.append([transcript_id])
            else:
                speaker_runs[-1].append(transcript_id)

        reference_orders = list(original["reference_orders"])
        source_text = "\n".join(
            references_by_order[order]["content"].strip()
            for order in reference_orders
            if order in references_by_order
        ).strip()
        live_weights = [
            max(1, len(_normalize_text(" ".join(
                live_by_id[transcript_id]["text"] for transcript_id in run
            ))))
            for run in speaker_runs
        ]
        run_texts = [
            " ".join(live_by_id[transcript_id]["text"] for transcript_id in run)
            for run in speaker_runs
        ]
        text_slices = _split_text_by_weights(source_text, live_weights, run_texts)
        split_id = "ais" + hashlib.sha1(json.dumps(
            [reference_orders, transcript_ids], ensure_ascii=False
        ).encode("utf-8")).hexdigest()[:14]

        for index, run in enumerate(speaker_runs):
            match = dict(original)
            match["reference_orders"] = reference_orders
            match["transcript_ids"] = run
            match["review_required"] = False
            match["review_reason"] = ""
            match["reason"] = "系统已按实时说话人边界切分准确录音文字"
            _refresh_match_text(match, references_by_order, live_by_id)
            match["reference_text"] = text_slices[index]
            match["corrected_text"] = text_slices[index]
            match["_reference_source_text"] = source_text
            match["_reference_split_id"] = split_id
            match["_reference_piece_index"] = index
            match["_reference_piece_count"] = len(speaker_runs)
            result.append(match)

    return result


def _split_source_error(matches: list[dict[str, Any]]) -> str | None:
    split_groups: dict[str, list[dict[str, Any]]] = {}
    for match in matches:
        split_id = match.get("_reference_split_id")
        if split_id:
            split_groups.setdefault(str(split_id), []).append(match)

    for pieces in split_groups.values():
        expected_count = int(pieces[0].get("_reference_piece_count", 0))
        expected_source = str(pieces[0].get("_reference_source_text", ""))
        if expected_count <= 0 or len(pieces) != expected_count:
            return "说话人切分后的准确文字段落数量不完整"
        if any(str(item.get("_reference_source_text", "")) != expected_source for item in pieces):
            return "说话人切分后的准确文字来源不一致"
        ordered = sorted(pieces, key=lambda item: int(item.get("_reference_piece_index", -1)))
        indexes = [int(item.get("_reference_piece_index", -1)) for item in ordered]
        if indexes != list(range(expected_count)):
            return "说话人切分后的准确文字顺序不完整"
        rebuilt = "".join(str(item.get("corrected_text", "")) for item in ordered)
        if re.sub(r"\s+", "", rebuilt) != re.sub(r"\s+", "", expected_source):
            return "说话人切分后的准确文字存在遗漏或重复"
    return None


def _alignment_structure_error(
    matches: list[dict[str, Any]],
    references: list[dict[str, Any]],
    live_items: list[dict[str, Any]],
    out_of_scope_transcript_ids: list[str],
) -> str | None:
    if any(not str(match.get("corrected_text", "")).strip() for match in matches):
        return "存在空白修订文字"
    references_by_order = {item["order_index"]: item for item in references}
    for match in matches:
        if match.get("_reference_split_id"):
            continue
        expected_text = "\n".join(
            references_by_order[order]["content"].strip()
            for order in match["reference_orders"]
            if order in references_by_order
        ).strip()
        if str(match.get("corrected_text", "")) != expected_text:
            return "修订正文不是录音转译原文"
    live_by_id = {item["transcript_id"]: item for item in live_items}
    expected_ids = {
        item["transcript_id"]
        for item in live_items
        if not item["is_corrected"]
        and item["transcript_id"] not in set(out_of_scope_transcript_ids)
    }
    assigned_ids = [
        transcript_id for match in matches for transcript_id in match["transcript_ids"]
    ]
    if len(assigned_ids) != len(set(assigned_ids)):
        return "实时转写被重复分配到多个修订段落"
    if not set(assigned_ids).issubset(expected_ids):
        return "修订引用了不属于当前对齐范围的实时转写"
    if any(not _has_single_speaker(match["transcript_ids"], live_by_id) for match in matches):
        return "仍存在跨说话人的修订段落"
    expected_reference_orders = {item["order_index"] for item in references}
    reference_matches: dict[int, list[dict[str, Any]]] = {}
    for match in matches:
        for order in match["reference_orders"]:
            reference_matches.setdefault(order, []).append(match)
    if set(reference_matches) != expected_reference_orders:
        return "准确录音文字存在未分配段落"
    for owners in reference_matches.values():
        if len(owners) <= 1:
            continue
        split_ids = {item.get("_reference_split_id") for item in owners}
        if None in split_ids or len(split_ids) != 1:
            return "准确录音文字被重复分配到多个修订段落"
    return _split_source_error(matches)


def _summary(
    matches: list[dict[str, Any]],
    references: list[dict[str, Any]],
    live_items: list[dict[str, Any]],
    out_of_scope_transcript_ids: list[str] | None = None,
) -> dict[str, int]:
    matched_references = {
        order for item in matches for order in item["reference_orders"]
    }
    matched_transcripts = {
        transcript_id for item in matches for transcript_id in item["transcript_ids"]
    }
    available_live = [item for item in live_items if not item["is_corrected"]]
    out_of_scope_ids = set(out_of_scope_transcript_ids or [])
    processed_transcripts = len(matched_transcripts | out_of_scope_ids)
    return {
        "high": sum(item["confidence_level"] == "high" for item in matches),
        "medium": sum(item["confidence_level"] == "medium" for item in matches),
        "low": sum(item["confidence_level"] == "low" for item in matches),
        "unmatched_references": len(references) - len(matched_references),
        "unmatched_transcripts": max(0, len(available_live) - processed_transcripts),
        "skipped_corrected_transcripts": sum(item["is_corrected"] for item in live_items),
        "replaceable_ai_transcripts": sum(
            bool(item.get("has_ai_correction")) for item in live_items
        ),
        "organized_transcripts": processed_transcripts,
        "total_target_transcripts": len(available_live),
        "review_required": sum(bool(item.get("review_required")) for item in matches),
        "out_of_scope_transcripts": len(out_of_scope_ids),
    }


def _build_prompt(chunk: dict[str, Any], alignment_offset_seconds: float) -> str:
    references = [
        {
            "order": item["order_index"],
            "time": item["start_time"],
            "text": item["content"],
        }
        for item in chunk["references"]
    ]
    live_items = [
        {
            "id": item["transcript_id"],
            "time": item["relative_seconds"],
            "original_time": item.get("original_relative_seconds", item["relative_seconds"]),
            "speaker": item["speaker_name"],
            "text": item["text"],
        }
        for item in chunk["live_items"]
    ]
    return (
        "请把准确录音文本与错误较多、可能被拆碎的实时转写按语义进行连续对齐。\n"
        "准确录音文本是最终正文的唯一来源，禁止改写；实时转写文字只用于判断对应关系、顺序和说话人。\n"
        "约束：\n"
        "1. 匹配只能按给定顺序向后推进，不能倒序。\n"
        "2. 优先保持每条准确录音文本为一个最终段落；一条准确文本可以对应连续多条实时转写碎片。\n"
        "3. 同一条内容最多使用一次，不能跨越未包含的中间实时转写。\n"
        "4. 实时残句、重复和识别噪声只能作为对应来源归入同一说话人的相邻组，绝不能进入 corrected_text。\n"
        "5. 时间仅用于限制候选，语义和连续上下文共同决定对应关系。\n"
        "6. 这里输出的是临时对应组：一段录音含多人发言时，可以包含连续的不同 speaker，系统随后会按说话人拆分最终段落；不要因此漏掉录音句或实时碎片。\n"
        "7. confidence 必须是 0 到 1 的数字，reason 用简短中文说明。\n"
        "8. 对每段录音给出最可能的说话人 speaker_guesses，即使未能精确匹配。根据上下文、发言顺序和候选转写判断，只能从候选中的 speaker 名称选择一个，不要留空或创造姓名。\n"
        "严格返回 JSON，不要输出 Markdown 或其他文字：\n"
        '{"matches":[{"reference_orders":[1],"transcript_ids":["id"],'
        '"confidence":0.95,"reason":"语义和时间一致"}],"speaker_guesses":[{"reference_order":1,"speaker_name":"候选中的姓名"}]}\n\n'
        + ("本段是在补查遗漏。请重新核对整段连续对应，允许一组包含多段录音及多条实时转写；"
         "尤其检查长句、残句和跨说话人内容，不要只返回最容易匹配的短句。"
         "仍须语义相关；无法确认的内容不得强行拼接。返回本段完整 matches，保留已能确认的对应。"
         f"待查录音编号：{chunk.get('repair_missing_references', [])}；"
         f"待查转写编号：{chunk.get('repair_missing_transcripts', [])}\n"
         if 'repair_missing_references' in chunk else "")
        + f"时间偏移（录音时间 - 实时时间）：{alignment_offset_seconds:.3f} 秒\n"
        f"准确录音文本：{json.dumps(references, ensure_ascii=False)}\n"
        f"实时转写候选：{json.dumps(live_items, ensure_ascii=False)}"
    )


async def _call_alignment_model(
    client: AsyncOpenAI,
    chunk: dict[str, Any],
    alignment_offset_seconds: float,
) -> tuple[Any, int]:
    response = await client.chat.completions.create(
        model=nlp_settings.transcript_alignment_model,
        max_tokens=6000,
        temperature=0,
        extra_body=QWEN_CHAT_EXTRA_BODY,
        messages=[
            {
                "role": "system",
                "content": "你是严格的中文语音转写对齐器，只返回符合要求的 JSON。",
            },
            {"role": "user", "content": _build_prompt(chunk, alignment_offset_seconds)},
        ],
    )
    raw = response.choices[0].message.content or ""
    parsed = json.loads(_strip_json_fence(raw))
    if isinstance(parsed, dict):
        names = {item['speaker_name'] for item in chunk['live_items']}
        orders = {item['order_index'] for item in chunk['references']}
        guesses = parsed.get('speaker_guesses', [])
        chunk['speaker_guesses'] = {
            str(item['reference_order']): item['speaker_name']
            for item in guesses if isinstance(item, dict)
            and isinstance(item.get('reference_order'), int) and item['reference_order'] in orders
            and isinstance(item.get('speaker_name'), str) and item['speaker_name'] in names
        } if isinstance(guesses, list) else {}
    usage = getattr(response, "usage", None)
    total_tokens = int(getattr(usage, "total_tokens", 0) or 0)
    return parsed.get("matches") if isinstance(parsed, dict) else None, total_tokens


def _adopt_repair(existing, replacement, references, live_items):
    """A repair may expand coverage, never erase or duplicate prior matches."""
    new_refs = {o for m in replacement for o in m["reference_orders"]}
    new_live = {i for m in replacement for i in m["transcript_ids"]}
    affected = [m for m in existing if new_refs.intersection(m["reference_orders"])
                or new_live.intersection(m["transcript_ids"])]
    old_refs = {o for m in affected for o in m["reference_orders"]}
    old_live = {i for m in affected for i in m["transcript_ids"]}
    if not old_refs.issubset(new_refs) or not old_live.issubset(new_live):
        return existing
    if not (new_refs - old_refs or new_live - old_live):
        return existing
    combined = [m for m in existing if m not in affected] + replacement
    rp = {r["order_index"]: r["position"] for r in references}
    lp = {t["transcript_id"]: t["position"] for t in live_items}
    combined.sort(key=lambda m: min(rp[o] for o in m["reference_orders"]))
    last_ref = last_live = -1
    for match in combined:
        ref_positions = [rp[o] for o in match["reference_orders"]]
        live_positions = [lp[i] for i in match["transcript_ids"]]
        if min(ref_positions) <= last_ref or min(live_positions) <= last_live:
            return existing
        last_ref, last_live = max(ref_positions), max(live_positions)
    return combined


async def _repair_missing_matches(client, existing, section, offset, progress):
    """One bounded repair pass over incomplete chunks, using broader context."""
    refs, live = section["references"], section["live_items"]
    for index, chunk in enumerate(_build_chunks(refs, live, offset, time_margin_seconds=90)):
        used_refs = {o for m in existing for o in m["reference_orders"]}
        used_live = {i for m in existing for i in m["transcript_ids"]}
        missing_refs = [r["order_index"] for r in chunk["references"] if r["order_index"] not in used_refs]
        # Only count the chunk's central time range, not its overlapping context.
        times = [r["start_time"] - offset for r in chunk["references"] if r["start_time"] is not None]
        missing_live = [t["transcript_id"] for t in chunk["live_items"] if t["transcript_id"] not in used_live
                        and times and t["relative_seconds"] is not None and min(times) <= t["relative_seconds"] <= max(times)]
        if not chunk["live_items"] or not missing_refs:
            continue
        chunk = {**chunk, "repair_missing_references": missing_refs, "repair_missing_transcripts": missing_live}
        await progress(f"正在补查遗漏段落 {index + 1}：{len(missing_refs)} 段录音、{len(missing_live)} 条转写")
        try:
            raw, tokens = await _call_alignment_model(client, chunk, offset)
            replacement = _deduplicate_matches(_validate_model_matches(raw, chunk, refs, live, offset, time_margin_seconds=90))
            existing = _adopt_repair(existing, replacement, refs, live)
            await progress(None, tokens)
        except Exception as exc:
            logger.warning("[transcript-alignment] gap repair failed chunk=%d type=%s", index, type(exc).__name__)
    return existing


async def _execute_alignment_run(
    run_id: str,
    references: list[dict[str, Any]],
    live_items: list[dict[str, Any]],
    alignment_offset_seconds: float,
) -> None:
    run = await _load_run(run_id)
    if not run:
        return
    run["status"] = "running"
    run["message"] = "正在准备分段匹配"
    await _store_run(run)
    sections = _partition_manual_sections(references, live_items, alignment_offset_seconds)
    for section in sections:
        section["live_items"] = _calibrate_live_times(section["references"], section["live_items"], alignment_offset_seconds)
    calibrated = {item["transcript_id"]: item for section in sections for item in section["live_items"]}
    live_items = [calibrated.get(item["transcript_id"], item) for item in live_items]
    references = [ref for section in sections for ref in section["references"]]
    chunks = [
        chunk for section in sections
        for chunk in _build_chunks(section["references"], section["live_items"], alignment_offset_seconds)
    ]
    client = AsyncOpenAI(
        api_key=nlp_settings.qwen_api_key,
        base_url=nlp_settings.qwen_base_url,
        timeout=60.0,
        max_retries=0,
    )
    all_matches: list[dict[str, Any]] = []
    try:
        for index, chunk in enumerate(chunks, start=1):
            run["message"] = f"正在匹配第 {index}/{len(chunks)} 段"
            await _store_run(run)
            if not chunk["live_items"]:
                run["completed_chunks"] = index
                await _store_run(run)
                continue
            try:
                raw_matches, tokens = await _call_alignment_model(
                    client,
                    chunk,
                    alignment_offset_seconds,
                )
                run.setdefault('speaker_guesses', {}).update(chunk.get('speaker_guesses', {}))
                all_matches.extend(_validate_model_matches(
                    raw_matches,
                    chunk,
                    references,
                    live_items,
                    alignment_offset_seconds,
                ))
                run["total_tokens"] += tokens
            except Exception as exc:
                logger.warning(
                    "[transcript-alignment] chunk failed run=%s chunk=%d: %s",
                    run_id,
                    index,
                    exc,
                )
                run["failed_chunks"].append(index)
            run["completed_chunks"] = index
            run["matches"] = _deduplicate_matches(all_matches)
            run["summary"] = _summary(run["matches"], references, live_items)
            await _store_run(run)

        completed_matches: list[dict[str, Any]] = []
        out_of_scope_ids: list[str] = []
        for section_index, section in enumerate(sections):
            section_ids = {item["transcript_id"] for item in section["live_items"]}
            section_seeds = [match for match in _deduplicate_matches(all_matches)
                             if set(match["transcript_ids"]).issubset(section_ids)]
            # One AI pass only; remaining recording rows are placed deterministically at save time.
            section_matches, outside = _complete_alignment(
                section_seeds,
                section["references"], section["live_items"], alignment_offset_seconds,
            )
            for match in section_matches:
                match["_section_index"] = section_index
            completed_matches.extend(section_matches)
            out_of_scope_ids.extend(outside)
        completed_matches = _split_alignment_groups_by_reference(
            completed_matches,
            references,
            live_items,
            alignment_offset_seconds,
        )
        completed_matches = _split_alignment_groups_by_speaker(
            completed_matches,
            references,
            live_items,
            alignment_offset_seconds,
        )
        run["matches"] = completed_matches
        excluded_ids, out_of_scope_ids = final_scope_exclusions(completed_matches, live_items)
        run["excluded_transcript_ids"] = excluded_ids
        run["out_of_scope_transcript_ids"] = out_of_scope_ids
        run["summary"] = _summary(
            completed_matches,
            references,
            live_items,
            out_of_scope_ids,
        )
        matched_live = {i for match in completed_matches for i in match["transcript_ids"]}
        matched_refs = {o for match in completed_matches for o in match["reference_orders"]}
        run["unmatched_transcript_ids"] = [item["transcript_id"] for item in live_items
            if not item["is_corrected"] and item["transcript_id"] not in matched_live and item["transcript_id"] not in out_of_scope_ids]
        run["unmatched_reference_orders"] = [item["order_index"] for item in references if item["order_index"] not in matched_refs]
        run["status"] = "completed_with_errors" if run["failed_chunks"] else "completed"
        run["message"] = "AI整理完成，全部录音将自动按顺序归入修订结果，可直接保存"
    except Exception as exc:  # pragma: no cover - defensive task boundary
        logger.exception("[transcript-alignment] run failed run=%s", run_id)
        run["status"] = "failed"
        run["message"] = f"AI 匹配失败：{type(exc).__name__}"
    await _store_run(run)


async def _load_alignment_source(
    db: AsyncSession,
    session_id: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    session = (
        await db.execute(
            text(
                """
                SELECT cs.id, cs.created_at, cs.started_at, g.condition
                FROM chat_sessions cs
                JOIN groups g ON g.id = cs.group_id
                WHERE cs.id = :session_id
                  AND g.condition IN ('glasses', 'app_notification')
                """
            ),
            {"session_id": session_id},
        )
    ).mappings().first()
    if not session:
        raise HTTPException(status_code=404, detail="辅助条件会话不存在")

    reference_rows = (
        await db.execute(
            text(
                """
                SELECT order_index, content, start_time
                FROM coi_utterances
                WHERE session_id = :session_id
                  AND NULLIF(BTRIM(COALESCE(content, '')), '') IS NOT NULL
                ORDER BY order_index
                """
            ),
            {"session_id": session_id},
        )
    ).mappings().all()
    references = [
        {
            "order_index": int(row["order_index"]),
            "content": str(row["content"]),
            "start_time": float(row["start_time"]) if row["start_time"] is not None else None,
            "position": position,
        }
        for position, row in enumerate(reference_rows)
    ]

    transcript_rows = (
        await db.execute(
            text(
                """
                SELECT t.transcript_id,
                       COALESCE(t.text, '') AS original_text,
                       COALESCE(u.name, t.speaker, '未知说话人') AS speaker_name,
                       COALESCE(
                           t.speaker_user_id,
                           t.user_id,
                           NULLIF(BTRIM(t.speaker), ''),
                           t.transcript_id
                       ) AS speaker_key,
                       t.start,
                       t.created_at,
                       existing_correction.id AS existing_correction_id,
                       existing_correction.corrected_text AS manual_corrected_text,
                       (
                           existing_correction.id IS NOT NULL
                           AND COALESCE(existing_correction.correction_reason, '') NOT LIKE 'AI 整场匹配%'
                           AND COALESCE(existing_correction.correction_reason, '') NOT LIKE '录音完整修订%'
                       ) AS is_corrected,
                       (
                           existing_correction.id IS NOT NULL
                           AND (COALESCE(existing_correction.correction_reason, '') LIKE 'AI 整场匹配%'
                                OR COALESCE(existing_correction.correction_reason, '') LIKE '录音完整修订%')
                       ) AS has_ai_correction
                FROM speech_transcripts t
                LEFT JOIN users_info u
                       ON u.id = COALESCE(
                           t.speaker_user_id,
                           t.user_id,
                           NULLIF(BTRIM(t.speaker), '')
                       )
                LEFT JOIN speech_transcript_correction_members existing_member
                       ON existing_member.transcript_id = t.transcript_id
                LEFT JOIN speech_transcript_corrections existing_correction
                       ON existing_correction.id = existing_member.correction_id
                WHERE t.session_id = :session_id
                ORDER BY t.start ASC NULLS LAST,
                         t.created_at ASC,
                         t.transcript_id ASC
                """
            ),
            {"session_id": session_id},
        )
    ).mappings().all()
    base_time = session["started_at"] or session["created_at"]
    live_items = [
        {
            "transcript_id": str(row["transcript_id"]),
            "text": str(row["original_text"] or ""),
            "speaker_name": str(row["speaker_name"]),
            "speaker_key": str(row["speaker_key"]),
            "relative_seconds": _relative_seconds(row["start"] or row["created_at"], base_time),
            "is_corrected": bool(row["is_corrected"]),
            "manual_corrected_text": str(row["manual_corrected_text"] or ""),
            "has_ai_correction": bool(row["has_ai_correction"]),
            "existing_correction_id": (
                str(row["existing_correction_id"])
                if row["existing_correction_id"] is not None else None
            ),
            "position": position,
        }
        for position, row in enumerate(transcript_rows)
    ]
    return dict(session), references, live_items


@router.post(
    "/sessions/{session_id}/ai-match-runs",
    response_model=AlignmentRunOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_alignment_run(
    session_id: str,
    payload: StartAlignmentRunIn,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> AlignmentRunOut:
    if not nlp_settings.qwen_api_key:
        raise HTTPException(status_code=503, detail="Qwen API Key 尚未配置")
    _, references, live_items = await _load_alignment_source(db, session_id)
    if not references:
        raise HTTPException(status_code=409, detail="该会话没有可用的录音重转译内容")
    if not live_items:
        raise HTTPException(status_code=409, detail="该会话没有实时转写")
    if not any(not item["is_corrected"] for item in live_items):
        raise HTTPException(status_code=409, detail="该会话没有未修订的实时转写")

    anchor_reference = next(
        (item for item in references if item["order_index"] == payload.anchor.reference_order),
        None,
    )
    anchor_transcript = next(
        (item for item in live_items if item["transcript_id"] == payload.anchor.transcript_id),
        None,
    )
    if anchor_reference is None or anchor_transcript is None:
        raise HTTPException(status_code=409, detail="对齐起点不属于当前会话，请重新设置")
    if anchor_reference["start_time"] is None:
        raise HTTPException(status_code=409, detail="对齐起点缺少录音时间，请重新选择")
    if anchor_transcript["relative_seconds"] is None:
        raise HTTPException(status_code=409, detail="实时转写起点缺少时间，请重新选择")
    if abs(anchor_reference["start_time"] - payload.anchor.reference_start_time) > 0.25:
        raise HTTPException(status_code=409, detail="录音对齐时间已经变化，请重新设置")
    if abs(anchor_transcript["relative_seconds"] - payload.anchor.transcript_relative_seconds) > 0.25:
        raise HTTPException(status_code=409, detail="实时转写对齐时间已经变化，请重新设置")

    references = references[anchor_reference["position"]:]
    live_items = live_items[anchor_transcript["position"]:]
    if not any(not item["is_corrected"] for item in live_items):
        raise HTTPException(status_code=409, detail="对齐起点之后没有未修订的实时转写")
    offset = anchor_reference["start_time"] - anchor_transcript["relative_seconds"]
    try:
        sections = _partition_manual_sections(references, live_items, offset)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    target_references = [ref for section in sections for ref in section["references"]]
    if not target_references:
        raise HTTPException(status_code=409, detail="对齐范围内没有人工修订之外的录音内容，请重新选择起点")
    chunks = [chunk for section in sections
              for chunk in _build_chunks(section["references"], section["live_items"], offset)]
    run_id = "air" + uuid.uuid4().hex[:16]
    run: dict[str, Any] = {
        "run_id": run_id,
        "logic_version": ALIGNMENT_LOGIC_VERSION,
        "alignment_offset_seconds": offset,
        "protected_manual": [
            {"transcript_id": item["transcript_id"],
             "correction_id": item["existing_correction_id"],
             "corrected_text": item["manual_corrected_text"]}
            for item in live_items if item["is_corrected"]
        ],
        "session_id": session_id,
        "model": nlp_settings.transcript_alignment_model,
        "status": "queued",
        "completed_chunks": 0,
        "total_chunks": len(chunks),
        "matches": [],
        "summary": _summary([], target_references, live_items),
        "failed_chunks": [],
        "message": "已进入 AI 匹配队列",
        "total_tokens": 0,
        "created_at": datetime.now().astimezone().isoformat(),
        "out_of_scope_transcript_ids": [],
    }
    await _store_run(run)
    background_tasks.add_task(
        _execute_alignment_run,
        run_id,
        references,
        live_items,
        offset,
    )
    return AlignmentRunOut.model_validate(run)


@router.get("/ai-match-runs/{run_id}", response_model=AlignmentRunOut)
async def get_alignment_run(run_id: str) -> AlignmentRunOut:
    run = await _load_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="AI 匹配结果不存在或已过期")
    return AlignmentRunOut.model_validate(run)


def _merge_preview_matches(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    reference_orders = list(dict.fromkeys(left["reference_orders"] + right["reference_orders"]))
    transcript_ids = list(dict.fromkeys(left["transcript_ids"] + right["transcript_ids"]))
    reference_text = "\n".join(
        value.strip() for value in (left["reference_text"], right["reference_text"]) if value.strip()
    )
    transcript_text = " ".join(
        value.strip() for value in (left["transcript_text"], right["transcript_text"]) if value.strip()
    )
    return {
        "match_id": _match_id(reference_orders, transcript_ids),
        "reference_orders": reference_orders,
        "transcript_ids": transcript_ids,
        "reference_text": reference_text,
        "transcript_text": transcript_text,
        "corrected_text": reference_text,
        "confidence": min(float(left.get("confidence", 0.5)), float(right.get("confidence", 0.5))),
        "confidence_level": "medium",
        "time_distance_seconds": left.get("time_distance_seconds"),
        "reason": "人工确认并入相邻段",
        "saved": False,
        "review_required": False,
        "review_reason": "",
    }


@router.post("/ai-match-runs/{run_id}/resolve", response_model=AlignmentRunOut)
async def resolve_alignment_boundary(
    run_id: str,
    payload: ResolveAlignmentBoundaryIn,
    db: AsyncSession = Depends(get_db),
) -> AlignmentRunOut:
    run = await _load_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="AI 整理结果不存在或已过期")
    if run["status"] not in {"completed", "completed_with_errors"}:
        raise HTTPException(status_code=409, detail="AI 整理尚未完成")
    matches = run["matches"]
    index = next((i for i, item in enumerate(matches) if item["match_id"] == payload.match_id), -1)
    if index < 0:
        raise HTTPException(status_code=404, detail="需要确认的分组不存在")
    if matches[index].get("saved"):
        raise HTTPException(status_code=409, detail="该分组已经保存，不能调整边界")

    if payload.action == "keep":
        matches[index]["review_required"] = False
        matches[index]["review_reason"] = ""
        matches[index]["reason"] = "人工确认保持当前分组"
    else:
        neighbor_index = index - 1 if payload.action == "previous" else index + 1
        if neighbor_index < 0 or neighbor_index >= len(matches):
            raise HTTPException(status_code=409, detail="该方向没有可以合并的相邻段")
        if matches[neighbor_index].get("saved"):
            raise HTTPException(status_code=409, detail="相邻段已经保存，不能调整边界")
        if matches[index].get("_section_index") != matches[neighbor_index].get("_section_index"):
            raise HTTPException(status_code=409, detail="不能跨越人工修订合并 AI 段落")
        candidate_transcript_ids = list(dict.fromkeys(
            matches[index]["transcript_ids"] + matches[neighbor_index]["transcript_ids"]
        ))
        speaker_rows = (
            await db.execute(
                text(
                    """
                    SELECT transcript_id,
                           COALESCE(
                               speaker_user_id,
                               user_id,
                               NULLIF(BTRIM(speaker), ''),
                               transcript_id
                           ) AS speaker_key
                    FROM speech_transcripts
                    WHERE session_id = :session_id
                      AND transcript_id = ANY(:transcript_ids)
                    """
                ),
                {
                    "session_id": run["session_id"],
                    "transcript_ids": candidate_transcript_ids,
                },
            )
        ).mappings().all()
        if len(speaker_rows) != len(candidate_transcript_ids):
            raise HTTPException(status_code=409, detail="实时转写已经变化，请重新整理")
        if len({str(row["speaker_key"]) for row in speaker_rows}) > 1:
            raise HTTPException(status_code=409, detail="不同说话人的内容不能合并")
        left_index = min(index, neighbor_index)
        right_index = max(index, neighbor_index)
        merged = _merge_preview_matches(matches[left_index], matches[right_index])
        merged["_section_index"] = matches[left_index].get("_section_index")
        matches[left_index:right_index + 1] = [merged]

    run["summary"]["review_required"] = sum(
        bool(item.get("review_required")) for item in matches
    )
    await _store_run(run)
    return AlignmentRunOut.model_validate(run)


@router.post("/ai-match-runs/{run_id}/save", response_model=SaveAlignmentRunOut)
async def save_alignment_run(
    run_id: str,
    payload: SaveAlignmentRunIn,
    db: AsyncSession = Depends(get_db),
) -> SaveAlignmentRunOut:
    run = await _load_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="AI 匹配结果不存在或已过期")
    if run.get("logic_version") != ALIGNMENT_LOGIC_VERSION:
        raise HTTPException(status_code=409, detail="该预览使用旧的对齐规则，请重新 AI 整理后再保存")
    protected = run.get("protected_manual", [])
    if protected:
        rows = (await db.execute(text("""
            SELECT member.transcript_id, correction.id AS correction_id,
                   correction.corrected_text
            FROM speech_transcript_correction_members member
            JOIN speech_transcript_corrections correction ON correction.id = member.correction_id
            WHERE member.transcript_id = ANY(:ids)
            FOR SHARE OF member, correction
        """), {"ids": [item["transcript_id"] for item in protected]})).mappings().all()
        expected = {tuple(item[key] for key in ("transcript_id", "correction_id", "corrected_text")) for item in protected}
        actual = {tuple(str(row[key]) for key in ("transcript_id", "correction_id", "corrected_text")) for row in rows}
        if actual != expected:
            raise HTTPException(status_code=409, detail="人工修订已变化，请重新 AI 整理后再保存")
    logger.info(
        "[transcript-alignment] save requested run=%s session=%s status=%s "
        "requested_matches=%d total_matches=%d summary=%s",
        run_id,
        run.get("session_id"),
        run.get("status"),
        len(payload.match_ids),
        len(run.get("matches", [])),
        json.dumps(run.get("summary", {}), ensure_ascii=False, sort_keys=True),
    )
    if run["status"] not in {"completed", "completed_with_errors"}:
        logger.warning(
            "[transcript-alignment] save rejected run=%s reason=run_not_completed status=%s",
            run_id,
            run.get("status"),
        )
        raise HTTPException(status_code=409, detail="AI 匹配尚未完成")
    if int(run.get("summary", {}).get("unmatched_references", 0)) != 0:
        logger.warning(
            "[transcript-alignment] save rejected run=%s reason=unmatched_references count=%s",
            run_id,
            run.get("summary", {}).get("unmatched_references"),
        )
        raise HTTPException(status_code=409, detail="准确录音文字仍有未分配内容，禁止保存")
    matches_by_id = {item["match_id"]: item for item in run["matches"]}
    if not set(payload.match_ids).issubset(matches_by_id):
        raise HTTPException(status_code=400, detail="包含无效的 AI 匹配建议")

    unsaved_match_ids = {
        item["match_id"] for item in run["matches"] if not item.get("saved")
    }
    if set(payload.match_ids) != unsaved_match_ids:
        logger.warning(
            "[transcript-alignment] save rejected run=%s reason=partial_selection "
            "requested=%d unsaved=%d",
            run_id,
            len(payload.match_ids),
            len(unsaved_match_ids),
        )
        raise HTTPException(status_code=400, detail="必须一次保存全部未保存的整场修订")

    selected = [matches_by_id[match_id] for match_id in payload.match_ids]
    blank_match = next(
        (item for item in selected if not str(item.get("corrected_text", "")).strip()),
        None,
    )
    if blank_match:
        logger.warning(
            "[transcript-alignment] save rejected run=%s reason=blank_corrected_text match=%s",
            run_id,
            blank_match.get("match_id"),
        )
        raise HTTPException(
            status_code=409,
            detail="整理结果包含空白修订文字，请重新运行整场整理",
        )
    split_error = _split_source_error(selected)
    if split_error:
        logger.warning(
            "[transcript-alignment] save rejected run=%s reason=split_source_invalid detail=%s",
            run_id,
            split_error,
        )
        raise HTTPException(status_code=409, detail=f"准确录音文字校验失败：{split_error}")
    all_transcript_ids = list(dict.fromkeys(
        transcript_id
        for item in selected
        for transcript_id in item["transcript_ids"]
    ))
    all_reference_orders = list(dict.fromkeys(
        order
        for item in selected
        for order in item["reference_orders"]
    ))
    replacement_scope_ids = list(dict.fromkeys(
        all_transcript_ids + [
            str(item) for item in run.get("excluded_transcript_ids", [])
        ]
    ))

    current_references = (
        await db.execute(
            text(
                """
                SELECT order_index, content
                FROM coi_utterances
                WHERE session_id = :session_id
                  AND order_index = ANY(:orders)
                """
            ),
            {"session_id": run["session_id"], "orders": all_reference_orders},
        )
    ).mappings().all()
    reference_content = {int(row["order_index"]): str(row["content"]) for row in current_references}
    if set(reference_content) != set(all_reference_orders):
        logger.warning(
            "[transcript-alignment] save rejected run=%s reason=reference_rows_changed "
            "expected=%d actual=%d",
            run_id,
            len(all_reference_orders),
            len(reference_content),
        )
        raise HTTPException(status_code=409, detail="录音重转译内容已经变化，请重新整理")
    for match in selected:
        current_reference_source = "\n".join(
            reference_content[order].strip() for order in match["reference_orders"]
        ).strip()
        expected_reference_source = str(
            match.get("_reference_source_text", match["corrected_text"])
        )
        if current_reference_source != expected_reference_source:
            logger.warning(
                "[transcript-alignment] save rejected run=%s reason=reference_text_changed "
                "match=%s reference_orders=%s",
                run_id,
                match["match_id"],
                match["reference_orders"],
            )
            raise HTTPException(status_code=409, detail="录音重转译内容已经变化，请重新整理")

    transcript_rows = (
        await db.execute(
            text(
                """
                SELECT t.transcript_id,
                       COALESCE(u.name, t.speaker, '未知说话人') AS speaker_name,
                       COALESCE(
                           t.speaker_user_id,
                           t.user_id,
                           NULLIF(BTRIM(t.speaker), ''),
                           t.transcript_id
                       ) AS speaker_key
                FROM speech_transcripts t
                LEFT JOIN users_info u
                       ON u.id = COALESCE(
                           t.speaker_user_id,
                           t.user_id,
                           NULLIF(BTRIM(t.speaker), '')
                       )
                WHERE t.session_id = :session_id
                  AND t.transcript_id = ANY(:transcript_ids)
                FOR UPDATE OF t
                """
            ),
            {"session_id": run["session_id"], "transcript_ids": all_transcript_ids},
        )
    ).mappings().all()
    existing_transcript_ids = {str(row["transcript_id"]) for row in transcript_rows}
    speaker_by_transcript_id = {
        str(row["transcript_id"]): str(row["speaker_key"] or row["speaker_name"] or "未知说话人")
        for row in transcript_rows
    }
    if existing_transcript_ids != set(all_transcript_ids):
        logger.warning(
            "[transcript-alignment] save rejected run=%s reason=transcript_rows_changed "
            "expected=%d actual=%d",
            run_id,
            len(all_transcript_ids),
            len(existing_transcript_ids),
        )
        raise HTTPException(status_code=409, detail="实时转写已经变化，请重新整理")
    if any(
        len({speaker_by_transcript_id[item] for item in match["transcript_ids"]}) > 1
        for match in selected
    ):
        logger.warning(
            "[transcript-alignment] save rejected run=%s reason=cross_speaker_match",
            run_id,
        )
        raise HTTPException(status_code=409, detail="仍存在跨说话人的段落，禁止保存")
    occupied_rows = (
        await db.execute(
            text(
                """
                SELECT member.transcript_id,
                       member.correction_id,
                       correction.correction_reason
                FROM speech_transcript_correction_members member
                JOIN speech_transcript_corrections correction
                  ON correction.id = member.correction_id
                WHERE member.transcript_id = ANY(:transcript_ids)
                """
            ),
            {"transcript_ids": replacement_scope_ids},
        )
    ).mappings().all()
    replaceable_correction_ids, all_blocking_transcript_ids = _partition_existing_corrections(
        [dict(row) for row in occupied_rows]
    )
    blocking_transcript_ids = all_blocking_transcript_ids.intersection(all_transcript_ids)
    if blocking_transcript_ids:
        logger.warning(
            "[transcript-alignment] save rejected run=%s reason=manual_corrections count=%d",
            run_id,
            len(blocking_transcript_ids),
        )
        raise HTTPException(status_code=409, detail="部分实时转写出现新的人工修订，请重新整理")

    # Existing AI results are replaceable. Delete them only inside the same
    # transaction that writes the complete new run, so any failure restores
    # the previous saved result automatically. Raw transcripts and manual
    # corrections are never deleted here.
    if replaceable_correction_ids:
        await db.execute(
            text(
                """
                DELETE FROM speech_transcript_corrections
                WHERE id = ANY(:correction_ids)
                  AND COALESCE(correction_reason, '') LIKE 'AI 整场匹配%'
                """
            ),
            {"correction_ids": sorted(replaceable_correction_ids)},
        )
        logger.info(
            "[transcript-alignment] replacing old AI corrections run=%s count=%d",
            run_id,
            len(replaceable_correction_ids),
        )

    saved_match_ids: list[str] = []
    saved_transcripts = 0
    skipped: list[dict[str, str]] = []
    corrected_by = (payload.corrected_by or "").strip() or None

    for match in selected:
        match_id = match["match_id"]
        transcript_ids = match["transcript_ids"]
        if match.get("saved"):
            skipped.append({"match_id": match_id, "reason": "该建议已经保存"})
            continue
        corrected_text = str(match["corrected_text"]).strip()

        correction_id = "stc" + uuid.uuid4().hex[:12]
        try:
            async with db.begin_nested():
                await db.execute(
                    text(
                        """
                        INSERT INTO speech_transcript_corrections (
                            id, transcript_id, corrected_text, correction_reason,
                            corrected_by, created_at, updated_at
                        ) VALUES (
                            :id, :transcript_id, :corrected_text, :correction_reason,
                            :corrected_by, NOW(), NOW()
                        )
                        """
                    ),
                    {
                        "id": correction_id,
                        "transcript_id": transcript_ids[0] if len(transcript_ids) == 1 else None,
                        "corrected_text": corrected_text,
                        "correction_reason": scope_reason(
                            f"AI 整场匹配（run={run_id}，{run['model']}，可信度 {match['confidence']:.3f}）",
                            run.get("excluded_transcript_ids", []),
                        ),
                        "corrected_by": corrected_by,
                    },
                )
                for order_index, transcript_id in enumerate(transcript_ids):
                    await db.execute(
                        text(
                            """
                            INSERT INTO speech_transcript_correction_members (
                                correction_id, transcript_id, order_index
                            ) VALUES (
                                :correction_id, :transcript_id, :order_index
                            )
                            """
                        ),
                        {
                            "correction_id": correction_id,
                            "transcript_id": transcript_id,
                            "order_index": order_index,
                        },
                    )
        except IntegrityError as exc:
            candidates = [exc.orig, getattr(exc.orig, "__cause__", None)]
            constraint_name = None
            sqlstate = None
            for candidate in candidates:
                if candidate is None:
                    continue
                diagnostic = getattr(candidate, "diag", None)
                constraint_name = constraint_name or getattr(candidate, "constraint_name", None)
                constraint_name = constraint_name or getattr(diagnostic, "constraint_name", None)
                sqlstate = sqlstate or getattr(candidate, "sqlstate", None)
                sqlstate = sqlstate or getattr(candidate, "pgcode", None)
            constraint_label = str(constraint_name or "unknown_constraint")
            sqlstate_label = str(sqlstate or "unknown_sqlstate")
            logger.warning(
                "[transcript-alignment] save integrity error run=%s session=%s "
                "match=%s correction=%s transcript_count=%d constraint=%s sqlstate=%s",
                run_id,
                run.get("session_id"),
                match_id,
                correction_id,
                len(transcript_ids),
                constraint_label,
                sqlstate_label,
            )
            await db.rollback()
            raise HTTPException(
                status_code=409,
                detail=(
                    "数据库完整性校验失败，整场未保存："
                    f"constraint={constraint_label}, sqlstate={sqlstate_label}"
                ),
            )
        saved_match_ids.append(match_id)
        saved_transcripts += len(transcript_ids)

    await db.commit()
    for item in run["matches"]:
        if item["match_id"] in saved_match_ids:
            item["saved"] = True
    await _store_run(run)
    logger.info(
        "[transcript-alignment] save completed run=%s session=%s "
        "saved_matches=%d saved_transcripts=%d",
        run_id,
        run.get("session_id"),
        len(saved_match_ids),
        saved_transcripts,
    )
    return SaveAlignmentRunOut(
        saved_matches=len(saved_match_ids),
        saved_transcripts=saved_transcripts,
        saved_match_ids=saved_match_ids,
        skipped=[SkippedAlignmentMatchOut.model_validate(item) for item in skipped],
    )


@router.post("/ai-match-runs/{run_id}/undo", response_model=UndoAlignmentRunOut)
async def undo_saved_alignment_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
) -> UndoAlignmentRunOut:
    """Remove only corrections created by this saved preview; manual work is protected."""
    run = await _load_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="AI 整理结果不存在或已过期")
    saved_matches = [item for item in run["matches"] if item.get("saved")]
    if not saved_matches:
        return UndoAlignmentRunOut(removed_matches=0, removed_corrections=0)

    transcript_ids = list(dict.fromkeys(
        transcript_id
        for match in saved_matches
        for transcript_id in match["transcript_ids"]
    ))
    rows = (
        await db.execute(
            text(
                """
                SELECT tc.id,
                       tc.correction_reason,
                       ARRAY_AGG(all_members.transcript_id ORDER BY all_members.order_index) AS transcript_ids
                FROM speech_transcript_correction_members selected_member
                JOIN speech_transcript_corrections tc
                  ON tc.id = selected_member.correction_id
                JOIN speech_transcript_correction_members all_members
                  ON all_members.correction_id = tc.id
                WHERE selected_member.transcript_id = ANY(:transcript_ids)
                GROUP BY tc.id, tc.correction_reason
                """
            ),
            {"transcript_ids": transcript_ids},
        )
    ).mappings().all()
    expected_groups = {
        frozenset(match["transcript_ids"]): match
        for match in saved_matches
    }
    removable_ids: list[str] = []
    removed_groups: set[frozenset[str]] = set()
    for row in rows:
        group = frozenset(str(item) for item in row["transcript_ids"])
        reason = str(row["correction_reason"] or "")
        if group in expected_groups and reason.startswith("AI 整场匹配"):
            removable_ids.append(str(row["id"]))
            removed_groups.add(group)

    if removable_ids:
        await db.execute(
            text("DELETE FROM speech_transcript_corrections WHERE id = ANY(:correction_ids)"),
            {"correction_ids": removable_ids},
        )
        await db.commit()

    for match in saved_matches:
        if frozenset(match["transcript_ids"]) in removed_groups:
            match["saved"] = False
    await _store_run(run)
    return UndoAlignmentRunOut(
        removed_matches=len(removed_groups),
        removed_corrections=len(removable_ids),
    )
