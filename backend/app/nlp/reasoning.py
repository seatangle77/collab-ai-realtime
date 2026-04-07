"""
论证结构判定模块
策略：规则优先，LLM 兜底
- 第一层：关键词规则，有明确指示词 → 直接返回，不调 LLM
- 第二层：规则无法判定时 → 调 Qwen API 做语义判断
- 使用 OpenAI 兼容接口对接 Qwen，模型名从配置读取，不硬编码
"""
from __future__ import annotations

import json
import logging

from openai import OpenAI

from ..settings import nlp_settings

logger = logging.getLogger(__name__)

# ── 规则词表 ──────────────────────────────────────────────────────────────────

# 有明确因果/转折关系，说明发言含 reasoning
REASONING_KEYWORDS: set[str] = {
    "因为", "由于", "所以", "因此", "导致", "基于",
    "既然", "之所以", "正是因为", "正因为",
}

# 有具体举例/数据/引用，说明发言含 evidence
EVIDENCE_KEYWORDS: set[str] = {
    "例如", "比如", "举例", "举个例子", "数据显示", "研究表明",
    "根据", "调查显示", "统计显示", "报告指出", "事实上",
    "以……为例", "以...为例",
}

# ── LLM 调用 ──────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "你是一个语言分析助手。请判断用户发言是否包含以下两种成分，"
    "只返回 JSON，不要任何解释。"
)

_USER_TEMPLATE = """判断以下发言：
1. has_reasoning：是否有明确的原因解释（如"因为"、"由于"、"导致"等因果逻辑，或隐式的逻辑推理）
2. has_evidence：是否有具体的例子、数据、事实或引用作为证据支持

发言：{text}

只返回 JSON：{{"has_reasoning": true或false, "has_evidence": true或false}}"""


def _get_client() -> OpenAI:
    """创建 Qwen OpenAI 兼容客户端"""
    return OpenAI(
        api_key=nlp_settings.qwen_api_key,
        base_url=nlp_settings.qwen_base_url,
    )


def _call_llm(text: str) -> dict[str, bool]:
    """调用 Qwen API 做语义判定，返回 {has_reasoning, has_evidence}"""
    if not nlp_settings.qwen_api_key:
        return {"has_reasoning": False, "has_evidence": False}

    client = _get_client()

    text_preview = text[:50] + ("..." if len(text) > 50 else "")
    logger.info("[NLP/reasoning] input: text=\"%s\" (%d字) method=llm", text_preview, len(text))

    try:
        response = client.chat.completions.create(
            model=nlp_settings.reasoning_model,
            max_tokens=64,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": _USER_TEMPLATE.format(text=text)},
            ],
        )
    except Exception as e:
        logger.warning("[NLP/reasoning] 调用失败: %s", e)
        # 认证失败、网络波动、上游限流等情况均降级，不影响主接口可用性
        return {"has_reasoning": False, "has_evidence": False}

    content = response.choices[0].message.content
    if not content:
        return {"has_reasoning": False, "has_evidence": False}

    raw = content.strip()
    try:
        result = json.loads(raw)
        parsed = {
            "has_reasoning": bool(result.get("has_reasoning", False)),
            "has_evidence":  bool(result.get("has_evidence", False)),
        }
        logger.info("[NLP/reasoning] output: %s", parsed)
        return parsed
    except (json.JSONDecodeError, KeyError):
        # LLM 输出格式异常时，保守返回 False
        return {"has_reasoning": False, "has_evidence": False}


# ── 对外接口 ──────────────────────────────────────────────────────────────────

def has_reasoning(text: str) -> dict:
    """
    判定发言是否含论证结构。

    返回：
    - has_reasoning: 是否含原因解释
    - has_evidence:  是否含证据/举例
    - method:        "rule"（规则判定）或 "llm"（Qwen兜底）
    """
    rule_reasoning = any(kw in text for kw in REASONING_KEYWORDS)
    rule_evidence  = any(kw in text for kw in EVIDENCE_KEYWORDS)

    # 两项规则都能判定 → 直接返回，不调 LLM
    if rule_reasoning and rule_evidence:
        return {
            "has_reasoning": True,
            "has_evidence":  True,
            "method": "rule",
        }

    # 规则至少有一项为 False → 用 Qwen 做完整判断
    llm_result = _call_llm(text)
    return {
        "has_reasoning": rule_reasoning or llm_result["has_reasoning"],
        "has_evidence":  rule_evidence  or llm_result["has_evidence"],
        "method": "llm",
    }
