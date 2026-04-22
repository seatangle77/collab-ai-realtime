# -*- coding: utf-8 -*-
"""
推送文案生成模块
- info_gap               ≤ 40字，用户点击后触发，使用 reasoning_model（heavy）
- generate_group_silence  ≤ 30字，实时沉默检测触发，使用 fast_model
- analyze_members_batch  全员分析，每2分钟触发，使用 reasoning_model（heavy），返回大JSON
"""
from __future__ import annotations

import json
import logging
from typing import Any

from openai import AsyncOpenAI, OpenAI

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
        "检测数据：基于讨论语境判断成员{username}对关键词\"{keyword}\"存在理解缺口"
        "（参考语义相似度得分 {skw_score}）。\n"
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


def _get_async_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=nlp_settings.qwen_api_key,
        base_url=nlp_settings.qwen_base_url,
    )


async def generate_push_content(
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
    根据触发类型生成推送文案（异步）。
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
        client = _get_async_client()
        response = await client.chat.completions.create(
            model=nlp_settings.fast_model if trigger_type == "info_gap" else nlp_settings.reasoning_model,
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


# ── group_silence：fast_model 生成一句破冰话题 ────────────────────────────────

_GROUP_SILENCE_SYSTEM = (
    "你是一个温暖积极的讨论伙伴。根据当前讨论摘要和最近发言，"
    "生成一句自然友好的话题提示，帮助全组重新打开讨论。"
    "话题本身要有追问性质，让成员自然地说出理由或举例，而不只是表态。"
    "不超过30字，直接给出话题，不要任何前缀或解释。"
)

_GROUP_SILENCE_TEMPLATE = (
    "讨论摘要：{summary}\n"
    "最近发言记录：{transcripts}\n"
    "全组已沉默 {silence_s} 秒，请生成一句话题提示帮助全组重新开口，并自然引导成员说出自己的理由或具体例子。"
)


async def generate_group_silence(
    summary: str,
    transcripts: str,
    silence_s: int,
) -> str:
    """使用 fast_model 为群体沉默场景生成一句破冰提示，失败时返回空字符串。"""
    if not nlp_settings.qwen_api_key:
        return ""
    prompt = _GROUP_SILENCE_TEMPLATE.format(
        summary=summary or "（暂无摘要）",
        transcripts=transcripts or "（暂无发言）",
        silence_s=silence_s,
    )
    logger.info("[NLP/group_silence] 生成破冰话题 silence_s=%d", silence_s)
    try:
        client = _get_async_client()
        response = await client.chat.completions.create(
            model=nlp_settings.fast_model,
            max_tokens=60,
            messages=[
                {"role": "system", "content": _GROUP_SILENCE_SYSTEM},
                {"role": "user",   "content": prompt},
            ],
        )
        result = (response.choices[0].message.content or "").strip()
        logger.info("[NLP/group_silence] output: \"%s\"", result)
        return result
    except Exception as e:
        logger.warning("[NLP/group_silence] 调用失败: %s", e)
        return ""


# ── analyze_members_batch：heavy_model 全员分析大JSON ──────────────────────────

_ANALYZE_MEMBERS_SYSTEM = (
    "你是一个小组讨论分析专家。根据讨论摘要、发言记录和各成员的量化指标与论证结构判定结果，"
    "判断每位成员是否需要干预提示，并生成自然友好的推送文案（≤30字）。\n\n"
    "challenge_type 只能是：\n"
    "  stagnation — 参与不足、思路停滞或新增贡献不足。重点信号：speaking_ratio<0.15 或 info_gain<0.3。\n"
    "               干预目标：帮助成员重新进入讨论。文案风格：低门槛、鼓励式、重新开口导向。\n"
    "  shallow    — 阐述浅薄、表达浅层、结构不足或展开不充分。重点信号：ttr<0.4 或 arg_density<0.02 或 srep>0.65。\n"
    "               论证结构是判断 shallow 的核心输入，规则如下：\n"
    "               · reasoning_status=false 且 evidence_status=false，且本轮发言量不低 → 优先判断是否需要深化型干预\n"
    "               · reasoning_status=true  且 evidence_status=false → 优先引导补充例子、数据或事实依据\n"
    "               · reasoning_status=false 且 evidence_status=true  → 优先引导补充原因、逻辑或判断链条\n"
    "               · reasoning_status=true  且 evidence_status=true  → 视为结构较完整，再结合其他指标判断是否仍需干预\n"
    "               reasoning_source / evidence_source 是模型对该成员表达特征的文字说明，可作为生成 analysis 和 content 的参考。\n"
    "               干预目标：帮助成员补充理由、补充依据或继续展开。文案风格：追问式、深化式、展开导向。\n"
    "  none       — 不需要干预\n\n"
    "anchor 必须引用 transcripts 中真实存在的一条（使用该条的 transcript_id），不允许编造。\n"
    "严格按 JSON 返回，不输出任何解释或 markdown。"
)

_ANALYZE_MEMBERS_TEMPLATE = (
    "讨论摘要：{summary}\n\n"
    "最近发言记录：\n{transcripts}\n\n"
    "各成员指标与论证结构判定：\n{members_metrics}\n\n"
    "请对每位成员输出分析，返回格式：\n"
    '{"members": [{"user_id": "...", "challenge_type": "stagnation|shallow|none", '
    '"needs_prompt": true/false, "analysis": "一句中文分析", "content": "推送文案（≤30字）", '
    '"anchor": {"transcript_id": "...", "speaker_id": "...", "speaker_name": "...", "text": "..."} 或 null}]}'
)


async def analyze_members_batch(
    summary: str,
    transcripts_text: str,
    members_metrics_text: str,
) -> dict[str, Any]:
    """
    使用 reasoning_model 对所有成员做一次批量分析，返回大JSON。
    失败时返回 {"members": []}。
    """
    if not nlp_settings.qwen_api_key:
        return {"members": []}

    prompt = _ANALYZE_MEMBERS_TEMPLATE.format(
        summary=summary or "（暂无摘要）",
        transcripts=transcripts_text or "（暂无发言）",
        members_metrics=members_metrics_text,
    )
    logger.info("[NLP/analyze_members] 开始全员分析")
    try:
        client = _get_async_client()
        response = await client.chat.completions.create(
            model=nlp_settings.reasoning_model,
            max_tokens=1024,
            messages=[
                {"role": "system", "content": _ANALYZE_MEMBERS_SYSTEM},
                {"role": "user",   "content": prompt},
            ],
        )
        raw = (response.choices[0].message.content or "").strip()
        # 去除可能的 markdown 代码块包裹
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw)
        members = result.get("members", [])
        logger.info("[NLP/analyze_members] 返回成员数=%d", len(members))
        return {"members": members}
    except json.JSONDecodeError as e:
        logger.warning("[NLP/analyze_members] JSON 解析失败: %s", e)
        return {"members": []}
    except Exception as e:
        logger.warning("[NLP/analyze_members] 调用失败: %s", e)
        return {"members": []}
