from __future__ import annotations

from collections import defaultdict
import math
from statistics import mean, median, stdev
from typing import Any, Literal

from ..api_model import ApiModel
from .stats_utils import MetricConditionStats, PostHocPairResult, _cohens_d, _eta_squared, _epsilon_squared, _stats_for

try:
    from scipy.stats import f_oneway, kruskal, mannwhitneyu, norm as _scipy_norm, shapiro, ttest_ind, tukey_hsd
except ImportError:  # pragma: no cover - exercised only in deployments without scipy
    f_oneway = None
    kruskal = None
    mannwhitneyu = None
    _scipy_norm = None
    shapiro = None
    ttest_ind = None
    tukey_hsd = None

try:
    import matplotlib.pyplot as plt
    from .chart_utils import condition_color, condition_label as _cond_label, fig_to_base64, draw_boxplot
    _CHARTS_AVAILABLE = True
except ImportError:
    _CHARTS_AVAILABLE = False


AnalysisMode = Literal["two_conditions", "three_conditions"]
TaskFilter = Literal["all", "moon_survival", "lost_at_sea", "winter_survival"]
MetricRole = Literal["primary", "baseline"]
NormalityStatus = Literal["ok", "insufficient_n", "constant_values", "dependency_missing"]
RecommendedTest = Literal[
    "independent_samples_t_test",
    "mann_whitney_u",
    "one_way_anova",
    "kruskal_wallis",
    "insufficient_data",
]
StatisticalTestStatus = Literal["ok", "insufficient_data", "dependency_missing", "calculation_error"]

CONDITIONS_BY_MODE: dict[AnalysisMode, list[str]] = {
    "two_conditions": ["no_assistance", "glasses"],
    "three_conditions": ["no_assistance", "glasses", "app_notification"],
}

METRIC_LABELS: dict[str, str] = {
    "gs": "GS 小组最终分",
    "ais": "AIS 平均个人分",
    "best_is": "Best IS 最佳个人分",
    "weak_synergy": "弱协同值",
    "strong_synergy": "强协同值",
}

PRIMARY_METRICS = ["gs", "weak_synergy", "strong_synergy"]
BASELINE_METRICS = ["ais", "best_is"]
ALL_METRICS = [*PRIMARY_METRICS, *BASELINE_METRICS]


class TaskScoreObservation(ApiModel):
    entry_id: str
    group_id: str
    task_id: str
    condition: str
    gs: float
    ais: float
    best_is: float
    weak_synergy: float
    strong_synergy: float


class MetricSummary(ApiModel):
    metric: str
    label: str
    role: MetricRole
    conditions: list[MetricConditionStats]


class NormalityConditionResult(ApiModel):
    metric: str
    label: str
    role: MetricRole
    condition: str
    n: int
    test: Literal["shapiro_wilk"] = "shapiro_wilk"
    statistic: float | None = None
    p_value: float | None = None
    is_normal: bool | None = None
    alpha: float = 0.05
    status: NormalityStatus
    note: str


class StatisticalTestRecommendation(ApiModel):
    metric: str
    label: str
    role: MetricRole
    recommended_test: RecommendedTest
    normality_assumption_met: bool | None
    conditions: list[str]
    note: str


class StatisticalTestResult(ApiModel):
    metric: str
    label: str
    role: MetricRole
    test: RecommendedTest
    statistic_name: str | None = None
    statistic: float | None = None
    p_value: float | None = None
    effect_size_name: str | None = None
    effect_size: float | None = None
    status: StatisticalTestStatus
    note: str


PostHocStatus = Literal["ok", "not_applicable", "insufficient_data", "dependency_missing", "calculation_error"]
PostHocMethod = Literal["tukey_hsd", "dunn_bonferroni"]


class PostHocResult(ApiModel):
    metric: str
    label: str
    role: MetricRole
    method: PostHocMethod | None = None
    pairs: list[PostHocPairResult] = []
    status: PostHocStatus
    note: str


class TaskScoreAnalysisResult(ApiModel):
    mode: AnalysisMode
    task_id: TaskFilter
    conditions: list[str]
    total_entries: int
    entries_by_condition: dict[str, int]
    metrics: list[MetricSummary]
    normality: list[NormalityConditionResult]
    test_recommendations: list[StatisticalTestRecommendation]
    statistical_tests: list[StatisticalTestResult]
    post_hoc_tests: list[PostHocResult]
    observations: list[TaskScoreObservation]
    charts: dict[str, str] = {}


