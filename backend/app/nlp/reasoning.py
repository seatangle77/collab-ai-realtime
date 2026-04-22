"""
论证结构判定模块
- has_reasoning：单条文本判定（规则优先，LLM 兜底），供工具调试接口使用
- batch_has_reasoning：全员批量判定（一次 LLM 调用，返回逐成员四字段），供主分析链路使用
"""
from __future__ import annotations

import json
import logging
from typing import TypedDict

from openai import OpenAI

from ..settings import nlp_settings

logger = logging.getLogger(__name__)

# ── 规则词表 ──────────────────────────────────────────────────────────────────

REASONING_KEYWORDS: set[str] = {
    "因为", "由于", "所以", "因此", "导致", "基于",
    "既然", "之所以", "正是因为", "正因为",
}

EVIDENCE_KEYWORDS: set[str] = {
    "例如", "比如", "举例", "举个例子", "数据显示", "研究表明",
    "根据", "调查显示", "统计显示", "报告指出", "事实上",
    "以……为例", "以...为例",
}

# ── 单条判定（调试用）────────────────────────────────────────────────────────

_SINGLE_SYSTEM = (
    "你是一个语言分析助手。请判断用户发言是否包含以下两种成分，"
    "只返回 JSON，不要任何解释。"
)

_SINGLE_USER_TEMPLATE = """判断以下发言：
1. has_reasoning：是否有明确的原因解释（如"因为"、"由于"、"导致"等因果逻辑，或隐式的逻辑推理）
2. has_evidence：是否有具体的例子、数据、事实或引用作为证据支持

发言：{text}

只返回 JSON：{{"has_reasoning": true或false, "has_evidence": true或false}}"""


def _get_client() -> OpenAI:
    return OpenAI(
        api_key=nlp_settings.qwen_api_key,
        base_url=nlp_settings.qwen_base_url,
    )


def _call_llm_single(text: str) -> dict[str, bool]:
    if not nlp_settings.qwen_api_key:
        return {"has_reasoning": False, "has_evidence": False}
    client = _get_client()
    try:
        response = client.chat.completions.create(
            model=nlp_settings.fast_model,
            max_tokens=64,
            messages=[
                {"role": "system", "content": _SINGLE_SYSTEM},
                {"role": "user",   "content": _SINGLE_USER_TEMPLATE.format(text=text)},
            ],
        )
    except Exception as e:
        logger.warning("[NLP/reasoning] 单条调用失败: %s", e)
        return {"has_reasoning": False, "has_evidence": False}
    content = (response.choices[0].message.content or "").strip()
    try:
        result = json.loads(content)
        return {
            "has_reasoning": bool(result.get("has_reasoning", False)),
            "has_evidence":  bool(result.get("has_evidence", False)),
        }
    except (json.JSONDecodeError, KeyError):
        return {"has_reasoning": False, "has_evidence": False}


def has_reasoning(text: str) -> dict:
    """单条文本判定，供 /api/nlp/has_reasoning 调试接口使用。"""
    rule_reasoning = any(kw in text for kw in REASONING_KEYWORDS)
    rule_evidence  = any(kw in text for kw in EVIDENCE_KEYWORDS)
    if rule_reasoning and rule_evidence:
        return {"has_reasoning": True, "has_evidence": True, "method": "rule"}
    llm_result = _call_llm_single(text)
    return {
        "has_reasoning": rule_reasoning or llm_result["has_reasoning"],
        "has_evidence":  rule_evidence  or llm_result["has_evidence"],
        "method": "llm",
    }


# ── 批量判定（主分析链路用）──────────────────────────────────────────────────

class MemberReasoningInput(TypedDict):
    user_id: str
    text: str


class MemberReasoningResult(TypedDict):
    user_id: str
    reasoning_status: bool
    evidence_status: bool
    reasoning_source: str
    evidence_source: str


