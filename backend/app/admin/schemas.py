from typing import Generic, List, TypeVar

from pydantic import BaseModel


T = TypeVar("T")


class PageMeta(BaseModel):
    total: int
    page: int
    page_size: int


class Page(BaseModel, Generic[T]):
    items: List[T]
    meta: PageMeta