def _round(value: float) -> float:
    return round(value, 3)


def _role_for_metric(metric: str) -> MetricRole:
    return "primary" if metric in PRIMARY_METRICS else "baseline"


def _normality_for(
    *,
    metric: str,
    condition: str,
    values: list[float],
    alpha: float = 0.05,
) -> NormalityConditionResult:
    role = _role_for_metric(metric)
    base = {
        "metric": metric,
        "label": METRIC_LABELS[metric],
        "role": role,
        "condition": condition,
        "n": len(values),
        "alpha": alpha,
    }

    if shapiro is None:
        return NormalityConditionResult(
            **base,
            status="dependency_missing",
            note="缺少 scipy，无法执行 Shapiro-Wilk 正态性检验",
        )
    if len(values) < 3:
        return NormalityConditionResult(
            **base,
            status="insufficient_n",
            note="Shapiro-Wilk 至少需要 3 个样本",
        )
    if len(set(values)) <= 1:
        return NormalityConditionResult(
            **base,
            status="constant_values",
            note="所有观测值相同，无法稳定判断正态性",
        )

    statistic, p_value = shapiro(values)
    p_value_float = float(p_value)
    return NormalityConditionResult(
        **base,
        statistic=_round(float(statistic)),
        p_value=_round(p_value_float),
        is_normal=p_value_float >= alpha,
        status="ok",
        note="p >= 0.05 时按近似正态处理" if p_value_float >= alpha else "p < 0.05，按偏离正态处理",
    )


def _recommend_test_for_metric(
    *,
    mode: AnalysisMode,
    metric: str,
    conditions: list[str],
    normality_results: list[NormalityConditionResult],
) -> StatisticalTestRecommendation:
    metric_normality = [
        item for item in normality_results
        if item.metric == metric and item.condition in conditions
    ]
    role = _role_for_metric(metric)
    if any(item.n < 2 for item in metric_normality):
        return StatisticalTestRecommendation(
            metric=metric,
            label=METRIC_LABELS[metric],
            role=role,
            recommended_test="insufficient_data",
            normality_assumption_met=None,
            conditions=conditions,
            note="至少每个条件需要 2 个样本才能进行组间比较",
        )

    all_normality_ok = all(item.status == "ok" and item.is_normal is True for item in metric_normality)
    all_normality_checked = all(item.status == "ok" for item in metric_normality)
    if mode == "two_conditions":
        if all_normality_ok:
            return StatisticalTestRecommendation(
                metric=metric,
                label=METRIC_LABELS[metric],
                role=role,
                recommended_test="independent_samples_t_test",
                normality_assumption_met=True,
                conditions=conditions,
                note="两个条件均通过 Shapiro-Wilk，建议使用 independent-samples t-test",
            )
        return StatisticalTestRecommendation(
            metric=metric,
            label=METRIC_LABELS[metric],
            role=role,
            recommended_test="mann_whitney_u",
            normality_assumption_met=False if all_normality_checked else None,
            conditions=conditions,
            note="至少一个条件未通过或无法完成正态性检查，建议使用 Mann-Whitney U test",
        )

    if all_normality_ok:
        return StatisticalTestRecommendation(
            metric=metric,
            label=METRIC_LABELS[metric],
            role=role,
            recommended_test="one_way_anova",
            normality_assumption_met=True,
            conditions=conditions,
            note="三个条件均通过 Shapiro-Wilk，建议使用 one-way ANOVA",
        )
    return StatisticalTestRecommendation(
        metric=metric,
        label=METRIC_LABELS[metric],
        role=role,
        recommended_test="kruskal_wallis",
        normality_assumption_met=False if all_normality_checked else None,
        conditions=conditions,
        note="至少一个条件未通过或无法完成正态性检查，建议使用 Kruskal-Wallis",
    )


