"""
中文分词模块
- 基于 HanLP，去停用词
- 一次调用同时返回 tokens / TTR / arg_density，上层无需二次计算
"""
from __future__ import annotations

from typing import Any
import unicodedata

import hanlp

from .lexicon_loader import (
    load_candidate_words,
    load_custom_words,
    load_external_stopwords,
    load_pystopwords,
)

# ── 停用词表（语气词、助词、连接词等，不计入 TTR） ──────────────────────────
BASE_STOPWORDS: set[str] = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都",
    "一", "上", "也", "很", "到", "说", "要", "去", "你", "会",
    "着", "看", "好", "自己", "这", "那", "他", "她", "它",
    "们", "这个", "那个", "什么", "怎么", "啊", "呢", "吧", "嗯",
    "哦", "哈", "呀", "哇", "哎", "唉", "喔", "哟",
    "我们", "你们", "他们", "她们", "它们", "这些", "那些",
    "可以", "应该", "需要", "能够", "就是", "还是", "或者", "而且",
    "其实", "已经", "正在", "将会", "对于", "关于", "通过",
    "比较", "非常", "特别", "更加", "真的", "确实", "一个", "一些",
    "没有", "如果", "时候", "进行", "使用", "这种", "那种",
}

# ── 论证词词表（用于 arg_density，来自 PDF 规格） ────────────────────────────
ARG_WORDS: set[str] = {
    # 因果 / 结果
    "因为", "所以", "因此", "由于", "导致", "造成", "带来", "源于",
    "取决于", "基于", "出于", "意味着",
    # 转折 / 对比
    "但是", "然而", "虽然", "尽管", "不过", "反而", "相反",
    "相比", "相较于", "不同的是", "共同点", "差异", "优点", "缺点",
    # 递进 / 补充
    "而且", "另外", "进一步", "更重要的是", "同时", "并且", "不仅",
    # 举例 / 依据
    "比如", "例如", "举个例子", "像是", "根据", "数据显示",
    "资料显示", "研究表明", "事实是",
    # 推论 / 总结
    "说明", "证明", "可以看出", "由此可见", "推测", "判断", "结论是",
    "总结一下",
    # 条件 / 让步
    "如果", "假如", "只要", "除非", "前提是", "即使", "哪怕",
    "至少", "可能", "未必", "不一定",
    # 观点组织
    "我认为", "我的理由是", "核心原因", "主要原因", "第一", "第二",
}

# 合并顺序：
# 1) 内置词表
# 2) 本地 stopwords/*.txt
# 3) pystopwords（可选，依赖缺失时自动忽略）
# 4) 论证词词表（避免 "因为/所以" 进入 TF-IDF）
STOPWORDS: set[str] = (
    BASE_STOPWORDS
    | load_external_stopwords()
    | load_pystopwords()
    | ARG_WORDS
)

_pipeline: Any | None = None


def _flatten_terms(terms: Any) -> list[str]:
    """兼容 HanLP 可能返回的平铺或按句嵌套结构。"""
    if not terms:
        return []
    first = terms[0]
    if isinstance(first, str):
        return [w for w in terms if isinstance(w, str) and w.strip()]
    flat: list[str] = []
    for sent in terms:
        if isinstance(sent, list):
            flat.extend([w for w in sent if isinstance(w, str) and w.strip()])
    return flat


def _is_punct_or_symbol(token: str) -> bool:
    return bool(token) and all(unicodedata.category(ch)[0] in {"P", "S"} for ch in token)


def get_pipeline() -> Any:
    global _pipeline
    if _pipeline is None:
        _pipeline = hanlp.load(
            hanlp.pretrained.mtl.CLOSE_TOK_POS_NER_SRL_DEP_SDP_CON_ELECTRA_SMALL_ZH
        )
        custom_words = load_custom_words()
        if custom_words:
            _pipeline["tok/fine"].dict_force = custom_words
        candidate_words = load_candidate_words()
        if candidate_words:
            _pipeline["tok/fine"].dict_combine = candidate_words
    return _pipeline


def segment(text: str) -> dict:
    """
    对单段文本做分词，返回：
    - tokens:       去停用词后的词列表（用于 TTR）
    - token_count:  去停用词后的总词数 N
    - unique_count: 去停用词后的不重复词数 |V|
    - ttr:          词汇多样性 = |V| / N
    - arg_density:  论证词密度 = 论证词出现次数 / 原始总词数
    """
    # 原始分词（保留所有词，含停用词）
    result = get_pipeline()(text, tasks=["tok/fine"])
    tokens_raw: list[str] = []
    for term in _flatten_terms(result["tok/fine"]):
        for piece in term.split():
            piece = piece.strip()
            if not piece:
                continue
            if _is_punct_or_symbol(piece):
                continue
            tokens_raw.append(piece)
    total_n = len(tokens_raw)  # 原始总词数，用于 arg_density 分母

    # 去停用词 + 去单字（单字噪音多，对语义贡献低）
    tokens = [
        t for t in tokens_raw
        if t not in STOPWORDS and len(t) > 1
    ]
    token_count = len(tokens)
    unique_count = len(set(tokens))
    ttr = round(unique_count / token_count, 4) if token_count > 0 else 0.0

    # 论证词计数（在原始 tokens 中匹配，不受停用词过滤影响）
    arg_word_count = sum(1 for t in tokens_raw if t in ARG_WORDS)
    arg_density = round(arg_word_count / total_n, 4) if total_n > 0 else 0.0

    return {
        "tokens": tokens,
        "token_count": token_count,
        "unique_count": unique_count,
        "ttr": ttr,
        "arg_density": arg_density,
    }
