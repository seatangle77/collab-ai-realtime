from __future__ import annotations

from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.analysis.task_score_analysis_service import build_task_score_analysis


def _row(entry_id: str, condition: str, task_id: str, gs: float, ais: float, best_is: float):
    return {
        "id": entry_id,
        "group_id": f"g-{entry_id}",
        "task_id": task_id,
        "condition": condition,
        "result_json": {
            "gs": gs,
            "ais": ais,
            "best_is": best_is,
            "weak_synergy": ais - gs,
            "strong_synergy": best_is - gs,
        },
    }


def test_two_condition_analysis_filters_app_notification() -> None:
    result = build_task_score_analysis(
        mode="two_conditions",
        task_id="all",
        rows=[
            _row("1", "no_assistance", "moon_survival", 10, 12, 9),
            _row("2", "glasses", "moon_survival", 8, 12, 7),
            _row("3", "app_notification", "moon_survival", 5, 10, 6),
        ],
    )

    assert result.conditions == ["no_assistance", "glasses"]
    assert result.total_entries == 2
    assert result.entries_by_condition == {"no_assistance": 1, "glasses": 1}


def test_analysis_descriptive_stats_by_condition() -> None:
    result = build_task_score_analysis(
        mode="three_conditions",
        task_id="moon_survival",
        rows=[
            _row("1", "no_assistance", "moon_survival", 10, 12, 9),
            _row("2", "no_assistance", "moon_survival", 14, 16, 13),
            _row("3", "glasses", "moon_survival", 8, 12, 7),
            _row("4", "glasses", "winter_survival", 2, 4, 1),
        ],
    )

    gs = next(metric for metric in result.metrics if metric.metric == "gs")
    no_assistance = next(item for item in gs.conditions if item.condition == "no_assistance")
    glasses = next(item for item in gs.conditions if item.condition == "glasses")
    app = next(item for item in gs.conditions if item.condition == "app_notification")

    assert no_assistance.n == 2
    assert no_assistance.mean == 12
    assert no_assistance.median == 12
    assert glasses.n == 1
    assert glasses.mean == 8
    assert app.n == 0


def test_analysis_can_be_built_from_manually_selected_groups() -> None:
    rows = [
        _row("1", "no_assistance", "moon_survival", 10, 12, 9),
        _row("2", "no_assistance", "moon_survival", 20, 22, 19),
        _row("3", "glasses", "moon_survival", 8, 12, 7),
        _row("4", "glasses", "moon_survival", 18, 20, 17),
    ]
    selected = {
        "no_assistance": {"g-1"},
        "glasses": {"g-3"},
    }

    result = build_task_score_analysis(
        mode="two_conditions",
        task_id="moon_survival",
        rows=[
            row
            for row in rows
            if row["group_id"] in selected.get(row["condition"], set())
        ],
    )

    assert result.entries_by_condition == {"no_assistance": 1, "glasses": 1}
    gs = next(metric for metric in result.metrics if metric.metric == "gs")
    no_assistance = next(item for item in gs.conditions if item.condition == "no_assistance")
    glasses = next(item for item in gs.conditions if item.condition == "glasses")
    assert no_assistance.mean == 10
    assert glasses.mean == 8


def test_analysis_includes_normality_results() -> None:
    result = build_task_score_analysis(
        mode="two_conditions",
        task_id="moon_survival",
        rows=[
            _row("1", "no_assistance", "moon_survival", 10, 12, 9),
            _row("2", "no_assistance", "moon_survival", 12, 14, 11),
            _row("3", "glasses", "moon_survival", 8, 12, 7),
            _row("4", "glasses", "moon_survival", 9, 13, 8),
        ],
    )

    assert len(result.normality) == 10
    gs_no_assistance = next(
        item for item in result.normality
        if item.metric == "gs" and item.condition == "no_assistance"
    )
    assert gs_no_assistance.n == 2
    assert gs_no_assistance.status == "insufficient_n"


def test_analysis_recommends_non_parametric_when_normality_is_insufficient() -> None:
    result = build_task_score_analysis(
        mode="two_conditions",
        task_id="moon_survival",
        rows=[
            _row("1", "no_assistance", "moon_survival", 10, 12, 9),
            _row("2", "no_assistance", "moon_survival", 12, 14, 11),
            _row("3", "glasses", "moon_survival", 8, 12, 7),
            _row("4", "glasses", "moon_survival", 9, 13, 8),
        ],
    )

    gs_recommendation = next(item for item in result.test_recommendations if item.metric == "gs")

    assert gs_recommendation.recommended_test == "mann_whitney_u"
    assert gs_recommendation.normality_assumption_met is None


def test_analysis_includes_statistical_test_results() -> None:
    result = build_task_score_analysis(
        mode="two_conditions",
        task_id="moon_survival",
        rows=[
            _row("1", "no_assistance", "moon_survival", 10, 12, 9),
            _row("2", "no_assistance", "moon_survival", 12, 14, 11),
            _row("3", "no_assistance", "moon_survival", 14, 16, 13),
            _row("4", "glasses", "moon_survival", 8, 12, 7),
            _row("5", "glasses", "moon_survival", 9, 13, 8),
            _row("6", "glasses", "moon_survival", 11, 15, 10),
        ],
    )

    gs_test = next(item for item in result.statistical_tests if item.metric == "gs")

    assert gs_test.test in {"independent_samples_t_test", "mann_whitney_u"}
    assert gs_test.status == "ok"
    assert gs_test.statistic is not None
    assert gs_test.p_value is not None
    assert gs_test.effect_size is not None


