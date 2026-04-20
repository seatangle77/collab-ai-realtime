"""
关键词召回 + 信息缺口评估（合并为一次大模型调用）
输入：各成员发言文本
输出：关键词列表，每个词含 needs_prompt / target_user_id / reason
"""
from __future__ import annotations

import json
import logging
from typing import Any

from openai import OpenAI

from ..settings import nlp_settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "你是一个对话分析助手，负责从多人对话中提取关键词并判断成员间的理解差异。"
    "严格按 JSON 返回，不输出任何解释文字和 markdown。"
)

_USER_TEMPLATE = """\
以下是多人对话，每位成员的发言单独列出：

{member_sections}

请完成以下两件事：
1. 提取 0~5 个对部分成员可能陌生的词，必须同时满足：
   - 对话中真实出现的词
   - 有一定理解门槛，属于以下类型之一：
     · 专业术语或学科概念（某领域才懂的词）
     · 缩写或简称（可能有人不知道全称）
     · 新梗、网络用语、地域性说法
     · 某成员反复提及但其他成员没有回应或跟进的概念
   - 排除：日常口语、通用名词、全员都在使用的词（说明大家都懂）
   - 没有符合条件的词时，返回空数组，不要凑数
2. 对每个词判断成员间是否存在理解差异
   - needs_prompt=true：某成员对这个词的理解明显与他人不同，需要提示
   - target_user_id：需要收到提示的成员 ID，没有则填空字符串
   - reason：一句话说明判断理由

返回严格 JSON（不含任何其他内容）：
{{
  "keywords": [
    {{
      "word": "量化宽松",
      "needs_prompt": true,
      "target_user_id": "u_terry",
      "reason": "Terry 多次提及但其他人没有回应，可能不熟悉这个概念"
    }},
    {{
      "word": "搭子",
      "needs_prompt": false,
      "target_user_id": "",
      "reason": "三人都在用这个词且语境一致"
    }}
  ]
}}\
"""


def _get_client() -> OpenAI:
    return OpenAI(
        api_key=nlp_settings.qwen_api_key,
        base_url=nlp_settings.qwen_base_url,
    )


def _build_member_sections(member_texts: dict[str, str]) -> str:
    parts: list[str] = []
    for uid, text in member_texts.items():
        content = (text or "").strip() or "（无发言）"
        parts.append(f"【成员 {uid} 发言】\n{content}")
    return "\n\n".join(parts)


def _normalize_item(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    word = str(raw.get("word", "")).strip()
    if not word:
        return None
    return {
        "word": word,
        "needs_prompt": bool(raw.get("needs_prompt", False)),
        "target_user_id": str(raw.get("target_user_id", "") or "").strip(),
        "reason": str(raw.get("reason", "")).strip(),
    }


def recall_with_gap(member_texts: dict[str, str]) -> dict[str, Any]:
    """
    调用大模型，一次完成关键词召回和信息缺口评估。

    :param member_texts: {user_id: 发言文本}
    :return: {"keywords": [{"word", "needs_prompt", "target_user_id", "reason"}]}
    """
    texts = {uid: t for uid, t in member_texts.items() if isinstance(t, str) and t.strip()}
    if len(texts) < 2:
        return {"keywords": []}

    if not nlp_settings.qwen_api_key:
        logger.warning("[candidate_recall] qwen_api_key 未配置，跳过召回")
        return {"keywords": []}

    member_sections = _build_member_sections(texts)
    prompt = _USER_TEMPLATE.format(member_sections=member_sections)

    logger.info("[candidate_recall] 调用大模型，成员数=%d", len(texts))

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=nlp_settings.reasoning_model,
            max_tokens=600,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        content = (response.choices[0].message.content or "").strip()
        parsed = json.loads(content)
        raw_keywords = parsed.get("keywords", [])
        if not isinstance(raw_keywords, list):
            logger.warning("[candidate_recall] 返回格式异常，keywords 不是列表")
            return {"keywords": []}

        keywords: list[dict[str, Any]] = []
        for item in raw_keywords:
            normalized = _normalize_item(item)
            if normalized is not None:
                keywords.append(normalized)

        logger.info("[candidate_recall] 召回完成，关键词数=%d", len(keywords))
        return {"keywords": keywords}

    except json.JSONDecodeError as e:
        logger.warning("[candidate_recall] JSON 解析失败: %s", e)
        return {"keywords": []}
    except Exception as e:
        logger.warning("[candidate_recall] 调用失败: %s", e)
        return {"keywords": []}
