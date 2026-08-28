"""Cluster-aware questionnaire analysis without modifying questionnaire data.

The service keeps the existing individual-level analysis as a baseline, then
adds two sensitivity analyses: equal-weight group means and a random-intercept
mixed model with participants nested in groups.
"""
from __future__ import annotations

import math
import warnings
from collections import defaultdict
from statistics import mean, stdev
from typing import Any, Literal

import numpy as np
from scipy.stats import chi2, f_oneway, norm, t as student_t, ttest_ind

from ..api_model import ApiModel
from .questionnaire_analysis_service import (
    AnalysisMode,
    MetricConditionStats,
    QuestionnaireAnalysisResult,
    QuestionnaireObservation,
    ScaleKind,
    _scale_labels,
    _scale_metrics,
    build_questionnaire_analysis,
    observation_from_row,
)
from .stats_utils import _cohens_d, _eta_squared, _stats_for, benjamini_hochberg

try:
    from statsmodels.regression.mixed_linear_model import MixedLM
    from statsmodels.stats.oneway import anova_oneway
except ImportError:  # pragma: no cover - surfaced as a result status
    MixedLM = None
    anova_oneway = None


AnalysisStatus = Literal[
    "ok", "insufficient_data", "constant_values", "dependency_missing", "calculation_error"
]


class ConditionSampleSummary(ApiModel):
    condition: str
    participant_count: int
    group_count: int
    min_group_size: int | None = None
    max_group_size: int | None = None
    mean_group_size: float | None = None


class GroupMeanObservation(ApiModel):
    metric: str
    group_id: str
    condition: str
    participant_count: int
    value: float


class PairwiseContrast(ApiModel):
    condition_a: str
    condition_b: str
    estimate: float | None = None
    standard_error: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    p_value: float | None = None
    p_value_adjusted: float | None = None
    significant: bool | None = None


class HierarchicalTestResult(ApiModel):
    metric: str
    label: str
    method: str
    statistic_name: str | None = None
    statistic: float | None = None
    p_value: float | None = None
    p_value_adjusted: float | None = None
    effect_size_name: str | None = None
    effect_size: float | None = None
    status: AnalysisStatus
    note: str
    pairwise: list[PairwiseContrast] = []


class GroupMeanMetricResult(ApiModel):
    metric: str
    label: str
    conditions: list[MetricConditionStats]
    observations: list[GroupMeanObservation]
    test: HierarchicalTestResult


class ModelEstimatedMean(ApiModel):
    condition: str
    estimate: float
    standard_error: float
    ci_low: float
    ci_high: float


class MixedModelMetricResult(ApiModel):
    metric: str
    label: str
    status: AnalysisStatus
    participant_count: int
    group_count: int
    converged: bool | None = None
    fixed_effect_test: HierarchicalTestResult
    estimated_means: list[ModelEstimatedMean] = []
    random_intercept_variance: float | None = None
    residual_variance: float | None = None
    icc: float | None = None
    note: str


class QuestionnaireHierarchicalAnalysisResult(ApiModel):
    scale: ScaleKind
    mode: AnalysisMode
    conditions: list[str]
    participant_count: int
    group_count: int
    sample_summary: list[ConditionSampleSummary]
    individual_analysis: QuestionnaireAnalysisResult
    individual_p_values_adjusted: dict[str, float | None]
    group_mean_metrics: list[GroupMeanMetricResult]
    mixed_model_metrics: list[MixedModelMetricResult]
    warnings: list[str]


def _round(value: float | None, digits: int = 4) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(float(value), digits)


def _holm_adjust(p_values: list[float]) -> list[float]:
    indexed = sorted(enumerate(p_values), key=lambda item: item[1])
    adjusted = [1.0] * len(p_values)
    running = 0.0
    count = len(p_values)
    for rank, (original_index, p_value) in enumerate(indexed):
        running = max(running, min(1.0, p_value * (count - rank)))
        adjusted[original_index] = running
    return adjusted


