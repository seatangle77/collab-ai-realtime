"""
词表加载模块
- 统一管理停用词/任务排除词/降权词
- 全部模块级缓存，避免请求路径重复 IO
"""
from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path


_NLP_DIR = Path(__file__).resolve().parent
_STOPWORDS_DIR = _NLP_DIR / "stopwords"
_LEXICONS_DIR = _NLP_DIR / "lexicons"

_STOPWORD_FILES: tuple[str, ...] = (
    "cn_stopwords.txt",
    "hit_stopwords.txt",
    "baidu_stopwords.txt",
    "scu_stopwords.txt",
)

_CONCEPT_WHITELIST_FILES: tuple[str, ...] = (
    "THUOCL_IT.txt",
)


def _read_word_list(path: Path) -> set[str]:
    words: set[str] = set()
    if not path.exists():
        return words
    with path.open("r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            words.add(line)
    return words


def _read_thuocl_word_list(path: Path) -> set[str]:
    words: set[str] = set()
    if not path.exists():
        return words
    with path.open("r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            # THUOCL 格式通常为：词\t词频
            word = line.split()[0].strip()
            if word:
                words.add(word)
    return words


@lru_cache(maxsize=1)
def load_external_stopwords() -> set[str]:
    words: set[str] = set()
    for filename in _STOPWORD_FILES:
        words |= _read_word_list(_STOPWORDS_DIR / filename)
    return words


@lru_cache(maxsize=1)
def load_pystopwords(source: str = "all") -> set[str]:
    """
    可选加载 pystopwords。
    若依赖未安装或运行异常，返回空集合，避免影响主流程。
    """
    try:
        from pystopwords import stopwords as get_stopwords  # type: ignore
    except Exception:
        return set()

    try:
        words = get_stopwords(langs="zh", source=source)
    except Exception:
        return set()
    return set(words)


@lru_cache(maxsize=1)
def load_gap_exclude_words() -> set[str]:
    return _read_word_list(_LEXICONS_DIR / "gap_exclude_words.txt")


@lru_cache(maxsize=1)
def load_subjective_words() -> set[str]:
    return _read_word_list(_LEXICONS_DIR / "ntusd_subjective_words.txt")


@lru_cache(maxsize=1)
def load_highfreq_words() -> set[str]:
    return _read_word_list(_LEXICONS_DIR / "subtlex_highfreq_words.txt")


@lru_cache(maxsize=1)
def load_custom_words() -> set[str]:
    """加载自定义专有词表，注入分词器防止被拆分。"""
    return _read_word_list(_LEXICONS_DIR / "custom_words.txt")


@lru_cache(maxsize=1)
def load_candidate_words() -> set[str]:
    """加载候选词表，用 dict_combine 软注入，不强制覆盖统计模型。"""
    return _read_word_list(_LEXICONS_DIR / "candidate_words.txt")


@lru_cache(maxsize=1)
def load_abstract_concepts() -> set[str]:
    """加载抽象概念词表，用于候选召回和重加权豁免。"""
    return _read_word_list(_LEXICONS_DIR / "abstract_concepts.txt")


@lru_cache(maxsize=1)
def load_concept_whitelist() -> set[str]:
    words: set[str] = set()
    for filename in _CONCEPT_WHITELIST_FILES:
        words |= _read_thuocl_word_list(_LEXICONS_DIR / filename)
    return words


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def get_reweight_config() -> dict[str, float | bool]:
    """
    轻量重加权开关与参数：
    - ENABLE_POS_FILTER: 是否启用词性过滤
    - ENABLE_NTUSD_REWEIGHT: 是否启用主观词降权
    - ENABLE_SUBTLEX_REWEIGHT: 是否启用高频泛词降权
    - ENABLE_CONCEPT_WHITELIST_REWEIGHT: 是否启用概念词表加权
    - NTUSD_WEIGHT: 主观词乘子（默认 0.6）
    - SUBTLEX_WEIGHT: 高频词乘子（默认 0.5）
    - CONCEPT_WHITELIST_WEIGHT: 概念词乘子（默认 1.35）
    - NON_CONCEPT_WEIGHT: 非概念词乘子（默认 0.9）
    """
    return {
        "enable_pos_filter": _env_flag("ENABLE_POS_FILTER", True),
        "enable_ntusd_reweight": _env_flag("ENABLE_NTUSD_REWEIGHT", True),
        "enable_subtlex_reweight": _env_flag("ENABLE_SUBTLEX_REWEIGHT", True),
        "enable_concept_whitelist_reweight": _env_flag("ENABLE_CONCEPT_WHITELIST_REWEIGHT", True),
        "ntusd_weight": _env_float("NTUSD_WEIGHT", 0.6),
        "subtlex_weight": _env_float("SUBTLEX_WEIGHT", 0.5),
        "concept_whitelist_weight": _env_float("CONCEPT_WHITELIST_WEIGHT", 1.35),
        "non_concept_weight": _env_float("NON_CONCEPT_WEIGHT", 0.9),
    }
