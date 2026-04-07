# -*- coding: utf-8 -*-
"""
推送文案生成模块
根据触发类型调用 Qwen API 生成推送内容
- group_silence    ≤ 30字
- low_participation ≤ 30字
- shallow_discussion ≤ 30字
- info_gap          ≤ 40字（用户点击按钮后触发）
"""
from __future__ import annotations

import logging
from openai import OpenAI

from ..settings import nlp_settings

logger = logging.getLogger(__name__)

# ── Prompt 模板 ───────────────────────────────────────────────────────────────

_PROMPTS: dict[str, str] = {
    "group_silence": (
        "你是一个温暖积极的讨论伙伴。以下是当前小组讨论的摘要和最近的发言记录。\n"
        "讨论摘要：{summary}\n"
        "最近发言记录：{transcripts}\n"
        "检测数据：全组已持续沉默{silence_s}秒，超过30秒，说明讨论陷入僵局。\n"
        "请根据当前讨论摘要，找出一个全组尚未覆盖的讨论方向，用轻松自然的语气生成1条话题提示，"
        "帮助全组重新打开讨论。要求：语气轻松自然，像朋友抛出话题一样，不超过30字，直接给出话题，不要解释原因。"
    ),
    "low_participation": (
        "你是一个温暖积极的讨论伙伴。以下是当前小组讨论的摘要和最近的发言记录。\n"
        "讨论摘要：{summary}\n"
        "最近发言记录：{transcripts}\n"
        "检测数据：成员{username}过去120秒发言时长占比为{speaking_ratio}%，低于15%，"
        "说明该成员参与较少，判定陷入思路停滞。\n"
        "请根据当前讨论内容，找出一个尚未被成员{username}提及的有趣角度或观点，用鼓励、自然的语气生成1条简短提示，"
        "激发该成员加入讨论。要求：语气友好亲切，像朋友提醒一样，不超过30字，直接给出观点，不要解释原因。"
    ),
    "shallow_discussion": (
        "你是一个温暖积极的讨论伙伴。以下是当前小组讨论的摘要和最近的发言记录。\n"
        "讨论摘要：{summary}\n"
        "最近发言记录：{transcripts}\n"
        "检测数据：成员{username}过去120秒发言触发以下指标：{triggered_metrics}，说明该成员发言深度不足。\n"
        "请根据该成员的具体发言内容，找出一个可以深化的论点或逻辑缺口，用鼓励、好奇的语气生成1个追问，"
        "引导该成员进一步展开思考。要求：语气像朋友追问一样好奇自然，不超过30字，直接给出问题，不要解释原因。"
    ),
    "info_gap": (
        "你是一个温暖积极的讨论伙伴。以下是当前小组讨论的摘要和最近的发言记录。\n"
        "讨论摘要：{summary}\n"
        "最近发言记录：{transcripts}\n"
        "检测数据：成员{username}对关键词\"{keyword}\"的理解与其他成员存在明显分歧"
        "（S_kw = {skw_score}，低于0.3）。\n"
        "请根据当前讨论语境，为\"{keyword}\"生成一个简洁清晰的定义或相关论据，用自然友好的语气呈现，"
        "帮助该成员更好地理解这个概念。要求：语气自然不说教，像朋友补充信息一样，不超过40字，"
        "直接给出定义或论据，不要解释原因。"
    ),
}

_SYSTEM_PROMPT = "你是一个温暖积极的讨论伙伴，擅长用简短自然的语言引导小组讨论。只输出提示内容本身，不要加任何前缀或解释。"


# ── Qwen 调用 ─────────────────────────────────────────────────────────────────

def _get_client() -> OpenAI:
    return OpenAI(
        api_key=nlp_settings.qwen_api_key,
        base_url=nlp_settings.qwen_base_url,
    )


def generate_push_content(
    trigger_type: str,
    summary: str,
    transcripts: str,
    username: str = "",
    silence_s: int = 0,
    speaking_ratio: float = 0.0,
    triggered_metrics: str = "",
    keyword: str = "",
    skw_score: float = 0.0,
) -> str:
    """
    根据触发类型生成推送文案。
    transcripts 传入格式：各成员发言拼接字符串，调用方负责格式化。
    返回 AI 生成的文案字符串，失败时返回空字符串。
    """
    template = _PROMPTS.get(trigger_type)
    if not template:
        return ""

    prompt = template.format(
        summary=summary or "（暂无摘要）",
        transcripts=transcripts or "（暂无发言）",
        username=username,
        silence_s=silence_s,
        speaking_ratio=round(speaking_ratio * 100, 1),
        triggered_metrics=triggered_metrics,
        keyword=keyword,
        skw_score=round(skw_score, 2),
    )

    if not nlp_settings.qwen_api_key:
        return ""

    transcript_count = len([l for l in transcripts.splitlines() if l.strip()]) if transcripts else 0
    logger.info(
        "[NLP/push] input: trigger=%s user=%s silence_s=%s speaking_ratio=%s transcripts=%d条",
        trigger_type, username or "—", silence_s, round(speaking_ratio * 100, 1), transcript_count,
    )

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=nlp_settings.reasoning_model,
            max_tokens=80,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
        )
        content = response.choices[0].message.content or ""
        result = content.strip()
        logger.info("[NLP/push] output: \"%s\" (%d字)", result, len(result))
        return result
    except Exception as e:
        logger.warning("[NLP/push] 调用失败: %s", e)
        return ""
