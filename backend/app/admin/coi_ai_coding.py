"""Admin API for AI coder C in the CoI workflow."""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from openai import AsyncOpenAI
from pydantic import Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..api_model import ApiModel
from ..analysis.coi_ai_audit_log import write_coi_ai_audit
from ..db import get_db
from ..settings import QWEN_CHAT_EXTRA_BODY, nlp_settings
from .deps import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/admin/coi-ai-coding",
    tags=["admin-coi-ai-coding"],
    dependencies=[Depends(require_admin)],
)

COI_CATEGORIES = {"TE", "EX", "IN", "RE", "OTHER"}
MAX_UNITS_PER_REQUEST = 20
MANUAL_PATH = Path(__file__).resolve().parents[1] / "resources" / "coi_ai_coding_manual.md"

CoiCategory = Literal["TE", "EX", "IN", "RE", "OTHER"]


class AiCodingItemOut(ApiModel):
    unit_id: str
    order_index: int
    content: str
    start_time: float | None
    ai_segmentation_suggestion: str | None
    ai_segmentation_reviewed_at: datetime | None
    coi_categories: list[CoiCategory]
    ai_original_categories: list[CoiCategory]
    coding_reason: str
    has_ai_result: bool
    coded_by: str | None
    coded_at: datetime | None
    updated_at: datetime | None


class GenerateAiCodesRequest(ApiModel):
    unit_ids: list[str] = Field(min_length=1, max_length=MAX_UNITS_PER_REQUEST)


class SaveAiCodeIn(ApiModel):
    unit_id: str
    coi_categories: list[CoiCategory] = Field(max_length=5)
    coding_reason: str = Field(min_length=1, max_length=2000)


class SaveAiCodesRequest(ApiModel):
    codes: list[SaveAiCodeIn] = Field(min_length=1)


class AiCodingResponse(ApiModel):
    saved: int
    items: list[AiCodingItemOut]


def _new_code_id() -> str:
    return "cuc" + uuid.uuid4().hex[:12]


def _new_audit_request_id() -> str:
    return "coia" + uuid.uuid4().hex[:16]


def _audit(
    *,
    request_id: str | None,
    session_id: str | None,
    operation: str,
    stage: str,
    **details: Any,
) -> None:
    if not request_id or not session_id:
        return
    write_coi_ai_audit({
        "request_id": request_id,
        "session_id": session_id,
        "operation": operation,
        "stage": stage,
        **details,
    })


def _normalize_categories(value: Any) -> list[CoiCategory]:
    if not isinstance(value, list):
        raise ValueError("coi_categories 必须是数组")
    selected = {str(item).upper() for item in value}
    if not selected.issubset(COI_CATEGORIES):
        raise ValueError("CoI 分类只能包含 TE、EX、IN、RE、OTHER")
    if "OTHER" in selected and len(selected) > 1:
        raise ValueError("OTHER 不能与 TE、EX、IN、RE 同时选择")
    return [category for category in ("TE", "EX", "IN", "RE", "OTHER") if category in selected]  # type: ignore[misc]


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


def _row_to_out(row: Any) -> AiCodingItemOut:
    return AiCodingItemOut(
        unit_id=row["unit_id"],
        order_index=row["order_index"],
        content=row["content"],
        start_time=row["start_time"],
        ai_segmentation_suggestion=row["ai_segmentation_suggestion"],
        ai_segmentation_reviewed_at=row["ai_segmentation_reviewed_at"],
        coi_categories=list(row["coi_categories"] or []),
        ai_original_categories=list(row["ai_original_categories"] or []),
        coding_reason=row["coding_reason"] or "",
        has_ai_result=bool(row["has_ai_result"]),
        coded_by=row["coded_by"],
        coded_at=row["coded_at"],
        updated_at=row["updated_at"],
    )


async def _load_session_items(db: AsyncSession, session_id: str) -> list[AiCodingItemOut]:
    result = await db.execute(text("""
        SELECT u.id AS unit_id, u.order_index, u.content, u.start_time,
               u.ai_segmentation_suggestion, u.ai_segmentation_reviewed_at,
               c.coi_categories, c.ai_original_categories, c.coding_reason,
               (c.unit_id IS NOT NULL) AS has_ai_result,
               c.coded_by, c.coded_at, c.updated_at
          FROM coi_units u
          LEFT JOIN coi_unit_codes c
            ON c.unit_id = u.id AND c.coder_role = 'coder_c'
         WHERE u.session_id = :session_id
         ORDER BY u.order_index
    """), {"session_id": session_id})
    return [_row_to_out(row) for row in result.mappings().all()]


