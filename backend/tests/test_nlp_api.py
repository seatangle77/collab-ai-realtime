#!/usr/bin/env python3
"""
NLP 微服务接口测试
覆盖：/api/nlp/segment · /api/nlp/embed · /api/nlp/similarity · /api/nlp/extract_keywords_broad · /api/nlp/keyword_recall_with_gap · /api/nlp/reasoning_batch

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


def _assert_log(ok: bool, message: str, extra: Any | None = None) -> None:
    assert _log(ok, message, extra)


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

def test_auth_no_token() -> None:
    endpoints = [
        ("POST", "/api/nlp/segment",      {"text": "测试"}),
        ("POST", "/api/nlp/embed",         {"texts": ["测试"]}),
        ("POST", "/api/nlp/similarity",    {"pairs": []}),
        ("POST", "/api/nlp/extract_keywords_broad", {"texts": ["测试"]}),
        ("POST", "/api/nlp/keyword_recall_with_gap", {"member_texts": {"u": "测试"}}),
        ("POST", "/api/nlp/reasoning_batch", {"members": [{"user_id": "u1", "text": "测试"}]}),
    ]
    results = []
    for method, path, body in endpoints:
        resp = requests.request(method, f"{BASE_URL}{path}", json=body)
        ok = resp.status_code == 403
        results.append(_log(ok, f"无 Token → {path} 应返回 403", {"status": resp.status_code}))
    assert all(results)


def test_auth_wrong_token() -> None:
    endpoints = [
        ("POST", "/api/nlp/segment",      {"text": "测试"}),
        ("POST", "/api/nlp/embed",         {"texts": ["测试"]}),
        ("POST", "/api/nlp/similarity",    {"pairs": []}),
        ("POST", "/api/nlp/extract_keywords_broad", {"texts": ["测试"]}),
        ("POST", "/api/nlp/keyword_recall_with_gap", {"member_texts": {"u": "测试"}}),
        ("POST", "/api/nlp/reasoning_batch", {"members": [{"user_id": "u1", "text": "测试"}]}),
    ]
    results = []
    for method, path, body in endpoints:
        resp = requests.request(method, f"{BASE_URL}{path}", json=body, headers=WRONG_HEADERS)
        ok = resp.status_code == 403
        results.append(_log(ok, f"错误 Token → {path} 应返回 403", {"status": resp.status_code}))
    assert all(results)


# ══════════════════════════════════════════════════════════════════
# /api/nlp/segment
# ══════════════════════════════════════════════════════════════════

def test_segment_normal_with_reasoning() -> None:
    """含论证词的正常句子：arg_density > 0，ttr 合理，tokens 非空"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/segment",
        json={"text": "我认为AI会影响教育，因为它改变了学生的学习方式和思维习惯"},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        _assert_log(False, "segment 正常句子（含论证词）应返回 200", resp.text)
    d = resp.json()
    ok = (
        len(d["tokens"]) > 0
        and d["arg_density"] > 0
        and 0 < d["ttr"] <= 1.0
        and d["token_count"] == len(d["tokens"])
        and d["unique_count"] <= d["token_count"]
    )
    _assert_log(ok, "segment：含论证词，字段值合理", d)


def test_segment_normal_no_reasoning() -> None:
    """不含论证词的句子：arg_density = 0"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/segment",
        json={"text": "AI技术正在快速发展，改变很多行业"},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        _assert_log(False, "segment 无论证词应返回 200", resp.text)
    d = resp.json()
    ok = d["arg_density"] == 0.0
    _assert_log(ok, "segment：无论证词，arg_density = 0", d)


def test_segment_all_unique_words() -> None:
    """每个词都不重复：ttr 应接近 1.0"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/segment",
        json={"text": "苹果 香蕉 橙子 西瓜 草莓 葡萄 柠檬"},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        _assert_log(False, "segment 全不重复词应返回 200", resp.text)
    d = resp.json()
    ok = d["token_count"] > 0 and d["ttr"] == 1.0
    _assert_log(ok, "segment：全不重复词，ttr = 1.0", d)


def test_segment_repeated_words() -> None:
    """同一个词重复出现：ttr < 1.0"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/segment",
        json={"text": "学习学习学习学习学习"},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        _assert_log(False, "segment 重复词应返回 200", resp.text)
    d = resp.json()
    ok = d["token_count"] > 0 and d["ttr"] < 1.0
    _assert_log(ok, "segment：重复词，ttr < 1.0", d)


def test_segment_edge_empty_string() -> None:
    """空字符串：所有数值归零，tokens 为空"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/segment",
        json={"text": ""},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        _assert_log(False, "segment 空字符串应返回 200", resp.text)
    d = resp.json()
    ok = (
        d["tokens"] == []
        and d["token_count"] == 0
        and d["ttr"] == 0.0
        and d["arg_density"] == 0.0
    )
    _assert_log(ok, "segment：空字符串，全零", d)


