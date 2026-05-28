"""Tests for ENA analysis service.

Run with:
    cd backend
    python -m pytest tests/test_ena_analysis_service.py -v
or directly:
    python tests/test_ena_analysis_service.py
"""
from __future__ import annotations

from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.analysis.ena_analysis_service import (
    build_ena_analysis,
    compute_session_ena_metrics,
)


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

def _utt(order: int, category: str | None, start_time: float | None = None) -> dict:
    return {"order_index": order, "coi_category": category, "start_time": start_time}


def _session_rows(session_id: str, group_id: str, condition: str, utterances: list[dict]) -> list[dict]:
    """Attach session/group/condition metadata to a list of utterances."""
    return [
        {**u, "session_id": session_id, "group_id": group_id, "condition": condition}
        for u in utterances
    ]


# ─────────────────────────────────────────────────────────────────
# compute_session_ena_metrics
# ─────────────────────────────────────────────────────────────────

def test_empty_session_returns_zeros() -> None:
    r = compute_session_ena_metrics([])
    assert r["ex_in_strength"] == 0.0
    assert r["in_re_strength"] == 0.0
    assert r["higher_order_strength"] == 0.0
    assert r["total_windows"] == 0


def test_ex_in_cooccur_same_window() -> None:
    # EX at 0s, IN at 60s — both inside the first 120s window
    utts = [_utt(1, "EX", 0.0), _utt(2, "IN", 60.0)]
    r = compute_session_ena_metrics(utts)
    assert r["ex_in_strength"] > 0.0, "EX and IN should co-occur in the same window"


def test_in_re_not_cooccur_across_window_boundary() -> None:
    # IN at 0s, RE at 200s — more than 120s apart, should never share a window
    utts = [_utt(1, "IN", 0.0), _utt(2, "RE", 200.0)]
    r = compute_session_ena_metrics(utts)
    assert r["in_re_strength"] == 0.0, "IN and RE are more than 120s apart and should not co-occur"


def test_higher_order_all_three_in_window() -> None:
    # EX, IN, RE all within 60s — should produce higher_order_strength > 0
    utts = [_utt(1, "EX", 0.0), _utt(2, "IN", 30.0), _utt(3, "RE", 60.0)]
    r = compute_session_ena_metrics(utts)
    assert r["higher_order_strength"] > 0.0


def test_higher_order_missing_re_is_zero() -> None:
    # EX and IN only — no RE, higher_order must be 0
    utts = [_utt(1, "EX", 0.0), _utt(2, "IN", 30.0)]
    r = compute_session_ena_metrics(utts)
    assert r["higher_order_strength"] == 0.0


def test_null_timestamps_fallback_to_synthetic() -> None:
    # Without start_time, order_index * 30s is used; EX(idx=0→0s) IN(idx=1→30s) → same window
    utts = [_utt(1, "EX", None), _utt(2, "IN", None)]
    r = compute_session_ena_metrics(utts)
    assert r["ex_in_strength"] > 0.0, "Synthetic timestamps should allow co-occurrence detection"


def test_uncoded_utterances_ignored() -> None:
    # NULL coi_category utterances should not affect results
    utts = [_utt(1, None, 0.0), _utt(2, None, 30.0), _utt(3, "EX", 60.0), _utt(4, "IN", 90.0)]
    r = compute_session_ena_metrics(utts)
    assert r["ex_in_strength"] > 0.0


def test_te_does_not_inflate_higher_order() -> None:
    # TE + EX + IN — only two of the three higher-order types present, should be 0
    utts = [_utt(1, "TE", 0.0), _utt(2, "EX", 30.0), _utt(3, "IN", 60.0)]
    r = compute_session_ena_metrics(utts)
    assert r["higher_order_strength"] == 0.0


def test_all_six_edge_weights_present() -> None:
    utts = [_utt(i, cat, float(i * 10)) for i, cat in enumerate(["TE", "EX", "IN", "RE"], 1)]
    r = compute_session_ena_metrics(utts)
    expected_keys = {"TE_EX", "TE_IN", "TE_RE", "EX_IN", "EX_RE", "IN_RE"}
    assert set(r["edge_weights"].keys()) == expected_keys