async def _load_selected_units(
    db: AsyncSession,
    session_id: str,
    unit_ids: list[str],
) -> list[dict[str, Any]]:
    unique_ids = list(dict.fromkeys(unit_ids))
    result = await db.execute(text("""
        SELECT id, group_id, order_index, content
          FROM coi_units
         WHERE session_id = :session_id
           AND id = ANY(:unit_ids)
         ORDER BY order_index
    """), {"session_id": session_id, "unit_ids": unique_ids})
    rows = [dict(row) for row in result.mappings().all()]
    if len(rows) != len(unique_ids):
        raise HTTPException(status_code=409, detail="部分观点已发生变化，请重新加载后再试")
    return rows


async def _review_segmentation(
    units: list[dict[str, Any]],
    *,
    session_id: str | None = None,
    request_id: str | None = None,
) -> list[dict[str, str]]:
    operation = "segmentation_review"
    if not nlp_settings.qwen_api_key:
        _audit(
            request_id=request_id, session_id=session_id, operation=operation,
            stage="failed", phase="configuration", error="AI 模型尚未配置",
        )
        raise HTTPException(status_code=503, detail="AI 模型尚未配置")
    try:
        manual = MANUAL_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        logger.exception("读取 CoI AI 编码手册失败")
        _audit(
            request_id=request_id, session_id=session_id, operation=operation,
            stage="failed", phase="manual_read", error_type=type(exc).__name__,
            error=str(exc),
        )
        raise HTTPException(status_code=500, detail="无法读取 CoI 编码手册") from exc

    unit_text = "\n".join(
        f"[{unit['id']}] 第{unit['order_index']}条：{unit['content']}" for unit in units
    )
    user_prompt = (
        "现在只执行编码前的观点单元检查，不要进行 TE/EX/IN/RE 编码。\n"
        "逐条判断是否需要拆分，或是否应与本次输入中的相邻观点合并。\n"
        "AI不得修改原文，只能给研究员建议。若无需调整，suggestion 必须写‘无需调整’。\n"
        "若需调整，必须以‘拆分建议：’或‘合并建议：’开头，并说明具体边界或相邻条目。\n"
        "建议正文只能使用‘第N条’指代观点，不得出现 unit_id；unit_id 仅用于 JSON 字段。\n"
        "严格返回 JSON，不要输出 Markdown 或其他文字。\n"
        "输出格式：{\"results\":[{\"unit_id\":\"...\",\"suggestion\":\"无需调整\"}]}\n"
        "必须返回每个输入 unit_id，且不得增加不存在的 unit_id。\n\n"
        f"观点单元：\n{unit_text}"
    )
    client = AsyncOpenAI(
        api_key=nlp_settings.qwen_api_key,
        base_url=nlp_settings.qwen_base_url,
        timeout=60.0,
    )
    messages = [
        {"role": "system", "content": manual},
        {"role": "user", "content": user_prompt},
    ]
    _audit(
        request_id=request_id, session_id=session_id, operation=operation,
        stage="request", model=nlp_settings.reasoning_model,
        manual_sha256=hashlib.sha256(manual.encode("utf-8")).hexdigest(),
        units=units, messages=messages, max_tokens=2500,
        extra_body=QWEN_CHAT_EXTRA_BODY,
    )
    raw = ""
    try:
        response = await client.chat.completions.create(
            model=nlp_settings.reasoning_model,
            max_tokens=2500,
            extra_body=QWEN_CHAT_EXTRA_BODY,
            messages=messages,
        )
        raw = response.choices[0].message.content or ""
        _audit(
            request_id=request_id, session_id=session_id, operation=operation,
            stage="model_response", raw_response=raw,
        )
        payload = json.loads(_strip_json_fence(raw))
        raw_results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(raw_results, list):
            raise ValueError("模型未返回 results 数组")

        by_id: dict[str, dict[str, str]] = {}
        expected_ids = {unit["id"] for unit in units}
        order_by_id = {unit["id"]: unit["order_index"] for unit in units}
        for item in raw_results:
            if not isinstance(item, dict) or item.get("unit_id") not in expected_ids:
                raise ValueError("模型返回了无效的 unit_id")
            unit_id = str(item["unit_id"])
            suggestion = str(item.get("suggestion") or "").strip()
            if not suggestion:
                raise ValueError("模型未返回观点单元建议")
            for referenced_id, order_index in order_by_id.items():
                suggestion = suggestion.replace(f"[{referenced_id}]", f"第{order_index}条")
                suggestion = suggestion.replace(referenced_id, f"第{order_index}条")
            by_id[unit_id] = {
                "unit_id": unit_id,
                "suggestion": suggestion[:2000],
            }
        if set(by_id) != expected_ids:
            raise ValueError("模型没有返回全部观点单元")
        parsed = [by_id[unit["id"]] for unit in units]
        _audit(
            request_id=request_id, session_id=session_id, operation=operation,
            stage="parsed", results=parsed,
        )
        return parsed
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(
            "[CoI/AI-C] 观点单元检查或解析失败 session_id=%s request_id=%s: %s",
            session_id, request_id, exc,
        )
        _audit(
            request_id=request_id, session_id=session_id, operation=operation,
            stage="failed", phase="model_or_parse", error_type=type(exc).__name__,
            error=str(exc), raw_response=raw,
        )
        raise HTTPException(status_code=502, detail="AI 观点检查失败，请稍后重试") from exc


