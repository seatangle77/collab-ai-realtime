"""SRCC / PCS questionnaire analysis service.

Supports two-condition and three-condition between-group comparisons.
Adds Cronbach's alpha reliability check on top of the standard descriptive /
normality / statistical-test / post-hoc pipeline used by task_score_analysis.
"""
from __future__ import annotations

import math
from collections import defaultdict
from statistics import mean, median, stdev, variance
from typing import Any, Literal

from ..api_model import ApiModel

try:
    from scipy.stats import f_oneway, kruskal, mannwhitneyu, norm as _scipy_norm, shapiro, ttest_ind, tukey_hsd
except ImportError:  # pragma: no cover
    f_oneway = None
    kruskal = None
    mannwhitneyu = None
    _scipy_norm = None
    shapiro = None
    ttest_ind = None
    tukey_hsd = None


# ─────────────────────────────────────────────────────────────────
# Type aliases
# ─────────────────────────────────────────────────────────────────

AnalysisMode = Literal["two_conditions", "three_conditions"]
ScaleKind = Literal["srcc", "pcs"]
NormalityStatus = Literal["ok", "insufficient_n", "constant_values", "dependency_missing"]
RecommendedTest = Literal[
    "independent_samples_t_test",
    "mann_whitney_u",
    "one_way_anova",
    "kruskal_wallis",
    "insufficient_data",
]
StatisticalTestStatus = Literal["ok", "insufficient_data", "dependency_missing", "calculation_error"]
PostHocStatus = Literal["ok", "not_applicable", "insufficient_data", "dependency_missing", "calculation_error"]
PostHocMethod = Literal["tukey_hsd", "dunn_bonferroni"]
CronbachStatus = Literal["ok", "insufficient_n", "insufficient_items", "constant_values"]

CONDITIONS_BY_MODE: dict[AnalysisMode, list[str]] = {
    "two_conditions": ["no_assistance", "glasses"],
    "three_conditions": ["no_assistance", "glasses", "app_notification"],
}

# ─────────────────────────────────────────────────────────────────
# Scale metadata
# ─────────────────────────────────────────────────────────────────

SRCC_METRICS = ["clarification_avg", "elaboration_avg", "refuting_avg", "summarization_avg", "total_avg"]
SRCC_METRIC_LABELS: dict[str, str] = {
    "clarification_avg": "澄清与解决",
    "elaboration_avg": "阐述与拓展",
    "refuting_avg": "反驳与质疑",
    "summarization_avg": "总结与整合",
    "total_avg": "SRCC 总均分",
}
# item ids (from questionnaire.py) per metric / dimension
SRCC_DIM_ITEMS: dict[str, list[str]] = {
    "clarification_avg": ["q1", "q2", "q3", "q4", "q5", "q6"],
    "elaboration_avg": ["q7", "q8", "q9", "q10", "q11"],
    "refuting_avg": ["q12", "q13"],
    "summarization_avg": ["q14", "q15"],
    "total_avg": ["q1", "q2", "q3", "q4", "q5", "q6", "q7", "q8", "q9", "q10", "q11", "q12", "q13", "q14", "q15"],
}

PCS_METRICS = ["belonging_avg", "morale_avg", "total_avg"]
PCS_METRIC_LABELS: dict[str, str] = {
    "belonging_avg": "归属感",
    "morale_avg": "士气 / 积极情感",
    "total_avg": "PCS 总均分",
}
PCS_DIM_ITEMS: dict[str, list[str]] = {
    "belonging_avg": ["q1", "q3", "q5"],
    "morale_avg": ["q2", "q4", "q6"],
    "total_avg": ["q1", "q2", "q3", "q4", "q5", "q6"],
}


def _scale_metrics(scale: ScaleKind) -> list[str]:
    return SRCC_METRICS if scale == "srcc" else PCS_METRICS


def _scale_labels(scale: ScaleKind) -> dict[str, str]:
    return SRCC_METRIC_LABELS if scale == "srcc" else PCS_METRIC_LABELS


def _scale_dim_items(scale: ScaleKind) -> dict[str, list[str]]:
    return SRCC_DIM_ITEMS if scale == "srcc" else PCS_DIM_ITEMS


