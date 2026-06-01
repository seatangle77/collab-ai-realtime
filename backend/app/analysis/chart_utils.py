from __future__ import annotations

import base64
import io
from typing import Sequence

import matplotlib
matplotlib.use("Agg")  # headless, no display needed
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.font_manager as fm
import numpy as np

# Try to find a CJK-capable font on the host system
_CJK_FONT_CANDIDATES = [
    "PingFang SC", "Hiragino Sans GB", "STHeiti",          # macOS
    "WenQuanYi Micro Hei", "Noto Sans CJK SC", "SimHei",   # Linux
    "Microsoft YaHei", "SimSun",                            # Windows
]
_found_cjk = next(
    (f.name for f in fm.fontManager.ttflist if f.name in _CJK_FONT_CANDIDATES),
    None,
)
if _found_cjk:
    plt.rcParams["font.family"] = _found_cjk
plt.rcParams["axes.unicode_minus"] = False  # prevent minus sign from breaking

# ---------------------------------------------------------------------------
# Shared style
# ---------------------------------------------------------------------------

CONDITION_COLORS: dict[str, str] = {
    "no_assistance":    "#1f77b4",   # blue
    "glasses":          "#e69f00",   # gold-orange
    "app_notification": "#2ca02c",   # green
}

CONDITION_LABELS: dict[str, str] = {
    "no_assistance":    "No Assistance",
    "glasses":          "Smart Glasses",
    "app_notification": "App Notification",
}

DPI = 180


def _apply_base_style(ax: plt.Axes) -> None:
    ax.set_facecolor("white")
    ax.grid(axis="y", linestyle="--", linewidth=0.6, color="#cccccc", zorder=0)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#999999")
    ax.spines["bottom"].set_color("#999999")
    ax.tick_params(colors="#444444", labelsize=9)


def fig_to_base64(fig: plt.Figure) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    data = base64.b64encode(buf.read()).decode("utf-8")
    return f"data:image/png;base64,{data}"


def condition_color(condition: str) -> str:
    return CONDITION_COLORS.get(condition, "#888888")


def condition_label(condition: str) -> str:
    return CONDITION_LABELS.get(condition, condition)


def legend_handles(conditions: Sequence[str]) -> list[mpatches.Patch]:
    return [
        mpatches.Patch(color=condition_color(c), label=condition_label(c))
        for c in conditions
    ]


# ---------------------------------------------------------------------------
# p-value annotation helper
# ---------------------------------------------------------------------------

def pvalue_label(p: float | None) -> str:
    if p is None:
        return "n.s."
    if p < 0.001:
        return "*** p < 0.001"
    if p < 0.01:
        return f"** p = {p:.3f}"
    if p < 0.05:
        return f"* p = {p:.3f}"
    return "n.s."


def annotate_pvalue(ax: plt.Axes, p: float | None, x: float, y: float) -> None:
    label = pvalue_label(p)
    color = "#cc0000" if (p is not None and p < 0.05) else "#888888"
    weight = "bold" if (p is not None and p < 0.05) else "normal"
    ax.text(
        x, y, label,
        ha="center", va="bottom",
        fontsize=9, color=color, fontweight=weight,
        transform=ax.transAxes,
    )


# ---------------------------------------------------------------------------
# Box plot (single metric, multiple conditions)
# ---------------------------------------------------------------------------

def draw_boxplot(
    ax: plt.Axes,
    data_by_condition: dict[str, list[float]],
    conditions: list[str],
    title: str,
    ylabel: str,
    p_value: float | None = None,
) -> None:
    _apply_base_style(ax)

    plot_data = [data_by_condition.get(c, []) for c in conditions]
    colors = [condition_color(c) for c in conditions]
    positions = list(range(1, len(conditions) + 1))

    bp = ax.boxplot(
        plot_data,
        positions=positions,
        widths=0.45,
        patch_artist=True,
        medianprops=dict(color="#cc0000", linewidth=2),
        whiskerprops=dict(color="#555555", linewidth=1.2),
        capprops=dict(color="#555555", linewidth=1.2),
        flierprops=dict(
            marker="o", markerfacecolor="#888888",
            markeredgecolor="#888888", markersize=4, alpha=0.6,
        ),
        boxprops=dict(linewidth=1.2),
        zorder=3,
    )

    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.82)

    # median value labels inside boxes
    for i, (pos, vals) in enumerate(zip(positions, plot_data)):
        if vals:
            med = float(np.median(vals))
            ax.text(
                pos, med, f"{med:.2f}",
                ha="center", va="center",
                fontsize=8, fontweight="bold", color="white", zorder=5,
            )

    n_labels = [f"n={len(data_by_condition.get(c, []))}" for c in conditions]
    ax.set_xticks(positions)
    ax.set_xticklabels(
        [f"{condition_label(c)}\n{n}" for c, n in zip(conditions, n_labels)],
        fontsize=9,
    )
    ax.set_ylabel(ylabel, fontsize=10)
    ax.set_title(title, fontsize=12, fontweight="bold", pad=8)

    annotate_pvalue(ax, p_value, x=0.5, y=0.97)


# ---------------------------------------------------------------------------
# Grouped bar chart (dimensions × conditions, with error bars)
# ---------------------------------------------------------------------------

def draw_grouped_bars(
    ax: plt.Axes,
    means: dict[str, dict[str, float]],     # metric_key -> condition -> mean
    errors: dict[str, dict[str, float]],    # metric_key -> condition -> SD or SE
    metric_labels: dict[str, str],          # metric_key -> display label
    conditions: list[str],
    title: str,
    ylabel: str,
    p_values: dict[str, float | None] | None = None,
) -> None:
    _apply_base_style(ax)

    metrics = list(metric_labels.keys())
    n_metrics = len(metrics)
    n_conds = len(conditions)
    width = 0.7 / n_conds
    x = np.arange(n_metrics)

    for i, cond in enumerate(conditions):
        offsets = x + (i - (n_conds - 1) / 2) * width
        vals = [means.get(m, {}).get(cond, 0.0) for m in metrics]
        errs = [errors.get(m, {}).get(cond, 0.0) for m in metrics]
        bars = ax.bar(
            offsets, vals, width=width * 0.9,
            color=condition_color(cond), alpha=0.88,
            yerr=errs, error_kw=dict(ecolor="#333333", capsize=3, linewidth=1.2),
            zorder=3, label=condition_label(cond),
        )
        for bar, val in zip(bars, vals):
            if val > 0:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + max(errs) * 0.15 + 0.02,
                    f"{val:.2f}",
                    ha="center", va="bottom", fontsize=8, fontweight="bold",
                )

    ax.set_xticks(x)
    ax.set_xticklabels([metric_labels[m] for m in metrics], fontsize=9)
    ax.set_ylabel(ylabel, fontsize=10)
    ax.set_title(title, fontsize=12, fontweight="bold", pad=8)
    ax.legend(fontsize=9, framealpha=0.6)

    if p_values:
        y_top = ax.get_ylim()[1]
        for j, m in enumerate(metrics):
            p = p_values.get(m)
            if p is not None and p < 0.05:
                ax.text(
                    x[j], y_top * 0.98,
                    pvalue_label(p),
                    ha="center", va="top",
                    fontsize=8, color="#cc0000", fontweight="bold",
                )