def _statistical_test_for_metric(
    *,
    metric: str,
    recommendation: StatisticalTestRecommendation,
    values_by_condition: dict[str, list[float]],
) -> StatisticalTestResult:
    role = _role_for_metric(metric)
    base = {
        "metric": metric,
        "label": METRIC_LABELS[metric],
        "role": role,
        "test": recommendation.recommended_test,
    }
    groups = [values_by_condition[condition] for condition in recommendation.conditions]
    if recommendation.recommended_test == "insufficient_data" or any(len(group) < 2 for group in groups):
        return StatisticalTestResult(
            **base,
            status="insufficient_data",
            note="至少每个条件需要 2 个样本才能计算推断统计",
        )
    if any(len(set(group)) <= 1 for group in groups):
        return StatisticalTestResult(
            **base,
            status="calculation_error",
            note="至少一个条件内数值恒定，统计检验结果可能不稳定，已跳过",
        )
    if recommendation.recommended_test == "independent_samples_t_test":
        if ttest_ind is None:
            return StatisticalTestResult(**base, status="dependency_missing", note="缺少 scipy，无法执行 t-test")
        statistic, p_value = ttest_ind(groups[0], groups[1], equal_var=False)
        return StatisticalTestResult(
            **base,
            statistic_name="t",
            statistic=_round(float(statistic)),
            p_value=_round(float(p_value)),
            effect_size_name="Cohen's d",
            effect_size=_round(d) if (d := _cohens_d(groups[0], groups[1])) is not None else None,
            status="ok",
            note="使用 Welch independent-samples t-test；Cohen's d 为第二条件均值减第一条件均值",
        )
    if recommendation.recommended_test == "mann_whitney_u":
        if mannwhitneyu is None:
            return StatisticalTestResult(**base, status="dependency_missing", note="缺少 scipy，无法执行 Mann-Whitney U")
        statistic, p_value = mannwhitneyu(groups[0], groups[1], alternative="two-sided")
        n1, n2 = len(groups[0]), len(groups[1])
        rank_biserial = (2 * float(statistic) / (n1 * n2)) - 1
        return StatisticalTestResult(
            **base,
            statistic_name="U",
            statistic=_round(float(statistic)),
            p_value=_round(float(p_value)),
            effect_size_name="rank-biserial r",
            effect_size=_round(rank_biserial),
            status="ok",
            note="rank-biserial r 方向为第一条件相对第二条件",
        )
    if recommendation.recommended_test == "one_way_anova":
        if f_oneway is None:
            return StatisticalTestResult(**base, status="dependency_missing", note="缺少 scipy，无法执行 one-way ANOVA")
        statistic, p_value = f_oneway(*groups)
        return StatisticalTestResult(
            **base,
            statistic_name="F",
            statistic=_round(float(statistic)),
            p_value=_round(float(p_value)),
            effect_size_name="eta squared",
            effect_size=_round(eta) if (eta := _eta_squared(groups)) is not None else None,
            status="ok",
            note="若 p < 0.05，后续可补 Tukey HSD 事后检验",
        )
    if recommendation.recommended_test == "kruskal_wallis":
        if kruskal is None:
            return StatisticalTestResult(**base, status="dependency_missing", note="缺少 scipy，无法执行 Kruskal-Wallis")
        statistic, p_value = kruskal(*groups)
        return StatisticalTestResult(
            **base,
            statistic_name="H",
            statistic=_round(float(statistic)),
            p_value=_round(float(p_value)),
            effect_size_name="epsilon squared",
            effect_size=_round(eps) if (eps := _epsilon_squared(float(statistic), len(groups), sum(len(g) for g in groups))) is not None else None,
            status="ok",
            note="若 p < 0.05，后续可补 Dunn + Bonferroni 事后检验",
        )
    return StatisticalTestResult(**base, status="calculation_error", note="未知检验类型")


def _dunn_bonferroni_pairs(
    groups: list[list[float]],
    conditions: list[str],
    alpha: float = 0.05,
) -> list[PostHocPairResult]:
    """Dunn test with Bonferroni correction (manual implementation, no extra deps)."""
    from itertools import combinations

    all_values = [v for group in groups for v in group]
    n_total = len(all_values)

    # scipy rankdata via sorted ranks (handles ties with average)
    sorted_with_idx = sorted(enumerate(all_values), key=lambda x: x[1])
    ranks = [0.0] * n_total
    i = 0
    while i < n_total:
        j = i
        while j < n_total - 1 and sorted_with_idx[j + 1][1] == sorted_with_idx[i][1]:
            j += 1
        avg_rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[sorted_with_idx[k][0]] = avg_rank
        i = j + 1

    # mean rank per group
    group_mean_ranks: list[float] = []
    idx = 0
    for group in groups:
        group_mean_ranks.append(sum(ranks[idx + k] for k in range(len(group))) / len(group))
        idx += len(group)

    pair_indices = list(combinations(range(len(groups)), 2))
    k = len(pair_indices)  # number of comparisons for Bonferroni

    pairs: list[PostHocPairResult] = []
    for i, j in pair_indices:
        n_i, n_j = len(groups[i]), len(groups[j])
        se = math.sqrt((n_total * (n_total + 1) / 12) * (1 / n_i + 1 / n_j))
        if se == 0:
            pairs.append(PostHocPairResult(condition_a=conditions[i], condition_b=conditions[j]))
            continue
        z = abs(group_mean_ranks[i] - group_mean_ranks[j]) / se
        p_raw = 2 * (1 - _scipy_norm.cdf(z))
        p_adj = min(1.0, p_raw * k)
        mean_diff = _round(mean(groups[j]) - mean(groups[i]))
        pairs.append(PostHocPairResult(
            condition_a=conditions[i],
            condition_b=conditions[j],
            mean_diff=mean_diff,
            p_value_adjusted=_round(p_adj),
            significant=p_adj < alpha,
        ))
    return pairs


