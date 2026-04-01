"""
中文分词模块
- 基于 jieba，去停用词
- 一次调用同时返回 tokens / TTR / arg_density，上层无需二次计算
"""
from __future__ import annotations

import jieba

# ── 停用词表（语气词、助词、连接词等，不计入 TTR） ──────────────────────────
STOPWORDS: set[str] = {
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
    "因为", "所以", "因此", "但是", "然而", "虽然", "尽管",
    "由于", "导致", "基于", "相反", "不过", "反而",
}


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
    tokens_raw = [t for t in jieba.lcut(text) if t.strip()]
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
