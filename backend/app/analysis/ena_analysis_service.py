"""ENA (Epistemic Network Analysis) service based on CoI coding results.

Analysis unit: session (conversation).
Window: 2-minute sliding window, 30-second step.
Metrics: EX-IN connection strength, IN-RE connection strength, higher-order strength.
Statistical pipeline mirrors task_score_analysis_service / coi_analysis_service.
"""
from __future__ import annotations

import math
from collections import defaultdict
from itertools import combinations
from statistics import mean, median, stdev
from typing import Any, Literal

from ..api_model import ApiModel
from .stats_utils import MetricConditionStats, PostHocPairResult, _cohens_d, _epsilon_squared, _eta_squared, _stats_for, benjamini_hochberg

try:
    from scipy.stats import f_oneway, kruskal, levene, mannwhitneyu, norm as _scipy_norm, shapiro, ttest_ind, tukey_hsd
except ImportError:  # pragma: no cover
    f_oneway = None
    kruskal = None
    levene = None
    mannwhitneyu = None
    _scipy_norm = None
    shapiro = None
    ttest_ind = None
    tukey_hsd = None

try:
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import numpy as np
    from .chart_utils import condition_label as _cond_label, fig_to_base64, annotate_pvalue, pvalue_label, _apply_base_style
    _CHARTS_AVAILABLE = True
except ImportError:
    _CHARTS_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────
# Constants
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

COI_NODES = ["TE", "EX", "IN", "RE"]
# All 6 pairs as (a, b) with a < b alphabetically
ALL_EDGE_PAIRS: list[tuple[str, str]] = [(a, b) for a, b in combinations(COI_NODES, 2)]

# The 3 key metrics the analysis focuses on
ENA_METRICS = ["ex_in_strength", "in_re_strength", "higher_order_strength"]

ENA_METRIC_LABELS: dict[str, str] = {
    "ex_in_strength": "EX-IN 连接强度（探索→整合）",
    "in_re_strength": "IN-RE 连接强度（整合→解决）",
    "higher_order_strength": "高阶认知连接强度（EX+IN+RE 共现）",
}

# Synthetic seconds-per-utterance when start_time is NULL
_SYNTHETIC_SECONDS_PER_UTTERANCE = 30.0
WINDOW_SIZE_SECONDS = 120.0   # 2 minutes
WINDOW_STEP_SECONDS = 30.0    # 30-second step


# ─────────────────────────────────────────────────────────────────
# Data models
# ─────────────────────────────────────────────────────────────────

class EnaObservation(ApiModel):
    session_id: str
    group_id: str
    condition: str
    ex_in_strength: float
    in_re_strength: float
    higher_order_strength: float
    total_windows: int


class EnaMetricSummary(ApiModel):
    metric: str
    label: str
    conditions: list[MetricConditionStats]


class EnaNormalityResult(ApiModel):
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


class EnaTestRecommendation(ApiModel):
    metric: str
    label: str
    recommended_test: RecommendedTest
    normality_assumption_met: bool | None
    conditions: list[str]
    note: str


class EnaStatTestResult(ApiModel):
    metric: str
    label: str
    test: RecommendedTest
    statistic_name: str | None = None
    statistic: float | None = None
    p_value: float | None = None
    p_value_adjusted: float | None = None  # Benjamini-Hochberg FDR corrected
    effect_size_name: str | None = None
    effect_size: float | None = None
    status: StatisticalTestStatus
    note: str


class EnaPostHocResult(ApiModel):
    metric: str
    label: str
    method: PostHocMethod | None = None
    pairs: list[PostHocPairResult] = []
    status: PostHocStatus
    note: str


class EnaEdge(ApiModel):
    source: str
    target: str
    weight: float      # mean co-occurrence strength for this condition
    weight_diff: float | None = None  # diff = condition_b - condition_a (only in diff network)


class EnaNetworkCondition(ApiModel):
    condition: str
    nodes: list[str]
    edges: list[EnaEdge]


class EnaAnalysisResult(ApiModel):
    mode: AnalysisMode
    conditions: list[str]
    total_sessions: int
    sessions_by_condition: dict[str, int]
    observations: list[EnaObservation]
    metrics: list[EnaMetricSummary]
    normality: list[EnaNormalityResult]
    test_recommendations: list[EnaTestRecommendation]
    statistical_tests: list[EnaStatTestResult]
    post_hoc_tests: list[EnaPostHocResult]
    networks: list[EnaNetworkCondition]     # one per condition
    diff_network: EnaNetworkCondition | None  # only for two_conditions
    charts: dict[str, str] = {}


