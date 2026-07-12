"""Pure in-memory checks for multi-label CoI metrics (no database access)."""
from __future__ import annotations

from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.analysis.coi_analysis_service import _compute_session_observation


def test_multicode_counts_and_unit_ratios() -> None:
    observation = _compute_session_observation(
        "session-1",
        "group-1",
        "no_assistance",
        [
            {"coi_categories": ["TE", "IN"]},
            {"coi_categories": ["EX"]},
            {"coi_categories": ["IN", "RE"]},
        ],
    )

    assert observation.unit_count == 3
    assert observation.total_count == 5
    assert observation.te_count == 1
    assert observation.ex_count == 1
    assert observation.in_count == 2
    assert observation.re_count == 1
    assert observation.multi_coded_count == 2
    assert observation.mixed_order_unit_ratio == 0.3333
    assert observation.multi_coded_unit_ratio == 0.6667
    assert observation.weighted_score == 2.5


def test_duplicate_categories_do_not_double_count() -> None:
    observation = _compute_session_observation(
        "session-1",
        "group-1",
        "no_assistance",
        [{"coi_categories": ["TE", "TE", "IN"]}],
    )

    assert observation.total_count == 2
    assert observation.te_count == 1
    assert observation.in_count == 1
