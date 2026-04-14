"""
TF-IDF 关键词提取模块
- 每个成员的发言作为独立文档，不合并
- 返回全局高频关键词 + 每个关键词在每位成员发言中的上下文句子
- 上下文句子供后续 embed + Skw 计算直接使用
"""
from __future__ import annotations

import re

from sklearn.feature_extraction.text import TfidfVectorizer
import numpy as np

from .lexicon_loader import (
    load_abstract_concepts,
    get_reweight_config,
    load_concept_whitelist,
    load_gap_exclude_words,
    load_highfreq_words,
    load_subjective_words,
)
from .segmenter import STOPWORDS, get_pipeline

CONCEPT_WHITELIST = load_concept_whitelist()
ABSTRACT_CONCEPTS = load_abstract_concepts()
GAP_EXCLUDE_WORDS = load_gap_exclude_words()
SUBJECTIVE_WORDS = load_subjective_words()
HIGHFREQ_WORDS = load_highfreq_words()
REWEIGHT_CONFIG = get_reweight_config()
CONCEPT_POS_PREFIXES: tuple[str, ...] = ("n", "vn")


def _is_concept_pos(flag: str) -> bool:
    return any(flag.startswith(prefix) for prefix in CONCEPT_POS_PREFIXES)


def _flatten_terms(terms: object) -> list[str]:
    if not isinstance(terms, list) or not terms:
        return []
    first = terms[0]
    if isinstance(first, str):
        return [w for w in terms if isinstance(w, str)]
    flat: list[str] = []
    for sent in terms:
        if isinstance(sent, list):
            flat.extend([w for w in sent if isinstance(w, str)])
    return flat


def _tokenize(text: str) -> list[str]:
    """HanLP 分词 + 词性过滤 + 去停用词，供 TfidfVectorizer 使用"""
    enable_pos_filter = bool(REWEIGHT_CONFIG["enable_pos_filter"])
    tokens: list[str] = []

    pipeline = get_pipeline()
    result = pipeline(text, tasks=["tok/fine", "pos/pku"])
    words = _flatten_terms(result["tok/fine"])
    flags = _flatten_terms(result["pos/pku"])

    for word, flag in zip(words, flags):
        word = word.strip()
        if not word:
            continue
        if len(word) <= 1:
            continue
        if word in STOPWORDS or word in GAP_EXCLUDE_WORDS:
            continue
        if enable_pos_filter and not _is_concept_pos(flag):
            continue
        tokens.append(word)

    return tokens


def _split_sentences(text: str) -> list[str]:
    """按中英文标点切分句子"""
    parts = re.split(r"[。！？.!?\n]+", text)
    return [s.strip() for s in parts if s.strip()]


def _find_context(text: str, keyword: str) -> str:
    """
    在 text 中找到包含 keyword 的第一个句子作为上下文。
    如果没有则返回空字符串。
    """
    for sentence in _split_sentences(text):
        if keyword in sentence:
            return sentence
    return ""


def _apply_reweight(feature_names: list[str], raw_scores: np.ndarray) -> np.ndarray:
    """
    轻量重加权：
    - gap_exclude_words: 硬排除（分数置 0）
    - concept_whitelist: 概念词温和增益，非概念词轻微抑制
    - NTUSD 主观词: 乘以 ntusd_weight
    - SUBTLEX 高频词: 乘以 subtlex_weight
    """
    scores = raw_scores.copy()
    enable_concept_whitelist_reweight = bool(REWEIGHT_CONFIG["enable_concept_whitelist_reweight"])
    enable_ntusd_reweight = bool(REWEIGHT_CONFIG["enable_ntusd_reweight"])
    enable_subtlex_reweight = bool(REWEIGHT_CONFIG["enable_subtlex_reweight"])
    concept_whitelist_weight = float(REWEIGHT_CONFIG["concept_whitelist_weight"])
    non_concept_weight = float(REWEIGHT_CONFIG["non_concept_weight"])
    ntusd_weight = float(REWEIGHT_CONFIG["ntusd_weight"])
    subtlex_weight = float(REWEIGHT_CONFIG["subtlex_weight"])

    for idx, word in enumerate(feature_names):
        if word in GAP_EXCLUDE_WORDS:
            scores[idx] = 0.0
            continue
        if enable_concept_whitelist_reweight:
            if word in CONCEPT_WHITELIST:
                scores[idx] *= concept_whitelist_weight
            else:
                scores[idx] *= non_concept_weight
        if enable_ntusd_reweight and word in SUBJECTIVE_WORDS:
            scores[idx] *= ntusd_weight
        # 抽象概念词不做 SUBTLEX 高频降权，避免被不必要压低
        if enable_subtlex_reweight and word in HIGHFREQ_WORDS and word not in ABSTRACT_CONCEPTS:
            scores[idx] *= subtlex_weight
    return scores


def extract_tfidf(member_texts: dict[str, str], top_n: int = 5) -> dict:
    """
    对多位成员的发言做 TF-IDF 关键词提取。

    :param member_texts: {user_id: 发言文本, ...}
    :param top_n: 取权重最高的前 N 个关键词
    :return:
        - keywords: 全局 top N 关键词列表
        - member_keyword_contexts: {user_id: {keyword: 包含该词的上下文句子}}
    """
    if not member_texts:
        return {"keywords": [], "member_keyword_contexts": {}}

    member_ids = list(member_texts.keys())
    corpus = [member_texts[uid] for uid in member_ids]

    # TF-IDF：每位成员的文本为一份独立文档
    vectorizer = TfidfVectorizer(
        tokenizer=_tokenize,
        token_pattern=None,   # 使用自定义 tokenizer 时需关闭默认 pattern
    )
    try:
        tfidf_matrix = vectorizer.fit_transform(corpus)
    except ValueError:
        # 语料过短或无有效词时 sklearn 会报错
        return {"keywords": [], "member_keyword_contexts": {}}

    feature_names: list[str] = vectorizer.get_feature_names_out().tolist()

    # 跨成员求和，得到全局词重要性排名，再做轻量重加权
    raw_scores = np.asarray(tfidf_matrix.sum(axis=0)).flatten()
    final_scores = _apply_reweight(feature_names, raw_scores)

    keywords: list[str] = []
    sorted_indices = final_scores.argsort()[::-1]
    for idx in sorted_indices:
        if final_scores[idx] <= 0:
            continue
        keywords.append(feature_names[idx])
        if len(keywords) >= top_n:
            break

    # 为每位成员、每个关键词找到上下文句子
    member_keyword_contexts: dict[str, dict[str, str]] = {}
    for uid in member_ids:
        member_keyword_contexts[uid] = {
            kw: _find_context(member_texts[uid], kw)
            for kw in keywords
        }

    return {
        "keywords": keywords,
        "member_keyword_contexts": member_keyword_contexts,
    }
