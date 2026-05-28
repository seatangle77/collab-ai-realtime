"""User-side questionnaire API for SRCC and PCS scales."""
from __future__ import annotations

import json
import statistics
from typing import Any, Mapping

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .api_model import ApiModel
from .auth import get_current_user
from .db import get_db

router = APIRouter(prefix="/api/questionnaire", tags=["questionnaire"])

# ─────────────────────────────────────────────────────────────────
# Scale definitions (source of truth in code)
# ─────────────────────────────────────────────────────────────────

SRCC_ITEMS: list[dict] = [
    # Clarification and Resolution (Q1–Q6)
    {"id": "q1", "dimension": "clarification", "en": "When I did not understand my peers' understanding of the problem I asked them to clarify it.", "zh": "当我不理解同伴对问题的理解时，我会请他们进一步澄清。"},
    {"id": "q2", "dimension": "clarification", "en": "When I did not understand my peers' perspectives I asked them to clarify their perspectives.", "zh": "当我不理解同伴的观点时，我会请他们进一步说明自己的观点。"},
    {"id": "q3", "dimension": "clarification", "en": "When I saw a misunderstanding of the problem among the team members I tried to resolve the issues.", "zh": "当我发现团队成员之间对问题存在误解时，我会尝试解决这些问题。"},
    {"id": "q4", "dimension": "clarification", "en": "When solving the problem as a group I explained the possible solution alternative(s) to my peers.", "zh": "当我们作为小组解决问题时，我会向同伴解释可能的解决方案。"},
    {"id": "q5", "dimension": "clarification", "en": "When I did not understand my peers' solution alternatives I asked them to clarify it.", "zh": "当我不理解同伴提出的解决方案时，我会请他们进一步澄清。"},
    {"id": "q6", "dimension": "clarification", "en": "When there was a misunderstanding to the solution alternatives among the team members I tried to resolve the issue.", "zh": "当团队成员之间对解决方案存在误解时，我会尝试解决这个问题。"},
    # Elaboration (Q7–Q11)
    {"id": "q7", "dimension": "elaboration", "en": "When I solved the problem I described the relationships between stakeholders and the problem to my peers.", "zh": "当我解决问题时，我会向同伴描述利益相关者与问题之间的关系。"},
    {"id": "q8", "dimension": "elaboration", "en": "When my peers explained their understanding of the problem I elaborated on their understanding.", "zh": "当同伴解释他们对问题的理解时，我会在他们的理解基础上进一步展开说明。"},
    {"id": "q9", "dimension": "elaboration", "en": "When my peers stated possible problem constraints I elaborated on their understanding.", "zh": "当同伴提出可能的问题限制条件时，我会进一步拓展他们的理解。"},
    {"id": "q10", "dimension": "elaboration", "en": "When my peers suggested a solution I elaborated on their understanding.", "zh": "当同伴提出解决方案时，我会进一步拓展他们的理解。"},
    {"id": "q11", "dimension": "elaboration", "en": "After my peers explained their solution alternatives I shared my understanding with them.", "zh": "在同伴解释他们的备选解决方案后，我会与他们分享我的理解。"},
    # Refuting (Q12–Q13)
    {"id": "q12", "dimension": "refuting", "en": "I refuted my peers' understanding(s) of the problem.", "zh": "我会反驳同伴对问题的理解。"},
    {"id": "q13", "dimension": "refuting", "en": "I refuted some of my peers' solution alternative(s).", "zh": "我会反驳同伴提出的某些备选解决方案。"},
    # Summarization (Q14–Q15)
    {"id": "q14", "dimension": "summarization", "en": "I summarized the group's understanding of the problem to understand the problem better.", "zh": "我会总结小组对问题的理解，以便更好地理解问题。"},
    {"id": "q15", "dimension": "summarization", "en": "I summarized the input of our team to come up with a solution.", "zh": "我会总结团队成员的输入，以形成解决方案。"},
]

PCS_ITEMS: list[dict] = [
    {"id": "q1", "dimension": "belonging", "en": "I feel that I belong to this group.", "zh": "我觉得自己属于这个小组。"},
    {"id": "q2", "dimension": "morale", "en": "I am happy to be part of this group.", "zh": "我很高兴成为这个小组的一员。"},
    {"id": "q3", "dimension": "belonging", "en": "I see myself as part of this group.", "zh": "我认为自己是这个小组的一部分。"},
    {"id": "q4", "dimension": "morale", "en": "This group is one of the best anywhere.", "zh": "我认为这个小组是非常优秀的小组之一。"},
    {"id": "q5", "dimension": "belonging", "en": "I feel that I am a member of this group.", "zh": "我觉得自己是这个小组的成员。"},
    {"id": "q6", "dimension": "morale", "en": "I am content to be part of this group.", "zh": "我对成为这个小组的一员感到满意。"},
]

