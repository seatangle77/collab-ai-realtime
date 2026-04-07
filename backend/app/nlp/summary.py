# -*- coding: utf-8 -*-
"""
讨论摘要生成模块
每 120s 触发一次，基于上一轮摘要 + 当前窗口发言，调用 Qwen API 生成滚动摘要（≤200字）
"""
from __future__ import annotations

import logging
from openai import OpenAI

from ..settings import nlp_settings

logger = logging.getLogger(__name__)

# ── Prompt ────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = "你是一个专业的讨论记录助手，擅长提炼小组讨论的核心内容。只输出摘要本身，不要加任何前缀或解释。"

_PROMPT_TEMPLATE = (
    "以下是一场小组讨论的内容。请基于上一轮摘要和当前新增发言，更新讨论摘要。\n"
    "上一轮摘要：{prev_summary}\n"
    "当前新增发言：\n{transcripts}\n"
    "请输出更新后的摘要，包含以下内容：\n"
    "- 当前讨论主题\n"
    "- 已提出的主要观点（去重）\n"
    "- 各成员的主要立场\n"
    "- 当前讨论进展与焦点\n"
    "请用简洁的结构化文字输出，不超过200字。"
)


# ── Qwen 调用 ─────────────────────────────────────────────────────────────────

def _get_client() -> OpenAI:
    return OpenAI(
        api_key=nlp_settings.qwen_api_key,
        base_url=nlp_settings.qwen_base_url,
    )


def generate_summary(
    transcripts: list[dict[str, str]],
    prev_summary: str = "",
) -> str:
    """
    生成滚动摘要。
    transcripts: [{"user_id": "uxx", "text": "发言内容"}, ...]
    返回摘要字符串，失败时返回空字符串。
    """
    if not transcripts:
        return ""

    # 格式化发言记录
    transcript_text = "\n".join(
        f"{t.get('user_id', '未知')}：{t.get('text', '')}"
        for t in transcripts
        if t.get("text", "").strip()
    )
    if not transcript_text.strip():
        return ""

    prompt = _PROMPT_TEMPLATE.format(
        prev_summary=prev_summary or "（本轮为第一次摘要，无历史摘要）",
        transcripts=transcript_text,
    )

    if not nlp_settings.qwen_api_key:
        return ""

    prev_preview = (prev_summary[:30] + "...") if len(prev_summary) > 30 else prev_summary
    logger.info(
        "[NLP/summary] input: transcripts=%d条 prev_summary=\"%s\"",
        len(transcripts), prev_preview or "（无）",
    )

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=nlp_settings.reasoning_model,
            max_tokens=300,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
        )
        content = response.choices[0].message.content or ""
        result = content.strip()
        logger.info("[NLP/summary] output: \"%s\" (%d字)", result[:40] + ("..." if len(result) > 40 else ""), len(result))
        return result
    except Exception as e:
        logger.warning("[NLP/summary] 调用失败: %s", e)
        return ""
