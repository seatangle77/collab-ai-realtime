#!/usr/bin/env python3
"""
NLP 微服务接口测试
覆盖：/api/nlp/segment · /api/nlp/embed · /api/nlp/similarity · /api/nlp/tfidf · /api/nlp/has_reasoning

运行前提：后端服务已在 127.0.0.1:8000 启动，且 NLP 模型已预加载。
运行方式：python -m backend.tests.test_nlp_api
"""
from __future__ import annotations

import sys
from typing import Any

import requests

BASE_URL = "http://127.0.0.1:8000"
ADMIN_HEADERS = {"X-Admin-Token": "TestAdminKey123"}
WRONG_HEADERS = {"X-Admin-Token": "wrong_token"}


def _log(ok: bool, message: str, extra: Any | None = None) -> bool:
    prefix = "✅" if ok else "❌"
    print(f"{prefix} {message}")
    if not ok and extra is not None:
        print("   详情:", extra)
    return ok


# ══════════════════════════════════════════════════════════════════
# 工具：构造固定长度向量
# ══════════════════════════════════════════════════════════════════

def _unit_vec(dim: int = 3) -> list[float]:
    """生成一个全为 1/dim 的单位向量，用于相似度边界测试"""
    v = 1.0 / dim
    return [v] * dim


def _zero_vec(dim: int = 3) -> list[float]:
    return [0.0] * dim


# ══════════════════════════════════════════════════════════════════
# 鉴权：所有接口统一校验
# ══════════════════════════════════════════════════════════════════

def test_auth_no_token() -> bool:
    endpoints = [
        ("POST", "/api/nlp/segment",      {"text": "测试"}),
        ("POST", "/api/nlp/embed",         {"texts": ["测试"]}),
        ("POST", "/api/nlp/similarity",    {"pairs": []}),
        ("POST", "/api/nlp/tfidf",         {"member_texts": {"u": "测试"}}),
        ("POST", "/api/nlp/has_reasoning", {"text": "测试"}),
    ]
    results = []
    for method, path, body in endpoints:
        resp = requests.request(method, f"{BASE_URL}{path}", json=body)
        ok = resp.status_code == 403
        results.append(_log(ok, f"无 Token → {path} 应返回 403", {"status": resp.status_code}))
    return all(results)


def test_auth_wrong_token() -> bool:
    endpoints = [
        ("POST", "/api/nlp/segment",      {"text": "测试"}),
        ("POST", "/api/nlp/embed",         {"texts": ["测试"]}),
        ("POST", "/api/nlp/similarity",    {"pairs": []}),
        ("POST", "/api/nlp/tfidf",         {"member_texts": {"u": "测试"}}),
        ("POST", "/api/nlp/has_reasoning", {"text": "测试"}),
    ]
    results = []
    for method, path, body in endpoints:
        resp = requests.request(method, f"{BASE_URL}{path}", json=body, headers=WRONG_HEADERS)
        ok = resp.status_code == 403
        results.append(_log(ok, f"错误 Token → {path} 应返回 403", {"status": resp.status_code}))
    return all(results)


# ══════════════════════════════════════════════════════════════════
# /api/nlp/segment
# ══════════════════════════════════════════════════════════════════

def test_segment_normal_with_reasoning() -> bool:
    """含论证词的正常句子：arg_density > 0，ttr 合理，tokens 非空"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/segment",
        json={"text": "我认为AI会影响教育，因为它改变了学生的学习方式和思维习惯"},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        return _log(False, "segment 正常句子（含论证词）应返回 200", resp.text)
    d = resp.json()
    ok = (
        len(d["tokens"]) > 0
        and d["arg_density"] > 0
        and 0 < d["ttr"] <= 1.0
        and d["token_count"] == len(d["tokens"])
        and d["unique_count"] <= d["token_count"]
    )
    return _log(ok, "segment：含论证词，字段值合理", d)


def test_segment_normal_no_reasoning() -> bool:
    """不含论证词的句子：arg_density = 0"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/segment",
        json={"text": "AI技术正在快速发展，改变很多行业"},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        return _log(False, "segment 无论证词应返回 200", resp.text)
    d = resp.json()
    ok = d["arg_density"] == 0.0
    return _log(ok, "segment：无论证词，arg_density = 0", d)