# ─────────────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────────────

class QuestionnaireObservation(ApiModel):
    user_id: str
    group_id: str
    condition: str
    # dimension averages extracted from *_result JSONB
    metric_values: dict[str, float | None]
    # raw item scores from *_responses JSONB (for Cronbach's alpha)
    item_responses: dict[str, int | None]


class MetricConditionStats(ApiModel):
    condition: str
    n: int
    mean: float | None = None
    sd: float | None = None
    median: float | None = None
    min: float | None = None
    max: float | None = None


class MetricSummary(ApiModel):
    metric: str
    label: str
    conditions: list[MetricConditionStats]


class CronbachAlphaResult(ApiModel):
    metric: str
    label: str
    n_items: int
    n_obs: int
    alpha: float | None = None
    status: CronbachStatus
    note: str


class NormalityConditionResult(ApiModel):
    metric: str
    label: str
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
    recommended_test: RecommendedTest
    normality_assumption_met: bool | None
    conditions: list[str]
    note: str


class StatisticalTestResult(ApiModel):
    metric: str
    label: str
    test: RecommendedTest
    statistic_name: str | None = None
    statistic: float | None = None
    p_value: float | None = None
    effect_size_name: str | None = None
    effect_size: float | None = None
    status: StatisticalTestStatus
    note: str


class PostHocPairResult(ApiModel):
    condition_a: str
    condition_b: str
    mean_diff: float | None = None
    p_value_adjusted: float | None = None
    significant: bool | None = None
    alpha: float = 0.05


class PostHocResult(ApiModel):
    metric: str
    label: str
    method: PostHocMethod | None = None
    pairs: list[PostHocPairResult] = []
    status: PostHocStatus
    note: str


class QuestionnaireAnalysisResult(ApiModel):
    scale: ScaleKind
    mode: AnalysisMode
    conditions: list[str]
    total_entries: int
    entries_by_condition: dict[str, int]
    metrics: list[MetricSummary]
    reliability: list[CronbachAlphaResult]
    normality: list[NormalityConditionResult]
    test_recommendations: list[StatisticalTestRecommendation]
    statistical_tests: list[StatisticalTestResult]
    post_hoc_tests: list[PostHocResult]
    observations: list[QuestionnaireObservation]


# ─────────────────────────────────────────────────────────────────
# Statistical helpers
# ─────────────────────────────────────────────────────────────────

def _round(value: float) -> float:
    return round(value, 3)


def _stats_for(values: list[float], condition: str) -> MetricConditionStats:
    if not values:
        return MetricConditionStats(condition=condition, n=0)
    return MetricConditionStats(
        condition=condition,
        n=len(values),
        mean=_round(mean(values)),
        sd=_round(stdev(values)) if len(values) > 1 else 0.0,
        median=_round(median(values)),
        min=_round(min(values)),
        max=_round(max(values)),
    )


def _cronbach_alpha(item_matrix: list[list[float]]) -> CronbachStatus | float:
    """Return alpha float on success, or a CronbachStatus string on failure."""
    if not item_matrix:
        return "insufficient_n"
    n_obs = len(item_matrix)
    n_items = len(item_matrix[0])
    if n_obs < 2:
        return "insufficient_n"
    if n_items < 2:
        return "insufficient_items"

    item_variances = []
    for i in range(n_items):
        col = [row[i] for row in item_matrix]
        if len(set(col)) <= 1:
            continue  # constant item – skip but don't fail
        item_variances.append(variance(col))

    total_scores = [sum(row) for row in item_matrix]
    if len(set(total_scores)) <= 1:
        return "constant_values"

    total_var = variance(total_scores)
    if total_var == 0:
        return "constant_values"

    k = n_items
    alpha = (k / (k - 1)) * (1 - sum(item_variances) / total_var)
    return round(alpha, 4)