def test_segment_edge_only_stopwords() -> None:
    """全是停用词：过滤后 tokens 为空"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/segment",
        json={"text": "的 了 在 是 我 有 和"},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        _assert_log(False, "segment 全停用词应返回 200", resp.text)
    d = resp.json()
    ok = d["tokens"] == [] and d["token_count"] == 0
    _assert_log(ok, "segment：全停用词，tokens 为空", d)


def test_segment_edge_only_punctuation() -> None:
    """全是标点：tokens 为空"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/segment",
        json={"text": "。！？，、…——"},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        _assert_log(False, "segment 全标点应返回 200", resp.text)
    d = resp.json()
    ok = d["tokens"] == [] and d["token_count"] == 0
    _assert_log(ok, "segment：全标点，tokens 为空", d)


def test_segment_extreme_long_text() -> None:
    """超长文本（500字）：正常返回，不报错"""
    long_text = "人工智能对教育的影响非常深远，因为它改变了学习方式。" * 20
    resp = requests.post(
        f"{BASE_URL}/api/nlp/segment",
        json={"text": long_text},
        headers=ADMIN_HEADERS,
    )
    ok = resp.status_code == 200 and len(resp.json()["tokens"]) > 0
    _assert_log(ok, "segment：超长文本正常返回", {"status": resp.status_code})


def test_segment_custom_words_dict_force() -> None:
    """custom_words(dict_force) 中的词应按整体分出"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/segment",
        json={"text": "这款水光棒和胶原棒最近讨论很多"},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        _assert_log(False, "segment custom_words 应返回 200", resp.text)
    tokens = resp.json()["tokens"]
    ok = "水光棒" in tokens and "胶原棒" in tokens
    _assert_log(ok, "segment：custom_words(dict_force) 生效", {"tokens": tokens})


def test_segment_candidate_words_dict_combine() -> None:
    """candidate_words(dict_combine) 候选词在常见语境下可被识别"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/segment",
        json={"text": "最近团队有点内卷，大家都快破防了，也有人想躺平"},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        _assert_log(False, "segment candidate_words 应返回 200", resp.text)
    tokens = resp.json()["tokens"]
    hits = {"内卷", "破防", "躺平"} & set(tokens)
    ok = len(hits) >= 2
    _assert_log(ok, "segment：candidate_words(dict_combine) 基本生效", {"tokens": tokens, "hits": sorted(hits)})


# ══════════════════════════════════════════════════════════════════
# /api/nlp/embed
# ══════════════════════════════════════════════════════════════════

def test_embed_single_text() -> None:
    """单条文本：返回 1 个 384 维向量"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/embed",
        json={"texts": ["AI让学习更方便"]},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        _assert_log(False, "embed 单条文本应返回 200", resp.text)
    embeddings = resp.json()["embeddings"]
    ok = len(embeddings) == 1 and len(embeddings[0]) == 384
    _assert_log(ok, "embed：单条文本，返回 1 个 384 维向量", {"count": len(embeddings), "dim": len(embeddings[0]) if embeddings else 0})


def test_embed_batch() -> None:
    """批量 3 条文本：返回 3 个向量"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/embed",
        json={"texts": ["句子一", "句子二", "句子三"]},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        _assert_log(False, "embed 批量文本应返回 200", resp.text)
    embeddings = resp.json()["embeddings"]
    ok = len(embeddings) == 3 and all(len(e) == 384 for e in embeddings)
    _assert_log(ok, "embed：批量 3 条，返回 3 个 384 维向量", {"count": len(embeddings)})


def test_embed_semantic_similarity() -> None:
    """语义相近的两句话，向量相似度应 > 0.7"""
    texts = ["人工智能正在改变教育", "AI技术在改变学习方式"]
    resp = requests.post(f"{BASE_URL}/api/nlp/embed", json={"texts": texts}, headers=ADMIN_HEADERS)
    if resp.status_code != 200:
        _assert_log(False, "embed 语义相似测试应返回 200", resp.text)
    embeddings = resp.json()["embeddings"]

    sim_resp = requests.post(
        f"{BASE_URL}/api/nlp/similarity",
        json={"pairs": [{"vec_a": embeddings[0], "vec_b": embeddings[1]}]},
        headers=ADMIN_HEADERS,
    )
    if sim_resp.status_code != 200:
        _assert_log(False, "similarity 接口应返回 200", sim_resp.text)
    score = sim_resp.json()["scores"][0]
    ok = score > 0.7
    _assert_log(ok, f"embed + similarity：语义相近，score = {score:.4f}（期望 > 0.7）", {"score": score})


