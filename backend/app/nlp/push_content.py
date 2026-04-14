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

import json
import logging
from typing import Any

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
        "检测数据：基于讨论语境判断成员{username}对关键词\"{keyword}\"存在理解缺口"
        "（参考语义相似度得分 {skw_score}）。\n"
        "请根据当前讨论语境，为\"{keyword}\"生成一个简洁清晰的定义或相关论据，用自然友好的语气呈现，"
        "帮助该成员更好地理解这个概念。要求：语气自然不说教，像朋友补充信息一样，不超过40字，"
        "直接给出定义或论据，不要解释原因。"
    ),
}

_SYSTEM_PROMPT = "你是一个温暖积极的讨论伙伴，擅长用简短自然的语言引导小组讨论。只输出提示内容本身，不要加任何前缀或解释。"

_BATCH_SYSTEM_PROMPT = """你不是普通文案助手，而是一个“小组协作引导助手”。你的任务不是泛泛鼓励成员发言，而是根据小组讨论中的协作挑战，为不同对象生成有针对性的认知支持内容，帮助讨论继续推进。

你需要理解以下4类协作挑战，并按对应目标生成内容：

1. personal_stagnation
含义：某个成员思路停滞，认知资源枯竭，难以继续产出新观点，逐渐退出讨论。
设计目标：提供一个该成员尚未提及的新观点、新切入角度或新问题，降低其重新参与讨论的认知门槛。
输出风格：像同伴轻轻抛出一个新角度，不要空泛鼓励，不要重复该成员已经表达过的话。

2. group_stagnation
含义：全组陷入僵局，讨论停止，无人打破沉默。
设计目标：提供一个当前讨论尚未覆盖的新方向，帮助全组重新开始讨论。
输出风格：像自然地抛出一个新话题，轻松、具体、可接续。

3. shallow_expression
含义：某个成员虽然在说话，但表达停留在表面，重复观点、缺乏逻辑延伸、缺少理由或例子。
设计目标：提供一个针对性的追问或深化问题，引导该成员进一步展开理由、依据、例子或影响。
输出风格：像同伴好奇追问，不要直接替他回答，不要给长解释。

4. information_gap
含义：某个成员对关键概念的理解与他人存在明显偏差，可能形成理解障碍。
设计目标：提供一个简洁清晰的定义、解释或相关论据，帮助该成员快速校准理解。
输出风格：像同伴补充背景知识，清楚、自然、不说教。

通用原则：
- 每条输出都必须服务于“推进协作讨论”，不是安慰、总结或评价。
- 必须结合当前讨论摘要、最近发言、目标对象的 challenge_type、diagnosis、design_goal、evidence 来生成。
- 生成内容必须围绕【当前讨论摘要】中的焦点主题展开，不能跳出当前讨论范围。
- 不同对象的输出要有明显区分，不能只是换名字。
- 要避免重复最近发言中已经说过的话。
- 不要输出分析过程，不要解释为什么这样写。
- 只返回 JSON，不要输出 markdown，不要输出额外文字。

长度要求：
- personal_stagnation / group_stagnation / shallow_expression：不超过30个字
- information_gap：不超过40个字

返回格式必须严格符合：
{
  "items": [
    {
      "user_id": "目标用户ID，或 ALL",
      "challenge_type": "协作挑战类型",
      "needs_prompt": true,
      "analysis": "一句简短分析",
      "content": "生成的提示内容；如果不需要提示则为空字符串"
    }
  ]
}"""

_BATCH_USER_TEMPLATE = """以下是本轮小组讨论的上下文，请你为需要干预的对象分别生成提示内容。

【当前讨论摘要】
{summary}

【最近发言】
{transcripts}

【成员列表】
{members_json}

【本轮待干预对象】
{targets_json}

请逐个处理 targets 中的对象，并遵循以下规则：
1. 对每个 target 都生成一条结果。
2. 如果 challenge_type 是 personal_stagnation，请在当前摘要焦点内，给该成员一个“他还没深入过”的新观点、新角度或新问题，帮助他重新接入讨论。
3. 如果 challenge_type 是 group_stagnation，请在当前摘要焦点内，给全组一个尚未充分展开的新讨论方向，帮助打破沉默。
4. 如果 challenge_type 是 shallow_expression，请围绕该成员当前表达的薄弱点，生成一句追问，推动其继续展开理由、依据、例子或影响，并优先根据 evidence.member_quotes 中该成员的具体发言来追问。
5. 如果 challenge_type 是 information_gap，请围绕 target 中的关键词或概念，给出一句简洁定义、解释或论据，帮助其修正理解偏差。
6. analysis 字段写一句简短判断，说明为什么该对象当前需要这种干预。
7. needs_prompt 字段必须明确为 true 或 false；如果为 false，则 content 置为空字符串。
8. 输出必须简短、自然、可直接显示在智能眼镜或手机上。
9. 不要重复“你可以”“建议你”“试着想想”这种空泛表达。
10. 不要输出任何解释，只返回 JSON。
11. 生成内容必须围绕【当前讨论摘要】中的焦点主题展开，不能跳出当前讨论范围。

再次强调，只返回以下格式：
{{
  "items": [
    {{
      "user_id": "u1",
      "challenge_type": "personal_stagnation",
      "needs_prompt": true,
      "analysis": "...",
      "content": "..."
    }}
  ]
}}"""


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


def generate_push_content_batch(
    session_id: str,
    summary: str,
    transcripts: str,
    members: list[dict[str, Any]],
    targets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    批量返回成员分析结果。
    """
    logger.info(
        "[NLP/push-batch] input: session_id=%s members=%d targets=%d transcripts=%d条",
        session_id,
        len(members),
        len(targets),
        len([l for l in transcripts.splitlines() if l.strip()]) if transcripts else 0,
    )
    if not targets:
        return []
    if not nlp_settings.qwen_api_key:
        return []

    prompt = _BATCH_USER_TEMPLATE.format(
        summary=summary or "（暂无摘要）",
        transcripts=transcripts or "（暂无发言）",
        members_json=json.dumps(members, ensure_ascii=False, indent=2),
        targets_json=json.dumps(targets, ensure_ascii=False, indent=2),
    )

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=nlp_settings.reasoning_model,
            max_tokens=800,
            messages=[
                {"role": "system", "content": _BATCH_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        content = response.choices[0].message.content or ""
        raw = content.strip()
        result = json.loads(raw)
        items = result.get("items", [])
        if not isinstance(items, list):
            return []

        normalized: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            user_id = str(item.get("user_id", "")).strip()
            challenge_type = str(item.get("challenge_type", "")).strip()
            needs_prompt = bool(item.get("needs_prompt", False))
            analysis = str(item.get("analysis", "")).strip()
            generated = str(item.get("content", "")).strip()
            if not user_id or not challenge_type:
                continue
            normalized.append(
                {
                    "user_id": user_id,
                    "challenge_type": challenge_type,
                    "needs_prompt": needs_prompt,
                    "analysis": analysis,
                    "content": generated if needs_prompt else "",
                }
            )

        logger.info("[NLP/push-batch] output: %d items", len(normalized))
        return normalized
    except Exception as e:
        logger.warning("[NLP/push-batch] 调用失败: %s", e)
        return []