def _cronbach_result(
    *,
    metric: str,
    label: str,
    item_ids: list[str],
    observations: list[QuestionnaireObservation],
) -> CronbachAlphaResult:
    # Build item matrix: only include participants who answered ALL items in this dim
    matrix: list[list[float]] = []
    for obs in observations:
        row = [obs.item_responses.get(item_id) for item_id in item_ids]
        if any(v is None for v in row):
            continue
        matrix.append([float(v) for v in row])  # type: ignore[arg-type]

    n_items = len(item_ids)
    base = {"metric": metric, "label": label, "n_items": n_items, "n_obs": len(matrix)}

    result = _cronbach_alpha(matrix)
    if result == "insufficient_n":
        return CronbachAlphaResult(**base, status="insufficient_n", note="至少需要 2 名参与者才能计算 Cronbach's alpha")
    if result == "insufficient_items":
        return CronbachAlphaResult(**base, status="insufficient_items", note="至少需要 2 个题项才能计算 Cronbach's alpha")
    if result == "constant_values":
        return CronbachAlphaResult(**base, status="constant_values", note="所有参与者总分相同，无法计算内部一致性")
    return CronbachAlphaResult(
        **base,
        alpha=float(result),  # type: ignore[arg-type]
        status="ok",
        note="α ≥ 0.7 通常视为可接受的内部一致性",
    )


def _normality_for(
    *,
    metric: str,
    label: str,
    condition: str,
    values: list[float],
    alpha: float = 0.05,
) -> NormalityConditionResult:
    base = {"metric": metric, "label": label, "condition": condition, "n": len(values), "alpha": alpha}
    if shapiro is None:
        return NormalityConditionResult(**base, status="dependency_missing", note="缺少 scipy，无法执行 Shapiro-Wilk 正态性检验")
    if len(values) < 3:
        return NormalityConditionResult(**base, status="insufficient_n", note="Shapiro-Wilk 至少需要 3 个样本")
    if len(set(values)) <= 1:
        return NormalityConditionResult(**base, status="constant_values", note="所有观测值相同，无法稳定判断正态性")
    statistic, p_value = shapiro(values)
    p_float = float(p_value)
    return NormalityConditionResult(
        **base,
        statistic=_round(float(statistic)),
        p_value=_round(p_float),
        is_normal=p_float >= alpha,
        status="ok",
        note="p >= 0.05 时按近似正态处理" if p_float >= alpha else "p < 0.05，按偏离正态处理",
    )


def _recommend_test(
    *,
    mode: AnalysisMode,
    metric: str,
    label: str,
    conditions: list[str],
    normality_results: list[NormalityConditionResult],
) -> StatisticalTestRecommendation:
    metric_normality = [r for r in normality_results if r.metric == metric and r.condition in conditions]
    if any(r.n < 2 for r in metric_normality):
        return StatisticalTestRecommendation(
            metric=metric, label=label, recommended_test="insufficient_data",
            normality_assumption_met=None, conditions=conditions,
            note="至少每个条件需要 2 个样本才能进行组间比较",
        )
    all_normal = all(r.status == "ok" and r.is_normal is True for r in metric_normality)
    all_checked = all(r.status == "ok" for r in metric_normality)
    if mode == "two_conditions":
        if all_normal:
            return StatisticalTestRecommendation(
                metric=metric, label=label, recommended_test="independent_samples_t_test",
                normality_assumption_met=True, conditions=conditions,
                note="两个条件均通过 Shapiro-Wilk，建议使用 independent-samples t-test",
            )
        return StatisticalTestRecommendation(
            metric=metric, label=label, recommended_test="mann_whitney_u",
            normality_assumption_met=False if all_checked else None, conditions=conditions,
            note="至少一个条件未通过或无法完成正态性检查，建议使用 Mann-Whitney U test",
        )
    if all_normal:
        return StatisticalTestRecommendation(
            metric=metric, label=label, recommended_test="one_way_anova",
            normality_assumption_met=True, conditions=conditions,
            note="三个条件均通过 Shapiro-Wilk，建议使用 one-way ANOVA",
        )
    return StatisticalTestRecommendation(
        metric=metric, label=label, recommended_test="kruskal_wallis",
        normality_assumption_met=False if all_checked else None, conditions=conditions,
        note="至少一个条件未通过或无法完成正态性检查，建议使用 Kruskal-Wallis",
    )