def _tukey_hsd_pairs(
    groups: list[list[float]],
    conditions: list[str],
    alpha: float = 0.05,
) -> list[PostHocPairResult]:
    from itertools import combinations

    result = tukey_hsd(*groups)
    pair_indices = list(combinations(range(len(groups)), 2))
    pairs: list[PostHocPairResult] = []
    for i, j in pair_indices:
        p_adj = float(result.pvalue[i, j])
        mean_diff = _round(mean(groups[j]) - mean(groups[i]))
        pairs.append(PostHocPairResult(
            condition_a=conditions[i],
            condition_b=conditions[j],
            mean_diff=mean_diff,
            p_value_adjusted=_round(p_adj),
            significant=p_adj < alpha,
        ))
    return pairs


def _post_hoc_for_metric(
    *,
    metric: str,
    omnibus_result: StatisticalTestResult,
    values_by_condition: dict[str, list[float]],
    conditions: list[str],
) -> PostHocResult:
    role = _role_for_metric(metric)
    base = {"metric": metric, "label": METRIC_LABELS[metric], "role": role}

    if omnibus_result.test not in ("one_way_anova", "kruskal_wallis"):
        return PostHocResult(**base, status="not_applicable", note="仅三条件全局检验有意义时才执行事后检验")

    if omnibus_result.status != "ok":
        return PostHocResult(**base, status="not_applicable", note="全局检验未能计算，跳过事后检验")

    if omnibus_result.p_value is None or omnibus_result.p_value >= 0.05:
        return PostHocResult(
            **base,
            status="not_applicable",
            note=f"全局检验 p={omnibus_result.p_value}，未达显著水平（≥ 0.05），无需事后检验",
        )

    groups = [values_by_condition[c] for c in conditions]
    if any(len(g) < 2 for g in groups):
        return PostHocResult(**base, status="insufficient_data", note="至少每个条件需要 2 个样本")

    if omnibus_result.test == "one_way_anova":
        if tukey_hsd is None:
            return PostHocResult(**base, status="dependency_missing", note="缺少 scipy，无法执行 Tukey HSD")
        try:
            pairs = _tukey_hsd_pairs(groups, conditions)
            return PostHocResult(**base, method="tukey_hsd", pairs=pairs, status="ok", note="Tukey HSD 事后检验，p 值已校正")
        except Exception as exc:
            return PostHocResult(**base, status="calculation_error", note=f"Tukey HSD 计算错误：{exc}")

    # kruskal_wallis → Dunn + Bonferroni
    if _scipy_norm is None:
        return PostHocResult(**base, status="dependency_missing", note="缺少 scipy，无法执行 Dunn test")
    try:
        pairs = _dunn_bonferroni_pairs(groups, conditions)
        return PostHocResult(**base, method="dunn_bonferroni", pairs=pairs, status="ok", note="Dunn test + Bonferroni 校正事后检验")
    except Exception as exc:
        return PostHocResult(**base, status="calculation_error", note=f"Dunn test 计算错误：{exc}")


