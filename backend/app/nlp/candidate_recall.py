"""
信息缺口候选召回
- 中文为主：TF-IDF 关键词 + 抽象概念词 + 名词短语
- 英文为辅：全大写缩写（2-5）
"""
from __future__ import annotations

import re
from collections import defaultdict

from .lexicon_loader import (
    load_abstract_concepts,
    load_gap_exclude_words,
)
from .segmenter import STOPWORDS, get_pipeline
from .tfidf import extract_tfidf

ABSTRACT_CONCEPTS = load_abstract_concepts()
GAP_EXCLUDE_WORDS = load_gap_exclude_words()
NOUN_POS_PREFIXES: tuple[str, ...] = ("n", "vn")
# 不能用 \b（在中文相邻场景下容易漏匹配，如 "MVP和"）。
# 用前后不是英文字母的约束，兼容中英文混排。
UPPER_ACRONYM_RE = re.compile(r"(?<![A-Z])[A-Z]{2,5}(?![A-Z])")
NOISE_ACRONYMS: set[str] = {"OK", "NO", "YES", "IT", "TO", "IN", "ON", "AT"}


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


def _is_noun(flag: str) -> bool:
    return any(flag.startswith(prefix) for prefix in NOUN_POS_PREFIXES)


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def _extract_noun_phrases(text: str) -> set[str]:
    pipeline = get_pipeline()
    result = pipeline(text, tasks=["tok/fine", "pos/pku"])
    words = _flatten_terms(result["tok/fine"])
    flags = _flatten_terms(result["pos/pku"])
    if not words or not flags:
        return set()

    out: set[str] = set()
    buf: list[str] = []
    for word, flag in zip(words, flags):
        token = word.strip()
        if not token:
            continue
        if _is_noun(flag) and token not in STOPWORDS and token not in GAP_EXCLUDE_WORDS:
            buf.append(token)
            continue

        if len(buf) >= 2:
            phrase = "".join(buf[:4]).strip()
            if 2 <= len(phrase) <= 16 and _contains_cjk(phrase):
                out.add(phrase)
        buf = []

    if len(buf) >= 2:
        phrase = "".join(buf[:4]).strip()
        if 2 <= len(phrase) <= 16 and _contains_cjk(phrase):
            out.add(phrase)
    return out


def recall_candidates(member_texts: dict[str, str], top_n: int = 15) -> dict:
    """
    返回候选词：
    - keywords: 按优先级排序后的候选词
    - sources: keyword -> source（tfidf / acronym / abstract / noun_phrase）
    """
    if not member_texts:
        return {"keywords": [], "sources": {}}

    texts = [v for v in member_texts.values() if isinstance(v, str) and v.strip()]
    if not texts:
        return {"keywords": [], "sources": {}}

    tfidf_res = extract_tfidf(member_texts, top_n=min(20, max(top_n, 10)))
    tfidf_keywords = tfidf_res.get("keywords", [])

    acronym_members: dict[str, set[str]] = defaultdict(set)
    noun_phrases: set[str] = set()
    abstract_hits: set[str] = set()

    for uid, text in member_texts.items():
        if not text:
            continue

        for hit in UPPER_ACRONYM_RE.findall(text):
            if len(hit) < 2 or hit in NOISE_ACRONYMS:
                continue
            acronym_members[hit].add(uid)

        noun_phrases |= _extract_noun_phrases(text)
        for concept in ABSTRACT_CONCEPTS:
            if concept in text:
                abstract_hits.add(concept)

    acronyms = [w for w, members in acronym_members.items() if len(members) >= 2]

    ordered: list[str] = []
    sources: dict[str, str] = {}

    def add_words(words: list[str] | set[str], source: str) -> None:
        for w in words:
            token = w.strip()
            if not token:
                continue
            if token in GAP_EXCLUDE_WORDS:
                continue
            if token in ordered:
                continue
            ordered.append(token)
            sources[token] = source
            if len(ordered) >= top_n:
                return

    add_words(tfidf_keywords, "tfidf")
    if len(ordered) < top_n:
        add_words(acronyms, "acronym")
    if len(ordered) < top_n:
        add_words(sorted(abstract_hits), "abstract")
    if len(ordered) < top_n:
        add_words(sorted(noun_phrases), "noun_phrase")

    return {"keywords": ordered[:top_n], "sources": sources}