# ─────────────────────────────────────────────────────────────────
# Chart generation
# ─────────────────────────────────────────────────────────────────

_NODE_POS = {"TE": (0.5, 0.88), "EX": (0.08, 0.44), "IN": (0.92, 0.44), "RE": (0.5, 0.0)}
_NODE_COLORS = {"TE": "#f59e0b", "EX": "#3b82f6", "IN": "#8b5cf6", "RE": "#10b981"}
_NODE_LABELS_ZH = {"TE": "触发", "EX": "探索", "IN": "整合", "RE": "解决"}
_EDGE_COLORS = {
    ("EX", "IN"): "#6366f1", ("IN", "RE"): "#8b5cf6",
    ("TE", "EX"): "#f59e0b", ("TE", "IN"): "#3b82f6",
    ("TE", "RE"): "#ef4444", ("EX", "RE"): "#06b6d4",
}


def _draw_ena_network(ax: "plt.Axes", network: "EnaNetworkCondition", title: str, is_diff: bool = False) -> None:
    ax.set_xlim(-0.18, 1.18)
    ax.set_ylim(-0.18, 1.08)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_facecolor("#f8fafc")
    ax.set_title(title, fontsize=11, fontweight="bold", pad=8)

    weights = [abs(e.weight_diff if is_diff else e.weight) for e in network.edges]
    max_w = max(weights) if any(w > 0 for w in weights) else 1.0

    for edge in network.edges:
        w = abs(edge.weight_diff if is_diff else edge.weight)
        x0, y0 = _NODE_POS.get(edge.source, (0.5, 0.5))
        x1, y1 = _NODE_POS.get(edge.target, (0.5, 0.5))
        lw = max(0.8, (w / max_w) * 9)
        alpha = max(0.12, w / max_w * 0.85 + 0.1) if w >= 0.001 else 0.08
        if is_diff:
            diff_val = edge.weight_diff or 0.0
            color = "#2563eb" if diff_val > 0.01 else ("#dc2626" if diff_val < -0.01 else "#cbd5e1")
        else:
            pair = (edge.source, edge.target)
            color = _EDGE_COLORS.get(pair, _EDGE_COLORS.get((edge.target, edge.source), "#94a3b8"))
        # Slight curve via control point offset
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        dx, dy = x1 - x0, y1 - y0
        length = max((dx**2 + dy**2) ** 0.5, 1e-6)
        cx, cy = mx - (dy / length) * 0.08, my + (dx / length) * 0.08
        from matplotlib.patches import FancyArrowPatch
        style = f"arc3,rad=0.15"
        ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                    arrowprops=dict(arrowstyle="-", color=color, lw=lw,
                                   connectionstyle=style, alpha=alpha), zorder=1)
        val = edge.weight_diff if is_diff else edge.weight
        if val is not None and abs(val) >= 0.03:
            txt = f"{val:+.2f}" if is_diff else f"{val:.2f}"
            ax.text(cx, cy + 0.04, txt, ha="center", va="bottom", fontsize=8,
                    fontweight="600", color=color, alpha=0.95, zorder=4)

    for node in network.nodes:
        x, y = _NODE_POS.get(node, (0.5, 0.5))
        color = _NODE_COLORS.get(node, "#888888")
        circle = mpatches.Circle((x, y), 0.1, facecolor=color, edgecolor="white",
                                  linewidth=2.0, zorder=3)
        ax.add_patch(circle)
        ax.text(x, y + 0.025, node, ha="center", va="center",
                fontsize=10, fontweight="bold", color="white", zorder=5)
        ax.text(x, y - 0.038, _NODE_LABELS_ZH.get(node, ""), ha="center", va="center",
                fontsize=7.5, color="white", alpha=0.9, zorder=5)