def test_segment_all_unique_words() -> bool:
    """每个词都不重复：ttr 应接近 1.0"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/segment",
        json={"text": "苹果 香蕉 橙子 西瓜 草莓 葡萄 柠檬"},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        return _log(False, "segment 全不重复词应返回 200", resp.text)
    d = resp.json()
    ok = d["token_count"] > 0 and d["ttr"] == 1.0
    return _log(ok, "segment：全不重复词，ttr = 1.0", d)


def test_segment_repeated_words() -> bool:
    """同一个词重复出现：ttr < 1.0"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/segment",
        json={"text": "学习学习学习学习学习"},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        return _log(False, "segment 重复词应返回 200", resp.text)
    d = resp.json()
    ok = d["token_count"] > 0 and d["ttr"] < 1.0
    return _log(ok, "segment：重复词，ttr < 1.0", d)


def test_segment_edge_empty_string() -> bool:
    """空字符串：所有数值归零，tokens 为空"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/segment",
        json={"text": ""},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        return _log(False, "segment 空字符串应返回 200", resp.text)
    d = resp.json()
    ok = (
        d["tokens"] == []
        and d["token_count"] == 0
        and d["ttr"] == 0.0
        and d["arg_density"] == 0.0
    )
    return _log(ok, "segment：空字符串，全零", d)


def test_segment_edge_only_stopwords() -> bool:
    """全是停用词：过滤后 tokens 为空"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/segment",
        json={"text": "的 了 在 是 我 有 和"},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        return _log(False, "segment 全停用词应返回 200", resp.text)
    d = resp.json()
    ok = d["tokens"] == [] and d["token_count"] == 0
    return _log(ok, "segment：全停用词，tokens 为空", d)


def test_segment_edge_only_punctuation() -> bool:
    """全是标点：tokens 为空"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/segment",
        json={"text": "。！？，、…——"},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        return _log(False, "segment 全标点应返回 200", resp.text)
    d = resp.json()
    ok = d["tokens"] == [] and d["token_count"] == 0
    return _log(ok, "segment：全标点，tokens 为空", d)


def test_segment_extreme_long_text() -> bool:
    """超长文本（500字）：正常返回，不报错"""
    long_text = "人工智能对教育的影响非常深远，因为它改变了学习方式。" * 20
    resp = requests.post(
        f"{BASE_URL}/api/nlp/segment",
        json={"text": long_text},
        headers=ADMIN_HEADERS,
    )
    ok = resp.status_code == 200 and len(resp.json()["tokens"]) > 0
    return _log(ok, "segment：超长文本正常返回", {"status": resp.status_code})


def test_segment_custom_words_dict_force() -> bool:
    """custom_words(dict_force) 中的词应按整体分出"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/segment",
        json={"text": "这款水光棒和胶原棒最近讨论很多"},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        return _log(False, "segment custom_words 应返回 200", resp.text)
    tokens = resp.json()["tokens"]
    ok = "水光棒" in tokens and "胶原棒" in tokens
    return _log(ok, "segment：custom_words(dict_force) 生效", {"tokens": tokens})


