# -*- coding: utf-8 -*-
"""
推送文案生成模块
- info_gap               ≤ 40字，用户点击后触发，使用 fast_model
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
    "info_gap": (
        "以下是当前小组讨论的摘要和最近的发言记录。\n"
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
    "你是一个温暖积极的讨论伙伴。"
    "输出一句自然友好的破冰话题，帮助全组重新打开讨论。"
    "话题本身要有追问性质，让成员自然地说出理由或举例，而不只是表态。"
    "不超过30字，直接给出话题，不要任何前缀或解释。"
)

_GROUP_SILENCE_TEMPLATE = (
    "讨论摘要：{summary}\n"
    "最近发言记录：{transcripts}\n"
    "全组已沉默 {silence_s} 秒。\n"
    "请基于以上上下文输出一句话题提示。"
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
    "客观评估每位成员的讨论表现。\n\n"
    "仅对确实存在明显问题的成员输出干预提示。\n"
    "表现正常、证据不足或无法确定时，应判定为 none，不生成干预。\n\n"
    "【数据缺失说明】\n"
    "指标值为“数据不足”时，表示该成员本轮发言量过少、首窗口无历史，或该指标无法可靠计算。\n"
    "数据不足不等于表现差，该指标不参与触发判断。不得因为数据不足本身判定 stagnation 或 shallow。\n\n"
    "【指标等级说明】\n"
    "speaking_ratio：<0.15 极低；0.15~0.25 偏低；≥0.25 正常。\n"
    "silence_s：>90s 较长时间未发言；≤90s 正常。\n"
    "info_gain：<0.3 低；≥0.3 正常或较高；数据不足不参与判断。\n"
    "TTR：<0.3 低；0.3~0.6 中；≥0.6 高。\n"
    "arg_density：<0.1 低；0.1~0.3 中；≥0.3 高。\n"
    "Srep：>0.65 高/重复；≤0.65 正常；数据不足不参与判断。\n"
    "reasoning_status：有=存在理由、因果、解释、推导、比较或权衡；无=没有明确论证结构；数据不足不参与判断。\n"
    "evidence_status：有=存在例子、事实、数据、引用、案例或观察；无=没有明确支撑依据；数据不足不参与判断。\n\n"
    "【分类规则】\n"
    "stagnation — 参与不足、思路停滞。\n"
    "强信号，单独触发：\n"
    "· speaking_ratio < 0.15，表示发言极少，是最直接的参与不足信号。\n"
    "弱信号，单独不触发：\n"
    "· info_gain < 0.3，表示内容新增较少，但可能是在认真听或延续同一主题。\n"
    "· silence_s > 90s，表示较长时间未发言，但需结合参与度判断。\n"
    "组合触发：\n"
    "· info_gain < 0.3 且 speaking_ratio < 0.25。\n"
    "注意：info_gain 为“数据不足”时，不参与 stagnation 判断；不要因为 info_gain 单独偏低就判定 stagnation。\n"
    "干预目标：帮助成员重新进入讨论。文案风格：低门槛、鼓励式、重新开口导向。\n\n"
    "shallow — 发言量尚可但内容深度不足。\n"
    "强信号，单独触发：\n"
    "· reasoning_status=无 且 evidence_status=无 且 speaking_ratio ≥ 0.15，表示成员发言量尚可，但完全没有论证结构或支撑依据。\n"
    "弱信号，需满足 2 条及以上才触发：\n"
    "· ttr < 0.3\n"
    "· srep > 0.65\n"
    "· arg_density < 0.1\n"
    "组合触发：\n"
    "· reasoning_status=无 且任意一条弱信号。\n"
    "注意：shallow 只用于“说了一些，但展开不足”的情况；发言极少时优先考虑 stagnation，不应仅因内容短而判 shallow；"
    "指标为“数据不足”时，不计入弱信号。\n"
    "干预目标：帮助成员补充理由或依据。文案风格：追问式、深化式、展开导向。\n\n"
    "none — 不需要干预。以下情况应判定为 none：\n"
    "· 未命中 stagnation 或 shallow 的强信号/组合触发条件\n"
    "· 仅有单一轻微信号偏低，但发言内容仍有实质贡献\n"
    "· reasoning_status=有 且 evidence_status=有，且没有明显低参与或重复问题\n"
    "· 成员发言较少但没有明确问题证据\n"
    "· 指标缺失较多，无法确定是否需要干预\n"
    "默认原则：证据不足时选择 none，不要猜测问题。\n\n"
    "【用户可见文案 content 约束】\n"
    "analysis 是内部分析，可说明触发原因；content 是发给用户看的文案，绝不能暴露内部判断、指标或参与状态。\n"
    "content 必须从发言记录里找到一个具体的主张、未被展开的方向或隐含的分歧，把它包进问句里——不能只用话题标签出题。\n"
    "shallow 的 content 必须针对 anchor 那句话追问更深一层：找出那句话里没说完的预设、隐含立场或未给出的理由，直接问它；不能脱离那句话生成泛化问题。\n"
    "stagnation 的 content 要从当前讨论里提一个有争议的具体点，让成员可以直接表态（同意/反对/补充），而不是泛泛邀请开口。\n"
    "content 语气亲切轻量，像同伴顺着话接一句；问句本身必须带一个立场、主张或两难张力，让对方有东西可以咬。\n"
    "content 禁止出现：发言少、参与度低、没听到你的声音、期待你的声音、大家期待、欢迎多分享、多说说、补充观点、会议进行中、讨论很热烈、内容质量正常、无需引导等泛化/评价性表达。\n"
    "content 禁止纯邀请式提问（即问句里没有任何具体立场或主张，只是开放邀请说话）。\n"
    "content 不要称呼用户姓名，不要评价用户表现，不要说教，不要像主持人点名。\n"
    "如果发言记录里找不到可追问的具体内容，content 留空且 needs_prompt=false。\n"
    "content 示例（注意：每条都从具体内容出题，而不是从话题标签出题）：\n"
    "· 有人说\"玩抽象就是缓解压力\"：你觉得它更像是在缓解压力，还是在制造新的社交暗号？\n"
    "· 有人说\"搭子就是随叫随到\"：如果对方叫了但你不想去，这段关系还成立吗？\n"
    "· 讨论里提到\"把压力转成玩笑\"：这个时候，玩笑是在消解问题，还是在帮你回避它？\n"
    "· 有人说\"效率最重要\"：效率高但结果没人认可，还算成功吗？\n\n"
    "【重要：anchor 约束】\n"
    "最近发言记录格式为：[transcript_id] user_id=系统用户ID speaker_name=展示名：原文。\n"
    "anchor 必须引用 transcripts 中真实存在的一条，不允许编造 transcript_id、user_id、speaker_name 或 text。\n"
    "anchor.speaker_id 必须填写 user_id（例如 u3140a51b），不能填写展示名。\n"
    "anchor.speaker_name 必须填写 speaker_name（例如 Ally）。\n"
    "anchor.text 必须尽量复制原文片段，不要总结、改写或翻译。\n"
    "shallow 类型必须提供 anchor，且 anchor 必须来自该 user_id 自己的发言。\n"
    "stagnation 若原因是未发言、低参与或长时间沉默，可以将 anchor 设为 null；若针对某句发言停滞，则提供 anchor。\n\n"
    "【输出格式】\n"
    "严格返回 JSON，不输出任何解释或 markdown：\n"
    '{"members": [{"user_id": "...", "challenge_type": "stagnation|shallow|none", '
    '"needs_prompt": true/false, "analysis": "一句中文分析", "content": "推送文案（≤30字）", '
    '"anchor": {"transcript_id": "...", "speaker_id": "...", "speaker_name": "...", "text": "..."} 或 null}]}'
)

_ANALYZE_MEMBERS_TEMPLATE = (
    "讨论摘要：{summary}\n\n"
    "最近发言记录：\n{transcripts}\n\n"
    "各成员指标与论证结构判定：\n{members_metrics}"
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
