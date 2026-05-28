from __future__ import annotations

from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.analysis.questionnaire_analysis_service import (
    _cronbach_alpha,
    build_questionnaire_analysis,
)


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

def _srcc_row(user_id: str, condition: str, scores: dict[str, int]):
    """Build a minimal questionnaire_entries row for SRCC."""
    from app.questionnaire import _compute_srcc_result  # type: ignore[import]
    result = _compute_srcc_result(scores)
    return {
        "user_id": user_id,
        "group_id": f"g-{user_id}",
        "condition": condition,
        "srcc_responses": scores,
        "srcc_result": result,
        "pcs_responses": None,
        "pcs_result": None,
    }


def _pcs_row(user_id: str, condition: str, scores: dict[str, int]):
    """Build a minimal questionnaire_entries row for PCS."""
    from app.questionnaire import _compute_pcs_result  # type: ignore[import]
    result = _compute_pcs_result(scores)
    return {
        "user_id": user_id,
        "group_id": f"g-{user_id}",
        "condition": condition,
        "srcc_responses": None,
        "srcc_result": None,
        "pcs_responses": scores,
        "pcs_result": result,
    }


def _srcc_scores(base: int = 5) -> dict[str, int]:
    """Return a full 15-item SRCC response with slight variation."""
    return {f"q{i}": max(1, min(7, base + (i % 3) - 1)) for i in range(1, 16)}


def _pcs_scores(base: int = 5) -> dict[str, int]:
    """Return a full 6-item PCS response with slight variation."""
    return {f"q{i}": max(1, min(7, base + (i % 3) - 1)) for i in range(1, 7)}


# ─────────────────────────────────────────────────────────────────
# Cronbach's alpha unit tests
# ─────────────────────────────────────────────────────────────────

def test_cronbach_alpha_known_value() -> None:
    # 3 participants, 3 items – hand-computed
    matrix = [
        [2.0, 3.0, 4.0],
        [3.0, 4.0, 5.0],
        [4.0, 5.0, 6.0],
    ]
    result = _cronbach_alpha(matrix)
    assert isinstance(result, float)
    assert result == 1.0  # perfectly correlated items → alpha = 1


def test_cronbach_alpha_insufficient_n() -> None:
    assert _cronbach_alpha([[1.0, 2.0]]) == "insufficient_n"
    assert _cronbach_alpha([]) == "insufficient_n"


def test_cronbach_alpha_insufficient_items() -> None:
    assert _cronbach_alpha([[1.0], [2.0], [3.0]]) == "insufficient_items"


def test_cronbach_alpha_constant_total() -> None:
    # All rows identical → total variance = 0
    assert _cronbach_alpha([[3.0, 3.0], [3.0, 3.0], [3.0, 3.0]]) == "constant_values"


def test_cronbach_alpha_realistic_range() -> None:
    # Simulate plausible Likert data
    matrix = [
        [5.0, 6.0, 4.0, 5.0],
        [6.0, 7.0, 5.0, 6.0],
        [3.0, 3.0, 4.0, 3.0],
        [4.0, 5.0, 3.0, 5.0],
        [7.0, 6.0, 6.0, 7.0],
    ]
    result = _cronbach_alpha(matrix)
    assert isinstance(result, float)
    assert 0.0 <= result <= 1.0


# ─────────────────────────────────────────────────────────────────
# build_questionnaire_analysis – SRCC two conditions
# ─────────────────────────────────────────────────────────────────

def test_srcc_two_conditions_filters_app_notification() -> None:
    rows = [
        _srcc_row("u1", "no_assistance", _srcc_scores(5)),
        _srcc_row("u2", "no_assistance", _srcc_scores(4)),
        _srcc_row("u3", "glasses", _srcc_scores(6)),
        _srcc_row("u4", "app_notification", _srcc_scores(5)),  # should be excluded
    ]
    result = build_questionnaire_analysis(scale="srcc", mode="two_conditions", rows=rows)
    assert result.conditions == ["no_assistance", "glasses"]
    assert result.total_entries == 3
    assert result.entries_by_condition == {"no_assistance": 2, "glasses": 1}


def test_srcc_metrics_present() -> None:
    rows = [_srcc_row(f"u{i}", "no_assistance", _srcc_scores(5)) for i in range(3)]
    result = build_questionnaire_analysis(scale="srcc", mode="two_conditions", rows=rows)
    metric_names = [m.metric for m in result.metrics]
    assert "clarification_avg" in metric_names
    assert "elaboration_avg" in metric_names
    assert "refuting_avg" in metric_names
    assert "summarization_avg" in metric_names
    assert "total_avg" in metric_names


