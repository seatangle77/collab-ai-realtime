from typing import Generic, List, TypeVar

from pydantic import BaseModel, field_validator


T = TypeVar("T")

# 批量删除请求体，四个管理模块共用
BATCH_DELETE_MAX_IDS = 100


class BatchDeleteRequest(BaseModel):
    ids: List[str]

    @field_validator("ids")
    @classmethod
    def ids_non_empty_and_bounded(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("ids 不能为空")
        if len(v) > BATCH_DELETE_MAX_IDS:
            raise ValueError(f"单次最多删除 {BATCH_DELETE_MAX_IDS} 条")
        return v


class BatchDeleteResponse(BaseModel):
    deleted: int


class PageMeta(BaseModel):
    total: int
    page: int
    page_size: int


class Page(BaseModel, Generic[T]):
    items: List[T]
    meta: PageMeta

