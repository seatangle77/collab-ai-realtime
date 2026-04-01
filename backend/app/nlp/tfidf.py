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

from .segmenter import STOPWORDS


def _tokenize(text: str) -> list[str]:
    """jieba 分词 + 去停用词，供 TfidfVectorizer 使用"""
    return [
        t for t in jieba.lcut(text)
        if t.strip() and t not in STOPWORDS and len(t) > 1
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

    # 跨成员求和，得到全局词重要性排名
    summed_scores = np.asarray(tfidf_matrix.sum(axis=0)).flatten()
    top_indices = summed_scores.argsort()[::-1][:top_n]
    keywords = [feature_names[i] for i in top_indices]

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
