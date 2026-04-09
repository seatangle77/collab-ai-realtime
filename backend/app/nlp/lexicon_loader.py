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
    - ENABLE_NTUSD_REWEIGHT: 是否启用主观词降权
    - ENABLE_SUBTLEX_REWEIGHT: 是否启用高频泛词降权
    - NTUSD_WEIGHT: 主观词乘子（默认 0.6）
    - SUBTLEX_WEIGHT: 高频词乘子（默认 0.5）
    """
    return {
        "enable_ntusd_reweight": _env_flag("ENABLE_NTUSD_REWEIGHT", True),
        "enable_subtlex_reweight": _env_flag("ENABLE_SUBTLEX_REWEIGHT", True),
        "ntusd_weight": _env_float("NTUSD_WEIGHT", 0.6),
        "subtlex_weight": _env_float("SUBTLEX_WEIGHT", 0.5),
    }