def _cohens_d(a: list[float], b: list[float]) -> float | None:
    if len(a) < 2 or len(b) < 2:
        return None
    pooled_var = ((len(a) - 1) * stdev(a) ** 2 + (len(b) - 1) * stdev(b) ** 2) / (len(a) + len(b) - 2)
    if pooled_var <= 0:
        return None
    return (mean(b) - mean(a)) / math.sqrt(pooled_var)


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


def _run_statistical_test(
    *,
    metric: str,
    label: str,
    recommendation: StatisticalTestRecommendation,
    values_by_condition: dict[str, list[float]],
) -> StatisticalTestResult:
    base = {"metric": metric, "label": label, "test": recommendation.recommended_test}
    groups = [values_by_condition[c] for c in recommendation.conditions]
    if recommendation.recommended_test == "insufficient_data" or any(len(g) < 2 for g in groups):
        return StatisticalTestResult(**base, status="insufficient_data", note="至少每个条件需要 2 个样本才能计算推断统计")
    if any(len(set(g)) <= 1 for g in groups):
        return StatisticalTestResult(**base, status="calculation_error", note="至少一个条件内数值恒定，统计检验结果不稳定，已跳过")

    if recommendation.recommended_test == "independent_samples_t_test":
        if ttest_ind is None:
            return StatisticalTestResult(**base, status="dependency_missing", note="缺少 scipy，无法执行 t-test")
        stat, p = ttest_ind(groups[0], groups[1], equal_var=False)
        d = _cohens_d(groups[0], groups[1])
        return StatisticalTestResult(
            **base, statistic_name="t", statistic=_round(float(stat)), p_value=_round(float(p)),
            effect_size_name="Cohen's d", effect_size=_round(d) if d is not None else None,
            status="ok", note="Welch independent-samples t-test；Cohen's d 正值表示第二条件均值更高",
        )
    if recommendation.recommended_test == "mann_whitney_u":
        if mannwhitneyu is None:
            return StatisticalTestResult(**base, status="dependency_missing", note="缺少 scipy，无法执行 Mann-Whitney U")
        stat, p = mannwhitneyu(groups[0], groups[1], alternative="two-sided")
        n1, n2 = len(groups[0]), len(groups[1])
        r = (2 * float(stat) / (n1 * n2)) - 1
        return StatisticalTestResult(
            **base, statistic_name="U", statistic=_round(float(stat)), p_value=_round(float(p)),
            effect_size_name="rank-biserial r", effect_size=_round(r),
            status="ok", note="rank-biserial r 方向为第一条件相对第二条件",
        )
    if recommendation.recommended_test == "one_way_anova":
        if f_oneway is None:
            return StatisticalTestResult(**base, status="dependency_missing", note="缺少 scipy，无法执行 one-way ANOVA")
        stat, p = f_oneway(*groups)
        eta = _eta_squared(groups)
        return StatisticalTestResult(
            **base, statistic_name="F", statistic=_round(float(stat)), p_value=_round(float(p)),
            effect_size_name="eta squared", effect_size=_round(eta) if eta is not None else None,
            status="ok", note="若 p < 0.05，后续可补 Tukey HSD 事后检验",
        )
    if recommendation.recommended_test == "kruskal_wallis":
        if kruskal is None:
            return StatisticalTestResult(**base, status="dependency_missing", note="缺少 scipy，无法执行 Kruskal-Wallis")
        stat, p = kruskal(*groups)
        h = float(stat)
        n_total = sum(len(g) for g in groups)
        eps = _epsilon_squared(h, len(groups), n_total)
        return StatisticalTestResult(
            **base, statistic_name="H", statistic=_round(h), p_value=_round(float(p)),
            effect_size_name="epsilon squared", effect_size=_round(eps) if eps is not None else None,
            status="ok", note="若 p < 0.05，后续可补 Dunn + Bonferroni 事后检验",
        )
    return StatisticalTestResult(**base, status="calculation_error", note="未知检验类型")


