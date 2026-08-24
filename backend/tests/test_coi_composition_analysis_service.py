from __future__ import annotations

from backend.app.analysis.coi_composition_analysis_service import build_coi_composition_analysis


def _session(session_id: str, group_id: str, condition: str, codes: list[list[str] | None]) -> list[dict]:
    return [
        {
            "session_id": session_id,
            "group_id": group_id,
            "condition": condition,
            "group_name": group_id,
            "coi_categories": categories,
        }
        for categories in codes
    ]


def test_multicode_units_are_counted_as_code_assignments() -> None:
    rows = []
    rows += _session("s1", "g1", "no_assistance", [["EX", "IN"], ["EX"]])
    rows += _session("s2", "g2", "glasses", [["TE"], ["RE"]])
    result = build_coi_composition_analysis(mode="two_conditions", rows=rows)

    observation = next(item for item in result.observations if item.session_id == "s1")
    assert observation.total_count == 3
    assert observation.ex_count == 2
    assert observation.in_count == 1
    assert observation.ex_ratio == 0.6667
    assert observation.in_ratio == 0.3333
    assert len(result.metrics) == 4
    assert {item.metric for item in result.metrics} == {"te_ratio", "ex_ratio", "in_ratio", "re_ratio"}


def test_fdr_family_contains_only_four_phases() -> None:
    rows = []
    for condition_index, condition in enumerate(("no_assistance", "glasses", "app_notification")):
        for group_index in range(4):
            codes = [["TE"], ["EX"], ["IN"], ["RE"]]
            if condition_index == 1:
                codes += [["IN"]] * (group_index + 1)
            if condition_index == 2:
                codes += [["EX"]] * (group_index + 1)
            rows += _session(f"s-{condition_index}-{group_index}", f"g-{condition_index}-{group_index}", condition, codes)

    result = build_coi_composition_analysis(mode="three_conditions", rows=rows)
    assert len(result.statistical_tests) == 4
    assert all(item.p_value_adjusted is not None for item in result.statistical_tests if item.status == "ok")
    assert result.global_test.status == "ok"
    assert result.global_test.statistic is not None
    assert result.global_test.p_value is not None
    assert result.global_test.effect_size is not None


def test_incomplete_sessions_are_excluded_entirely() -> None:
    rows = []
    rows += _session("complete", "g1", "no_assistance", [["EX"], ["IN"]])
    rows += _session("incomplete", "g2", "glasses", [["EX"], None])
    rows += _session("complete-2", "g3", "glasses", [["TE"], ["RE"]])

    result = build_coi_composition_analysis(mode="two_conditions", rows=rows)
    assert result.total_sessions == 2
    assert {item.session_id for item in result.observations} == {"complete", "complete-2"}
    assert len(result.excluded_sessions) == 1
    assert result.excluded_sessions[0].session_id == "incomplete"
    assert result.excluded_sessions[0].uncoded_count == 1


def test_condition_means_weight_sessions_equally() -> None:
    rows = []
    rows += _session("short", "g1", "no_assistance", [["TE"], ["EX"]])
    rows += _session("long", "g2", "no_assistance", [["EX"]] * 8 + [["TE"]] * 2)
    rows += _session("glasses-1", "g3", "glasses", [["TE"], ["EX"]])
    rows += _session("glasses-2", "g4", "glasses", [["TE"], ["EX"]])

    result = build_coi_composition_analysis(mode="two_conditions", rows=rows)
    ex_metric = next(item for item in result.metrics if item.metric == "ex_ratio")
    no_assistance = next(item for item in ex_metric.conditions if item.condition == "no_assistance")
    assert no_assistance.mean == 0.65  # mean of 0.50 and 0.80, not pooled 9/12
