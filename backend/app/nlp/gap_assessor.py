"""
信息缺口 LLM 评估器
输入：候选词、上下文、SKW 辅助值
输出：结构化评估结果（每个词一条）
"""
from __future__ import annotations

import json
import logging
from typing import Any

from openai import OpenAI

from ..settings import nlp_settings

logger = logging.getLogger(__name__)

VALID_GAP_TYPES = {
    "术语不懂",
    "缩写不懂",
    "文化引用",
    "抽象概念未对齐",
    "指代不清",
}

_SYSTEM_PROMPT = """你是一个小组讨论的信息缺口评估助手。目标是识别“是否需要给某位成员推一个解释提示”。
你必须严格按 JSON 返回，不能输出 markdown，不能输出解释段落。"""

_USER_TEMPLATE = """请按以下 rubric 对候选词逐个判断：
1) 这个词是本次讨论的核心概念吗？
2) 这个词需要背景知识才能理解吗？
3) 对话里是否已被清楚解释过？
4) 是否存在成员间明显用法差异？
5) 是否需要给某个成员推送提示？目标是谁？
6) 置信度（0-1）

【窗口摘要】
{summary}

【成员发言】
{member_context}

【候选词】
{keywords_json}

【辅助SKW分数（仅参考）】
{skw_json}

返回格式（严格 JSON）：
{{
  "items": [
    {{
      "keyword": "词本身",
      "needs_prompt": true,
      "target_user_id": "u123 或空字符串",
      "gap_type": "术语不懂/缩写不懂/文化引用/抽象概念未对齐/指代不清",
      "confidence": 0.82,
      "reason": "一句话说明",
      "skw_score": 0.21
    }}
  ]
}}"""


def _get_client() -> OpenAI:
    return OpenAI(
        api_key=nlp_settings.qwen_api_key,
        base_url=nlp_settings.qwen_base_url,
    )


def _build_member_context(member_texts: dict[str, str]) -> str:
    parts: list[str] = []
    for uid, text in member_texts.items():
        content = (text or "").strip() or "（无发言）"
        parts.append(f"【成员 {uid} 发言】\n{content}")
    return "\n\n".join(parts)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, f))


def _normalize_item(raw: dict[str, Any], skw_scores: dict[str, float]) -> dict[str, Any] | None:
    keyword = str(raw.get("keyword", "")).strip()
    if not keyword:
        return None

    needs_prompt = bool(raw.get("needs_prompt", False))
    target_user_id = str(raw.get("target_user_id", "") or "").strip()
    gap_type = str(raw.get("gap_type", "抽象概念未对齐")).strip()
    if gap_type not in VALID_GAP_TYPES:
        gap_type = "抽象概念未对齐"

    confidence = _safe_float(raw.get("confidence", 0.0), 0.0)
    reason = str(raw.get("reason", "")).strip()
    skw_score = _safe_float(raw.get("skw_score", skw_scores.get(keyword, 0.0)), 0.0)

    return {
        "keyword": keyword,
        "needs_prompt": needs_prompt,
        "target_user_id": target_user_id,
        "gap_type": gap_type,
        "confidence": confidence,
        "reason": reason,
        "skw_score": skw_score,
    }


def assess_gap(
    keywords: list[str],
    summary: str,
    member_texts: dict[str, str],
    skw_scores: dict[str, float],
) -> list[dict[str, Any]]:
    if not keywords:
        return []

    if not nlp_settings.qwen_api_key:
        return [
            {
                "keyword": kw,
                "needs_prompt": False,
                "target_user_id": "",
                "gap_type": "抽象概念未对齐",
                "confidence": 0.0,
                "reason": "未配置模型",
                "skw_score": _safe_float(skw_scores.get(kw, 0.0), 0.0),
            }
            for kw in keywords
        ]

    member_context = _build_member_context(member_texts)
    prompt = _USER_TEMPLATE.format(
        summary=summary or "（暂无摘要）",
        member_context=member_context or "（暂无发言）",
        keywords_json=json.dumps(keywords, ensure_ascii=False),
        skw_json=json.dumps(skw_scores, ensure_ascii=False),
    )

    logger.info(
        "[NLP/assess-gap] input: keywords=%d members=%d",
        len(keywords),
        len(member_texts),
    )

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=nlp_settings.reasoning_model,
            max_tokens=1200,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        content = (response.choices[0].message.content or "").strip()
        parsed = json.loads(content)
        items = parsed.get("items", [])
        if not isinstance(items, list):
            return []

        normalized: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            normalized_item = _normalize_item(item, skw_scores)
            if normalized_item is not None:
                normalized.append(normalized_item)

        logger.info("[NLP/assess-gap] output: items=%d", len(normalized))
        return normalized
    except Exception as e:
        logger.warning("[NLP/assess-gap] 调用失败: %s", e)
        return []
