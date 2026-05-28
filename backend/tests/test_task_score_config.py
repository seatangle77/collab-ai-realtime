from __future__ import annotations

from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.analysis.task_score_config import TASK_SCORE_CONFIG, validate_task_score_config


def test_task_score_config_is_complete() -> None:
    validate_task_score_config()


def test_task_score_config_contains_expected_tasks() -> None:
    assert set(TASK_SCORE_CONFIG) == {"moon_survival", "lost_at_sea", "winter_survival"}


def test_task_score_config_item_counts() -> None:
    assert TASK_SCORE_CONFIG["moon_survival"]["item_count"] == 15
    assert TASK_SCORE_CONFIG["lost_at_sea"]["item_count"] == 15
    assert TASK_SCORE_CONFIG["winter_survival"]["item_count"] == 12