def _generate_ena_charts(
    networks: list["EnaNetworkCondition"],
    diff_network: "EnaNetworkCondition | None",
    statistical_tests: list["EnaStatTestResult"],
) -> dict[str, str]:
    if not _CHARTS_AVAILABLE:
        return {}
    try:
        all_nets = list(networks) + ([diff_network] if diff_network else [])
        n_cols = len(all_nets)
        if n_cols == 0:
            return {}

        fig, axes = plt.subplots(1, n_cols, figsize=(n_cols * 4.2, 4.5))
        fig.patch.set_facecolor("white")
        if n_cols == 1:
            axes = [axes]

        for ax, net in zip(axes, networks):
            _draw_ena_network(ax, net, _cond_label(net.condition), is_diff=False)

        if diff_network is not None:
            _draw_ena_network(axes[-1], diff_network, "差异图 (B − A)", is_diff=True)
            legend_items = [
                mpatches.Patch(color="#1f77b4", label="B 更强 (>0.01)"),
                mpatches.Patch(color="#d62728", label="A 更强 (<-0.01)"),
                mpatches.Patch(color="#cccccc", label="差异 < 0.01"),
            ]
            axes[-1].legend(handles=legend_items,
                            loc="upper center",
                            bbox_to_anchor=(0.5, -0.04),
                            fontsize=8, framealpha=0.0, ncol=3)

        p_by_metric = {t.metric: t.p_value for t in statistical_tests}
        p_lines = [
            f"{ENA_METRIC_LABELS[m]}: {pvalue_label(p_by_metric.get(m))}"
            for m in ENA_METRICS
        ]
        fig.text(0.5, 0.01, "  |  ".join(p_lines), ha="center", va="bottom",
                 fontsize=8.5, color="#555555")

        fig.tight_layout(pad=1.5, rect=(0, 0.10, 1, 1))
        return {"networks": fig_to_base64(fig)}
    except Exception:
        return {}


# ─────────────────────────────────────────────────────────────────
# Step 3: Sliding window core logic
# ─────────────────────────────────────────────────────────────────

def _assign_times(utterances: list[dict[str, Any]]) -> list[tuple[float, str | None]]:
    """Return (timestamp_seconds, coi_category) for each utterance.

    If start_time is present, normalize so the first utterance starts at 0.
    If start_time is NULL for all utterances, fall back to order_index * synthetic seconds.
    Mixed case: use start_time where available, interpolate/fallback for NULLs.
    """
    times: list[tuple[float, str | None]] = []
    real_times = [u.get("start_time") for u in utterances]
    has_real = any(t is not None for t in real_times)

    if has_real:
        # Normalize to 0-based: find the minimum real timestamp
        min_t = min(t for t in real_times if t is not None)
        # For NULLs, fall back to synthetic based on order_index
        for i, u in enumerate(utterances):
            t = u.get("start_time")
            if t is not None:
                times.append((float(t) - min_t, u.get("coi_category")))
            else:
                # Use neighbour interpolation: position * synthetic step
                times.append((i * _SYNTHETIC_SECONDS_PER_UTTERANCE, u.get("coi_category")))
    else:
        for i, u in enumerate(utterances):
            times.append((i * _SYNTHETIC_SECONDS_PER_UTTERANCE, u.get("coi_category")))

    return times


def compute_session_ena_metrics(
    utterances: list[dict[str, Any]],
    window_size: float = WINDOW_SIZE_SECONDS,
    step: float = WINDOW_STEP_SECONDS,
) -> dict[str, Any]:
    """Compute ENA co-occurrence metrics for a single session.

    Returns dict with ex_in_strength, in_re_strength, higher_order_strength,
    total_windows, and full edge_weights dict for all 6 pairs.
    """
    if not utterances:
        return {
            "ex_in_strength": 0.0,
            "in_re_strength": 0.0,
            "higher_order_strength": 0.0,
            "total_windows": 0,
            "edge_weights": {f"{a}_{b}": 0.0 for a, b in ALL_EDGE_PAIRS},
        }

    timed = _assign_times(utterances)
    max_time = max(t for t, _ in timed)

    # Generate window start positions
    window_starts = []
    t = 0.0
    while t <= max_time:
        window_starts.append(t)
        t += step
    if not window_starts:
        window_starts = [0.0]

    # Count co-occurrences per window
    edge_counts: dict[tuple[str, str], int] = {pair: 0 for pair in ALL_EDGE_PAIRS}
    higher_order_count = 0
    valid_windows = 0

    for w_start in window_starts:
        w_end = w_start + window_size
        # Collect categories present in this window (only coded utterances)
        cats_in_window = {
            cat
            for t_val, cat in timed
            if w_start <= t_val <= w_end and cat in ("TE", "EX", "IN", "RE")
        }
        if not cats_in_window:
            continue
        valid_windows += 1

        # Record pairwise co-occurrences
        for a, b in ALL_EDGE_PAIRS:
            if a in cats_in_window and b in cats_in_window:
                edge_counts[(a, b)] += 1

        # Higher order: EX + IN + RE all present
        if {"EX", "IN", "RE"}.issubset(cats_in_window):
            higher_order_count += 1

    if valid_windows == 0:
        return {
            "ex_in_strength": 0.0,
            "in_re_strength": 0.0,
            "higher_order_strength": 0.0,
            "total_windows": 0,
            "edge_weights": {f"{a}_{b}": 0.0 for a, b in ALL_EDGE_PAIRS},
        }

    edge_weights = {
        f"{a}_{b}": round(edge_counts[(a, b)] / valid_windows, 4)
        for a, b in ALL_EDGE_PAIRS
    }

    return {
        "ex_in_strength": edge_weights["EX_IN"],
        "in_re_strength": edge_weights["IN_RE"],
        "higher_order_strength": round(higher_order_count / valid_windows, 4),
        "total_windows": valid_windows,
        "edge_weights": edge_weights,
    }