def _welch_contrast(a: list[float], b: list[float], condition_a: str, condition_b: str) -> PairwiseContrast:
    estimate = mean(b) - mean(a)
    var_a = stdev(a) ** 2
    var_b = stdev(b) ** 2
    se2 = var_a / len(a) + var_b / len(b)
    if se2 <= 0:
        return PairwiseContrast(condition_a=condition_a, condition_b=condition_b, estimate=_round(estimate))
    se = math.sqrt(se2)
    numerator = se2 ** 2
    denominator = (var_a / len(a)) ** 2 / (len(a) - 1) + (var_b / len(b)) ** 2 / (len(b) - 1)
    df = numerator / denominator if denominator > 0 else len(a) + len(b) - 2
    critical = float(student_t.ppf(0.975, df))
    _, p_value = ttest_ind(a, b, equal_var=False)
    return PairwiseContrast(
        condition_a=condition_a,
        condition_b=condition_b,
        estimate=_round(estimate),
        standard_error=_round(se),
        ci_low=_round(estimate - critical * se),
        ci_high=_round(estimate + critical * se),
        p_value=_round(float(p_value)),
    )


def _apply_pairwise_holm(pairs: list[PairwiseContrast]) -> None:
    valid = [(index, pair.p_value) for index, pair in enumerate(pairs) if pair.p_value is not None]
    if not valid:
        return
    adjusted = _holm_adjust([float(p) for _, p in valid])
    for (index, _), p_adjusted in zip(valid, adjusted):
        pairs[index].p_value_adjusted = _round(p_adjusted)
        pairs[index].significant = p_adjusted < 0.05


def _group_mean_analysis(
    observations: list[QuestionnaireObservation],
    metrics: list[str],
    labels: dict[str, str],
    conditions: list[str],
) -> list[GroupMeanMetricResult]:
    values: dict[str, dict[str, dict[str, list[float]]]] = {
        metric: defaultdict(lambda: defaultdict(list)) for metric in metrics
    }
    for observation in observations:
        for metric in metrics:
            value = observation.metric_values.get(metric)
            if value is not None:
                values[metric][observation.condition][observation.group_id].append(value)

    results: list[GroupMeanMetricResult] = []
    for metric in metrics:
        metric_observations: list[GroupMeanObservation] = []
        by_condition: dict[str, list[float]] = {condition: [] for condition in conditions}
        for condition in conditions:
            for group_id, group_values in values[metric][condition].items():
                group_mean = mean(group_values)
                by_condition[condition].append(group_mean)
                metric_observations.append(GroupMeanObservation(
                    metric=metric,
                    group_id=group_id,
                    condition=condition,
                    participant_count=len(group_values),
                    value=round(group_mean, 4),
                ))

        groups = [by_condition[condition] for condition in conditions]
        if any(len(group) < 2 for group in groups):
            test = HierarchicalTestResult(
                metric=metric, label=labels[metric], method="group_mean",
                status="insufficient_data", note="每个实验条件至少需要 2 个小组。",
            )
        elif any(len(set(group)) <= 1 for group in groups):
            test = HierarchicalTestResult(
                metric=metric, label=labels[metric], method="group_mean",
                status="constant_values", note="至少一个条件的小组均值完全相同，无法稳定检验。",
            )
        elif len(conditions) == 2:
            statistic, p_value = ttest_ind(groups[0], groups[1], equal_var=False)
            pair = _welch_contrast(groups[0], groups[1], conditions[0], conditions[1])
            pair.p_value_adjusted = pair.p_value
            pair.significant = pair.p_value is not None and pair.p_value < 0.05
            test = HierarchicalTestResult(
                metric=metric, label=labels[metric], method="Welch t-test on group means",
                statistic_name="t", statistic=_round(float(statistic)), p_value=_round(float(p_value)),
                effect_size_name="Hedges' g", effect_size=_round(_cohens_d(groups[0], groups[1])),
                status="ok", note="每个小组等权；正值表示第二条件更高。", pairwise=[pair],
            )
        else:
            if anova_oneway is not None:
                omnibus = anova_oneway(groups, use_var="unequal")
                statistic, p_value = float(omnibus.statistic), float(omnibus.pvalue)
                method = "Welch ANOVA on group means"
            else:  # pragma: no cover
                statistic, p_value = f_oneway(*groups)
                statistic, p_value = float(statistic), float(p_value)
                method = "One-way ANOVA on group means"
            pairs = [
                _welch_contrast(groups[a], groups[b], conditions[a], conditions[b])
                for a in range(len(conditions)) for b in range(a + 1, len(conditions))
            ]
            _apply_pairwise_holm(pairs)
            test = HierarchicalTestResult(
                metric=metric, label=labels[metric], method=method,
                statistic_name="F", statistic=_round(statistic), p_value=_round(p_value),
                effect_size_name="eta squared", effect_size=_round(_eta_squared(groups)),
                status="ok", note="两两比较使用 Holm 校正。", pairwise=pairs,
            )
        results.append(GroupMeanMetricResult(
            metric=metric,
            label=labels[metric],
            conditions=[_stats_for(by_condition[condition], condition) for condition in conditions],
            observations=metric_observations,
            test=test,
        ))

    adjusted = benjamini_hochberg([item.test.p_value for item in results])
    for item, p_adjusted in zip(results, adjusted):
        item.test.p_value_adjusted = p_adjusted
    return results


