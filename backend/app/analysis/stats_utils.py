"""Shared statistical helpers and models for analysis services."""
from __future__ import annotations

import math
from statistics import mean, median, stdev

from ..api_model import ApiModel


class MetricConditionStats(ApiModel):
    condition: str
    n: int
    mean: float | None = None
    sd: float | None = None
    median: float | None = None
    min: float | None = None
    max: float | None = None


class PostHocPairResult(ApiModel):
    condition_a: str
    condition_b: str
    mean_diff: float | None = None
    p_value_adjusted: float | None = None
    significant: bool | None = None
    alpha: float = 0.05


def _stats_for(values: list[float], condition: str, ndigits: int = 3) -> MetricConditionStats:
    if not values:
        return MetricConditionStats(condition=condition, n=0)
    return MetricConditionStats(
        condition=condition,
        n=len(values),
        mean=round(mean(values), ndigits),
        sd=round(stdev(values), ndigits) if len(values) > 1 else None,
        median=round(median(values), ndigits),
        min=round(min(values), ndigits),
        max=round(max(values), ndigits),
    )


def _cohens_d(a: list[float], b: list[float]) -> float | None:
    """Hedges' g: Cohen's d with small-sample correction factor J."""
    if len(a) < 2 or len(b) < 2:
        return None
    pooled_var = ((len(a) - 1) * stdev(a) ** 2 + (len(b) - 1) * stdev(b) ** 2) / (len(a) + len(b) - 2)
    if pooled_var <= 0:
        return None
    d = (mean(b) - mean(a)) / math.sqrt(pooled_var)
    df = len(a) + len(b) - 2
    j = 1 - 3 / (4 * df - 1)
    return d * j


def _eta_squared(groups: list[list[float]]) -> float | None:
    values = [v for g in groups for v in g]
    if len(values) <= 1:
        return None
    grand = mean(values)
    ss_between = sum(len(g) * (mean(g) - grand) ** 2 for g in groups if g)
    ss_total = sum((v - grand) ** 2 for v in values)
    if ss_total <= 0:
        return None
    return ss_between / ss_total


def _epsilon_squared(h: float, k: int, n: int) -> float | None:
    denom = n - k
    if denom <= 0:
        return None
    return max(0.0, (h - k + 1) / denom)
