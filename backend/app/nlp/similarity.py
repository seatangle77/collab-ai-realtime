"""
余弦相似度计算模块
- 支持单对和批量计算
- 纯 numpy 运算，无 IO，极快
"""
from __future__ import annotations

import numpy as np


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """计算两个向量的余弦相似度，返回 [-1, 1]，通常为 [0, 1]"""
    a = np.array(vec_a, dtype=np.float32)
    b = np.array(vec_b, dtype=np.float32)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    raw = float(np.dot(a, b) / (norm_a * norm_b))
    # float32 精度误差可能让结果略超出 [-1, 1]，clip 修正
    return float(np.clip(raw, -1.0, 1.0))


def batch_similarity(pairs: list[dict]) -> list[float]:
    """
    批量计算多对向量的余弦相似度
    :param pairs: [{"vec_a": [...], "vec_b": [...]}, ...]
    :return: 每对的相似度列表，顺序与输入一致
    """
    return [
        cosine_similarity(pair["vec_a"], pair["vec_b"])
        for pair in pairs
    ]
