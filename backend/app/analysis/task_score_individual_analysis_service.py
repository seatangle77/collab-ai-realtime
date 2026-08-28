"""Read-only individual task-score baseline analysis.

Individual scores are displayed at participant level, while inferential tests keep
the group as the assignment/cluster unit. Condition labels are permuted between
whole groups (within task strata); individual rows are never permuted separately.
"""
from __future__ import annotations

from collections import defaultdict
from statistics import mean, median, stdev
from typing import Any, Literal

from ..api_model import ApiModel
from .stats_utils import MetricConditionStats
from .task_score_analysis_service import AnalysisMode, CONDITIONS_BY_MODE, TaskFilter

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None


PERMUTATIONS = 4999
_RNG_SEED = 2027082801


class IndividualScoreObservation(ApiModel):
    entry_id: str
    group_id: str
    task_id: str
    condition: str
    participant_id: str
    participant_name: str | None = None
    score: float


class IndividualScoreExcludedEntry(ApiModel):
    entry_id: str
    group_id: str
    task_id: str
    condition: str
    reason: Literal[
        "missing_result",
        "invalid_individual_scores",
        "invalid_participant",
        "duplicate_participant",
        "ais_mismatch",
    ]
    note: str


class IndividualTaskSummary(ApiModel):
    task_id: str
    conditions: list[MetricConditionStats]


class IndividualAisConsistency(ApiModel):
    checked_groups: int
    consistent_groups: int
    max_absolute_difference: float | None = None
    status: Literal["ok", "warning", "not_available"]
    note: str


class IndividualClusterTest(ApiModel):
    method: str = "group-clustered stratified permutation test"
    statistic_name: str = "pseudo-F"
    statistic: float | None = None
    p_value: float | None = None
    effect_size_name: str = "eta squared"
    effect_size: float | None = None
    permutations: int = PERMUTATIONS
    cluster_unit: str = "group"
    status: Literal["ok", "insufficient_data", "dependency_missing", "calculation_error"]
    note: str


class IndividualPairwiseResult(ApiModel):
    condition_a: str
    condition_b: str
    mean_difference: float | None = None
    p_value: float | None = None
    p_value_adjusted: float | None = None
    significant: bool | None = None
    method: str = "group-clustered stratified permutation contrast with Holm correction"


class TaskScoreIndividualAnalysisResult(ApiModel):
    mode: AnalysisMode
    task_id: TaskFilter
    conditions: list[str]
    total_groups: int
    total_individuals: int
    groups_by_condition: dict[str, int]
    individuals_by_condition: dict[str, int]
    score_direction: str = "lower_is_better"
    individual_stats: list[MetricConditionStats]
    task_summaries: list[IndividualTaskSummary]
    ais_consistency: IndividualAisConsistency
    statistical_test: IndividualClusterTest
    pairwise_tests: list[IndividualPairwiseResult]
    observations: list[IndividualScoreObservation]
    excluded_entries: list[IndividualScoreExcludedEntry]