# ─────────────────────────────────────────────────────────────────
# Statistical helpers (mirrors task_score_analysis_service)
# ─────────────────────────────────────────────────────────────────

def _round(v: float) -> float:
    return round(v, 3)


def _normality_for(*, metric: str, condition: str, values: list[float], alpha: float = 0.05) -> EnaNormalityResult:
    base = {
        "metric": metric,
        "label": ENA_METRIC_LABELS[metric],
        "condition": condition,
        "n": len(values),
        "alpha": alpha,
    }
    if shapiro is None:
        return EnaNormalityResult(**base, status="dependency_missing", note="缺少 scipy，无法执行 Shapiro-Wilk 正态性检验")
    if len(values) < 3:
        return EnaNormalityResult(**base, status="insufficient_n", note="Shapiro-Wilk 至少需要 3 个样本")
    if len(set(values)) <= 1:
        return EnaNormalityResult(**base, status="constant_values", note="所有观测值相同，无法稳定判断正态性")
    stat, p = shapiro(values)
    p_f = float(p)
    return EnaNormalityResult(
        **base,
        statistic=_round(float(stat)),
        p_value=_round(p_f),
        is_normal=p_f >= alpha,
        status="ok",
        note="p >= 0.05 时按近似正态处理" if p_f >= alpha else "p < 0.05，按偏离正态处理",
    )


def _recommend(*, mode: AnalysisMode, metric: str, conditions: list[str], normality: list[EnaNormalityResult]) -> EnaTestRecommendation:
    relevant = [n for n in normality if n.metric == metric and n.condition in conditions]
    base = {"metric": metric, "label": ENA_METRIC_LABELS[metric], "conditions": conditions}

    if any(n.n < 2 for n in relevant):
        return EnaTestRecommendation(**base, recommended_test="insufficient_data", normality_assumption_met=None,
                                     note="至少每个条件需要 2 个样本才能进行组间比较")

    all_normal = all(n.status == "ok" and n.is_normal is True for n in relevant)
    all_checked = all(n.status == "ok" for n in relevant)

    if mode == "two_conditions":
        if all_normal:
            return EnaTestRecommendation(**base, recommended_test="independent_samples_t_test",
                                         normality_assumption_met=True,
                                         note="两个条件均通过 Shapiro-Wilk，建议使用 independent-samples t-test")
        return EnaTestRecommendation(**base, recommended_test="mann_whitney_u",
                                     normality_assumption_met=False if all_checked else None,
                                     note="至少一个条件未通过正态性检验，建议使用 Mann-Whitney U test")

    if all_normal:
        return EnaTestRecommendation(**base, recommended_test="one_way_anova", normality_assumption_met=True,
                                     note="三个条件均通过 Shapiro-Wilk，建议使用 one-way ANOVA")
    return EnaTestRecommendation(**base, recommended_test="kruskal_wallis",
                                 normality_assumption_met=False if all_checked else None,
                                 note="至少一个条件未通过正态性检验，建议使用 Kruskal-Wallis")


