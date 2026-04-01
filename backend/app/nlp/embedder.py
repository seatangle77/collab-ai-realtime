"""
句子向量化模块
- 服务启动时预加载模型，挂载到 app.state，避免每次请求重新加载
- 对外提供 encode() 批量向量化接口
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sentence_transformers import SentenceTransformer

if TYPE_CHECKING:
    pass

_model: SentenceTransformer | None = None


def load_model(model_name: str) -> SentenceTransformer:
    """启动时调用，加载模型到模块级单例"""
    global _model
    _model = SentenceTransformer(model_name)
    # warm-up：跑一次空推理，避免第一个真实请求延迟
    _model.encode(["warm up"])
    return _model


def get_model() -> SentenceTransformer:
    if _model is None:
        raise RuntimeError("NLP 模型尚未加载，请确认服务启动时已调用 load_model()")
    return _model


def encode(texts: list[str]) -> list[list[float]]:
    """
    批量将文本转为向量
    :param texts: 文本列表
    :return: 对应的 embedding 列表，每个 embedding 为 384 维 float 列表
    """
    model = get_model()
    embeddings = model.encode(texts, convert_to_numpy=True)
    return embeddings.tolist()