def _generate_task_score_charts(
    observations: list["TaskScoreObservation"],
    conditions: list[str],
    statistical_tests: list["StatisticalTestResult"],
) -> dict[str, str]:
    if not _CHARTS_AVAILABLE:
        return {}
    try:
        p_by_metric = {t.metric: t.p_value for t in statistical_tests}
        plot_metrics = [
            ("gs",            "GS 小组最终分",             "Score (lower = better)"),
            ("weak_synergy",  "弱协同值 (AIS − GS)",       "Synergy Score"),
            ("strong_synergy","强协同值 (Best IS − GS)",    "Synergy Score"),
        ]
        fig, axes = plt.subplots(1, 3, figsize=(13, 5))
        fig.patch.set_facecolor("white")
        for ax, (metric, title, ylabel) in zip(axes, plot_metrics):
            data_by_condition = {
                c: [getattr(obs, metric) for obs in observations if obs.condition == c]
                for c in conditions
            }
            draw_boxplot(
                ax=ax,
                data_by_condition=data_by_condition,
                conditions=conditions,
                title=title,
                ylabel=ylabel,
                p_value=p_by_metric.get(metric),
            )
        fig.tight_layout(pad=2.0)
        return {"box_plots": fig_to_base64(fig)}
    except Exception:
        return {}


def _value_from_result(result_json: dict[str, Any], metric: str) -> float:
    value = result_json.get(metric)
    if value is None:
        raise ValueError(f"result_json 缺少指标: {metric}")
    return float(value)


def observation_from_entry(row: dict[str, Any]) -> TaskScoreObservation:
    result_json = row.get("result_json")
    if not isinstance(result_json, dict):
        raise ValueError("result_json 必须是对象")

    return TaskScoreObservation(
        entry_id=str(row["id"]),
        group_id=str(row["group_id"]),
        task_id=str(row["task_id"]),
        condition=str(row["condition"]),
        gs=_value_from_result(result_json, "gs"),
        ais=_value_from_result(result_json, "ais"),
        best_is=_value_from_result(result_json, "best_is"),
        weak_synergy=_value_from_result(result_json, "weak_synergy"),
        strong_synergy=_value_from_result(result_json, "strong_synergy"),
    )


def build_task_score_analysis(
    *,
    mode: AnalysisMode,
    task_id: TaskFilter,
    rows: list[dict[str, Any]],
) -> TaskScoreAnalysisResult:
    conditions = CONDITIONS_BY_MODE[mode]
    observations = [
        observation_from_entry(row)
        for row in rows
        if row.get("condition") in conditions
        and (task_id == "all" or row.get("task_id") == task_id)
        and row.get("result_json")
    ]

    entries_by_condition = {condition: 0 for condition in conditions}
    for observation in observations:
        entries_by_condition[observation.condition] += 1

    values_by_metric_condition: dict[str, dict[str, list[float]]] = {
        metric: defaultdict(list) for metric in ALL_METRICS
    }
    for observation in observations:
        for metric in ALL_METRICS:
            values_by_metric_condition[metric][observation.condition].append(float(getattr(observation, metric)))

    summaries: list[MetricSummary] = []
    for metric in ALL_METRICS:
        summaries.append(
            MetricSummary(
                metric=metric,
                label=METRIC_LABELS[metric],
                role=_role_for_metric(metric),
                conditions=[
                    _stats_for(values_by_metric_condition[metric][condition], condition)
                    for condition in conditions
                ],
            )
        )

    normality = [
        _normality_for(
            metric=metric,
            condition=condition,
            values=values_by_metric_condition[metric][condition],
        )
        for metric in ALL_METRICS
        for condition in conditions
    ]
    test_recommendations = [
        _recommend_test_for_metric(
            mode=mode,
            metric=metric,
            conditions=conditions,
            normality_results=normality,
        )
        for metric in ALL_METRICS
    ]
    recommendation_by_metric = {item.metric: item for item in test_recommendations}
    statistical_tests = [
        _statistical_test_for_metric(
            metric=metric,
            recommendation=recommendation_by_metric[metric],
            values_by_condition=values_by_metric_condition[metric],
        )
        for metric in ALL_METRICS
    ]
    omnibus_by_metric = {item.metric: item for item in statistical_tests}
    post_hoc_tests = [
        _post_hoc_for_metric(
            metric=metric,
            omnibus_result=omnibus_by_metric[metric],
            values_by_condition=values_by_metric_condition[metric],
            conditions=conditions,
        )
        for metric in ALL_METRICS
    ]

    return TaskScoreAnalysisResult(
        mode=mode,
        task_id=task_id,
        conditions=conditions,
        total_entries=len(observations),
        entries_by_condition=entries_by_condition,
        metrics=summaries,
        normality=normality,
        test_recommendations=test_recommendations,
        statistical_tests=statistical_tests,
        post_hoc_tests=post_hoc_tests,
        observations=observations,
        charts=_generate_task_score_charts(observations, conditions, statistical_tests),
    )
