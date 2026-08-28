"""Read-only individual-to-group task-score change analysis.

Each participant's independent score (IS) is paired with the shared final group
score (GS). Improvement is IS - GS, so a positive value means the group answer is
better. Inferential tests keep the group as the assignment/cluster unit.
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
    individual_score: float
    group_score: float
    improvement: float
    member_position: Literal["best", "middle", "weakest"]


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
        "invalid_group_score",
    ]
    note: str


class IndividualTaskSummary(ApiModel):
    task_id: str
    conditions: list[MetricConditionStats]


class IndividualImprovementSummary(ApiModel):
    condition: str
    individual_count: int
    group_count: int
    mean: float | None = None
    sd: float | None = None
    median: float | None = None
    min: float | None = None
    max: float | None = None
    improved_count: int = 0
    unchanged_count: int = 0
    worsened_count: int = 0
    improved_percentage: float | None = None


class IndividualMemberPositionSummary(ApiModel):
    position: Literal["best", "middle", "weakest"]
    conditions: list[MetricConditionStats]


class IndividualWithinConditionTest(ApiModel):
    condition: str
    group_count: int
    mean_group_improvement: float | None = None
    p_value: float | None = None
    p_value_adjusted: float | None = None
    significant: bool | None = None
    effect_size_name: str = "Cohen's dz"
    effect_size: float | None = None
    method: str = "two-sided group-level sign-flip permutation test with Holm correction"
    status: Literal["ok", "insufficient_data", "dependency_missing", "calculation_error"]
    note: str


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
    baseline_stats: list[MetricConditionStats]
    improvement_summaries: list[IndividualImprovementSummary]
    within_condition_tests: list[IndividualWithinConditionTest]
    task_summaries: list[IndividualTaskSummary]
    member_position_summaries: list[IndividualMemberPositionSummary]
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


def _improvement_summary(
    values: list[float],
    condition: str,
    group_count: int,
) -> IndividualImprovementSummary:
    if not values:
        return IndividualImprovementSummary(condition=condition, individual_count=0, group_count=group_count)
    improved_count = sum(value > 0 for value in values)
    unchanged_count = sum(value == 0 for value in values)
    worsened_count = sum(value < 0 for value in values)
    return IndividualImprovementSummary(
        condition=condition,
        individual_count=len(values),
        group_count=group_count,
        mean=round(mean(values), 3),
        sd=round(stdev(values), 3) if len(values) > 1 else None,
        median=round(median(values), 3),
        min=round(min(values), 3),
        max=round(max(values), 3),
        improved_count=improved_count,
        unchanged_count=unchanged_count,
        worsened_count=worsened_count,
        improved_percentage=round(improved_count / len(values) * 100, 1),
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
        raise ValueError("小组平均改善值缺少足够变异")
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
            note="每人的改善值为个人独立分IS减小组最终分GS；推断统计先取每组三人的平均改善值，再在相同任务内整体置换小组条件标签4999次。",
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


def _within_condition_tests(
    group_scores: list[tuple[str, str, str, float]],
    conditions: list[str],
) -> list[IndividualWithinConditionTest]:
    if np is None:
        return [
            IndividualWithinConditionTest(
                condition=condition,
                group_count=sum(item[1] == condition for item in group_scores),
                status="dependency_missing",
                note="缺少 numpy，无法执行组内改善置换检验",
            )
            for condition in conditions
        ]

    tests: list[IndividualWithinConditionTest] = []
    valid_indices: list[int] = []
    raw_p_values: list[float] = []
    for condition_index, condition in enumerate(conditions):
        values = np.asarray([item[3] for item in group_scores if item[1] == condition], dtype=float)
        if len(values) < 2:
            tests.append(IndividualWithinConditionTest(
                condition=condition,
                group_count=len(values),
                status="insufficient_data",
                note="至少需要2个完整小组",
            ))
            continue
        try:
            observed = float(values.mean())
            rng = np.random.default_rng(_RNG_SEED + 100 + condition_index)
            signs = rng.choice(np.asarray([-1.0, 1.0]), size=(PERMUTATIONS, len(values)))
            permuted_means = (signs * values).mean(axis=1)
            exceedances = int((np.abs(permuted_means) >= abs(observed) - 1e-12).sum())
            p_value = (exceedances + 1) / (PERMUTATIONS + 1)
            sample_sd = float(values.std(ddof=1))
            tests.append(IndividualWithinConditionTest(
                condition=condition,
                group_count=len(values),
                mean_group_improvement=round(observed, 3),
                p_value=round(p_value, 4),
                effect_size=round(observed / sample_sd, 4) if sample_sd > 0 else None,
                status="ok",
                note="先计算每组 AIS−GS，再检验小组平均改善是否偏离0；正值表示小组答案更好。",
            ))
            valid_indices.append(len(tests) - 1)
            raw_p_values.append(p_value)
        except Exception as exc:
            tests.append(IndividualWithinConditionTest(
                condition=condition,
                group_count=len(values),
                status="calculation_error",
                note=f"组内改善置换检验失败：{exc}",
            ))

    for test_index, adjusted in zip(valid_indices, _holm_adjust(raw_p_values)):
        tests[test_index].p_value_adjusted = round(adjusted, 4)
        tests[test_index].significant = adjusted < 0.05
    return tests


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
        try:
            group_score = float(result_json.get("gs"))
        except (TypeError, ValueError):
            excluded.append(IndividualScoreExcludedEntry(**base, reason="invalid_group_score", note="缺少有效的小组最终分GS"))
            continue
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

        group_improvement = group_mean - group_score
        group_scores.append((group_id, condition, row_task, group_improvement))
        sorted_participants = sorted(parsed, key=lambda item: (item[2], item[0]))
        positions = ("best", "middle", "weakest")
        for position, (participant_id, participant_name, score) in zip(positions, sorted_participants):
            observations.append(IndividualScoreObservation(
                **base,
                participant_id=participant_id,
                participant_name=participant_name,
                individual_score=score,
                group_score=group_score,
                improvement=round(score - group_score, 3),
                member_position=position,
            ))

    baseline_values_by_condition: dict[str, list[float]] = defaultdict(list)
    improvement_values_by_condition: dict[str, list[float]] = defaultdict(list)
    for observation in observations:
        baseline_values_by_condition[observation.condition].append(observation.individual_score)
        improvement_values_by_condition[observation.condition].append(observation.improvement)
    baseline_stats = [_condition_stats(baseline_values_by_condition[condition], condition) for condition in conditions]

    task_ids = sorted({observation.task_id for observation in observations})
    task_summaries = [
        IndividualTaskSummary(
            task_id=current_task,
            conditions=[
                _condition_stats(
                    [item.improvement for item in observations if item.task_id == current_task and item.condition == condition],
                    condition,
                )
                for condition in conditions
            ],
        )
        for current_task in task_ids
    ]

    groups_by_condition = {condition: sum(item[1] == condition for item in group_scores) for condition in conditions}
    individuals_by_condition = {condition: len(baseline_values_by_condition[condition]) for condition in conditions}
    improvement_summaries = [
        _improvement_summary(
            improvement_values_by_condition[condition],
            condition,
            groups_by_condition[condition],
        )
        for condition in conditions
    ]
    member_position_summaries = [
        IndividualMemberPositionSummary(
            position=position,
            conditions=[
                _condition_stats(
                    [
                        item.improvement
                        for item in observations
                        if item.member_position == position and item.condition == condition
                    ],
                    condition,
                )
                for condition in conditions
            ],
        )
        for position in ("best", "middle", "weakest")
    ]
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
    within_condition_tests = _within_condition_tests(group_scores, conditions)
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
        baseline_stats=baseline_stats,
        improvement_summaries=improvement_summaries,
        within_condition_tests=within_condition_tests,
        task_summaries=task_summaries,
        member_position_summaries=member_position_summaries,
        ais_consistency=consistency,
        statistical_test=statistical_test,
        pairwise_tests=pairwise_tests,
        observations=observations,
        excluded_entries=excluded,
    )