def _condition_stats(values: list[float], condition: str) -> MetricConditionStats:
    if not values:
        return MetricConditionStats(condition=condition, n=0)
    return MetricConditionStats(
        condition=condition,
        n=len(values),
        mean=round(mean(values), 3),
        sd=round(stdev(values), 3) if len(values) > 1 else None,
        median=round(median(values), 3),
        min=round(min(values), 3),
        max=round(max(values), 3),
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
        raise ValueError("小组平均个人分缺少足够变异")
    return (between_ss / (k - 1)) / (within_ss / (n - k)), between_ss / total_ss


def _permute_within_tasks(labels: "np.ndarray", tasks: "np.ndarray", rng: "np.random.Generator") -> "np.ndarray":
    permuted = labels.copy()
    for task in np.unique(tasks):
        indices = np.flatnonzero(tasks == task)
        permuted[indices] = rng.permutation(labels[indices])
    return permuted


def _cluster_test(
    group_scores: list[tuple[str, str, str, float]],
    conditions: list[str],
) -> IndividualClusterTest:
    if np is None:
        return IndividualClusterTest(status="dependency_missing", note="缺少 numpy，无法执行小组聚类置换检验")
    counts = {condition: 0 for condition in conditions}
    for _, condition, _, _ in group_scores:
        counts[condition] += 1
    if any(counts[condition] < 2 for condition in conditions):
        return IndividualClusterTest(status="insufficient_data", note="每个条件至少需要2个完整小组")
    try:
        values = np.asarray([item[3] for item in group_scores], dtype=float)
        labels = np.asarray([item[1] for item in group_scores])
        tasks = np.asarray([item[2] for item in group_scores])
        observed_f, eta_squared = _pseudo_f(values, labels)
        rng = np.random.default_rng(_RNG_SEED)
        exceedances = 0
        for _ in range(PERMUTATIONS):
            permuted_labels = _permute_within_tasks(labels, tasks, rng)
            permuted_f, _ = _pseudo_f(values, permuted_labels)
            if permuted_f >= observed_f - 1e-12:
                exceedances += 1
        p_value = (exceedances + 1) / (PERMUTATIONS + 1)
        return IndividualClusterTest(
            statistic=round(float(observed_f), 4),
            p_value=round(float(p_value), 4),
            effect_size=round(float(eta_squared), 4),
            status="ok",
            note="个人分数用于描述；推断统计先取每组三人的平均个人分，再在相同任务内整体置换小组条件标签4999次。",
        )
    except Exception as exc:
        return IndividualClusterTest(status="calculation_error", note=f"小组聚类置换检验失败：{exc}")


def _pairwise_raw_p(
    group_scores: list[tuple[str, str, str, float]],
    condition_a: str,
    condition_b: str,
    seed_offset: int,
) -> tuple[float, float] | None:
    if np is None:
        return None
    selected = [item for item in group_scores if item[1] in {condition_a, condition_b}]
    if sum(item[1] == condition_a for item in selected) < 2 or sum(item[1] == condition_b for item in selected) < 2:
        return None
    values = np.asarray([item[3] for item in selected], dtype=float)
    labels = np.asarray([item[1] for item in selected])
    tasks = np.asarray([item[2] for item in selected])
    observed = float(values[labels == condition_b].mean() - values[labels == condition_a].mean())
    rng = np.random.default_rng(_RNG_SEED + seed_offset)
    exceedances = 0
    for _ in range(PERMUTATIONS):
        permuted = _permute_within_tasks(labels, tasks, rng)
        diff = float(values[permuted == condition_b].mean() - values[permuted == condition_a].mean())
        if abs(diff) >= abs(observed) - 1e-12:
            exceedances += 1
    return observed, (exceedances + 1) / (PERMUTATIONS + 1)


def _holm_adjust(p_values: list[float]) -> list[float]:
    indexed = sorted(enumerate(p_values), key=lambda item: item[1])
    adjusted_sorted: list[float] = []
    running = 0.0
    m = len(p_values)
    for rank, (_, p_value) in enumerate(indexed):
        running = max(running, min(1.0, p_value * (m - rank)))
        adjusted_sorted.append(running)
    result = [1.0] * m
    for adjusted, (original_index, _) in zip(adjusted_sorted, indexed):
        result[original_index] = adjusted
    return result


def _pairwise_tests(
    group_scores: list[tuple[str, str, str, float]],
    conditions: list[str],
) -> list[IndividualPairwiseResult]:
    if len(conditions) < 3:
        return []
    raw_results: list[tuple[str, str, float, float]] = []
    seed_offset = 1
    for index, condition_a in enumerate(conditions):
        for condition_b in conditions[index + 1:]:
            result = _pairwise_raw_p(group_scores, condition_a, condition_b, seed_offset)
            seed_offset += 1
            if result is not None:
                difference, p_value = result
                raw_results.append((condition_a, condition_b, difference, p_value))
    adjusted = _holm_adjust([item[3] for item in raw_results])
    return [
        IndividualPairwiseResult(
            condition_a=condition_a,
            condition_b=condition_b,
            mean_difference=round(difference, 3),
            p_value=round(p_value, 4),
            p_value_adjusted=round(p_adjusted, 4),
            significant=p_adjusted < 0.05,
        )
        for (condition_a, condition_b, difference, p_value), p_adjusted in zip(raw_results, adjusted)
    ]


def build_task_score_individual_analysis(
    *,
    mode: AnalysisMode,
    task_id: TaskFilter,
    rows: list[dict[str, Any]],
) -> TaskScoreIndividualAnalysisResult:
    conditions = CONDITIONS_BY_MODE[mode]
    observations: list[IndividualScoreObservation] = []
    excluded: list[IndividualScoreExcludedEntry] = []
    group_scores: list[tuple[str, str, str, float]] = []
    ais_differences: list[float] = []

    for row in rows:
        condition = str(row.get("condition"))
        row_task = str(row.get("task_id"))
        if condition not in conditions or (task_id != "all" and row_task != task_id):
            continue
        entry_id = str(row.get("id"))
        group_id = str(row.get("group_id"))
        base = {"entry_id": entry_id, "group_id": group_id, "task_id": row_task, "condition": condition}
        result_json = row.get("result_json")
        if not isinstance(result_json, dict):
            excluded.append(IndividualScoreExcludedEntry(**base, reason="missing_result", note="缺少可读取的计算结果"))
            continue
        individual_scores = result_json.get("individual_scores")
        if not isinstance(individual_scores, list) or len(individual_scores) != 3:
            excluded.append(IndividualScoreExcludedEntry(**base, reason="invalid_individual_scores", note="每个小组必须恰好包含3名成员的个人分数"))
            continue

        participant_ids: set[str] = set()
        parsed: list[tuple[str, str | None, float]] = []
        invalid_note: str | None = None
        for item in individual_scores:
            if not isinstance(item, dict) or not item.get("participant_id") or item.get("score") is None:
                invalid_note = "个人分数记录缺少 participant_id 或 score"
                break
            participant_id = str(item["participant_id"])
            if participant_id in participant_ids:
                invalid_note = "同一小组内 participant_id 重复"
                break
            try:
                score = float(item["score"])
            except (TypeError, ValueError):
                invalid_note = "个人分数不是有效数字"
                break
            participant_ids.add(participant_id)
            parsed.append((participant_id, item.get("participant_name"), score))
        if invalid_note:
            reason = "duplicate_participant" if "重复" in invalid_note else "invalid_participant"
            excluded.append(IndividualScoreExcludedEntry(**base, reason=reason, note=invalid_note))
            continue

        group_mean = mean(item[2] for item in parsed)
        ais_value = result_json.get("ais")
        if ais_value is not None:
            try:
                difference = abs(group_mean - float(ais_value))
                ais_differences.append(difference)
                if difference > 0.011:
                    excluded.append(IndividualScoreExcludedEntry(
                        **base,
                        reason="ais_mismatch",
                        note=f"三名成员均值{group_mean:.3f}与已保存AIS {float(ais_value):.3f}不一致；该组未纳入分析",
                    ))
                    continue
            except (TypeError, ValueError):
                excluded.append(IndividualScoreExcludedEntry(**base, reason="ais_mismatch", note="已保存AIS不是有效数字"))
                continue

        group_scores.append((group_id, condition, row_task, group_mean))
        observations.extend(
            IndividualScoreObservation(
                **base,
                participant_id=participant_id,
                participant_name=participant_name,
                score=score,
            )
            for participant_id, participant_name, score in parsed
        )

    values_by_condition: dict[str, list[float]] = defaultdict(list)
    for observation in observations:
        values_by_condition[observation.condition].append(observation.score)
    individual_stats = [_condition_stats(values_by_condition[condition], condition) for condition in conditions]

    task_ids = sorted({observation.task_id for observation in observations})
    task_summaries = [
        IndividualTaskSummary(
            task_id=current_task,
            conditions=[
                _condition_stats(
                    [item.score for item in observations if item.task_id == current_task and item.condition == condition],
                    condition,
                )
                for condition in conditions
            ],
        )
        for current_task in task_ids
    ]

    groups_by_condition = {condition: sum(item[1] == condition for item in group_scores) for condition in conditions}
    individuals_by_condition = {condition: len(values_by_condition[condition]) for condition in conditions}
    checked_groups = len(ais_differences)
    consistent_groups = sum(value <= 0.011 for value in ais_differences)
    consistency = IndividualAisConsistency(
        checked_groups=checked_groups,
        consistent_groups=consistent_groups,
        max_absolute_difference=round(max(ais_differences), 4) if ais_differences else None,
        status="not_available" if not ais_differences else ("ok" if checked_groups == consistent_groups else "warning"),
        note=(
            "没有可用于核对的AIS"
            if not ais_differences
            else ("所有纳入小组的三人均值均与已保存AIS一致" if checked_groups == consistent_groups else "部分小组的三人均值与已保存AIS不一致")
        ),
    )

    statistical_test = _cluster_test(group_scores, conditions)
    pairwise_tests = (
        _pairwise_tests(group_scores, conditions)
        if statistical_test.status == "ok"
        and statistical_test.p_value is not None
        and statistical_test.p_value < 0.05
        else []
    )

    return TaskScoreIndividualAnalysisResult(
        mode=mode,
        task_id=task_id,
        conditions=conditions,
        total_groups=len(group_scores),
        total_individuals=len(observations),
        groups_by_condition=groups_by_condition,
        individuals_by_condition=individuals_by_condition,
        individual_stats=individual_stats,
        task_summaries=task_summaries,
        ais_consistency=consistency,
        statistical_test=statistical_test,
        pairwise_tests=pairwise_tests,
        observations=observations,
        excluded_entries=excluded,
    )