def test_strengths_are_between_0_and_1() -> None:
    utts = [_utt(i, cat, float(i * 15)) for i, cat in enumerate(["TE", "EX", "IN", "RE", "EX", "IN"], 1)]
    r = compute_session_ena_metrics(utts)
    for key in ("ex_in_strength", "in_re_strength", "higher_order_strength"):
        assert 0.0 <= r[key] <= 1.0, f"{key} out of [0, 1]: {r[key]}"


# ─────────────────────────────────────────────────────────────────
# build_ena_analysis
# ─────────────────────────────────────────────────────────────────

def _make_rows(sessions: list[tuple[str, str, str, list[dict]]]) -> list[dict]:
    """sessions: list of (session_id, group_id, condition, utterances)"""
    rows = []
    for sid, gid, cond, utts in sessions:
        rows.extend(_session_rows(sid, gid, cond, utts))
    return rows


def test_build_filters_irrelevant_conditions() -> None:
    rows = _make_rows([
        ("s1", "g1", "no_assistance", [_utt(1, "EX", 0.0), _utt(2, "IN", 30.0)]),
        ("s2", "g2", "glasses",       [_utt(1, "EX", 0.0), _utt(2, "IN", 30.0)]),
        ("s3", "g3", "app_notification", [_utt(1, "EX", 0.0)]),  # excluded in two_conditions
    ])
    result = build_ena_analysis(mode="two_conditions", rows=rows)
    assert result.total_sessions == 2
    assert result.conditions == ["no_assistance", "glasses"]
    assert "app_notification" not in result.sessions_by_condition or result.sessions_by_condition.get("app_notification", 0) == 0


def test_build_three_conditions() -> None:
    rows = _make_rows([
        ("s1", "g1", "no_assistance",    [_utt(1, "EX", 0.0), _utt(2, "IN", 60.0)]),
        ("s2", "g2", "glasses",          [_utt(1, "EX", 0.0), _utt(2, "IN", 60.0)]),
        ("s3", "g3", "app_notification", [_utt(1, "EX", 0.0), _utt(2, "IN", 60.0)]),
    ])
    result = build_ena_analysis(mode="three_conditions", rows=rows)
    assert result.total_sessions == 3
    assert len(result.conditions) == 3


def test_observations_contain_correct_fields() -> None:
    rows = _make_rows([
        ("s1", "g1", "no_assistance", [_utt(1, "EX", 0.0), _utt(2, "IN", 30.0)]),
    ])
    result = build_ena_analysis(mode="two_conditions", rows=rows)
    assert len(result.observations) == 1
    obs = result.observations[0]
    assert obs.session_id == "s1"
    assert obs.group_id == "g1"
    assert obs.condition == "no_assistance"
    assert 0.0 <= obs.ex_in_strength <= 1.0
    assert obs.total_windows > 0


def test_metrics_summary_has_all_three_metrics() -> None:
    rows = _make_rows([
        ("s1", "g1", "no_assistance", [_utt(1, "EX", 0.0), _utt(2, "IN", 30.0)]),
        ("s2", "g2", "glasses",       [_utt(1, "IN", 0.0), _utt(2, "RE", 30.0)]),
    ])
    result = build_ena_analysis(mode="two_conditions", rows=rows)
    metric_names = {m.metric for m in result.metrics}
    assert metric_names == {"ex_in_strength", "in_re_strength", "higher_order_strength"}


def test_normality_results_count() -> None:
    # 3 metrics × 2 conditions = 6 normality results
    rows = _make_rows([
        ("s1", "g1", "no_assistance", [_utt(1, "EX", 0.0), _utt(2, "IN", 30.0)]),
        ("s2", "g2", "glasses",       [_utt(1, "EX", 0.0), _utt(2, "IN", 30.0)]),
    ])
    result = build_ena_analysis(mode="two_conditions", rows=rows)
    assert len(result.normality) == 6


def test_statistical_tests_count() -> None:
    rows = _make_rows([
        ("s1", "g1", "no_assistance", [_utt(1, "EX", 0.0), _utt(2, "IN", 30.0)]),
        ("s2", "g2", "glasses",       [_utt(1, "EX", 0.0), _utt(2, "IN", 30.0)]),
    ])
    result = build_ena_analysis(mode="two_conditions", rows=rows)
    assert len(result.statistical_tests) == 3  # one per metric