SRCC_DIMENSIONS = {
    "clarification": "澄清与解决",
    "elaboration": "阐述与拓展",
    "refuting": "反驳与质疑",
    "summarization": "总结与整合",
}

PCS_DIMENSIONS = {
    "belonging": "归属感",
    "morale": "士气 / 积极情感",
}


# ─────────────────────────────────────────────────────────────────
# Score computation helpers
# ─────────────────────────────────────────────────────────────────

def _compute_srcc_result(responses: dict[str, int]) -> dict[str, Any]:
    dim_scores: dict[str, list[float]] = {d: [] for d in SRCC_DIMENSIONS}
    for item in SRCC_ITEMS:
        val = responses.get(item["id"])
        if val is not None:
            dim_scores[item["dimension"]].append(float(val))

    result: dict[str, Any] = {}
    all_vals: list[float] = []
    for dim, vals in dim_scores.items():
        if vals:
            avg = round(statistics.mean(vals), 4)
            result[f"{dim}_avg"] = avg
            all_vals.extend(vals)
        else:
            result[f"{dim}_avg"] = None

    result["total_avg"] = round(statistics.mean(all_vals), 4) if all_vals else None
    return result


def _compute_pcs_result(responses: dict[str, int]) -> dict[str, Any]:
    dim_scores: dict[str, list[float]] = {d: [] for d in PCS_DIMENSIONS}
    for item in PCS_ITEMS:
        val = responses.get(item["id"])
        if val is not None:
            dim_scores[item["dimension"]].append(float(val))

    result: dict[str, Any] = {}
    all_vals: list[float] = []
    for dim, vals in dim_scores.items():
        if vals:
            avg = round(statistics.mean(vals), 4)
            result[f"{dim}_avg"] = avg
            all_vals.extend(vals)
        else:
            result[f"{dim}_avg"] = None

    result["total_avg"] = round(statistics.mean(all_vals), 4) if all_vals else None
    return result


# ─────────────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────────────

class SrccResponses(ApiModel):
    q1: int | None = Field(default=None, ge=1, le=7)
    q2: int | None = Field(default=None, ge=1, le=7)
    q3: int | None = Field(default=None, ge=1, le=7)
    q4: int | None = Field(default=None, ge=1, le=7)
    q5: int | None = Field(default=None, ge=1, le=7)
    q6: int | None = Field(default=None, ge=1, le=7)
    q7: int | None = Field(default=None, ge=1, le=7)
    q8: int | None = Field(default=None, ge=1, le=7)
    q9: int | None = Field(default=None, ge=1, le=7)
    q10: int | None = Field(default=None, ge=1, le=7)
    q11: int | None = Field(default=None, ge=1, le=7)
    q12: int | None = Field(default=None, ge=1, le=7)
    q13: int | None = Field(default=None, ge=1, le=7)
    q14: int | None = Field(default=None, ge=1, le=7)
    q15: int | None = Field(default=None, ge=1, le=7)


class PcsResponses(ApiModel):
    q1: int | None = Field(default=None, ge=1, le=7)
    q2: int | None = Field(default=None, ge=1, le=7)
    q3: int | None = Field(default=None, ge=1, le=7)
    q4: int | None = Field(default=None, ge=1, le=7)
    q5: int | None = Field(default=None, ge=1, le=7)
    q6: int | None = Field(default=None, ge=1, le=7)


class UpsertSrccRequest(ApiModel):
    responses: SrccResponses


class UpsertPcsRequest(ApiModel):
    responses: PcsResponses


class QuestionnaireEntryOut(ApiModel):
    user_id: str
    group_id: str | None
    condition: str | None
    srcc_responses: dict | None
    srcc_result: dict | None
    pcs_responses: dict | None
    pcs_result: dict | None
    updated_at: str | None


class ScaleMetaOut(ApiModel):
    srcc_items: list[dict]
    pcs_items: list[dict]
    srcc_dimensions: dict[str, str]
    pcs_dimensions: dict[str, str]


# ─────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────

@router.get("/meta", response_model=ScaleMetaOut)
async def get_scale_meta():
    """Return question definitions for the frontend to render."""
    return ScaleMetaOut(
        srcc_items=SRCC_ITEMS,
        pcs_items=PCS_ITEMS,
        srcc_dimensions=SRCC_DIMENSIONS,
        pcs_dimensions=PCS_DIMENSIONS,
    )