def test_embed_semantic_different() -> None:
    """语义差异大的两句话，相似度应 < 0.6"""
    texts = ["今天天气很好，阳光明媚", "人工智能改变了教育行业"]
    resp = requests.post(f"{BASE_URL}/api/nlp/embed", json={"texts": texts}, headers=ADMIN_HEADERS)
    if resp.status_code != 200:
        _assert_log(False, "embed 语义差异测试应返回 200", resp.text)
    embeddings = resp.json()["embeddings"]

    sim_resp = requests.post(
        f"{BASE_URL}/api/nlp/similarity",
        json={"pairs": [{"vec_a": embeddings[0], "vec_b": embeddings[1]}]},
        headers=ADMIN_HEADERS,
    )
    score = sim_resp.json()["scores"][0]
    ok = score < 0.6
    _assert_log(ok, f"embed + similarity：语义差异，score = {score:.4f}（期望 < 0.6）", {"score": score})


def test_embed_edge_empty_list() -> None:
    """空列表：返回空 embeddings"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/embed",
        json={"texts": []},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        _assert_log(False, "embed 空列表应返回 200", resp.text)
    ok = resp.json()["embeddings"] == []
    _assert_log(ok, "embed：空列表，返回空 embeddings", resp.json())


def test_embed_edge_empty_string() -> None:
    """空字符串：模型能处理，返回 1 个 384 维向量"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/embed",
        json={"texts": [""]},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        _assert_log(False, "embed 空字符串应返回 200", resp.text)
    embeddings = resp.json()["embeddings"]
    ok = len(embeddings) == 1 and len(embeddings[0]) == 384
    _assert_log(ok, "embed：空字符串，仍返回 384 维向量", {"dim": len(embeddings[0]) if embeddings else 0})


# ══════════════════════════════════════════════════════════════════
# /api/nlp/similarity
# ══════════════════════════════════════════════════════════════════

def test_similarity_single_pair() -> None:
    """单对向量：返回 1 个 score，值在 [-1, 1]"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/similarity",
        json={"pairs": [{"vec_a": [0.1, 0.5, 0.3], "vec_b": [0.2, 0.4, 0.6]}]},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        _assert_log(False, "similarity 单对应返回 200", resp.text)
    scores = resp.json()["scores"]
    ok = len(scores) == 1 and -1.0 <= scores[0] <= 1.0
    _assert_log(ok, f"similarity：单对向量，score = {scores[0]:.4f}", {"scores": scores})


def test_similarity_batch() -> None:
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
        _assert_log(False, "similarity 批量 3 对应返回 200", resp.text)
    scores = resp.json()["scores"]
    ok = len(scores) == 3 and all(-1.0 <= s <= 1.0 for s in scores)
    _assert_log(ok, "similarity：批量 3 对，返回 3 个 score", {"scores": scores})


def test_similarity_identical_vectors() -> None:
    """完全相同的向量：score ≈ 1.0"""
    v = [0.3, 0.6, 0.1, 0.8, 0.5]
    resp = requests.post(
        f"{BASE_URL}/api/nlp/similarity",
        json={"pairs": [{"vec_a": v, "vec_b": v}]},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        _assert_log(False, "similarity 相同向量应返回 200", resp.text)
    score = resp.json()["scores"][0]
    ok = abs(score - 1.0) < 1e-5
    _assert_log(ok, f"similarity：相同向量，score ≈ 1.0（实际 {score:.6f}）", {"score": score})


def test_similarity_zero_vector() -> None:
    """零向量：score = 0.0，不报错"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/similarity",
        json={"pairs": [{"vec_a": _zero_vec(4), "vec_b": [0.1, 0.2, 0.3, 0.4]}]},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        _assert_log(False, "similarity 零向量应返回 200", resp.text)
    score = resp.json()["scores"][0]
    ok = score == 0.0
    _assert_log(ok, f"similarity：零向量，score = 0.0（实际 {score}）", {"score": score})


