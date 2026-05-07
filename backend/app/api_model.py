from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, field_serializer

from .time_utils import utc_iso


class ApiModel(BaseModel):
    @field_serializer("*", when_used="json", check_fields=False)
    def serialize_datetimes(self, value: Any) -> Any:
        if isinstance(value, datetime):
            return utc_iso(value)
        if isinstance(value, dict):
            return {key: self.serialize_datetimes(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.serialize_datetimes(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self.serialize_datetimes(item) for item in value)
        return value