def _design_row(condition: str, conditions: list[str]) -> np.ndarray:
    return np.asarray([1.0] + [1.0 if condition == c else 0.0 for c in conditions[1:]], dtype=float)


def _fit_mixed_metric(
    metric: str,
    label: str,
    observations: list[QuestionnaireObservation],
    conditions: list[str],
) -> MixedModelMetricResult:
    usable = [obs for obs in observations if obs.metric_values.get(metric) is not None]
    groups_by_condition = {
        condition: {obs.group_id for obs in usable if obs.condition == condition}
        for condition in conditions
    }
    base_test = dict(metric=metric, label=label, method="random-intercept mixed model")
    if MixedLM is None:
        test = HierarchicalTestResult(**base_test, status="dependency_missing", note="缺少 statsmodels。")
        return MixedModelMetricResult(
            metric=metric, label=label, status="dependency_missing",
            participant_count=len(usable), group_count=len({obs.group_id for obs in usable}),
            fixed_effect_test=test, note="缺少 statsmodels，无法拟合混合效应模型。",
        )
    if any(len(group_ids) < 2 for group_ids in groups_by_condition.values()):
        test = HierarchicalTestResult(**base_test, status="insufficient_data", note="每个条件至少需要 2 个小组。")
        return MixedModelMetricResult(
            metric=metric, label=label, status="insufficient_data",
            participant_count=len(usable), group_count=len({obs.group_id for obs in usable}),
            fixed_effect_test=test, note="每个条件至少需要 2 个小组才能估计小组随机效应。",
        )

    endog = np.asarray([float(obs.metric_values[metric]) for obs in usable], dtype=float)
    exog = np.vstack([_design_row(obs.condition, conditions) for obs in usable])
    group_ids = np.asarray([obs.group_id for obs in usable])
    if len(set(endog.tolist())) <= 1:
        test = HierarchicalTestResult(**base_test, status="constant_values", note="所有个人得分相同。")
        return MixedModelMetricResult(
            metric=metric, label=label, status="constant_values", participant_count=len(usable),
            group_count=len(set(group_ids.tolist())), fixed_effect_test=test, note="所有得分相同。",
        )

    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            full_model = MixedLM(endog, exog, groups=group_ids)
            try:
                fitted = full_model.fit(reml=False, method="lbfgs", disp=False)
            except Exception:
                fitted = full_model.fit(reml=False, method="powell", disp=False)
            null_exog = np.ones((len(endog), 1), dtype=float)
            null_model = MixedLM(endog, null_exog, groups=group_ids)
            try:
                fitted_null = null_model.fit(reml=False, method="lbfgs", disp=False)
            except Exception:
                fitted_null = null_model.fit(reml=False, method="powell", disp=False)

        fixed_count = exog.shape[1]
        beta = np.asarray(fitted.fe_params, dtype=float)
        covariance = np.asarray(fitted.cov_params(), dtype=float)[:fixed_count, :fixed_count]
        estimated_means: list[ModelEstimatedMean] = []
        for condition in conditions:
            vector = _design_row(condition, conditions)
            estimate = float(vector @ beta)
            se = math.sqrt(max(0.0, float(vector @ covariance @ vector)))
            estimated_means.append(ModelEstimatedMean(
                condition=condition, estimate=round(estimate, 4), standard_error=round(se, 4),
                ci_low=round(estimate - 1.96 * se, 4), ci_high=round(estimate + 1.96 * se, 4),
            ))

        pairs: list[PairwiseContrast] = []
        for a in range(len(conditions)):
            for b in range(a + 1, len(conditions)):
                contrast = _design_row(conditions[b], conditions) - _design_row(conditions[a], conditions)
                estimate = float(contrast @ beta)
                se = math.sqrt(max(0.0, float(contrast @ covariance @ contrast)))
                p_value = 2 * float(norm.sf(abs(estimate / se))) if se > 0 else None
                pairs.append(PairwiseContrast(
                    condition_a=conditions[a], condition_b=conditions[b], estimate=_round(estimate),
                    standard_error=_round(se), ci_low=_round(estimate - 1.96 * se),
                    ci_high=_round(estimate + 1.96 * se), p_value=_round(p_value),
                ))
        _apply_pairwise_holm(pairs)

        likelihood_ratio = max(0.0, 2 * (float(fitted.llf) - float(fitted_null.llf)))
        omnibus_p = float(chi2.sf(likelihood_ratio, len(conditions) - 1))
        random_variance = float(np.asarray(fitted.cov_re)[0, 0])
        residual_variance = float(fitted.scale)
        variance_total = random_variance + residual_variance
        icc = random_variance / variance_total if variance_total > 0 else None
        warning_text = "; ".join(str(item.message) for item in caught)
        note = "ML 随机截距模型；条件总体显著性使用似然比检验。"
        if random_variance < 1e-8:
            note += " 小组随机效应估计接近 0。"
        if warning_text:
            note += " 模型产生拟合警告，请结合小组数谨慎解释。"
        test = HierarchicalTestResult(
            **base_test, statistic_name="LR χ²", statistic=_round(likelihood_ratio),
            p_value=_round(omnibus_p), status="ok", note=note, pairwise=pairs,
        )
        return MixedModelMetricResult(
            metric=metric, label=label, status="ok", participant_count=len(usable),
            group_count=len(set(group_ids.tolist())), converged=bool(fitted.converged),
            fixed_effect_test=test, estimated_means=estimated_means,
            random_intercept_variance=_round(random_variance), residual_variance=_round(residual_variance),
            icc=_round(icc), note=note,
        )
    except Exception as exc:
        test = HierarchicalTestResult(**base_test, status="calculation_error", note="模型无法稳定拟合。")
        return MixedModelMetricResult(
            metric=metric, label=label, status="calculation_error", participant_count=len(usable),
            group_count=len(set(group_ids.tolist())), fixed_effect_test=test,
            note=f"模型无法稳定拟合：{type(exc).__name__}",
        )