def test_network_data_structure() -> None:
    rows = _make_rows([
        ("s1", "g1", "no_assistance", [_utt(1, "EX", 0.0), _utt(2, "IN", 30.0), _utt(3, "RE", 60.0)]),
        ("s2", "g2", "glasses",       [_utt(1, "EX", 0.0), _utt(2, "IN", 30.0)]),
    ])
    result = build_ena_analysis(mode="two_conditions", rows=rows)
    assert len(result.networks) == 2
    for net in result.networks:
        assert net.nodes == ["TE", "EX", "IN", "RE"]
        assert len(net.edges) == 6  # all 6 pairs
        for edge in net.edges:
            assert 0.0 <= edge.weight <= 1.0


def test_diff_network_only_for_two_conditions() -> None:
    rows = _make_rows([
        ("s1", "g1", "no_assistance", [_utt(1, "EX", 0.0), _utt(2, "IN", 30.0)]),
        ("s2", "g2", "glasses",       [_utt(1, "EX", 0.0), _utt(2, "IN", 30.0)]),
    ])
    result = build_ena_analysis(mode="two_conditions", rows=rows)
    assert result.diff_network is not None
    assert result.diff_network.condition == "diff"
    for edge in result.diff_network.edges:
        assert edge.weight_diff is not None


def test_diff_network_none_for_three_conditions() -> None:
    rows = _make_rows([
        ("s1", "g1", "no_assistance",    [_utt(1, "EX", 0.0), _utt(2, "IN", 30.0)]),
        ("s2", "g2", "glasses",          [_utt(1, "EX", 0.0), _utt(2, "IN", 30.0)]),
        ("s3", "g3", "app_notification", [_utt(1, "EX", 0.0), _utt(2, "IN", 30.0)]),
    ])
    result = build_ena_analysis(mode="three_conditions", rows=rows)
    assert result.diff_network is None


def test_diff_network_direction() -> None:
    # glasses group has strong EX-IN, no_assistance has weak — diff should be positive for EX-IN
    rows = _make_rows([
        ("s1", "g1", "no_assistance", [
            _utt(1, "TE", 0.0), _utt(2, "TE", 30.0),       # mostly TE, weak EX-IN
        ]),
        ("s2", "g2", "glasses", [
            _utt(1, "EX", 0.0), _utt(2, "IN", 30.0),        # strong EX-IN
            _utt(3, "EX", 60.0), _utt(4, "IN", 90.0),
        ]),
    ])
    result = build_ena_analysis(mode="two_conditions", rows=rows)
    diff_ex_in = next(e for e in result.diff_network.edges if e.source == "EX" and e.target == "IN")
    assert diff_ex_in.weight_diff > 0.0, "glasses has stronger EX-IN than no_assistance, diff should be positive"


def test_empty_rows_returns_zero_sessions() -> None:
    result = build_ena_analysis(mode="two_conditions", rows=[])
    assert result.total_sessions == 0
    assert result.sessions_by_condition == {"no_assistance": 0, "glasses": 0}


def test_multiple_sessions_per_condition() -> None:
    rows = _make_rows([
        ("s1", "g1", "no_assistance", [_utt(1, "EX", 0.0), _utt(2, "IN", 30.0)]),
        ("s2", "g1", "no_assistance", [_utt(1, "IN", 0.0), _utt(2, "RE", 30.0)]),
        ("s3", "g2", "glasses",       [_utt(1, "EX", 0.0), _utt(2, "IN", 30.0)]),
        ("s4", "g2", "glasses",       [_utt(1, "IN", 0.0), _utt(2, "RE", 30.0)]),
    ])
    result = build_ena_analysis(mode="two_conditions", rows=rows)
    assert result.total_sessions == 4
    assert result.sessions_by_condition == {"no_assistance": 2, "glasses": 2}


# ─────────────────────────────────────────────────────────────────
# Run directly
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for fn in tests:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
            passed += 1
        except Exception as exc:
            print(f"  FAIL  {fn.__name__}: {exc}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
