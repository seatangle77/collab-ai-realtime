from __future__ import annotations

from pathlib import Path
import sys

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.analysis.task_score_config import TASK_SCORE_CONFIG
from app.analysis.task_score_service import (
    TaskScoreAnswers,
    TaskScoreGroupAnswer,
    TaskScoreIndividualAnswer,
    calculate_task_score_result,
)


def _expert_order(task_id: str) -> list[str]:
    return [
        item["key"]
        for item in sorted(TASK_SCORE_CONFIG[task_id]["items"], key=lambda item: item["expert_rank"])
    ]


def test_calculate_task_score_result_for_perfect_answers() -> None:
    ordered_items = _expert_order("moon_survival")
    answers = TaskScoreAnswers(
        individual=[
            TaskScoreIndividualAnswer(participant_id="u1", participant_name="A", ordered_items=ordered_items),
            TaskScoreIndividualAnswer(participant_id="u2", participant_name="B", ordered_items=ordered_items),
            TaskScoreIndividualAnswer(participant_id="u3", participant_name="C", ordered_items=ordered_items),
        ],
        group_final=TaskScoreGroupAnswer(ordered_items=ordered_items),
    )

    result = calculate_task_score_result("moon_survival", answers)

    assert [item.score for item in result.individual_scores] == [0, 0, 0]
    assert result.ais == 0
    assert result.best_is == 0
    assert result.gs == 0
    assert result.weak_synergy == 0
    assert result.strong_synergy == 0


def test_calculate_task_score_result_synergy_values() -> None:
    expert = _expert_order("winter_survival")
    reversed_order = list(reversed(expert))
    answers = TaskScoreAnswers(
        individual=[
            TaskScoreIndividualAnswer(participant_id="u1", ordered_items=reversed_order),
            TaskScoreIndividualAnswer(participant_id="u2", ordered_items=reversed_order),
            TaskScoreIndividualAnswer(participant_id="u3", ordered_items=expert),
        ],
        group_final=TaskScoreGroupAnswer(ordered_items=expert),
    )

    result = calculate_task_score_result("winter_survival", answers)

    assert result.gs == 0
    assert result.best_is == 0
    assert result.weak_synergy > 0
    assert result.strong_synergy == 0


def test_calculate_task_score_result_rejects_duplicate_items() -> None:
    expert = _expert_order("lost_at_sea")
    bad_order = [expert[0], *expert[:-1]]
    answers = TaskScoreAnswers(
        individual=[
            TaskScoreIndividualAnswer(participant_id="u1", ordered_items=bad_order),
            TaskScoreIndividualAnswer(participant_id="u2", ordered_items=expert),
            TaskScoreIndividualAnswer(participant_id="u3", ordered_items=expert),
        ],
        group_final=TaskScoreGroupAnswer(ordered_items=expert),
    )

    with pytest.raises(ValueError, match="重复物品"):
        calculate_task_score_result("lost_at_sea", answers)