def test_srcc_reliability_included() -> None:
    rows = [_srcc_row(f"u{i}", "no_assistance", _srcc_scores(i + 3)) for i in range(4)]
    result = build_questionnaire_analysis(scale="srcc", mode="two_conditions", rows=rows)
    assert len(result.reliability) == 5  # 4 dimensions + total
    total_rel = next(r for r in result.reliability if r.metric == "total_avg")
    assert total_rel.n_items == 15


def test_srcc_descriptive_stats_correct() -> None:
    rows = [
        _srcc_row("u1", "no_assistance", {f"q{i}": 4 for i in range(1, 16)}),
        _srcc_row("u2", "no_assistance", {f"q{i}": 6 for i in range(1, 16)}),
    ]
    result = build_questionnaire_analysis(scale="srcc", mode="two_conditions", rows=rows)
    total = next(m for m in result.metrics if m.metric == "total_avg")
    na_stats = next(c for c in total.conditions if c.condition == "no_assistance")
    assert na_stats.n == 2
    assert na_stats.mean == 5.0  # (4+6)/2
    assert na_stats.min == 4.0
    assert na_stats.max == 6.0


# ─────────────────────────────────────────────────────────────────
# build_questionnaire_analysis – PCS three conditions
# ─────────────────────────────────────────────────────────────────

def test_pcs_three_conditions_all_present() -> None:
    rows = [
        _pcs_row("u1", "no_assistance", _pcs_scores(5)),
        _pcs_row("u2", "glasses", _pcs_scores(4)),
        _pcs_row("u3", "app_notification", _pcs_scores(6)),
    ]
    result = build_questionnaire_analysis(scale="pcs", mode="three_conditions", rows=rows)
    assert result.conditions == ["no_assistance", "glasses", "app_notification"]
    assert result.total_entries == 3


def test_pcs_metrics_present() -> None:
    rows = [_pcs_row(f"u{i}", "glasses", _pcs_scores(5)) for i in range(3)]
    result = build_questionnaire_analysis(scale="pcs", mode="three_conditions", rows=rows)
    metric_names = [m.metric for m in result.metrics]
    assert "belonging_avg" in metric_names
    assert "morale_avg" in metric_names
    assert "total_avg" in metric_names


def test_pcs_reliability_n_items() -> None:
    rows = [_pcs_row(f"u{i}", "no_assistance", _pcs_scores(i + 3)) for i in range(4)]
    result = build_questionnaire_analysis(scale="pcs", mode="two_conditions", rows=rows)
    total_rel = next(r for r in result.reliability if r.metric == "total_avg")
    assert total_rel.n_items == 6
    belonging_rel = next(r for r in result.reliability if r.metric == "belonging_avg")
    assert belonging_rel.n_items == 3


# ─────────────────────────────────────────────────────────────────
# Edge cases
# ─────────────────────────────────────────────────────────────────

def test_empty_rows_returns_zero_entries() -> None:
    result = build_questionnaire_analysis(scale="srcc", mode="two_conditions", rows=[])
    assert result.total_entries == 0
    assert result.entries_by_condition == {"no_assistance": 0, "glasses": 0}


def test_missing_result_json_skips_observation() -> None:
    rows = [
        {"user_id": "u1", "group_id": "g1", "condition": "no_assistance",
         "srcc_responses": None, "srcc_result": None,
         "pcs_responses": None, "pcs_result": None},
    ]
    result = build_questionnaire_analysis(scale="srcc", mode="two_conditions", rows=rows)
    assert result.total_entries == 0


def test_normality_insufficient_n_when_few_samples() -> None:
    rows = [_srcc_row("u1", "no_assistance", _srcc_scores(5))]
    result = build_questionnaire_analysis(scale="srcc", mode="two_conditions", rows=rows)
    na_normality = [r for r in result.normality if r.condition == "no_assistance" and r.metric == "total_avg"]
    assert na_normality[0].status == "insufficient_n"


def test_statistical_test_insufficient_data_when_single_sample() -> None:
    rows = [_srcc_row("u1", "no_assistance", _srcc_scores(5))]
    result = build_questionnaire_analysis(scale="srcc", mode="two_conditions", rows=rows)
    total_test = next(t for t in result.statistical_tests if t.metric == "total_avg")
    assert total_test.status == "insufficient_data"