@router.get("/me", response_model=QuestionnaireEntryOut)
async def get_my_entry(
    current_user: Mapping[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = current_user["id"]
    row = await db.execute(
        text("""
            SELECT user_id, group_id, condition,
                   srcc_responses, srcc_result,
                   pcs_responses, pcs_result,
                   updated_at
            FROM questionnaire_entries
            WHERE user_id = :user_id
        """),
        {"user_id": user_id},
    )
    row = row.mappings().first()
    if not row:
        return QuestionnaireEntryOut(
            user_id=user_id,
            group_id=None,
            condition=None,
            srcc_responses=None,
            srcc_result=None,
            pcs_responses=None,
            pcs_result=None,
            updated_at=None,
        )
    return QuestionnaireEntryOut(
        user_id=row["user_id"],
        group_id=row["group_id"],
        condition=row["condition"],
        srcc_responses=row["srcc_responses"],
        srcc_result=row["srcc_result"],
        pcs_responses=row["pcs_responses"],
        pcs_result=row["pcs_result"],
        updated_at=row["updated_at"].isoformat() if row["updated_at"] else None,
    )


async def _get_user_group(user_id: str, db: AsyncSession) -> tuple[str, str] | None:
    """Return (group_id, condition) for the user's active group membership."""
    row = await db.execute(
        text("""
            SELECT g.id AS group_id, g.condition
            FROM group_memberships gm
            JOIN groups g ON g.id = gm.group_id
            WHERE gm.user_id = :user_id
              AND gm.status = 'active'
              AND g.is_active = true
            LIMIT 1
        """),
        {"user_id": user_id},
    )
    row = row.mappings().first()
    if not row:
        return None
    condition = row["condition"]
    if not condition:
        return None
    return row["group_id"], condition


@router.post("/srcc", response_model=QuestionnaireEntryOut)
async def upsert_srcc(
    payload: UpsertSrccRequest,
    current_user: Mapping[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = current_user["id"]
    group_info = await _get_user_group(user_id, db)
    if not group_info:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="未找到活跃的群组，或群组尚未配置实验条件（condition）",
        )
    group_id, condition = group_info

    responses_dict = payload.responses.model_dump(exclude_none=False)
    result = _compute_srcc_result({k: v for k, v in responses_dict.items() if v is not None})

    await db.execute(
        text("""
            INSERT INTO questionnaire_entries
                (user_id, group_id, condition, srcc_responses, srcc_result, updated_at)
            VALUES
                (:user_id, :group_id, :condition,
                 CAST(:srcc_responses AS jsonb), CAST(:srcc_result AS jsonb), NOW())
            ON CONFLICT (user_id) DO UPDATE SET
                group_id       = EXCLUDED.group_id,
                condition      = EXCLUDED.condition,
                srcc_responses = EXCLUDED.srcc_responses,
                srcc_result    = EXCLUDED.srcc_result,
                updated_at     = NOW()
        """),
        {
            "user_id": user_id,
            "group_id": group_id,
            "condition": condition,
            "srcc_responses": json.dumps(responses_dict),
            "srcc_result": json.dumps(result),
        },
    )
    await db.commit()
    return await get_my_entry(current_user=current_user, db=db)


@router.post("/pcs", response_model=QuestionnaireEntryOut)
async def upsert_pcs(
    payload: UpsertPcsRequest,
    current_user: Mapping[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = current_user["id"]
    group_info = await _get_user_group(user_id, db)
    if not group_info:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="未找到活跃的群组，或群组尚未配置实验条件（condition）",
        )
    group_id, condition = group_info

    responses_dict = payload.responses.model_dump(exclude_none=False)
    result = _compute_pcs_result({k: v for k, v in responses_dict.items() if v is not None})

    await db.execute(
        text("""
            INSERT INTO questionnaire_entries
                (user_id, group_id, condition, pcs_responses, pcs_result, updated_at)
            VALUES
                (:user_id, :group_id, :condition,
                 CAST(:pcs_responses AS jsonb), CAST(:pcs_result AS jsonb), NOW())
            ON CONFLICT (user_id) DO UPDATE SET
                group_id      = EXCLUDED.group_id,
                condition     = EXCLUDED.condition,
                pcs_responses = EXCLUDED.pcs_responses,
                pcs_result    = EXCLUDED.pcs_result,
                updated_at    = NOW()
        """),
        {
            "user_id": user_id,
            "group_id": group_id,
            "condition": condition,
            "pcs_responses": json.dumps(responses_dict),
            "pcs_result": json.dumps(result),
        },
    )
    await db.commit()
    return await get_my_entry(current_user=current_user, db=db)