def test_similarity_edge_empty_pairs() -> None:
    """空列表：返回空 scores"""
    resp = requests.post(
        f"{BASE_URL}/api/nlp/similarity",
        json={"pairs": []},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        _assert_log(False, "similarity 空列表应返回 200", resp.text)
    ok = resp.json()["scores"] == []
    _assert_log(ok, "similarity：空列表，返回空 scores", resp.json())


# ══════════════════════════════════════════════════════════════════
# /api/nlp/extract_keywords_broad
# ══════════════════════════════════════════════════════════════════

def test_extract_keywords_broad_basic() -> None:
    resp = requests.post(
        f"{BASE_URL}/api/nlp/extract_keywords_broad",
        json={
            "texts": [
                "AI让学习更方便，提高了效率，个性化学习成为可能",
                "人工智能改变了教育方式，老师的角色也会随之变化",
                "个性化学习是AI最大的优势，每个学生都能得到定制化教育",
            ],
            "top_n": 5,
        },
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        _assert_log(False, "extract_keywords_broad 应返回 200", resp.text)
    d = resp.json()
    ok = isinstance(d.get("keywords"), list) and len(d["keywords"]) <= 5
    _assert_log(ok, "extract_keywords_broad：返回关键词列表", d)


def test_extract_keywords_broad_edge_empty_texts() -> None:
    resp = requests.post(
        f"{BASE_URL}/api/nlp/extract_keywords_broad",
        json={"texts": [], "top_n": 5},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        _assert_log(False, "extract_keywords_broad 空 texts 应返回 200", resp.text)
    d = resp.json()
    ok = d["keywords"] == []
    _assert_log(ok, "extract_keywords_broad：空 texts 返回空列表", d)


# ══════════════════════════════════════════════════════════════════
# /api/nlp/keyword_recall_with_gap
# ══════════════════════════════════════════════════════════════════

def test_keyword_recall_with_gap_basic() -> None:
    resp = requests.post(
        f"{BASE_URL}/api/nlp/keyword_recall_with_gap",
        json={
            "member_texts": {
                "u1": "我们先做 MVP，再看路径验证",
                "u2": "MVP 是什么，我还不太理解",
            },
        },
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        _assert_log(False, "keyword_recall_with_gap 应返回 200", resp.text)
    d = resp.json()
    ok = isinstance(d.get("keywords"), list)
    _assert_log(ok, "keyword_recall_with_gap：返回关键词结果列表", d)


# ══════════════════════════════════════════════════════════════════
# /api/nlp/reasoning_batch
# ══════════════════════════════════════════════════════════════════

def test_reasoning_batch_multi_members() -> None:
    resp = requests.post(
        f"{BASE_URL}/api/nlp/reasoning_batch",
        json={
            "members": [
                {"user_id": "u1", "text": "我建议先做 MVP，因为范围更容易控制。"},
                {"user_id": "u2", "text": "比如腾讯会议也用了类似做法。"},
            ]
        },
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        _assert_log(False, "reasoning_batch 多成员应返回 200", resp.text)
    d = resp.json()
    members = d.get("members", [])
    ok = (
        len(members) == 2
        and {"u1", "u2"} == {m["user_id"] for m in members}
        and all(isinstance(m["reasoning_status"], bool) for m in members)
        and all(isinstance(m["evidence_status"], bool) for m in members)
        and all(isinstance(m["reasoning_source"], str) and m["reasoning_source"] for m in members)
        and all(isinstance(m["evidence_source"], str) and m["evidence_source"] for m in members)
    )
    _assert_log(ok, "reasoning_batch：多成员返回完整四字段结果", d)


def test_reasoning_batch_edge_empty_text() -> None:
    resp = requests.post(
        f"{BASE_URL}/api/nlp/reasoning_batch",
        json={"members": [{"user_id": "u1", "text": ""}]},
        headers=ADMIN_HEADERS,
    )
    if resp.status_code != 200:
        _assert_log(False, "reasoning_batch 空文本应返回 200", resp.text)
    d = resp.json()
    member = d["members"][0]
    ok = (
        member["user_id"] == "u1"
        and member["reasoning_status"] is None
        and member["evidence_status"] is None
        and isinstance(member["reasoning_source"], str)
        and isinstance(member["evidence_source"], str)
    )
    _assert_log(ok, "reasoning_batch：空文本返回合法结构", member)


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

        # ── extract_keywords_broad / keyword_recall_with_gap ──
        ("extract_keywords_broad：基础结构",              test_extract_keywords_broad_basic),
        ("extract_keywords_broad 边界：空 texts",         test_extract_keywords_broad_edge_empty_texts),
        ("keyword_recall_with_gap：基础结构",             test_keyword_recall_with_gap_basic),

        # ── reasoning_batch ───────────────────────────────────
        ("reasoning_batch：多成员完整四字段",             test_reasoning_batch_multi_members),
        ("reasoning_batch 边界：空文本",                  test_reasoning_batch_edge_empty_text),
    ]

    results: list[bool] = []
    print(f"\n{'='*60}")
    print("NLP 微服务接口测试")
    print(f"{'='*60}")

    for label, fn in all_cases:
        print(f"\n── {label}")
        try:
            fn()
            results.append(True)
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