# ─────────────────────────────────────────────────────────────────
# Group-based filtering (simulates router POST group_ids_by_condition)
# ─────────────────────────────────────────────────────────────────

def _srcc_row_with_group(user_id: str, group_id: str, condition: str, scores: dict[str, int]):
    """Build a row with an explicit group_id (not derived from user_id)."""
    from app.questionnaire import _compute_srcc_result  # type: ignore[import]
    result = _compute_srcc_result(scores)
    return {
        "user_id": user_id,
        "group_id": group_id,
        "condition": condition,
        "srcc_responses": scores,
        "srcc_result": result,
        "pcs_responses": None,
        "pcs_result": None,
    }


def _simulate_group_filter(
    rows: list[dict],
    group_ids_by_condition: dict[str, list[str]],
) -> list[dict]:
    """Mirror the router POST filtering logic."""
    selected = {c: set(ids) for c, ids in group_ids_by_condition.items()}
    return [
        row for row in rows
        if row.get("group_id") in selected.get(str(row.get("condition")), set())
    ]


def test_group_filter_only_includes_selected_groups() -> None:
    rows = [
        _srcc_row_with_group("u1", "g-na-1", "no_assistance", _srcc_scores(5)),
        _srcc_row_with_group("u2", "g-na-2", "no_assistance", _srcc_scores(4)),  # excluded
        _srcc_row_with_group("u3", "g-gl-1", "glasses", _srcc_scores(6)),
    ]
    filtered = _simulate_group_filter(rows, {
        "no_assistance": ["g-na-1"],  # only group 1, not group 2
        "glasses": ["g-gl-1"],
    })
    result = build_questionnaire_analysis(scale="srcc", mode="two_conditions", rows=filtered)
    assert result.total_entries == 2
    assert result.entries_by_condition["no_assistance"] == 1
    assert result.entries_by_condition["glasses"] == 1


def test_group_filter_empty_condition_yields_zero_entries() -> None:
    rows = [
        _srcc_row_with_group("u1", "g-na-1", "no_assistance", _srcc_scores(5)),
        _srcc_row_with_group("u2", "g-gl-1", "glasses", _srcc_scores(5)),
    ]
    filtered = _simulate_group_filter(rows, {
        "no_assistance": ["g-na-1"],
        "glasses": [],  # no glasses group selected
    })
    result = build_questionnaire_analysis(scale="srcc", mode="two_conditions", rows=filtered)
    assert result.entries_by_condition["glasses"] == 0


def test_group_filter_excludes_wrong_condition_group() -> None:
    # group g-na-1 is listed under glasses in the filter but actually belongs to no_assistance
    rows = [
        _srcc_row_with_group("u1", "g-na-1", "no_assistance", _srcc_scores(5)),
    ]
    filtered = _simulate_group_filter(rows, {
        "no_assistance": [],
        "glasses": ["g-na-1"],  # wrong condition for this group
    })
    result = build_questionnaire_analysis(scale="srcc", mode="two_conditions", rows=filtered)
    # row condition is "no_assistance" but filter only allows g-na-1 under "glasses" → excluded
    assert result.total_entries == 0


def test_group_filter_three_conditions_partial_selection() -> None:
    from app.questionnaire import _compute_pcs_result  # type: ignore[import]

    def _pcs_row_with_group(user_id: str, group_id: str, condition: str, scores: dict[str, int]):
        return {
            "user_id": user_id,
            "group_id": group_id,
            "condition": condition,
            "srcc_responses": None,
            "srcc_result": None,
            "pcs_responses": scores,
            "pcs_result": _compute_pcs_result(scores),
        }

    rows = [
        _pcs_row_with_group("u1", "g-na", "no_assistance", _pcs_scores(5)),
        _pcs_row_with_group("u2", "g-gl", "glasses", _pcs_scores(6)),
        _pcs_row_with_group("u3", "g-app-1", "app_notification", _pcs_scores(4)),
        _pcs_row_with_group("u4", "g-app-2", "app_notification", _pcs_scores(5)),  # excluded
    ]
    filtered = _simulate_group_filter(rows, {
        "no_assistance": ["g-na"],
        "glasses": ["g-gl"],
        "app_notification": ["g-app-1"],  # only one of two app groups
    })
    result = build_questionnaire_analysis(scale="pcs", mode="three_conditions", rows=filtered)
    assert result.total_entries == 3
    assert result.entries_by_condition["app_notification"] == 1
