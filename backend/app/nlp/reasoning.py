"""
论证结构判定模块
- batch_has_reasoning：全员批量判定（一次 LLM 调用，返回逐成员四字段），供主分析链路使用
"""
from __future__ import annotations

import json
import logging
from typing import TypedDict

from openai import OpenAI

from ..settings import QWEN_CHAT_EXTRA_BODY, nlp_settings

logger = logging.getLogger(__name__)

# ── 规则词表 ──────────────────────────────────────────────────────────────────

REASONING_KEYWORDS: tuple[str, ...] = (
    "因为", "由于", "所以", "因此", "因而", "从而", "于是", "故而",
    "导致", "造成", "引发", "决定了", "取决于",
    "基于", "依据", "按照", "由此可见",
    "既然", "之所以", "正是因为", "正因为",
    "说明", "意味着", "表明", "可见",
    "如果", "假如", "若", "那么",
    "但是", "不过", "然而", "相反",
    "相比之下", "另一方面", "换句话说",
)

EVIDENCE_KEYWORDS: tuple[str, ...] = (
    "例如", "比如", "举例", "举个例子", "以……为例", "以...为例",
    "数据显示", "数据表明", "研究表明", "实验表明",
    "根据", "依据", "调查显示", "统计显示", "报告指出", "资料显示",
    "事实上", "实践中", "现实中", "案例", "样本", "观察到",
)

_REASONING_KEYWORDS_TEXT = "、".join(REASONING_KEYWORDS)
_EVIDENCE_KEYWORDS_TEXT = "、".join(EVIDENCE_KEYWORDS)

def _get_client() -> OpenAI:
    return OpenAI(
        api_key=nlp_settings.qwen_api_key,
        base_url=nlp_settings.qwen_base_url,
    )


# ── 批量判定（主分析链路用）──────────────────────────────────────────────────

class MemberReasoningInput(TypedDict):
    user_id: str
    text: str


class MemberReasoningResult(TypedDict):
    user_id: str
    reasoning_status: bool | None
    evidence_status: bool | None
    reasoning_source: str
    evidence_source: str


_BATCH_SYSTEM = (
    "你是一个语言分析助手，负责逐成员判断本轮发言是否含论证结构。\n\n"
    f"理由信号词（出现即强信号，说明有论证）：{_REASONING_KEYWORDS_TEXT}\n"
    f"依据信号词（出现即强信号，说明有证据）：{_EVIDENCE_KEYWORDS_TEXT}\n\n"
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
        reasoning_status=None,
        evidence_status=None,
        reasoning_source=reason,
        evidence_source=reason,
    )


def batch_has_reasoning(members: list[MemberReasoningInput]) -> list[MemberReasoningResult]:
    """
    全员批量论证结构判定，一次 LLM 调用返回逐成员四字段结果。
    无发言的成员直接返回降级结果，不进入 LLM。
    失败时每个成员均返回 reasoning_status=None 的降级结果。
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
            extra_body=QWEN_CHAT_EXTRA_BODY,
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
            reasoning_status=item.get("reasoning_status") if isinstance(item.get("reasoning_status"), bool) else None,
            evidence_status=item.get("evidence_status") if isinstance(item.get("evidence_status"), bool) else None,
            reasoning_source=str(item.get("reasoning_source") or "").strip() or "无说明",
            evidence_source=str(item.get("evidence_source") or "").strip() or "无说明",
        ))

    logger.info("[NLP/reasoning_batch] 批量判定完成 成员数=%d", len(results))
    return results