_BATCH_SYSTEM = (
    "你是一个语言分析助手，负责逐成员判断本轮发言是否含论证结构。\n\n"
    "理由信号词（出现即强信号，说明有论证）：因为、由于、所以、因此、导致、基于、既然、之所以、正是因为、正因为\n"
    "依据信号词（出现即强信号，说明有证据）：例如、比如、举例、举个例子、数据显示、研究表明、根据、调查显示、统计显示、报告指出、事实上、以……为例\n\n"
    "判断维度：\n"
    "1. reasoning_status（布尔）：本轮表达中是否存在明确的理由、因果、解释、推导、比较、权衡或其他逻辑展开\n"
    "2. evidence_status（布尔）：本轮表达中是否存在明确的例子、事实、数据、引用、案例、观察或其他支撑依据\n"
    "3. reasoning_source：一句简洁中文，直接对应该成员本轮表达特征，说明为何判定有/没有论证结构\n"
    "4. evidence_source：一句简洁中文，直接对应该成员本轮表达特征，说明为何判定有/没有支撑依据\n\n"
    "只返回 JSON 数组，不要任何解释或 markdown。"
)

_BATCH_USER_TEMPLATE = (
    "以下是本轮各成员的聚合发言，请逐一判定：\n\n"
    "{member_sections}\n\n"
    "严格返回 JSON 数组：\n"
    '[{{"user_id": "...", "reasoning_status": true/false, "evidence_status": true/false, '
    '"reasoning_source": "...", "evidence_source": "..."}}]'
)


def _make_fallback(user_id: str, reason: str = "无发言内容") -> MemberReasoningResult:
    return MemberReasoningResult(
        user_id=user_id,
        reasoning_status=False,
        evidence_status=False,
        reasoning_source=reason,
        evidence_source=reason,
    )


def batch_has_reasoning(members: list[MemberReasoningInput]) -> list[MemberReasoningResult]:
    """
    全员批量论证结构判定，一次 LLM 调用返回逐成员四字段结果。
    无发言的成员直接返回降级结果，不进入 LLM。
    失败时每个成员均返回 reasoning_status=False 的降级结果。
    """
    if not members:
        return []

    results: list[MemberReasoningResult] = []
    llm_members: list[MemberReasoningInput] = []

    for m in members:
        text = (m.get("text") or "").strip()
        if not text:
            results.append(_make_fallback(m["user_id"]))
        else:
            llm_members.append({"user_id": m["user_id"], "text": text})

    if not llm_members:
        return results

    if not nlp_settings.qwen_api_key:
        logger.warning("[NLP/reasoning_batch] qwen_api_key 未配置，全员降级")
        results.extend(_make_fallback(m["user_id"], "API 未配置") for m in llm_members)
        return results

    sections = "\n\n".join(
        f"【成员 {m['user_id']}】\n{m['text']}" for m in llm_members
    )
    prompt = _BATCH_USER_TEMPLATE.format(member_sections=sections)

    logger.info("[NLP/reasoning_batch] 批量判定 成员数=%d", len(llm_members))

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=nlp_settings.fast_model,
            max_tokens=512,
            messages=[
                {"role": "system", "content": _BATCH_SYSTEM},
                {"role": "user",   "content": prompt},
            ],
        )
        raw = (response.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        parsed: list[dict] = json.loads(raw)
    except Exception as e:
        logger.warning("[NLP/reasoning_batch] 调用或解析失败: %s", e)
        results.extend(_make_fallback(m["user_id"], "判定失败") for m in llm_members)
        return results

    uid_map = {item["user_id"]: item for item in parsed if isinstance(item, dict)}

    for m in llm_members:
        item = uid_map.get(m["user_id"])
        if not item:
            logger.warning("[NLP/reasoning_batch] 缺少成员 %s 的结果，使用降级", m["user_id"])
            results.append(_make_fallback(m["user_id"], "模型未返回该成员结果"))
            continue
        results.append(MemberReasoningResult(
            user_id=m["user_id"],
            reasoning_status=bool(item.get("reasoning_status", False)),
            evidence_status=bool(item.get("evidence_status", False)),
            reasoning_source=str(item.get("reasoning_source") or "").strip() or "无说明",
            evidence_source=str(item.get("evidence_source") or "").strip() or "无说明",
        ))

    logger.info("[NLP/reasoning_batch] 批量判定完成 成员数=%d", len(results))
    return results
