"""CoI Cognitive Presence analysis service.

Computes per-session CoI metrics and runs descriptive / normality /
statistical-test / post-hoc pipeline, mirroring questionnaire_analysis_service.
"""
from __future__ import annotations

import math
from collections import defaultdict
from statistics import mean, median, stdev
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

CONDITIONS_BY_MODE: dict[AnalysisMode, list[str]] = {
    "two_conditions": ["no_assistance", "glasses"],
    "three_conditions": ["no_assistance", "glasses", "app_notification"],
}

COI_METRICS = [
    "te_ratio",
    "ex_ratio",
    "in_ratio",
    "re_ratio",
    "higher_order_ratio",
    "weighted_score",
]

COI_METRIC_LABELS: dict[str, str] = {
    "te_ratio": "Triggering Event 比例",
    "ex_ratio": "Exploration 比例",
    "in_ratio": "Integration 比例",
    "re_ratio": "Resolution 比例",
    "higher_order_ratio": "高阶认知参与比例 (IN+RE)",
    "weighted_score": "认知参与加权得分",
}

CATEGORY_WEIGHTS = {"TE": 1, "EX": 2, "IN": 3, "RE": 4}


# ─────────────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────────────

class ExcludedSession(ApiModel):
    session_id: str
    group_id: str
    group_name: str | None = None
    condition: str
    uncoded_count: int
    total_count: int


class CoiSessionObservation(ApiModel):
    session_id: str
    group_id: str
    condition: str
    te_count: int
    ex_count: int
    in_count: int
    re_count: int
    total_count: int
    te_ratio: float
    ex_ratio: float
    in_ratio: float
    re_ratio: float
    higher_order_ratio: float
    weighted_score: float


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


class CoiAnalysisResult(ApiModel):
    mode: AnalysisMode
    conditions: list[str]
    total_sessions: int
    sessions_by_condition: dict[str, int]
    excluded_sessions: list[ExcludedSession]
    metrics: list[MetricSummary]
    normality: list[NormalityConditionResult]
    statistical_tests: list[StatisticalTestResult]
    post_hoc_tests: list[PostHocResult]
    observations: list[CoiSessionObservation]


# ─────────────────────────────────────────────────────────────────
# Statistical helpers (same logic as questionnaire_analysis_service)
# ─────────────────────────────────────────────────────────────────

def _round(value: float) -> float:
    return round(value, 4)


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
# CoI metrics computation
# ─────────────────────────────────────────────────────────────────

def _compute_session_observation(
    session_id: str,
    group_id: str,
    condition: str,
    utterances: list[dict[str, Any]],
) -> CoiSessionObservation:
    counts = {"TE": 0, "EX": 0, "IN": 0, "RE": 0}
    for u in utterances:
        cat = u.get("coi_category")
        if cat in counts:
            counts[cat] += 1

    total = sum(counts.values())
    te, ex, in_, re = counts["TE"], counts["EX"], counts["IN"], counts["RE"]

    te_ratio = te / total if total else 0.0
    ex_ratio = ex / total if total else 0.0
    in_ratio = in_ / total if total else 0.0
    re_ratio = re / total if total else 0.0
    higher_order_ratio = (in_ + re) / total if total else 0.0
    weighted_score = (te * 1 + ex * 2 + in_ * 3 + re * 4) / total if total else 0.0

    return CoiSessionObservation(
        session_id=session_id,
        group_id=group_id,
        condition=condition,
        te_count=te,
        ex_count=ex,
        in_count=in_,
        re_count=re,
        total_count=total,
        te_ratio=_round(te_ratio),
        ex_ratio=_round(ex_ratio),
        in_ratio=_round(in_ratio),
        re_ratio=_round(re_ratio),
        higher_order_ratio=_round(higher_order_ratio),
        weighted_score=_round(weighted_score),
    )


# ─────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────

def build_coi_analysis(
    *,
    mode: AnalysisMode,
    rows: list[dict[str, Any]],
) -> CoiAnalysisResult:
    """Build CoI analysis from raw DB rows.

    Each row must contain: session_id, group_id, condition, coi_category (nullable),
    group_name (optional).
    """
    conditions = CONDITIONS_BY_MODE[mode]

    # Group utterances by session, filter to selected conditions
    sessions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    session_meta: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("condition") not in conditions:
            continue
        sid = str(row["session_id"])
        sessions[sid].append(row)
        if sid not in session_meta:
            session_meta[sid] = {
                "group_id": str(row["group_id"]),
                "condition": str(row["condition"]),
                "group_name": row.get("group_name"),
            }

    observations: list[CoiSessionObservation] = []
    excluded_sessions: list[ExcludedSession] = []

    for sid, utterances in sessions.items():
        meta = session_meta[sid]
        uncoded = [u for u in utterances if u.get("coi_category") is None]
        if uncoded:
            excluded_sessions.append(ExcludedSession(
                session_id=sid,
                group_id=meta["group_id"],
                group_name=meta.get("group_name"),
                condition=meta["condition"],
                uncoded_count=len(uncoded),
                total_count=len(utterances),
            ))
            continue
        if not utterances:
            continue
        obs = _compute_session_observation(sid, meta["group_id"], meta["condition"], utterances)
        observations.append(obs)

    sessions_by_condition = {c: 0 for c in conditions}
    for obs in observations:
        sessions_by_condition[obs.condition] += 1

    # Build per-metric per-condition value lists
    values_by_metric_condition: dict[str, dict[str, list[float]]] = {
        m: defaultdict(list) for m in COI_METRICS
    }
    for obs in observations:
        for m in COI_METRICS:
            values_by_metric_condition[m][obs.condition].append(getattr(obs, m))

    # Descriptive stats
    summaries = [
        MetricSummary(
            metric=m,
            label=COI_METRIC_LABELS[m],
            conditions=[_stats_for(values_by_metric_condition[m][c], c) for c in conditions],
        )
        for m in COI_METRICS
    ]

    # Normality
    normality = [
        _normality_for(
            metric=m,
            label=COI_METRIC_LABELS[m],
            condition=c,
            values=values_by_metric_condition[m][c],
        )
        for m in COI_METRICS
        for c in conditions
    ]

    # Statistical tests
    test_recommendations = [
        _recommend_test(
            mode=mode, metric=m, label=COI_METRIC_LABELS[m],
            conditions=conditions, normality_results=normality,
        )
        for m in COI_METRICS
    ]
    rec_by_metric = {r.metric: r for r in test_recommendations}

    statistical_tests = [
        _run_statistical_test(
            metric=m, label=COI_METRIC_LABELS[m],
            recommendation=rec_by_metric[m],
            values_by_condition=values_by_metric_condition[m],
        )
        for m in COI_METRICS
    ]
    omnibus_by_metric = {r.metric: r for r in statistical_tests}

    post_hoc_tests = [
        _run_post_hoc(
            metric=m, label=COI_METRIC_LABELS[m],
            omnibus=omnibus_by_metric[m],
            values_by_condition=values_by_metric_condition[m],
            conditions=conditions,
        )
        for m in COI_METRICS
    ]

    return CoiAnalysisResult(
        mode=mode,
        conditions=conditions,
        total_sessions=len(observations),
        sessions_by_condition=sessions_by_condition,
        excluded_sessions=excluded_sessions,
        metrics=summaries,
        normality=normality,
        statistical_tests=statistical_tests,
        post_hoc_tests=post_hoc_tests,
        observations=observations,
    )