def test_segment_candidate_words_dict_combine() -> bool:
    """candidate_words(dict_combine) 候选词在常见语境下可被识别"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/segment",
        json={"text": "最近团队有点内卷，大家都快破防了，也有人想躺平"},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        return _log(False, "segment candidate_words 应返回 200", resp.text)
    tokens = resp.json()["tokens"]
    hits = {"内卷", "破防", "躺平"} & set(tokens)
    ok = len(hits) >= 2
    return _log(ok, "segment：candidate_words(dict_combine) 基本生效", {"tokens": tokens, "hits": sorted(hits)})


# ══════════════════════════════════════════════════════════════════
# /api/nlp/embed
# ══════════════════════════════════════════════════════════════════

def test_embed_single_text() -> bool:
    """单条文本：返回 1 个 384 维向量"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/embed",
        json={"texts": ["AI让学习更方便"]},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        return _log(False, "embed 单条文本应返回 200", resp.text)
    embeddings = resp.json()["embeddings"]
    ok = len(embeddings) == 1 and len(embeddings[0]) == 384
    return _log(ok, "embed：单条文本，返回 1 个 384 维向量", {"count": len(embeddings), "dim": len(embeddings[0]) if embeddings else 0})


def test_embed_batch() -> bool:
    """批量 3 条文本：返回 3 个向量"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/embed",
        json={"texts": ["句子一", "句子二", "句子三"]},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        return _log(False, "embed 批量文本应返回 200", resp.text)
    embeddings = resp.json()["embeddings"]
    ok = len(embeddings) == 3 and all(len(e) == 384 for e in embeddings)
    return _log(ok, "embed：批量 3 条，返回 3 个 384 维向量", {"count": len(embeddings)})


def test_embed_semantic_similarity() -> bool:
    """语义相近的两句话，向量相似度应 > 0.7"""
    texts = ["人工智能正在改变教育", "AI技术在改变学习方式"]
    resp = requests.post(f"{BASE_URL}/api/nlp/embed", json={"texts": texts}, headers=ADMIN_HEADERS)
    if resp.status_code != 200:
        return _log(False, "embed 语义相似测试应返回 200", resp.text)
    embeddings = resp.json()["embeddings"]

    sim_resp = requests.post(
        f"{BASE_URL}/api/nlp/similarity",
        json={"pairs": [{"vec_a": embeddings[0], "vec_b": embeddings[1]}]},
        headers=ADMIN_HEADERS,
    )
    if sim_resp.status_code != 200:
        return _log(False, "similarity 接口应返回 200", sim_resp.text)
    score = sim_resp.json()["scores"][0]
    ok = score > 0.7
    return _log(ok, f"embed + similarity：语义相近，score = {score:.4f}（期望 > 0.7）", {"score": score})


def test_embed_semantic_different() -> bool:
    """语义差异大的两句话，相似度应 < 0.6"""
    texts = ["今天天气很好，阳光明媚", "人工智能改变了教育行业"]
    resp = requests.post(f"{BASE_URL}/api/nlp/embed", json={"texts": texts}, headers=ADMIN_HEADERS)
    if resp.status_code != 200:
        return _log(False, "embed 语义差异测试应返回 200", resp.text)
    embeddings = resp.json()["embeddings"]

    sim_resp = requests.post(
        f"{BASE_URL}/api/nlp/similarity",
        json={"pairs": [{"vec_a": embeddings[0], "vec_b": embeddings[1]}]},
        headers=ADMIN_HEADERS,
    )
    score = sim_resp.json()["scores"][0]
    ok = score < 0.6
    return _log(ok, f"embed + similarity：语义差异，score = {score:.4f}（期望 < 0.6）", {"score": score})


def test_embed_edge_empty_list() -> bool:
    """空列表：返回空 embeddings"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/embed",
        json={"texts": []},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        return _log(False, "embed 空列表应返回 200", resp.text)
    ok = resp.json()["embeddings"] == []
    return _log(ok, "embed：空列表，返回空 embeddings", resp.json())