def _stat_test(*, metric: str, rec: EnaTestRecommendation, values_by_condition: dict[str, list[float]]) -> EnaStatTestResult:
    base = {"metric": metric, "label": ENA_METRIC_LABELS[metric], "test": rec.recommended_test}
    groups = [values_by_condition.get(c, []) for c in rec.conditions]

    if rec.recommended_test == "insufficient_data" or any(len(g) < 2 for g in groups):
        return EnaStatTestResult(**base, status="insufficient_data", note="至少每个条件需要 2 个样本")

    if any(len(set(g)) <= 1 for g in groups):
        return EnaStatTestResult(**base, status="calculation_error", note="至少一个条件数值恒定，统计检验已跳过")

    if rec.recommended_test == "independent_samples_t_test":
        if ttest_ind is None:
            return EnaStatTestResult(**base, status="dependency_missing", note="缺少 scipy")
        stat, p = ttest_ind(groups[0], groups[1], equal_var=False)
        d = _cohens_d(groups[0], groups[1])
        return EnaStatTestResult(**base, statistic_name="t", statistic=_round(float(stat)), p_value=_round(float(p)),
                                  effect_size_name="Cohen's d", effect_size=_round(d) if d is not None else None,
                                  status="ok", note="Welch independent-samples t-test")

    if rec.recommended_test == "mann_whitney_u":
        if mannwhitneyu is None:
            return EnaStatTestResult(**base, status="dependency_missing", note="缺少 scipy")
        stat, p = mannwhitneyu(groups[0], groups[1], alternative="two-sided")
        n1, n2 = len(groups[0]), len(groups[1])
        r = (2 * float(stat) / (n1 * n2)) - 1
        return EnaStatTestResult(**base, statistic_name="U", statistic=_round(float(stat)), p_value=_round(float(p)),
                                  effect_size_name="rank-biserial r", effect_size=_round(r),
                                  status="ok", note="Mann-Whitney U test（双尾）；rank-biserial r 正值表示第一条件（no_assistance）的值倾向更大")

    if rec.recommended_test == "one_way_anova":
        if f_oneway is None:
            return EnaStatTestResult(**base, status="dependency_missing", note="缺少 scipy")
        levene_ok = True
        if levene is not None and all(len(g) >= 2 for g in groups):
            _, levene_p = levene(*groups)
            levene_ok = float(levene_p) >= 0.05
        stat, p = f_oneway(*groups)
        eta = _eta_squared(groups)
        note = (
            "Levene 检验通过（方差齐）；若 p < 0.05，后续可补 Tukey HSD 事后检验"
            if levene_ok
            else "Levene 检验 p < 0.05，方差不齐；结果仅供参考，建议改用 Welch's ANOVA"
        )
        return EnaStatTestResult(**base, statistic_name="F", statistic=_round(float(stat)), p_value=_round(float(p)),
                                  effect_size_name="eta squared", effect_size=_round(eta) if eta is not None else None,
                                  status="ok", note=note)

    if rec.recommended_test == "kruskal_wallis":
        if kruskal is None:
            return EnaStatTestResult(**base, status="dependency_missing", note="缺少 scipy")
        stat, p = kruskal(*groups)
        eps = _epsilon_squared(float(stat), len(groups), sum(len(g) for g in groups))
        return EnaStatTestResult(**base, statistic_name="H", statistic=_round(float(stat)), p_value=_round(float(p)),
                                  effect_size_name="epsilon squared", effect_size=_round(eps) if eps is not None else None,
                                  status="ok", note="Kruskal-Wallis test")

    return EnaStatTestResult(**base, status="calculation_error", note="未知检验类型")


def _dunn_bonferroni(groups: list[list[float]], conditions: list[str]) -> list[PostHocPairResult]:
    all_vals = [v for g in groups for v in g]
    n = len(all_vals)
    sorted_idx = sorted(enumerate(all_vals), key=lambda x: x[1])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j < n - 1 and sorted_idx[j + 1][1] == sorted_idx[i][1]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[sorted_idx[k][0]] = avg
        i = j + 1
    group_mean_ranks, idx = [], 0
    for g in groups:
        group_mean_ranks.append(sum(ranks[idx + k] for k in range(len(g))) / len(g))
        idx += len(g)
    pair_idxs = list(combinations(range(len(groups)), 2))
    num_pairs = len(pair_idxs)
    pairs = []
    for a, b in pair_idxs:
        se = math.sqrt((n * (n + 1) / 12) * (1 / len(groups[a]) + 1 / len(groups[b])))
        if se == 0:
            pairs.append(PostHocPairResult(condition_a=conditions[a], condition_b=conditions[b]))
            continue
        z = abs(group_mean_ranks[a] - group_mean_ranks[b]) / se
        p_raw = 2 * (1 - _scipy_norm.cdf(z)) if _scipy_norm else 1.0
        p_adj = min(1.0, p_raw * num_pairs)
        pairs.append(PostHocPairResult(
            condition_a=conditions[a], condition_b=conditions[b],
            mean_diff=_round(mean(groups[b]) - mean(groups[a])),
            p_value_adjusted=_round(p_adj), significant=p_adj < 0.05,
        ))
    return pairs