async def _generate_codes(
    units: list[dict[str, Any]],
    *,
    session_id: str | None = None,
    request_id: str | None = None,
) -> list[dict[str, Any]]:
    operation = "coding"
    if not nlp_settings.qwen_api_key:
        _audit(
            request_id=request_id, session_id=session_id, operation=operation,
            stage="failed", phase="configuration", error="AI 模型尚未配置",
        )
        raise HTTPException(status_code=503, detail="AI 模型尚未配置")
    try:
        manual = MANUAL_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        logger.exception("读取 CoI AI 编码手册失败")
        _audit(
            request_id=request_id, session_id=session_id, operation=operation,
            stage="failed", phase="manual_read", error_type=type(exc).__name__,
            error=str(exc),
        )
        raise HTTPException(status_code=500, detail="无法读取 CoI 编码手册") from exc

    unit_text = "\n".join(
        f"[{unit['id']}] {unit['content']}" for unit in units
    )
    user_prompt = (
        "请逐条编码以下观点单元。严格返回 JSON，不要输出 Markdown 或其他文字。\n"
        "输出格式：{\"results\":[{\"unit_id\":\"...\","
        "\"coi_categories\":[\"TE\",\"EX\"],\"reason\":\"简短中文理由\"}]}\n"
        "coi_categories 可以包含一个或多个类别。必须逐分句检查全部认知功能；"
        "选出 TE 后仍须继续检查是否同时存在回答或观点（EX）、比较或综合（IN）、"
        "具体方案（RE），不得以‘主要功能’或‘TE 为主导’为由省略其他类别。\n"
        "若某条仅为重复、附和、程序性话语或无实质认知贡献，"
        "coi_categories 必须返回 [\"OTHER\"]，reason 说明为何不属于四个认知阶段；不得强行选择最接近的类别。\n"
        "选择 OTHER 前必须逐分句确认整条均无实质认知贡献。若原文使用物品名、字母、编号或简称"
        "表达排序方向、相对位置或有序答案，这是具体排序方案，应编码为 RE；"
        "同一条中的程序性片段不得抵消该排序贡献。\n"
        "必须返回每个输入 unit_id，且不得增加不存在的 unit_id。\n\n"
        f"观点单元：\n{unit_text}"
    )
    client = AsyncOpenAI(
        api_key=nlp_settings.qwen_api_key,
        base_url=nlp_settings.qwen_base_url,
        timeout=60.0,
    )
    messages = [
        {"role": "system", "content": manual},
        {"role": "user", "content": user_prompt},
    ]
    _audit(
        request_id=request_id, session_id=session_id, operation=operation,
        stage="request", model=nlp_settings.reasoning_model,
        manual_sha256=hashlib.sha256(manual.encode("utf-8")).hexdigest(),
        units=units, messages=messages, max_tokens=2500,
        extra_body=QWEN_CHAT_EXTRA_BODY,
    )
    raw = ""
    try:
        response = await client.chat.completions.create(
            model=nlp_settings.reasoning_model,
            max_tokens=2500,
            extra_body=QWEN_CHAT_EXTRA_BODY,
            messages=messages,
        )
        raw = response.choices[0].message.content or ""
        _audit(
            request_id=request_id, session_id=session_id, operation=operation,
            stage="model_response", raw_response=raw,
        )
        payload = json.loads(_strip_json_fence(raw))
        raw_results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(raw_results, list):
            raise ValueError("模型未返回 results 数组")

        by_id: dict[str, dict[str, Any]] = {}
        expected_ids = {unit["id"] for unit in units}
        for item in raw_results:
            if not isinstance(item, dict) or item.get("unit_id") not in expected_ids:
                raise ValueError("模型返回了无效的 unit_id")
            unit_id = str(item["unit_id"])
            reason = str(item.get("reason") or "").strip()
            if not reason:
                raise ValueError("模型未返回编码理由")
            by_id[unit_id] = {
                "unit_id": unit_id,
                "coi_categories": _normalize_categories(item.get("coi_categories")),
                "coding_reason": reason[:2000],
            }
        if set(by_id) != expected_ids:
            raise ValueError("模型没有返回全部观点单元")
        parsed = [by_id[unit["id"]] for unit in units]
        _audit(
            request_id=request_id, session_id=session_id, operation=operation,
            stage="parsed", results=parsed,
        )
        return parsed
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(
            "[CoI/AI-C] 编码或解析失败 session_id=%s request_id=%s: %s",
            session_id, request_id, exc,
        )
        _audit(
            request_id=request_id, session_id=session_id, operation=operation,
            stage="failed", phase="model_or_parse", error_type=type(exc).__name__,
            error=str(exc), raw_response=raw,
        )
        raise HTTPException(status_code=502, detail="AI 编码失败，请稍后重试") from exc