def test_embed_edge_empty_string() -> bool:
    """空字符串：模型能处理，返回 1 个 384 维向量"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/embed",
        json={"texts": [""]},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        return _log(False, "embed 空字符串应返回 200", resp.text)
    embeddings = resp.json()["embeddings"]
    ok = len(embeddings) == 1 and len(embeddings[0]) == 384
    return _log(ok, "embed：空字符串，仍返回 384 维向量", {"dim": len(embeddings[0]) if embeddings else 0})


# ══════════════════════════════════════════════════════════════════
# /api/nlp/similarity
# ══════════════════════════════════════════════════════════════════

def test_similarity_single_pair() -> bool:
    """单对向量：返回 1 个 score，值在 [-1, 1]"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/similarity",
        json={"pairs": [{"vec_a": [0.1, 0.5, 0.3], "vec_b": [0.2, 0.4, 0.6]}]},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        return _log(False, "similarity 单对应返回 200", resp.text)
    scores = resp.json()["scores"]
    ok = len(scores) == 1 and -1.0 <= scores[0] <= 1.0
    return _log(ok, f"similarity：单对向量，score = {scores[0]:.4f}", {"scores": scores})


def test_similarity_batch() -> bool:
    """批量 3 对：返回 3 个 score"""
    pairs = [
        {"vec_a": [1.0, 0.0, 0.0], "vec_b": [0.0, 1.0, 0.0]},
        {"vec_a": [1.0, 1.0, 0.0], "vec_b": [1.0, 1.0, 0.0]},
        {"vec_a": [0.5, 0.5, 0.5], "vec_b": [0.1, 0.9, 0.3]},
    ]
    resp = requests.post(
        f"{BASE_URL}/api/nlp/similarity",
        json={"pairs": pairs},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        return _log(False, "similarity 批量 3 对应返回 200", resp.text)
    scores = resp.json()["scores"]
    ok = len(scores) == 3 and all(-1.0 <= s <= 1.0 for s in scores)
    return _log(ok, "similarity：批量 3 对，返回 3 个 score", {"scores": scores})


def test_similarity_identical_vectors() -> bool:
    """完全相同的向量：score ≈ 1.0"""
    v = [0.3, 0.6, 0.1, 0.8, 0.5]
    resp = requests.post(
        f"{BASE_URL}/api/nlp/similarity",
        json={"pairs": [{"vec_a": v, "vec_b": v}]},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        return _log(False, "similarity 相同向量应返回 200", resp.text)
    score = resp.json()["scores"][0]
    ok = abs(score - 1.0) < 1e-5
    return _log(ok, f"similarity：相同向量，score ≈ 1.0（实际 {score:.6f}）", {"score": score})


def test_similarity_zero_vector() -> bool:
    """零向量：score = 0.0，不报错"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/similarity",
        json={"pairs": [{"vec_a": _zero_vec(4), "vec_b": [0.1, 0.2, 0.3, 0.4]}]},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        return _log(False, "similarity 零向量应返回 200", resp.text)
    score = resp.json()["scores"][0]
    ok = score == 0.0
    return _log(ok, f"similarity：零向量，score = 0.0（实际 {score}）", {"score": score})


def test_similarity_edge_empty_pairs() -> bool:
    """空列表：返回空 scores"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/similarity",
        json={"pairs": []},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        return _log(False, "similarity 空列表应返回 200", resp.text)
    ok = resp.json()["scores"] == []
    return _log(ok, "similarity：空列表，返回空 scores", resp.json())


# ══════════════════════════════════════════════════════════════════
# /api/nlp/tfidf
# ══════════════════════════════════════════════════════════════════

_MEMBER_TEXTS_3 = {
    "user_a": "AI让学习更方便，提高了效率，个性化学习成为可能",
    "user_b": "人工智能改变了教育方式，老师的角色也会随之变化",
    "user_c": "个性化学习是AI最大的优势，每个学生都能得到定制化教育",
}


def test_tfidf_normal_3_members() -> bool:
    """3 个成员正常文本：keywords 长度 = top_n，contexts 覆盖所有成员"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/tfidf",
        json={"member_texts": _MEMBER_TEXTS_3, "top_n": 5},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        return _log(False, "tfidf 3 成员应返回 200", resp.text)
    d = resp.json()
    ok = (
        len(d["keywords"]) <= 5
        and set(d["member_keyword_contexts"].keys()) == {"user_a", "user_b", "user_c"}
    )
    return _log(ok, "tfidf：3 成员，keywords 和 contexts 结构正确", {"keywords": d["keywords"]})


def test_tfidf_keyword_context_present() -> bool:
    """某关键词出现在成员发言里：context 不为空字符串"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/tfidf",
        json={"member_texts": _MEMBER_TEXTS_3, "top_n": 5},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        return _log(False, "tfidf context 检查应返回 200", resp.text)
    d = resp.json()
    keywords = d["keywords"]
    contexts = d["member_keyword_contexts"]
    # 至少一位成员对至少一个关键词有非空 context
    has_context = any(
        contexts[uid][kw] != ""
        for uid in contexts
        for kw in keywords
        if kw in contexts[uid]
    )
    return _log(has_context, "tfidf：至少有一个成员-关键词的 context 不为空", {"keywords": keywords})


def test_tfidf_top_n_1() -> bool:
    """top_n = 1：只返回 1 个关键词"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/tfidf",
        json={"member_texts": _MEMBER_TEXTS_3, "top_n": 1},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        return _log(False, "tfidf top_n=1 应返回 200", resp.text)
    ok = len(resp.json()["keywords"]) == 1
    return _log(ok, "tfidf：top_n=1，返回 1 个关键词", {"keywords": resp.json()["keywords"]})


def test_tfidf_single_member() -> bool:
    """单个成员：正常返回，不报错"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/tfidf",
        json={"member_texts": {"user_a": "人工智能改变了学习方式和教育环境"}, "top_n": 3},
        headers=ADMIN_HEADERS,
    )
    ok = resp.status_code == 200
    return _log(ok, "tfidf：单个成员，正常返回", {"status": resp.status_code, "body": resp.json() if ok else resp.text})


def test_tfidf_top_n_exceeds_vocab() -> bool:
    """top_n 超过词汇表大小：返回实际有的词，不报错"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/tfidf",
        json={"member_texts": {"user_a": "苹果 香蕉"}, "top_n": 20},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        return _log(False, "tfidf top_n 超过词汇量应返回 200", resp.text)
    keywords = resp.json()["keywords"]
    ok = len(keywords) <= 20
    return _log(ok, f"tfidf：top_n=20 超过词汇量，返回 {len(keywords)} 个词", {"keywords": keywords})


def test_tfidf_edge_empty_member_texts() -> bool:
    """member_texts 为空：返回空结果，不报错"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/tfidf",
        json={"member_texts": {}, "top_n": 5},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        return _log(False, "tfidf 空 member_texts 应返回 200", resp.text)
    d = resp.json()
    ok = d["keywords"] == [] and d["member_keyword_contexts"] == {}
    return _log(ok, "tfidf：空 member_texts，返回空结果", d)


def test_tfidf_edge_member_with_empty_text() -> bool:
    """某成员文本为空字符串：不报错，该成员 contexts 全为空"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/tfidf",
        json={
            "member_texts": {
                "user_a": "人工智能改变了教育",
                "user_b": "",
            },
            "top_n": 3,
        },
        headers=ADMIN_HEADERS,
    )
    ok = resp.status_code == 200
    return _log(ok, "tfidf：某成员文本为空，不报错", {"status": resp.status_code})


def test_tfidf_with_custom_and_candidate_words() -> bool:
    """tfidf 链路应能提取新词典中的词（至少命中一个）"""
    member_texts = {
        "u1": "我们最近一直在讨论水光棒的成分和效果",
        "u2": "组里有点内卷，大家对产品经理的节奏有分歧",
        "u3": "有人说自己快破防了，也有人想躺平",
    }
    resp = requests.post(
        f"{BASE_URL}/api/nlp/tfidf",
        json={"member_texts": member_texts, "top_n": 8},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        return _log(False, "tfidf 新词典联动应返回 200", resp.text)
    keywords = resp.json()["keywords"]
    expected = {"水光棒", "内卷", "破防", "躺平", "产品经理"}
    ok = len(expected & set(keywords)) >= 1
    return _log(ok, "tfidf：新词典词项可进入关键词结果", {"keywords": keywords})


# ══════════════════════════════════════════════════════════════════
# /api/nlp/has_reasoning
# ══════════════════════════════════════════════════════════════════

def test_reasoning_rule_both_true() -> bool:
    """含明确论证词 + 证据词：method='rule'，两者均 True，不调 LLM"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/has_reasoning",
        json={"text": "因为研究表明AI能提高效率，所以它对教育很有帮助，例如个性化学习就是典型案例"},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        return _log(False, "has_reasoning 规则两者为 True 应返回 200", resp.text)
    d = resp.json()
    ok = d["has_reasoning"] is True and d["has_evidence"] is True and d["method"] == "rule"
    return _log(ok, f"has_reasoning：规则层，两者均 True，method={d['method']}", d)


def test_reasoning_rule_only_reasoning_keyword() -> bool:
    """只含论证词，不含证据词：has_reasoning=True，触发 LLM 兜底"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/has_reasoning",
        json={"text": "因为AI改变了学习效率，所以教育行业必须跟上这个趋势"},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        return _log(False, "has_reasoning 只含论证词应返回 200", resp.text)
    d = resp.json()
    ok = d["has_reasoning"] is True and "method" in d
    return _log(ok, f"has_reasoning：只含论证词，has_reasoning=True，method={d['method']}", d)


def test_reasoning_rule_only_evidence_keyword() -> bool:
    """只含证据词，不含论证词：has_evidence=True，触发 LLM 兜底"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/has_reasoning",
        json={"text": "比如说，很多学校已经开始使用AI辅助教学了"},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        return _log(False, "has_reasoning 只含证据词应返回 200", resp.text)
    d = resp.json()
    ok = d["has_evidence"] is True and "method" in d
    return _log(ok, f"has_reasoning：只含证据词，has_evidence=True，method={d['method']}", d)


def test_reasoning_llm_fallback_pure_statement() -> bool:
    """纯陈述句，无关键词：触发 LLM 兜底，method='llm'，结构正确"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/has_reasoning",
        json={"text": "AI对教育很有帮助，学生可以学得更快"},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        return _log(False, "has_reasoning LLM 兜底应返回 200", resp.text)
    d = resp.json()
    # LLM 路径：method="llm"，结构字段齐全
    ok = (
        d["method"] == "llm"
        and isinstance(d["has_reasoning"], bool)
        and isinstance(d["has_evidence"], bool)
    )
    return _log(ok, f"has_reasoning：LLM 兜底，method=llm，结构正确", d)


def test_reasoning_edge_empty_text() -> bool:
    """空字符串：不报错，返回合法结构"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/has_reasoning",
        json={"text": ""},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        return _log(False, "has_reasoning 空字符串应返回 200", resp.text)
    d = resp.json()
    ok = "has_reasoning" in d and "has_evidence" in d and "method" in d
    return _log(ok, "has_reasoning：空字符串，返回合法结构", d)


def test_reasoning_edge_single_arg_word() -> bool:
    """只有一个论证词：has_reasoning=True"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/has_reasoning",
        json={"text": "因为"},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        return _log(False, "has_reasoning 单论证词应返回 200", resp.text)
    d = resp.json()
    ok = d["has_reasoning"] is True
    return _log(ok, "has_reasoning：单论证词，has_reasoning=True", d)


# ══════════════════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════════════════

def main() -> int:
    all_cases: list[tuple[str, Any]] = [
        # ── 鉴权 ──────────────────────────────────────────────
        ("鉴权：无 Token，所有接口返回 403",             test_auth_no_token),
        ("鉴权：错误 Token，所有接口返回 403",           test_auth_wrong_token),

        # ── segment ───────────────────────────────────────────
        ("segment：含论证词，字段合理",                  test_segment_normal_with_reasoning),
        ("segment：无论证词，arg_density = 0",           test_segment_normal_no_reasoning),
        ("segment：全不重复词，ttr = 1.0",               test_segment_all_unique_words),
        ("segment：重复词，ttr < 1.0",                   test_segment_repeated_words),
        ("segment 边界：空字符串",                        test_segment_edge_empty_string),
        ("segment 边界：全停用词",                        test_segment_edge_only_stopwords),
        ("segment 边界：全标点",                          test_segment_edge_only_punctuation),
        ("segment 极端：超长文本",                        test_segment_extreme_long_text),
        ("segment：custom_words(dict_force) 生效",        test_segment_custom_words_dict_force),
        ("segment：candidate_words(dict_combine) 生效",   test_segment_candidate_words_dict_combine),

        # ── embed ─────────────────────────────────────────────
        ("embed：单条文本，384 维",                       test_embed_single_text),
        ("embed：批量 3 条",                              test_embed_batch),
        ("embed + similarity：语义相近 > 0.7",            test_embed_semantic_similarity),
        ("embed + similarity：语义差异 < 0.6",            test_embed_semantic_different),
        ("embed 边界：空列表",                            test_embed_edge_empty_list),
        ("embed 边界：空字符串",                          test_embed_edge_empty_string),

        # ── similarity ────────────────────────────────────────
        ("similarity：单对向量",                          test_similarity_single_pair),
        ("similarity：批量 3 对",                         test_similarity_batch),
        ("similarity 边界：相同向量 ≈ 1.0",               test_similarity_identical_vectors),
        ("similarity 边界：零向量 = 0.0",                 test_similarity_zero_vector),
        ("similarity 边界：空列表",                        test_similarity_edge_empty_pairs),

        # ── tfidf ─────────────────────────────────────────────
        ("tfidf：3 成员正常",                             test_tfidf_normal_3_members),
        ("tfidf：关键词 context 不为空",                  test_tfidf_keyword_context_present),
        ("tfidf：top_n = 1",                              test_tfidf_top_n_1),
        ("tfidf：单个成员",                               test_tfidf_single_member),
        ("tfidf：top_n 超过词汇量",                       test_tfidf_top_n_exceeds_vocab),
        ("tfidf 边界：空 member_texts",                   test_tfidf_edge_empty_member_texts),
        ("tfidf 边界：某成员文本为空",                    test_tfidf_edge_member_with_empty_text),
        ("tfidf：custom/candidate 词典联动",              test_tfidf_with_custom_and_candidate_words),

        # ── has_reasoning ─────────────────────────────────────
        ("has_reasoning：规则层，两者均 True",            test_reasoning_rule_both_true),
        ("has_reasoning：只含论证词",                     test_reasoning_rule_only_reasoning_keyword),
        ("has_reasoning：只含证据词",                     test_reasoning_rule_only_evidence_keyword),
        ("has_reasoning：LLM 兜底，纯陈述",              test_reasoning_llm_fallback_pure_statement),
        ("has_reasoning 边界：空字符串",                  test_reasoning_edge_empty_text),
        ("has_reasoning 边界：单论证词",                  test_reasoning_edge_single_arg_word),
    ]

    results: list[bool] = []
    print(f"\n{'='*60}")
    print("NLP 微服务接口测试")
    print(f"{'='*60}")

    for label, fn in all_cases:
        print(f"\n── {label}")
        try:
            results.append(fn())
        except Exception as e:
            results.append(_log(False, f"{label} 抛出异常", str(e)))

    passed = sum(results)
    total = len(results)
    print(f"\n{'='*60}")
    print(f"结果：{passed}/{total} 通过")
    if passed < total:
        print("❌ 存在失败项，请检查上方详情")
        return 1
    print("✅ 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