def _post_hoc(*, metric: str, omnibus: EnaStatTestResult, values_by_condition: dict[str, list[float]], conditions: list[str]) -> EnaPostHocResult:
    base = {"metric": metric, "label": ENA_METRIC_LABELS[metric]}
    if omnibus.test not in ("one_way_anova", "kruskal_wallis"):
        return EnaPostHocResult(**base, status="not_applicable", note="仅三条件全局检验有意义时才执行事后检验")
    if omnibus.status != "ok":
        return EnaPostHocResult(**base, status="not_applicable", note="全局检验未能计算，跳过事后检验")
    if omnibus.p_value is None or omnibus.p_value >= 0.05:
        return EnaPostHocResult(**base, status="not_applicable",
                                note=f"全局检验 p={omnibus.p_value}，未达显著水平（≥ 0.05），无需事后检验")
    groups = [values_by_condition.get(c, []) for c in conditions]
    if any(len(g) < 2 for g in groups):
        return EnaPostHocResult(**base, status="insufficient_data", note="至少每个条件需要 2 个样本")
    if omnibus.test == "one_way_anova":
        if tukey_hsd is None:
            return EnaPostHocResult(**base, status="dependency_missing", note="缺少 scipy")
        try:
            res = tukey_hsd(*groups)
            pair_idxs = list(combinations(range(len(groups)), 2))
            pairs = [PostHocPairResult(
                condition_a=conditions[a], condition_b=conditions[b],
                mean_diff=_round(mean(groups[b]) - mean(groups[a])),
                p_value_adjusted=_round(float(res.pvalue[a, b])),
                significant=float(res.pvalue[a, b]) < 0.05,
            ) for a, b in pair_idxs]
            return EnaPostHocResult(**base, method="tukey_hsd", pairs=pairs, status="ok", note="Tukey HSD 事后检验")
        except Exception as exc:
            return EnaPostHocResult(**base, status="calculation_error", note=f"Tukey HSD 计算错误：{exc}")
    if _scipy_norm is None:
        return EnaPostHocResult(**base, status="dependency_missing", note="缺少 scipy")
    try:
        pairs = _dunn_bonferroni(groups, conditions)
        return EnaPostHocResult(**base, method="dunn_bonferroni", pairs=pairs, status="ok",
                                note="Dunn test + Bonferroni 校正事后检验")
    except Exception as exc:
        return EnaPostHocResult(**base, status="calculation_error", note=f"Dunn test 计算错误：{exc}")


# ─────────────────────────────────────────────────────────────────
# Network data builder (for SVG visualization)
# ─────────────────────────────────────────────────────────────────

def _build_network(condition: str, edge_weights_list: list[dict[str, float]]) -> EnaNetworkCondition:
    """Average edge weights across all sessions in a condition."""
    if not edge_weights_list:
        return EnaNetworkCondition(
            condition=condition,
            nodes=COI_NODES,
            edges=[EnaEdge(source=a, target=b, weight=0.0) for a, b in ALL_EDGE_PAIRS],
        )
    edges = []
    for a, b in ALL_EDGE_PAIRS:
        key = f"{a}_{b}"
        avg_weight = round(mean(w[key] for w in edge_weights_list), 4)
        edges.append(EnaEdge(source=a, target=b, weight=avg_weight))
    return EnaNetworkCondition(condition=condition, nodes=COI_NODES, edges=edges)


def _build_diff_network(net_a: EnaNetworkCondition, net_b: EnaNetworkCondition) -> EnaNetworkCondition:
    """Difference network: net_b - net_a (positive = B stronger, negative = A stronger)."""
    weight_a = {(e.source, e.target): e.weight for e in net_a.edges}
    edges = []
    for e in net_b.edges:
        diff = round(e.weight - weight_a.get((e.source, e.target), 0.0), 4)
        edges.append(EnaEdge(source=e.source, target=e.target, weight=e.weight, weight_diff=diff))
    return EnaNetworkCondition(condition="diff", nodes=COI_NODES, edges=edges)