@router.get("/sessions/{session_id}", response_model=list[AiCodingItemOut])
async def get_ai_codes(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[AiCodingItemOut]:
    return await _load_session_items(db, session_id)


@router.post("/sessions/{session_id}/review-units", response_model=AiCodingResponse)
async def review_ai_coding_units(
    session_id: str,
    payload: GenerateAiCodesRequest,
    db: AsyncSession = Depends(get_db),
) -> AiCodingResponse:
    request_id = _new_audit_request_id()
    _audit(
        request_id=request_id, session_id=session_id,
        operation="segmentation_review", stage="received",
        requested_unit_ids=payload.unit_ids,
    )
    try:
        units = await _load_selected_units(db, session_id, payload.unit_ids)
    except Exception as exc:
        _audit(
            request_id=request_id, session_id=session_id,
            operation="segmentation_review", stage="failed", phase="load_units",
            error_type=type(exc).__name__, error=str(exc),
        )
        raise
    await db.rollback()
    suggestions = await _review_segmentation(
        units, session_id=session_id, request_id=request_id,
    )
    try:
        await _load_selected_units(db, session_id, payload.unit_ids)
        rows = [
            {
                "unit_id": item["unit_id"],
                "session_id": session_id,
                "suggestion": item["suggestion"],
            }
            for item in suggestions
        ]
        await db.execute(text("""
            UPDATE coi_units
               SET ai_segmentation_suggestion = :suggestion,
                   ai_segmentation_reviewed_at = NOW()
             WHERE id = :unit_id
               AND session_id = :session_id
        """), rows)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        _audit(
            request_id=request_id, session_id=session_id,
            operation="segmentation_review", stage="failed", phase="save",
            error_type=type(exc).__name__, error=str(exc), results=suggestions,
        )
        raise
    _audit(
        request_id=request_id, session_id=session_id,
        operation="segmentation_review", stage="saved", saved=len(rows),
        results=suggestions,
    )
    return AiCodingResponse(saved=len(rows), items=await _load_session_items(db, session_id))


@router.post("/sessions/{session_id}/generate", response_model=AiCodingResponse)
async def generate_ai_codes(
    session_id: str,
    payload: GenerateAiCodesRequest,
    db: AsyncSession = Depends(get_db),
) -> AiCodingResponse:
    request_id = _new_audit_request_id()
    _audit(
        request_id=request_id, session_id=session_id, operation="coding",
        stage="received", requested_unit_ids=payload.unit_ids,
    )
    try:
        units = await _load_selected_units(db, session_id, payload.unit_ids)
    except Exception as exc:
        _audit(
            request_id=request_id, session_id=session_id, operation="coding",
            stage="failed", phase="load_units", error_type=type(exc).__name__,
            error=str(exc),
        )
        raise
    await db.rollback()
    generated = await _generate_codes(
        units, session_id=session_id, request_id=request_id,
    )
    try:
        units = await _load_selected_units(db, session_id, payload.unit_ids)
        rows = [
            {
                "id": _new_code_id(),
                "unit_id": item["unit_id"],
                "session_id": session_id,
                "group_id": next(
                    unit["group_id"]
                    for unit in units
                    if unit["id"] == item["unit_id"]
                ),
                "coi_categories": item["coi_categories"],
                "coding_reason": item["coding_reason"],
            }
            for item in generated
        ]
        await db.execute(text("""
            INSERT INTO coi_unit_codes
                (id, unit_id, session_id, group_id, coder_role, coded_by,
                 coi_categories, ai_original_categories, coding_reason,
                 coded_at, created_at, updated_at)
            VALUES
                (:id, :unit_id, :session_id, :group_id, 'coder_c', 'AI 编码员 C',
                 :coi_categories, :coi_categories, :coding_reason,
                 NOW(), NOW(), NOW())
            ON CONFLICT (unit_id, coder_role) DO UPDATE SET
                coi_categories = EXCLUDED.coi_categories,
                ai_original_categories = EXCLUDED.ai_original_categories,
                coding_reason = EXCLUDED.coding_reason,
                coded_by = 'AI 编码员 C',
                coded_at = NOW(),
                updated_at = NOW()
        """), rows)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        _audit(
            request_id=request_id, session_id=session_id, operation="coding",
            stage="failed", phase="save", error_type=type(exc).__name__,
            error=str(exc), results=generated,
        )
        raise
    items = await _load_session_items(db, session_id)
    selected_ids = set(payload.unit_ids)
    readback = [
        {
            "unit_id": item.unit_id,
            "has_ai_result": item.has_ai_result,
            "coi_categories": item.coi_categories,
            "coding_reason": item.coding_reason,
            "coded_at": item.coded_at,
        }
        for item in items
        if item.unit_id in selected_ids
    ]
    _audit(
        request_id=request_id, session_id=session_id, operation="coding",
        stage="saved", saved=len(rows), results=generated, readback=readback,
    )
    return AiCodingResponse(saved=len(rows), items=items)


@router.put("/sessions/{session_id}/codes", response_model=AiCodingResponse)
async def save_ai_code_adjustments(
    session_id: str,
    payload: SaveAiCodesRequest,
    db: AsyncSession = Depends(get_db),
) -> AiCodingResponse:
    unit_ids = [code.unit_id for code in payload.codes]
    await _load_selected_units(db, session_id, unit_ids)
    existing_result = await db.execute(text("""
        SELECT unit_id
          FROM coi_unit_codes
         WHERE session_id = :session_id
           AND coder_role = 'coder_c'
           AND unit_id = ANY(:unit_ids)
    """), {"session_id": session_id, "unit_ids": list(dict.fromkeys(unit_ids))})
    existing_ids = {row[0] for row in existing_result.all()}
    if existing_ids != set(unit_ids):
        raise HTTPException(status_code=409, detail="部分 AI 编码不存在，请重新加载后再试")
    rows = [
        {
            "unit_id": code.unit_id,
            "session_id": session_id,
            "coi_categories": _normalize_categories(code.coi_categories),
            "coding_reason": code.coding_reason.strip(),
        }
        for code in payload.codes
    ]
    if any(not row["coding_reason"] for row in rows):
        raise HTTPException(status_code=400, detail="编码理由不能为空")
    await db.execute(text("""
        UPDATE coi_unit_codes
           SET coi_categories = :coi_categories,
               coding_reason = :coding_reason,
               coded_by = '研究员调整',
               updated_at = NOW()
         WHERE unit_id = :unit_id
           AND session_id = :session_id
           AND coder_role = 'coder_c'
    """), rows)
    await db.commit()
    return AiCodingResponse(saved=len(rows), items=await _load_session_items(db, session_id))
