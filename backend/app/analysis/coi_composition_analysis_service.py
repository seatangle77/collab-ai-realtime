"""Focused CoI code-composition analysis.

This service deliberately leaves the legacy CoI analysis untouched.  It keeps only
the four original CoI phases, treats each session as one observation, and adds a
single global compositional test before the phase-level follow-up tests.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Literal

from ..api_model import ApiModel
from .coi_analysis_service import (
    AnalysisMode,
    CoiSessionObservation,
    ExcludedSession,
    MetricSummary,
    PostHocResult,
    StatisticalTestResult,
    build_coi_analysis,
)
from .stats_utils import benjamini_hochberg

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None


PHASE_METRICS = ("te_ratio", "ex_ratio", "in_ratio", "re_ratio")


class CompositionGlobalTest(ApiModel):
    method: str = "Aitchison-distance PERMANOVA"
    statistic_name: str = "pseudo-F"
    statistic: float | None = None
    p_value: float | None = None
    effect_size_name: str = "R²"
    effect_size: float | None = None
    permutations: int = 4999
    status: Literal["ok", "insufficient_data", "dependency_missing", "calculation_error"]
    note: str


class CoiCompositionAnalysisResult(ApiModel):
    mode: AnalysisMode
    conditions: list[str]
    total_sessions: int
    sessions_by_condition: dict[str, int]
    excluded_sessions: list[ExcludedSession]
    metrics: list[MetricSummary]
    statistical_tests: list[StatisticalTestResult]
    post_hoc_tests: list[PostHocResult]
    observations: list[CoiSessionObservation]
    global_test: CompositionGlobalTest


def _complete_session_rows(rows: list[dict[str, Any]], conditions: list[str]) -> tuple[list[dict[str, Any]], list[ExcludedSession]]:
    sessions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("condition") in conditions:
            sessions[str(row["session_id"])].append(row)

    complete_rows: list[dict[str, Any]] = []
    excluded: list[ExcludedSession] = []
    for session_id, session_rows in sessions.items():
        uncoded_count = sum(not row.get("coi_categories") for row in session_rows)
        if uncoded_count:
            first = session_rows[0]
            excluded.append(ExcludedSession(
                session_id=session_id,
                group_id=str(first["group_id"]),
                group_name=first.get("group_name"),
                condition=str(first["condition"]),
                uncoded_count=uncoded_count,
                total_count=len(session_rows),
            ))
            continue
        complete_rows.extend(session_rows)
    return complete_rows, excluded


def _pseudo_f(coords: "np.ndarray", labels: "np.ndarray") -> tuple[float, float]:
    unique_labels = np.unique(labels)
    n = len(coords)
    k = len(unique_labels)
    grand_mean = coords.mean(axis=0)
    total_ss = float(((coords - grand_mean) ** 2).sum())
    within_ss = 0.0
    for label in unique_labels:
        group = coords[labels == label]
        within_ss += float(((group - group.mean(axis=0)) ** 2).sum())
    between_ss = max(0.0, total_ss - within_ss)
    if total_ss <= 0 or n <= k or within_ss <= 0:
        raise ValueError("组成数据缺少足够变异，无法计算整体检验")
    statistic = (between_ss / (k - 1)) / (within_ss / (n - k))
    return statistic, between_ss / total_ss


def _global_composition_test(
    observations: list[CoiSessionObservation],
    conditions: list[str],
    permutations: int = 4999,
) -> CompositionGlobalTest:
    if np is None:
        return CompositionGlobalTest(
            status="dependency_missing",
            permutations=permutations,
            note="缺少 numpy，无法执行整体组成检验",
        )
    counts_by_condition = {condition: 0 for condition in conditions}
    for obs in observations:
        counts_by_condition[obs.condition] += 1
    if any(counts_by_condition[condition] < 2 for condition in conditions):
        return CompositionGlobalTest(
            status="insufficient_data",
            permutations=permutations,
            note="每个条件至少需要2场完整会话",
        )

    try:
        compositions = []
        labels = []
        for obs in observations:
            counts = np.asarray([obs.te_count, obs.ex_count, obs.in_count, obs.re_count], dtype=float)
            # A small count-scale replacement keeps zero-phase sessions in the log-ratio analysis.
            if np.any(counts == 0):
                counts = counts + 0.5
            composition = counts / counts.sum()
            compositions.append(composition)
            labels.append(obs.condition)

        matrix = np.asarray(compositions, dtype=float)
        # Helmert sub-matrix provides an orthonormal ilr basis; Euclidean distance
        # in these coordinates is the Aitchison distance between compositions.
        helmert = np.zeros((3, 4), dtype=float)
        for row_index in range(3):
            denominator = np.sqrt((row_index + 1) * (row_index + 2))
            helmert[row_index, : row_index + 1] = 1.0 / denominator
            helmert[row_index, row_index + 1] = -(row_index + 1) / denominator
        coords = np.log(matrix) @ helmert.T
        label_array = np.asarray(labels)
        observed_f, r_squared = _pseudo_f(coords, label_array)

        rng = np.random.default_rng(20270824)
        exceedances = 0
        for _ in range(permutations):
            permuted_f, _ = _pseudo_f(coords, rng.permutation(label_array))
            if permuted_f >= observed_f - 1e-12:
                exceedances += 1
        p_value = (exceedances + 1) / (permutations + 1)
        return CompositionGlobalTest(
            statistic=round(float(observed_f), 4),
            p_value=round(float(p_value), 4),
            effect_size=round(float(r_squared), 4),
            permutations=permutations,
            status="ok",
            note="先检验三种条件下TE/EX/IN/RE整体编码构成是否不同；零计数仅在整体检验中使用0.5计数替代。",
        )
    except Exception as exc:
        return CompositionGlobalTest(
            status="calculation_error",
            permutations=permutations,
            note=f"整体组成检验计算失败：{exc}",
        )


def build_coi_composition_analysis(
    *,
    mode: AnalysisMode,
    rows: list[dict[str, Any]],
) -> CoiCompositionAnalysisResult:
    conditions = ["no_assistance", "glasses"] if mode == "two_conditions" else [
        "no_assistance", "glasses", "app_notification",
    ]
    complete_rows, excluded_sessions = _complete_session_rows(rows, conditions)
    legacy = build_coi_analysis(mode=mode, rows=complete_rows)

    metrics = [metric for metric in legacy.metrics if metric.metric in PHASE_METRICS]
    statistical_tests = [
        test.model_copy(deep=True)
        for test in legacy.statistical_tests
        if test.metric in PHASE_METRICS
    ]
    adjusted = benjamini_hochberg([
        test.p_value if test.status == "ok" else None
        for test in statistical_tests
    ])
    for test, p_adjusted in zip(statistical_tests, adjusted):
        if test.status == "ok":
            test.p_value_adjusted = p_adjusted

    test_by_metric = {test.metric: test for test in statistical_tests}
    post_hoc_tests: list[PostHocResult] = []
    for post_hoc in legacy.post_hoc_tests:
        if post_hoc.metric not in PHASE_METRICS:
            continue
        copied = post_hoc.model_copy(deep=True)
        adjusted_p = test_by_metric[copied.metric].p_value_adjusted
        if adjusted_p is None or adjusted_p >= 0.05:
            copied.method = None
            copied.pairs = []
            copied.status = "not_applicable"
            copied.note = f"四阶段BH校正后的总体检验 p={adjusted_p}，未达显著水平，无需事后检验"
        post_hoc_tests.append(copied)

    return CoiCompositionAnalysisResult(
        mode=mode,
        conditions=conditions,
        total_sessions=legacy.total_sessions,
        sessions_by_condition=legacy.sessions_by_condition,
        excluded_sessions=excluded_sessions,
        metrics=metrics,
        statistical_tests=statistical_tests,
        post_hoc_tests=post_hoc_tests,
        observations=legacy.observations,
        global_test=_global_composition_test(legacy.observations, conditions),
    )