# ─────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────

def build_ena_analysis(
    *,
    mode: AnalysisMode,
    rows: list[dict[str, Any]],
) -> EnaAnalysisResult:
    """Build full ENA analysis from coi_utterances rows.

    rows: list of dicts with keys: session_id, group_id, condition,
          order_index, coi_category, start_time (float | None)
    """
    conditions = CONDITIONS_BY_MODE[mode]

    # Group utterances by session
    sessions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    session_meta: dict[str, dict[str, str]] = {}
    for row in rows:
        if row.get("condition") not in conditions:
            continue
        sid = row["session_id"]
        sessions[sid].append(row)
        session_meta[sid] = {
            "group_id": row["group_id"],
            "condition": row["condition"],
        }

    # Compute per-session ENA metrics
    observations: list[EnaObservation] = []
    edge_weights_by_condition: dict[str, list[dict[str, float]]] = defaultdict(list)

    for sid, utts in sessions.items():
        utts_sorted = sorted(utts, key=lambda u: u.get("order_index", 0))
        result = compute_session_ena_metrics(utts_sorted)
        meta = session_meta[sid]
        observations.append(EnaObservation(
            session_id=sid,
            group_id=meta["group_id"],
            condition=meta["condition"],
            ex_in_strength=result["ex_in_strength"],
            in_re_strength=result["in_re_strength"],
            higher_order_strength=result["higher_order_strength"],
            total_windows=result["total_windows"],
        ))
        edge_weights_by_condition[meta["condition"]].append(result["edge_weights"])

    sessions_by_condition = {c: sum(1 for o in observations if o.condition == c) for c in conditions}

    # Descriptive stats
    values_by_metric_condition: dict[str, dict[str, list[float]]] = {
        m: defaultdict(list) for m in ENA_METRICS
    }
    for obs in observations:
        for m in ENA_METRICS:
            values_by_metric_condition[m][obs.condition].append(getattr(obs, m))

    metrics = [
        EnaMetricSummary(
            metric=m,
            label=ENA_METRIC_LABELS[m],
            conditions=[_stats_for(values_by_metric_condition[m][c], c) for c in conditions],
        )
        for m in ENA_METRICS
    ]

    # Normality
    normality = [
        _normality_for(metric=m, condition=c, values=values_by_metric_condition[m][c])
        for m in ENA_METRICS
        for c in conditions
    ]

    # Statistical tests
    recommendations = [
        _recommend(mode=mode, metric=m, conditions=conditions, normality=normality)
        for m in ENA_METRICS
    ]
    rec_by_metric = {r.metric: r for r in recommendations}
    stat_tests = [
        _stat_test(metric=m, rec=rec_by_metric[m], values_by_condition=values_by_metric_condition[m])
        for m in ENA_METRICS
    ]

    # Benjamini-Hochberg FDR correction across all metrics
    raw_p = [t.p_value if t.status == "ok" else None for t in stat_tests]
    adjusted_p = benjamini_hochberg(raw_p)
    for t, p_adj in zip(stat_tests, adjusted_p):
        if t.status == "ok":
            t.p_value_adjusted = p_adj

    omnibus_by_metric = {t.metric: t for t in stat_tests}
    post_hoc = [
        _post_hoc(
            metric=m,
            omnibus=omnibus_by_metric[m],
            values_by_condition=values_by_metric_condition[m],
            conditions=conditions,
        )
        for m in ENA_METRICS
    ]

    # Network data for visualization
    networks = [_build_network(c, edge_weights_by_condition[c]) for c in conditions]
    diff_network: EnaNetworkCondition | None = None
    if mode == "two_conditions" and len(networks) == 2:
        diff_network = _build_diff_network(networks[0], networks[1])

    return EnaAnalysisResult(
        mode=mode,
        conditions=conditions,
        total_sessions=len(observations),
        sessions_by_condition=sessions_by_condition,
        observations=observations,
        metrics=metrics,
        normality=normality,
        test_recommendations=recommendations,
        statistical_tests=stat_tests,
        post_hoc_tests=post_hoc,
        networks=networks,
        diff_network=diff_network,
        charts=_generate_ena_charts(networks, diff_network, stat_tests),
    )
