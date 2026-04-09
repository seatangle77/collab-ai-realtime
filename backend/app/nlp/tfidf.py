"""
TF-IDF 关键词提取模块
- 每个成员的发言作为独立文档，不合并
- 返回全局高频关键词 + 每个关键词在每位成员发言中的上下文句子
- 上下文句子供后续 embed + Skw 计算直接使用
"""
from __future__ import annotations

import re

import jieba
from sklearn.feature_extraction.text import TfidfVectorizer
import numpy as np

from .lexicon_loader import (
    get_reweight_config,
    load_gap_exclude_words,
    load_highfreq_words,
    load_subjective_words,
)
from .segmenter import STOPWORDS

GAP_EXCLUDE_WORDS = load_gap_exclude_words()
SUBJECTIVE_WORDS = load_subjective_words()
HIGHFREQ_WORDS = load_highfreq_words()
REWEIGHT_CONFIG = get_reweight_config()


def _tokenize(text: str) -> list[str]:
    """jieba 分词 + 去停用词，供 TfidfVectorizer 使用"""
    return [
        t for t in jieba.lcut(text)
        if t.strip()
        and len(t) > 1
        and t not in STOPWORDS
        and t not in GAP_EXCLUDE_WORDS
    ]


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
    - NTUSD 主观词: 乘以 ntusd_weight
    - SUBTLEX 高频词: 乘以 subtlex_weight
    """
    scores = raw_scores.copy()
    enable_ntusd_reweight = bool(REWEIGHT_CONFIG["enable_ntusd_reweight"])
    enable_subtlex_reweight = bool(REWEIGHT_CONFIG["enable_subtlex_reweight"])
    ntusd_weight = float(REWEIGHT_CONFIG["ntusd_weight"])
    subtlex_weight = float(REWEIGHT_CONFIG["subtlex_weight"])

    for idx, word in enumerate(feature_names):
        if word in GAP_EXCLUDE_WORDS:
            scores[idx] = 0.0
            continue
        if enable_ntusd_reweight and word in SUBJECTIVE_WORDS:
            scores[idx] *= ntusd_weight
        if enable_subtlex_reweight and word in HIGHFREQ_WORDS:
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
