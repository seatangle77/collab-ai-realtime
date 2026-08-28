from __future__ import annotations

import base64
import io
from typing import Sequence

import matplotlib
matplotlib.use("Agg")  # headless, no display needed
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.font_manager as fm
import matplotlib.patheffects as path_effects
import numpy as np

# Try to find a CJK-capable font — file path first, then name-based fallback
import os as _os
_CJK_FONT_PATHS = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",   # Ubuntu/Debian
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
]
_CJK_FONT_NAMES = [
    "PingFang SC", "Hiragino Sans GB", "STHeiti",
    "Noto Sans CJK SC", "WenQuanYi Micro Hei", "SimHei",
    "Microsoft YaHei", "SimSun",
]
_registered = False
for _path in _CJK_FONT_PATHS:
    if _os.path.exists(_path):
        fm.fontManager.addfont(_path)
        _prop = fm.FontProperties(fname=_path)
        plt.rcParams["font.family"] = _prop.get_name()
        _registered = True
        break
if not _registered:
    _found = next((f.name for f in fm.fontManager.ttflist if f.name in _CJK_FONT_NAMES), None)
    if _found:
        plt.rcParams["font.family"] = _found
plt.rcParams["axes.unicode_minus"] = False

# ---------------------------------------------------------------------------
# Shared style
# ---------------------------------------------------------------------------

CONDITION_COLORS: dict[str, str] = {
    "no_assistance":    "#4B5563",   # neutral slate
    "glasses":          "#0072B2",   # color-blind-safe blue
    "app_notification": "#D55E00",   # color-blind-safe vermillion
}

CONDITION_LABELS: dict[str, str] = {
    "no_assistance":    "No Assistance",
    "glasses":          "Smart Glasses",
    "app_notification": "App Notification",
}

DPI = 180


def _strengthen_text(text_obj, width: float, color: str):
    if width > 0:
        text_obj.set_path_effects([path_effects.withStroke(linewidth=width, foreground=color)])
    return text_obj


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


def fig_to_base64_pair(fig: plt.Figure) -> tuple[str, str]:
    """Render one figure as a high-resolution PNG and a scalable SVG data URI."""
    png_buf = io.BytesIO()
    svg_buf = io.BytesIO()
    fig.savefig(png_buf, format="png", dpi=DPI, bbox_inches="tight", facecolor="white")
    fig.savefig(svg_buf, format="svg", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    png = base64.b64encode(png_buf.getvalue()).decode("utf-8")
    svg = base64.b64encode(svg_buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{png}", f"data:image/svg+xml;base64,{svg}"


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
        return "p = —"
    if p < 0.001:
        return "p < .001"
    if p < 0.05:
        return f"*p = {p:.3f}".replace("0.", ".")
    return f"p = {p:.3f} · n.s.".replace("0.", ".")


def annotate_pvalue(
    ax: plt.Axes,
    p: float | None,
    x: float,
    y: float,
    *,
    fontsize: float = 9,
    nonsig_fontweight: str = "normal",
    stroke_width: float = 0,
) -> None:
    label = pvalue_label(p)
    color = "#cc0000" if (p is not None and p < 0.05) else "#888888"
    weight = "bold" if (p is not None and p < 0.05) else nonsig_fontweight
    text_obj = ax.text(
        x, y, label,
        ha="center", va="bottom",
        fontsize=fontsize, color=color, fontweight=weight,
        transform=ax.transAxes,
    )
    _strengthen_text(text_obj, stroke_width, color)


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
    effect_size: float | None = None,
    effect_size_name: str | None = None,
    panel_label: str | None = None,
    condition_labels: dict[str, str] | None = None,
    y_limits: tuple[float, float] | None = None,
    zero_reference: bool = False,
    annotation_y: float = 0.97,
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

    if y_limits is not None:
        ax.set_ylim(*y_limits)
    if zero_reference:
        ax.axhline(0, color="#4b5563", linewidth=1.5, linestyle="--", zorder=2)

    # median value labels inside boxes
    for i, (pos, vals) in enumerate(zip(positions, plot_data)):
        if vals:
            med = float(np.median(vals))
            med_obj = ax.text(
                pos, med, f"{med:.2f}",
                ha="center", va="center",
                fontsize=11, fontweight="black", color="white", zorder=5,
            )
            _strengthen_text(med_obj, 0.45, "white")

    n_labels = [f"n={len(data_by_condition.get(c, []))}" for c in conditions]
    ax.set_xticks(positions)
    ax.set_xticklabels(
        [f"{(condition_labels or {}).get(c, condition_label(c))}\n{n}" for c, n in zip(conditions, n_labels)],
        fontsize=10,
        fontweight="black",
    )
    for label in ax.get_xticklabels():
        label.set_color("#111111")
        _strengthen_text(label, 0.35, "#111111")
    for label in ax.get_yticklabels():
        label.set_fontweight("black")
        label.set_fontsize(10)
        label.set_color("#111111")
        _strengthen_text(label, 0.35, "#111111")

    ylabel_obj = ax.set_ylabel(ylabel, fontsize=11, fontweight="black", color="#111111")
    _strengthen_text(ylabel_obj, 0.35, "#111111")
    xlabel_obj = ax.set_xlabel("Experimental Condition", fontsize=10, fontweight="bold", color="#333333", labelpad=8)
    _strengthen_text(xlabel_obj, 0.25, "#333333")
    display_title = f"{panel_label}  {title}" if panel_label else title
    title_obj = ax.set_title(display_title, fontsize=13, fontweight="black", pad=8, color="#111111", loc="left")
    _strengthen_text(title_obj, 0.35, "#111111")

    annotate_pvalue(ax, p_value, x=0.5, y=annotation_y, fontsize=11, nonsig_fontweight="black", stroke_width=0.35)
    if effect_size is not None and effect_size_name:
        effect_obj = ax.text(
            0.98, annotation_y, f"{effect_size_name} = {effect_size:.2f}",
            ha="right", va="bottom", transform=ax.transAxes,
            fontsize=10, color="#333333", fontweight="bold",
        )
        _strengthen_text(effect_obj, 0.25, "#333333")


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
