"""Admin API for AI coder C in the CoI workflow."""
from __future__ import annotations

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
from ..db import get_db
from ..settings import QWEN_CHAT_EXTRA_BODY, nlp_settings
from .deps import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/admin/coi-ai-coding",
    tags=["admin-coi-ai-coding"],
    dependencies=[Depends(require_admin)],
)

COI_CATEGORIES = {"TE", "EX", "IN", "RE"}
MAX_UNITS_PER_REQUEST = 20
MANUAL_PATH = Path(__file__).resolve().parents[1] / "resources" / "coi_ai_coding_manual.md"

CoiCategory = Literal["TE", "EX", "IN", "RE"]


class AiCodingItemOut(ApiModel):
    unit_id: str
    order_index: int
    content: str
    start_time: float | None
    coi_categories: list[CoiCategory]
    ai_original_categories: list[CoiCategory]
    coding_reason: str
    coded_by: str | None
    coded_at: datetime | None
    updated_at: datetime | None


class GenerateAiCodesRequest(ApiModel):
    unit_ids: list[str] = Field(min_length=1, max_length=MAX_UNITS_PER_REQUEST)


class SaveAiCodeIn(ApiModel):
    unit_id: str
    coi_categories: list[CoiCategory] = Field(min_length=1, max_length=4)
    coding_reason: str = Field(min_length=1, max_length=2000)


class SaveAiCodesRequest(ApiModel):
    codes: list[SaveAiCodeIn] = Field(min_length=1)


class AiCodingResponse(ApiModel):
    saved: int
    items: list[AiCodingItemOut]


def _new_code_id() -> str:
    return "cuc" + uuid.uuid4().hex[:12]


def _normalize_categories(value: Any) -> list[CoiCategory]:
    if not isinstance(value, list):
        raise ValueError("coi_categories 必须是数组")
    selected = {str(item).upper() for item in value}
    if not selected or not selected.issubset(COI_CATEGORIES):
        raise ValueError("CoI 分类必须是 TE、EX、IN、RE 的非空组合")
    return [category for category in ("TE", "EX", "IN", "RE") if category in selected]  # type: ignore[misc]


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
        coi_categories=list(row["coi_categories"] or []),
        ai_original_categories=list(row["ai_original_categories"] or []),
        coding_reason=row["coding_reason"] or "",
        coded_by=row["coded_by"],
        coded_at=row["coded_at"],
        updated_at=row["updated_at"],
    )


async def _load_session_items(db: AsyncSession, session_id: str) -> list[AiCodingItemOut]:
    result = await db.execute(text("""
        SELECT u.id AS unit_id, u.order_index, u.content, u.start_time,
               c.coi_categories, c.ai_original_categories, c.coding_reason,
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


async def _generate_codes(units: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not nlp_settings.qwen_api_key:
        raise HTTPException(status_code=503, detail="AI 模型尚未配置")
    try:
        manual = MANUAL_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        logger.exception("读取 CoI AI 编码手册失败")
        raise HTTPException(status_code=500, detail="无法读取 CoI 编码手册") from exc

    unit_text = "\n".join(
        f"[{unit['id']}] {unit['content']}" for unit in units
    )
    user_prompt = (
        "请逐条编码以下观点单元。严格返回 JSON，不要输出 Markdown 或其他文字。\n"
        "输出格式：{\"results\":[{\"unit_id\":\"...\","
        "\"coi_categories\":[\"TE\"],\"reason\":\"简短中文理由\"}]}\n"
        "必须返回每个输入 unit_id，且不得增加不存在的 unit_id。\n\n"
        f"观点单元：\n{unit_text}"
    )
    client = AsyncOpenAI(
        api_key=nlp_settings.qwen_api_key,
        base_url=nlp_settings.qwen_base_url,
        timeout=60.0,
    )
    try:
        response = await client.chat.completions.create(
            model=nlp_settings.reasoning_model,
            max_tokens=2500,
            extra_body=QWEN_CHAT_EXTRA_BODY,
            messages=[
                {"role": "system", "content": manual},
                {"role": "user", "content": user_prompt},
            ],
        )
        raw = response.choices[0].message.content or ""
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
        return [by_id[unit["id"]] for unit in units]
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("[CoI/AI-C] 编码或解析失败: %s", exc)
        raise HTTPException(status_code=502, detail="AI 编码失败，请稍后重试") from exc


@router.get("/sessions/{session_id}", response_model=list[AiCodingItemOut])
async def get_ai_codes(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[AiCodingItemOut]:
    return await _load_session_items(db, session_id)


@router.post("/sessions/{session_id}/generate", response_model=AiCodingResponse)
async def generate_ai_codes(
    session_id: str,
    payload: GenerateAiCodesRequest,
    db: AsyncSession = Depends(get_db),
) -> AiCodingResponse:
    units = await _load_selected_units(db, session_id, payload.unit_ids)
    await db.rollback()
    generated = await _generate_codes(units)
    units = await _load_selected_units(db, session_id, payload.unit_ids)
    rows = [
        {
            "id": _new_code_id(),
            "unit_id": item["unit_id"],
            "session_id": session_id,
            "group_id": next(unit["group_id"] for unit in units if unit["id"] == item["unit_id"]),
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
    return AiCodingResponse(saved=len(rows), items=await _load_session_items(db, session_id))


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