def _dunn_bonferroni(groups: list[list[float]], conditions: list[str], alpha: float = 0.05) -> list[PostHocPairResult]:
    from itertools import combinations
    all_vals = [v for g in groups for v in g]
    n_total = len(all_vals)
    sorted_with_idx = sorted(enumerate(all_vals), key=lambda x: x[1])
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

    group_mean_ranks: list[float] = []
    idx = 0
    for g in groups:
        group_mean_ranks.append(sum(ranks[idx + k] for k in range(len(g))) / len(g))
        idx += len(g)

    pairs_idx = list(combinations(range(len(groups)), 2))
    m = len(pairs_idx)
    pairs: list[PostHocPairResult] = []
    for a, b in pairs_idx:
        n_a, n_b = len(groups[a]), len(groups[b])
        se = math.sqrt((n_total * (n_total + 1) / 12) * (1 / n_a + 1 / n_b))
        if se == 0 or _scipy_norm is None:
            pairs.append(PostHocPairResult(condition_a=conditions[a], condition_b=conditions[b]))
            continue
        z = abs(group_mean_ranks[a] - group_mean_ranks[b]) / se
        p_raw = 2 * (1 - _scipy_norm.cdf(z))
        p_adj = min(1.0, p_raw * m)
        pairs.append(PostHocPairResult(
            condition_a=conditions[a], condition_b=conditions[b],
            mean_diff=_round(mean(groups[b]) - mean(groups[a])),
            p_value_adjusted=_round(p_adj), significant=p_adj < alpha,
        ))
    return pairs


def _tukey_pairs(groups: list[list[float]], conditions: list[str], alpha: float = 0.05) -> list[PostHocPairResult]:
    from itertools import combinations
    result = tukey_hsd(*groups)
    pairs: list[PostHocPairResult] = []
    for a, b in combinations(range(len(groups)), 2):
        p_adj = float(result.pvalue[a, b])
        pairs.append(PostHocPairResult(
            condition_a=conditions[a], condition_b=conditions[b],
            mean_diff=_round(mean(groups[b]) - mean(groups[a])),
            p_value_adjusted=_round(p_adj), significant=p_adj < alpha,
        ))
    return pairs


def _run_post_hoc(
    *,
    metric: str,
    label: str,
    omnibus: StatisticalTestResult,
    values_by_condition: dict[str, list[float]],
    conditions: list[str],
) -> PostHocResult:
    base = {"metric": metric, "label": label}
    if omnibus.test not in ("one_way_anova", "kruskal_wallis"):
        return PostHocResult(**base, status="not_applicable", note="仅三条件全局检验有意义时才执行事后检验")
    if omnibus.status != "ok":
        return PostHocResult(**base, status="not_applicable", note="全局检验未能计算，跳过事后检验")
    if omnibus.p_value is None or omnibus.p_value >= 0.05:
        return PostHocResult(**base, status="not_applicable",
                             note=f"全局检验 p={omnibus.p_value}，未达显著水平（≥ 0.05），无需事后检验")
    groups = [values_by_condition[c] for c in conditions]
    if any(len(g) < 2 for g in groups):
        return PostHocResult(**base, status="insufficient_data", note="至少每个条件需要 2 个样本")
    if omnibus.test == "one_way_anova":
        if tukey_hsd is None:
            return PostHocResult(**base, status="dependency_missing", note="缺少 scipy，无法执行 Tukey HSD")
        try:
            return PostHocResult(**base, method="tukey_hsd", pairs=_tukey_pairs(groups, conditions),
                                 status="ok", note="Tukey HSD 事后检验，p 值已校正")
        except Exception as exc:
            return PostHocResult(**base, status="calculation_error", note=f"Tukey HSD 计算错误：{exc}")
    if _scipy_norm is None:
        return PostHocResult(**base, status="dependency_missing", note="缺少 scipy，无法执行 Dunn test")
    try:
        return PostHocResult(**base, method="dunn_bonferroni", pairs=_dunn_bonferroni(groups, conditions),
                             status="ok", note="Dunn test + Bonferroni 校正事后检验")
    except Exception as exc:
        return PostHocResult(**base, status="calculation_error", note=f"Dunn test 计算错误：{exc}")


# ─────────────────────────────────────────────────────────────────
# Build observation from DB row
# ─────────────────────────────────────────────────────────────────