def test_three_condition_analysis_includes_omnibus_test() -> None:
    result = build_task_score_analysis(
        mode="three_conditions",
        task_id="moon_survival",
        rows=[
            _row("1", "no_assistance", "moon_survival", 10, 12, 9),
            _row("2", "no_assistance", "moon_survival", 12, 14, 11),
            _row("3", "no_assistance", "moon_survival", 14, 16, 13),
            _row("4", "glasses", "moon_survival", 8, 12, 7),
            _row("5", "glasses", "moon_survival", 9, 13, 8),
            _row("6", "glasses", "moon_survival", 11, 15, 10),
            _row("7", "app_notification", "moon_survival", 6, 10, 5),
            _row("8", "app_notification", "moon_survival", 7, 11, 6),
            _row("9", "app_notification", "moon_survival", 9, 13, 8),
        ],
    )

    gs_test = next(item for item in result.statistical_tests if item.metric == "gs")

    assert gs_test.test in {"one_way_anova", "kruskal_wallis"}
    assert gs_test.status == "ok"
    assert gs_test.statistic_name in {"F", "H"}


def test_post_hoc_not_applicable_for_two_conditions() -> None:
    result = build_task_score_analysis(
        mode="two_conditions",
        task_id="moon_survival",
        rows=[
            _row("1", "no_assistance", "moon_survival", 10, 12, 9),
            _row("2", "no_assistance", "moon_survival", 12, 14, 11),
            _row("3", "no_assistance", "moon_survival", 14, 16, 13),
            _row("4", "glasses", "moon_survival", 8, 12, 7),
            _row("5", "glasses", "moon_survival", 9, 13, 8),
            _row("6", "glasses", "moon_survival", 11, 15, 10),
        ],
    )

    gs_post_hoc = next(item for item in result.post_hoc_tests if item.metric == "gs")
    assert gs_post_hoc.status == "not_applicable"
    assert gs_post_hoc.pairs == []


def test_post_hoc_not_applicable_when_omnibus_not_significant() -> None:
    # 三组数据差异极小，ANOVA/KW 不显著
    result = build_task_score_analysis(
        mode="three_conditions",
        task_id="moon_survival",
        rows=[
            _row("1", "no_assistance", "moon_survival", 10, 12, 9),
            _row("2", "no_assistance", "moon_survival", 10, 12, 9),
            _row("3", "no_assistance", "moon_survival", 10, 12, 9),
            _row("4", "glasses", "moon_survival", 10, 12, 9),
            _row("5", "glasses", "moon_survival", 10, 12, 9),
            _row("6", "glasses", "moon_survival", 10, 12, 9),
            _row("7", "app_notification", "moon_survival", 10, 12, 9),
            _row("8", "app_notification", "moon_survival", 10, 12, 9),
            _row("9", "app_notification", "moon_survival", 10, 12, 9),
        ],
    )

    gs_post_hoc = next(item for item in result.post_hoc_tests if item.metric == "gs")
    assert gs_post_hoc.status == "not_applicable"


def test_post_hoc_runs_when_omnibus_is_significant() -> None:
    # 三组数据差异很大，全局检验应显著，触发事后检验
    result = build_task_score_analysis(
        mode="three_conditions",
        task_id="moon_survival",
        rows=[
            _row("1", "no_assistance", "moon_survival", 30, 35, 28),
            _row("2", "no_assistance", "moon_survival", 32, 36, 29),
            _row("3", "no_assistance", "moon_survival", 31, 34, 27),
            _row("4", "glasses", "moon_survival", 15, 20, 13),
            _row("5", "glasses", "moon_survival", 16, 21, 14),
            _row("6", "glasses", "moon_survival", 14, 19, 12),
            _row("7", "app_notification", "moon_survival", 5, 10, 4),
            _row("8", "app_notification", "moon_survival", 6, 11, 5),
            _row("9", "app_notification", "moon_survival", 4, 9, 3),
        ],
    )

    gs_omnibus = next(item for item in result.statistical_tests if item.metric == "gs")
    gs_post_hoc = next(item for item in result.post_hoc_tests if item.metric == "gs")

    assert gs_omnibus.status == "ok"
    assert gs_omnibus.p_value is not None and gs_omnibus.p_value < 0.05
    assert gs_post_hoc.status == "ok"
    assert gs_post_hoc.method in {"tukey_hsd", "dunn_bonferroni"}
    assert len(gs_post_hoc.pairs) == 3  # C(3,2) = 3 对
    for pair in gs_post_hoc.pairs:
        assert pair.p_value_adjusted is not None
        assert pair.significant is not None
        assert pair.mean_diff is not None


def test_post_hoc_pairs_cover_all_condition_combinations() -> None:
    result = build_task_score_analysis(
        mode="three_conditions",
        task_id="moon_survival",
        rows=[
            _row("1", "no_assistance", "moon_survival", 30, 35, 28),
            _row("2", "no_assistance", "moon_survival", 32, 36, 29),
            _row("3", "no_assistance", "moon_survival", 31, 34, 27),
            _row("4", "glasses", "moon_survival", 15, 20, 13),
            _row("5", "glasses", "moon_survival", 16, 21, 14),
            _row("6", "glasses", "moon_survival", 14, 19, 12),
            _row("7", "app_notification", "moon_survival", 5, 10, 4),
            _row("8", "app_notification", "moon_survival", 6, 11, 5),
            _row("9", "app_notification", "moon_survival", 4, 9, 3),
        ],
    )

    gs_post_hoc = next(item for item in result.post_hoc_tests if item.metric == "gs")
    assert gs_post_hoc.status == "ok"
    pair_keys = {(p.condition_a, p.condition_b) for p in gs_post_hoc.pairs}
    assert ("no_assistance", "glasses") in pair_keys
    assert ("no_assistance", "app_notification") in pair_keys
    assert ("glasses", "app_notification") in pair_keys