def build_questionnaire_hierarchical_analysis(
    *, scale: ScaleKind, mode: AnalysisMode, rows: list[dict[str, Any]],
) -> QuestionnaireHierarchicalAnalysisResult:
    individual = build_questionnaire_analysis(scale=scale, mode=mode, rows=rows)
    conditions = individual.conditions
    metrics = _scale_metrics(scale)
    labels = _scale_labels(scale)
    observations = [
        observation for row in rows
        if row.get("condition") in conditions
        for observation in [observation_from_row(row, scale)]
        if observation is not None
    ]
    group_sizes: dict[str, dict[str, int]] = {condition: defaultdict(int) for condition in conditions}
    for observation in observations:
        group_sizes[observation.condition][observation.group_id] += 1
    sample_summary = []
    for condition in conditions:
        sizes = list(group_sizes[condition].values())
        sample_summary.append(ConditionSampleSummary(
            condition=condition,
            participant_count=sum(sizes),
            group_count=len(sizes),
            min_group_size=min(sizes) if sizes else None,
            max_group_size=max(sizes) if sizes else None,
            mean_group_size=round(mean(sizes), 2) if sizes else None,
        ))

    group_results = _group_mean_analysis(observations, metrics, labels, conditions)
    mixed_results = [_fit_mixed_metric(metric, labels[metric], observations, conditions) for metric in metrics]
    mixed_adjusted = benjamini_hochberg([item.fixed_effect_test.p_value for item in mixed_results])
    for item, p_adjusted in zip(mixed_results, mixed_adjusted):
        item.fixed_effect_test.p_value_adjusted = p_adjusted
    individual_adjusted = benjamini_hochberg([item.p_value for item in individual.statistical_tests])

    warnings_list: list[str] = []
    if any(item.group_count < 5 for item in sample_summary):
        warnings_list.append("至少一个条件少于 5 个小组；小组均值和混合模型结果仅宜作为探索性证据。")
    if any(item.min_group_size != item.max_group_size for item in sample_summary if item.group_count):
        warnings_list.append("小组人数不完全均衡；小组均值分析按小组等权，混合模型保留个人观测。")
    return QuestionnaireHierarchicalAnalysisResult(
        scale=scale,
        mode=mode,
        conditions=conditions,
        participant_count=len(observations),
        group_count=len({observation.group_id for observation in observations}),
        sample_summary=sample_summary,
        individual_analysis=individual,
        individual_p_values_adjusted={
            item.metric: p_adjusted
            for item, p_adjusted in zip(individual.statistical_tests, individual_adjusted)
        },
        group_mean_metrics=group_results,
        mixed_model_metrics=mixed_results,
        warnings=warnings_list,
    )
