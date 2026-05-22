"""
关键词召回 + 信息缺口评估（合并为一次大模型调用）
输入：各成员发言文本
输出：关键词列表，每个词含 needs_prompt / target_user_ids / reason
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from openai import OpenAI

from ..settings import QWEN_CHAT_EXTRA_BODY, nlp_settings
from . import embedder, similarity

logger = logging.getLogger(__name__)

_SEMANTIC_DEDUP_THRESHOLD = 0.87

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
   - 必须返回原文中连续出现的完整词语或短语，不能拆开、截断或只取其中一个字
   - 中文关键词通常至少为 2 个字；只有像 AI、PT、MBTI 这类固定英文缩写可以少于 2 个字
   - 例如：原文出现“搭子”时只能返回“搭子”，不能返回“搭”；原文出现“熟人社会”时不能只返回“熟人”或“社会”
   - 如果拿不准是否为完整词语，宁可不返回，也不要返回单字或残缺词
   - 有一定理解门槛，属于以下类型之一：
     · 专业术语或学科概念（某领域才懂的词）
     · 缩写或简称（可能有人不知道全称）
     · 新梗、网络用语、地域性说法
     · 某成员反复提及但其他成员没有回应或跟进的概念
   - 如果多个候选词语义高度相近，只保留最有代表性的一个，不要同时返回
   - 排除：日常口语、通用名词、全员都在使用的词（说明大家都懂）
   - 没有符合条件的词时，返回空数组，不要凑数
2. 对每个词判断是否需要给未提及者提示
   - 先判断哪些成员明确提到了这个词，或明显使用了这个词的同义表达
   - needs_prompt=true：这个词有理解门槛，且存在没有提到/没有回应这个词的成员
   - target_user_ids：需要收到提示的成员 ID 列表，必须包含所有符合条件的成员，不能只挑一部分
   - target_user_ids 必须只包含没有提到这个词的成员
   - 绝对不要把提示推送给已经提到这个词的成员
   - 如果只有 1 个成员提到该词，且该词值得解释，则把其余所有没有提到该词的成员都加入 target_user_ids，不能遗漏
   - 如果所有成员都提到了这个词，则 needs_prompt=false，target_user_ids=[]
   - 如果这个词不值得解释，则 needs_prompt=false，target_user_ids=[]
   - reason：一句话说明判断理由

返回严格 JSON（不含任何其他内容）：
{{
  "keywords": [
    {{
      "word": "量化宽松",
      "needs_prompt": true,
      "target_user_ids": ["u_lily", "u_tom"],
      "reason": "Terry 提到了“量化宽松”，Lily 和 Tom 没有提到或回应，这个词可能需要补充解释"
    }},
    {{
      "word": "搭子",
      "needs_prompt": false,
      "target_user_ids": [],
      "reason": "三人都在用这个词且语境一致"
    }}
  ]
}}\
"""


_VALIDATE_SYSTEM_PROMPT = (
    "你是一个语言质量检测助手。严格按 JSON 返回，不输出任何解释文字和 markdown。"
)

_VALIDATE_USER_TEMPLATE = """\
以下词语提取自语音转文本对话，每个词附带其在对话中出现的原句上下文。
请判断每个词是否是有明确语义的真实词语（含专业术语、网络用语、英文缩写等），还是语音识别产生的乱码或残片。

判断标准：
- is_valid=true：有明确词义，无论常见或罕见（如"量化宽松""搭子""MBTI""内卷"）
- is_valid=false：无实际意义，看起来像语音识别错误（如"八子""哦的""嗯然"）

词语列表：
{word_list}

返回严格 JSON（不含任何其他内容）：
{{
  "results": [
    {{"word": "搭子", "is_valid": true}},
    {{"word": "八子", "is_valid": false}}
  ]
}}\
"""

_SENTENCE_SPLIT_RE = re.compile(r"[。！？.!?\n]+")


def _find_word_context(word: str, member_texts: dict[str, str]) -> str:
    """在所有成员文本里找到包含该词的第一个句子作为上下文。"""
    for text in member_texts.values():
        for sentence in _SENTENCE_SPLIT_RE.split(text):
            sentence = sentence.strip()
            if sentence and word in sentence:
                return sentence
    return ""


