"""Session-level CoI idea-generation rate analysis.

The analysis uses the real chat-session start/end timestamps as exposure time.
It never infers utterance end times from the next unit timestamp.  Each session is
one observation and each condition therefore receives equal inferential weight.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from statistics import mean, median, stdev
from typing import Any, Literal

from ..api_model import ApiModel
from .coi_analysis_service import AnalysisMode
from .stats_utils import MetricConditionStats, benjamini_hochberg

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None


CONDITIONS_BY_MODE: dict[AnalysisMode, list[str]] = {
    "two_conditions": ["no_assistance", "glasses"],
    "three_conditions": ["no_assistance", "glasses", "app_notification"],
}
PHASES = ("TE", "EX", "IN", "RE")
RATE_METRICS = ("total_rate", "te_rate", "ex_rate", "in_rate", "re_rate")
RATE_LABELS = {
    "total_rate": "全部四阶段观点产生率",
    "te_rate": "TE 产生率",
    "ex_rate": "EX 产生率",
    "in_rate": "IN 产生率",
    "re_rate": "RE 产生率",
    "other_rate": "OTHER 产生率",
}
_METRIC_SEEDS = {
    "total_rate": 2027082701,
    "te_rate": 2027082702,
    "ex_rate": 2027082703,
    "in_rate": 2027082704,
    "re_rate": 2027082705,
}


class CoiRateExcludedSession(ApiModel):
    session_id: str
    group_id: str
    group_name: str | None = None
    condition: str
    reason: Literal["incomplete_coding", "missing_start_time", "missing_end_time", "invalid_duration"]
    note: str
    uncoded_count: int = 0
    total_units: int = 0


class CoiRateObservation(ApiModel):
    session_id: str
    session_title: str | None = None
    group_id: str
    group_name: str | None = None
    condition: str
    started_at: datetime
    ended_at: datetime
    duration_minutes: float
    coded_unit_count: int
    phase_code_count: int
    other_count: int
    te_count: int
    ex_count: int
    in_count: int
    re_count: int
    total_rate: float
    other_rate: float
    te_rate: float
    ex_rate: float
    in_rate: float
    re_rate: float


class CoiRateMetricSummary(ApiModel):
    metric: str
    label: str
    unit: str = "codes_per_minute"
    conditions: list[MetricConditionStats]


class CoiRatePermutationTest(ApiModel):
    metric: str
    label: str
    method: str = "one-way permutation test"
    statistic_name: str = "pseudo-F"
    statistic: float | None = None
    p_value: float | None = None
    p_value_adjusted: float | None = None
    effect_size_name: str = "eta squared"
    effect_size: float | None = None
    permutations: int = 4999
    status: Literal["ok", "insufficient_data", "dependency_missing", "calculation_error"]
    note: str


class CoiRateContrast(ApiModel):
    metric: str
    label: str
    reference_condition: str = "no_assistance"
    comparison_condition: str
    reference_mean: float
    comparison_mean: float
    mean_difference: float
    rate_ratio: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    confidence_level: float = 0.95
    method: str = "session-level bootstrap mean difference"


class CoiRateAnalysisResult(ApiModel):
    mode: AnalysisMode
    conditions: list[str]
    duration_source: str = "chat_sessions.started_at / chat_sessions.ended_at"
    total_sessions: int
    sessions_by_condition: dict[str, int]
    excluded_sessions: list[CoiRateExcludedSession]
    duration_stats: list[MetricConditionStats]
    metrics: list[CoiRateMetricSummary]
    statistical_tests: list[CoiRatePermutationTest]
    contrasts: list[CoiRateContrast]
    observations: list[CoiRateObservation]


def _condition_stats(values: list[float], condition: str) -> MetricConditionStats:
    if not values:
        return MetricConditionStats(condition=condition, n=0)
    return MetricConditionStats(
        condition=condition,
        n=len(values),
        mean=round(mean(values), 4),
        sd=round(stdev(values), 4) if len(values) > 1 else None,
        median=round(median(values), 4),
        min=round(min(values), 4),
        max=round(max(values), 4),
    )


def _pseudo_f(values: "np.ndarray", labels: "np.ndarray") -> tuple[float, float]:
    unique_labels = np.unique(labels)
    n = len(values)
    k = len(unique_labels)
    grand_mean = float(values.mean())
    total_ss = float(((values - grand_mean) ** 2).sum())
    within_ss = 0.0
    for label in unique_labels:
        group = values[labels == label]
        within_ss += float(((group - group.mean()) ** 2).sum())
    between_ss = max(0.0, total_ss - within_ss)
    if total_ss <= 0 or n <= k or within_ss <= 0:
        raise ValueError("会话级产生率缺少足够变异")
    return (between_ss / (k - 1)) / (within_ss / (n - k)), between_ss / total_ss


def _permutation_test(
    metric: str,
    values_by_condition: dict[str, list[float]],
    conditions: list[str],
    permutations: int = 4999,
) -> CoiRatePermutationTest:
    base = {"metric": metric, "label": RATE_LABELS[metric], "permutations": permutations}
    if np is None:
        return CoiRatePermutationTest(**base, status="dependency_missing", note="缺少 numpy，无法执行置换检验")
    if any(len(values_by_condition.get(condition, [])) < 2 for condition in conditions):
        return CoiRatePermutationTest(**base, status="insufficient_data", note="每个条件至少需要2场具有有效时长的完整会话")
    try:
        values = np.asarray([
            value
            for condition in conditions
            for value in values_by_condition[condition]
        ], dtype=float)
        labels = np.asarray([
            condition
            for condition in conditions
            for _ in values_by_condition[condition]
        ])
        observed_f, eta_squared = _pseudo_f(values, labels)
        rng = np.random.default_rng(_METRIC_SEEDS[metric])
        exceedances = 0
        for _ in range(permutations):
            permuted_f, _ = _pseudo_f(values, rng.permutation(labels))
            if permuted_f >= observed_f - 1e-12:
                exceedances += 1
        p_value = (exceedances + 1) / (permutations + 1)
        return CoiRatePermutationTest(
            **base,
            statistic=round(float(observed_f), 4),
            p_value=round(float(p_value), 4),
            effect_size=round(float(eta_squared), 4),
            status="ok",
            note="以每场会话为观测值；编码次数除以真实会话分钟数，条件标签随机置换4999次。",
        )
    except Exception as exc:
        return CoiRatePermutationTest(**base, status="calculation_error", note=f"置换检验计算失败：{exc}")


def _bootstrap_contrast(
    metric: str,
    reference: list[float],
    comparison: list[float],
    comparison_condition: str,
    samples: int = 4999,
) -> CoiRateContrast | None:
    if not reference or not comparison:
        return None
    ref_mean = mean(reference)
    comp_mean = mean(comparison)
    ci_low: float | None = None
    ci_high: float | None = None
    if np is not None and len(reference) >= 2 and len(comparison) >= 2:
        rng = np.random.default_rng(_METRIC_SEEDS[metric] + (10 if comparison_condition == "glasses" else 20))
        ref_array = np.asarray(reference, dtype=float)
        comp_array = np.asarray(comparison, dtype=float)
        differences = np.empty(samples, dtype=float)
        for index in range(samples):
            differences[index] = (
                rng.choice(comp_array, size=len(comp_array), replace=True).mean()
                - rng.choice(ref_array, size=len(ref_array), replace=True).mean()
            )
        ci_low, ci_high = [round(float(value), 4) for value in np.percentile(differences, [2.5, 97.5])]
    return CoiRateContrast(
        metric=metric,
        label=RATE_LABELS[metric],
        comparison_condition=comparison_condition,
        reference_mean=round(ref_mean, 4),
        comparison_mean=round(comp_mean, 4),
        mean_difference=round(comp_mean - ref_mean, 4),
        rate_ratio=round(comp_mean / ref_mean, 4) if ref_mean > 0 else None,
        ci_low=ci_low,
        ci_high=ci_high,
    )


def build_coi_rate_analysis(*, mode: AnalysisMode, rows: list[dict[str, Any]]) -> CoiRateAnalysisResult:
    conditions = CONDITIONS_BY_MODE[mode]
    sessions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("condition") in conditions:
            sessions[str(row["session_id"])].append(row)

    observations: list[CoiRateObservation] = []
    excluded: list[CoiRateExcludedSession] = []
    raw_values: dict[str, dict[str, list[float]]] = {
        metric: defaultdict(list) for metric in (*RATE_METRICS, "other_rate")
    }
    durations_by_condition: dict[str, list[float]] = defaultdict(list)

    for session_id, session_rows in sessions.items():
        first = session_rows[0]
        base_exclusion = {
            "session_id": session_id,
            "group_id": str(first["group_id"]),
            "group_name": first.get("group_name"),
            "condition": str(first["condition"]),
            "total_units": len(session_rows),
        }
        uncoded_count = sum(not row.get("coi_categories") for row in session_rows)
        if uncoded_count:
            excluded.append(CoiRateExcludedSession(
                **base_exclusion,
                reason="incomplete_coding",
                note=f"存在{uncoded_count}个未完成当前编码来源的观点单元",
                uncoded_count=uncoded_count,
            ))
            continue
        started_at = first.get("started_at")
        ended_at = first.get("ended_at")
        if started_at is None:
            excluded.append(CoiRateExcludedSession(**base_exclusion, reason="missing_start_time", note="会话缺少 started_at"))
            continue
        if ended_at is None:
            excluded.append(CoiRateExcludedSession(**base_exclusion, reason="missing_end_time", note="会话缺少 ended_at"))
            continue
        duration_minutes = (ended_at - started_at).total_seconds() / 60.0
        if duration_minutes <= 0:
            excluded.append(CoiRateExcludedSession(**base_exclusion, reason="invalid_duration", note="会话结束时间不晚于开始时间"))
            continue

        counts = {phase: 0 for phase in PHASES}
        other_count = 0
        for row in session_rows:
            categories = list(dict.fromkeys(row.get("coi_categories") or []))
            for category in categories:
                if category in counts:
                    counts[category] += 1
                elif category == "OTHER":
                    other_count += 1
        phase_code_count = sum(counts.values())
        rates = {
            "total_rate": phase_code_count / duration_minutes,
            "te_rate": counts["TE"] / duration_minutes,
            "ex_rate": counts["EX"] / duration_minutes,
            "in_rate": counts["IN"] / duration_minutes,
            "re_rate": counts["RE"] / duration_minutes,
            "other_rate": other_count / duration_minutes,
        }
        condition = str(first["condition"])
        for metric, value in rates.items():
            raw_values[metric][condition].append(value)
        durations_by_condition[condition].append(duration_minutes)
        observations.append(CoiRateObservation(
            session_id=session_id,
            session_title=first.get("session_title"),
            group_id=str(first["group_id"]),
            group_name=first.get("group_name"),
            condition=condition,
            started_at=started_at,
            ended_at=ended_at,
            duration_minutes=round(duration_minutes, 4),
            coded_unit_count=len(session_rows),
            phase_code_count=phase_code_count,
            other_count=other_count,
            te_count=counts["TE"],
            ex_count=counts["EX"],
            in_count=counts["IN"],
            re_count=counts["RE"],
            **{metric: round(value, 4) for metric, value in rates.items()},
        ))

    metrics = [
        CoiRateMetricSummary(
            metric=metric,
            label=RATE_LABELS[metric],
            conditions=[_condition_stats(raw_values[metric][condition], condition) for condition in conditions],
        )
        for metric in (*RATE_METRICS, "other_rate")
    ]
    tests = [_permutation_test(metric, raw_values[metric], conditions) for metric in RATE_METRICS]
    adjusted = benjamini_hochberg([test.p_value if test.status == "ok" else None for test in tests])
    for test, p_adjusted in zip(tests, adjusted):
        if test.status == "ok":
            test.p_value_adjusted = p_adjusted

    contrasts: list[CoiRateContrast] = []
    for metric in RATE_METRICS:
        for condition in conditions:
            if condition == "no_assistance":
                continue
            contrast = _bootstrap_contrast(
                metric,
                raw_values[metric]["no_assistance"],
                raw_values[metric][condition],
                condition,
            )
            if contrast is not None:
                contrasts.append(contrast)

    sessions_by_condition = {condition: 0 for condition in conditions}
    for observation in observations:
        sessions_by_condition[observation.condition] += 1
    return CoiRateAnalysisResult(
        mode=mode,
        conditions=conditions,
        total_sessions=len(observations),
        sessions_by_condition=sessions_by_condition,
        excluded_sessions=excluded,
        duration_stats=[_condition_stats(durations_by_condition[condition], condition) for condition in conditions],
        metrics=metrics,
        statistical_tests=tests,
        contrasts=contrasts,
        observations=observations,
    )