def observation_from_row(row: dict[str, Any], scale: ScaleKind) -> QuestionnaireObservation | None:
    result_key = "srcc_result" if scale == "srcc" else "pcs_result"
    response_key = "srcc_responses" if scale == "srcc" else "pcs_responses"
    metrics = _scale_metrics(scale)

    result_json = row.get(result_key)
    if not isinstance(result_json, dict):
        return None

    metric_values: dict[str, float | None] = {}
    for m in metrics:
        val = result_json.get(m)
        metric_values[m] = float(val) if val is not None else None

    responses_json = row.get(response_key) or {}
    item_responses: dict[str, int | None] = {}
    all_item_ids = _scale_dim_items(scale)["total_avg"]
    for item_id in all_item_ids:
        v = responses_json.get(item_id)
        item_responses[item_id] = int(v) if v is not None else None

    return QuestionnaireObservation(
        user_id=str(row["user_id"]),
        group_id=str(row["group_id"]),
        condition=str(row["condition"]),
        metric_values=metric_values,
        item_responses=item_responses,
    )


# ─────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────

def build_questionnaire_analysis(
    *,
    scale: ScaleKind,
    mode: AnalysisMode,
    rows: list[dict[str, Any]],
) -> QuestionnaireAnalysisResult:
    conditions = CONDITIONS_BY_MODE[mode]
    metrics = _scale_metrics(scale)
    labels = _scale_labels(scale)
    dim_items = _scale_dim_items(scale)

    observations: list[QuestionnaireObservation] = []
    for row in rows:
        if row.get("condition") not in conditions:
            continue
        obs = observation_from_row(row, scale)
        if obs is not None:
            observations.append(obs)

    entries_by_condition = {c: 0 for c in conditions}
    for obs in observations:
        entries_by_condition[obs.condition] += 1

    # values per metric per condition (skip None metric values)
    values_by_metric_condition: dict[str, dict[str, list[float]]] = {
        m: defaultdict(list) for m in metrics
    }
    for obs in observations:
        for m in metrics:
            v = obs.metric_values.get(m)
            if v is not None:
                values_by_metric_condition[m][obs.condition].append(v)

    # Step 1: descriptive stats
    summaries = [
        MetricSummary(
            metric=m,
            label=labels[m],
            conditions=[_stats_for(values_by_metric_condition[m][c], c) for c in conditions],
        )
        for m in metrics
    ]

    # Step 2: Cronbach's alpha (computed across all observations regardless of condition)
    reliability = [
        _cronbach_result(
            metric=m,
            label=labels[m],
            item_ids=dim_items[m],
            observations=observations,
        )
        for m in metrics
    ]

    # Step 3 + 4: normality
    normality = [
        _normality_for(
            metric=m,
            label=labels[m],
            condition=c,
            values=values_by_metric_condition[m][c],
        )
        for m in metrics
        for c in conditions
    ]

    # Step 5: recommend and run tests
    test_recommendations = [
        _recommend_test(
            mode=mode, metric=m, label=labels[m],
            conditions=conditions, normality_results=normality,
        )
        for m in metrics
    ]
    rec_by_metric = {r.metric: r for r in test_recommendations}

    statistical_tests = [
        _run_statistical_test(
            metric=m, label=labels[m],
            recommendation=rec_by_metric[m],
            values_by_condition=values_by_metric_condition[m],
        )
        for m in metrics
    ]
    omnibus_by_metric = {r.metric: r for r in statistical_tests}

    post_hoc_tests = [
        _run_post_hoc(
            metric=m, label=labels[m],
            omnibus=omnibus_by_metric[m],
            values_by_condition=values_by_metric_condition[m],
            conditions=conditions,
        )
        for m in metrics
    ]

    return QuestionnaireAnalysisResult(
        scale=scale,
        mode=mode,
        conditions=conditions,
        total_entries=len(observations),
        entries_by_condition=entries_by_condition,
        metrics=summaries,
        reliability=reliability,
        normality=normality,
        test_recommendations=test_recommendations,
        statistical_tests=statistical_tests,
        post_hoc_tests=post_hoc_tests,
        observations=observations,
    )