def _validate_keywords(
    keywords: list[dict[str, Any]],
    member_texts: dict[str, str],
) -> set[str]:
    """
    用轻模型批量验证候选词是否是有语义的真实词语。
    失败时 fail open：返回所有词都有效，不阻断主流程。
    """
    if not keywords:
        return set()

    if not nlp_settings.qwen_api_key:
        return {item["word"] for item in keywords}

    word_list = [
        {"word": item["word"], "context": _find_word_context(item["word"], member_texts)}
        for item in keywords
    ]
    prompt = _VALIDATE_USER_TEMPLATE.format(word_list=json.dumps(word_list, ensure_ascii=False))

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=nlp_settings.fast_model,
            max_tokens=300,
            extra_body=QWEN_CHAT_EXTRA_BODY,
            messages=[
                {"role": "system", "content": _VALIDATE_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        content = (response.choices[0].message.content or "").strip()
        parsed = json.loads(content)
        results = parsed.get("results", [])
        valid_words: set[str] = set()
        for r in results:
            if isinstance(r, dict) and r.get("is_valid"):
                word = str(r.get("word", "")).strip()
                if word:
                    valid_words.add(word)
        logger.info(
            "[candidate_recall] 验证完成，有效词=%d / 候选词=%d，过滤掉: %s",
            len(valid_words),
            len(keywords),
            [item["word"] for item in keywords if item["word"] not in valid_words],
        )
        return valid_words
    except json.JSONDecodeError as e:
        logger.warning("[candidate_recall] 验证 JSON 解析失败，fail open: %s", e)
        return {item["word"] for item in keywords}
    except Exception as e:
        logger.warning("[candidate_recall] 验证调用失败，fail open: %s", e)
        return {item["word"] for item in keywords}


def _keyword_mention_count(word: str, member_texts: dict[str, str]) -> int:
    return sum((text or "").count(word) for text in member_texts.values())


def _choose_representative_keyword(
    group: list[dict[str, Any]],
    member_texts: dict[str, str],
    original_index: dict[str, int],
) -> dict[str, Any]:
    return max(
        group,
        key=lambda item: (
            bool(item.get("needs_prompt")),
            len(str(item.get("word", ""))),
            _keyword_mention_count(str(item.get("word", "")), member_texts),
            -original_index.get(str(item.get("word", "")), 0),
        ),
    )


def _dedupe_semantic_keywords(
    keywords: list[dict[str, Any]],
    member_texts: dict[str, str],
    threshold: float = _SEMANTIC_DEDUP_THRESHOLD,
) -> list[dict[str, Any]]:
    """
    用本地 embedding 对当前窗口候选词做语义去重。
    失败时 fail open：返回原始列表，不阻断主流程。
    """
    if len(keywords) < 2:
        return keywords

    words = [str(item.get("word", "")).strip() for item in keywords]
    try:
        embeddings = embedder.encode(words)
        parent = list(range(len(words)))

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(i: int, j: int) -> None:
            root_i = find(i)
            root_j = find(j)
            if root_i != root_j:
                parent[root_j] = root_i

        for i in range(len(words)):
            for j in range(i + 1, len(words)):
                score = similarity.cosine_similarity(embeddings[i], embeddings[j])
                if score >= threshold:
                    union(i, j)

        groups_by_root: dict[int, list[dict[str, Any]]] = {}
        for idx, item in enumerate(keywords):
            groups_by_root.setdefault(find(idx), []).append(item)

        if all(len(group) == 1 for group in groups_by_root.values()):
            return keywords

        original_index = {word: idx for idx, word in enumerate(words)}
        result: list[dict[str, Any]] = []
        for group in groups_by_root.values():
            result.append(_choose_representative_keyword(group, member_texts, original_index))

        dropped = [item["word"] for item in keywords if item not in result]
        logger.info(
            "[candidate_recall] 语义去重完成，剩余关键词数=%d（原=%d），合并掉: %s",
            len(result),
            len(keywords),
            dropped,
        )
        return result
    except Exception as e:
        logger.warning("[candidate_recall] 语义去重失败，fail open: %s", e)
        return keywords


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
    raw_target_user_ids = raw.get("target_user_ids", [])
    target_user_ids = raw_target_user_ids if isinstance(raw_target_user_ids, list) else []
    return {
        "word": word,
        "needs_prompt": bool(raw.get("needs_prompt", False)),
        "target_user_ids": [
            str(uid).strip()
            for uid in target_user_ids
            if str(uid).strip()
        ],
        "reason": str(raw.get("reason", "")).strip(),
    }


def recall_with_gap(member_texts: dict[str, str]) -> dict[str, Any]:
    """
    调用大模型，一次完成关键词召回和信息缺口评估。

    :param member_texts: {user_id: 发言文本}
    :return: {"keywords": [{"word", "needs_prompt", "target_user_ids", "reason"}]}
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
            extra_body=QWEN_CHAT_EXTRA_BODY,
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

        if keywords:
            valid_words = _validate_keywords(keywords, texts)
            before_count = len(keywords)
            keywords = [kw for kw in keywords if kw["word"] in valid_words]
            if len(keywords) < before_count:
                logger.info(
                    "[candidate_recall] 验证过滤后剩余关键词数=%d（原=%d）",
                    len(keywords),
                    before_count,
                )

        if keywords:
            keywords = _dedupe_semantic_keywords(keywords, texts)

        return {"keywords": keywords}

    except json.JSONDecodeError as e:
        logger.warning("[candidate_recall] JSON 解析失败: %s", e)
        return {"keywords": []}
    except Exception as e:
        logger.warning("[candidate_recall] 调用失败: %s", e)
        return {"keywords": []}
