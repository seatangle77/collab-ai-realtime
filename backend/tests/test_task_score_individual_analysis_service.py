from __future__ import annotations

from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.analysis.task_score_individual_analysis_service import build_task_score_individual_analysis


def _row(
    entry_id: str,
    condition: str,
    task_id: str,
    scores: tuple[float, float, float],
) -> dict:
    individual_scores = [
        {
            "participant_id": f"p-{entry_id}-{index}",
            "participant_name": f"成员{index}",
            "score": score,
        }
        for index, score in enumerate(scores, start=1)
    ]
    return {
        "id": entry_id,
        "group_id": f"g-{entry_id}",
        "task_id": task_id,
        "condition": condition,
        "result_json": {
            "individual_scores": individual_scores,
            "ais": round(sum(scores) / 3, 2),
        },
    }


def test_expands_each_group_to_three_individuals() -> None:
    result = build_task_score_individual_analysis(
        mode="two_conditions",
        task_id="all",
        rows=[
            _row("1", "no_assistance", "moon_survival", (10, 12, 14)),
            _row("2", "glasses", "moon_survival", (8, 9, 10)),
        ],
    )

    assert result.total_groups == 2
    assert result.total_individuals == 6
    assert result.groups_by_condition == {"no_assistance": 1, "glasses": 1}
    assert result.individuals_by_condition == {"no_assistance": 3, "glasses": 3}
    assert result.ais_consistency.status == "ok"


def test_individual_condition_mean_matches_mean_group_ais() -> None:
    rows = [
        _row("1", "no_assistance", "moon_survival", (9, 12, 15)),
        _row("2", "no_assistance", "lost_at_sea", (15, 18, 21)),
        _row("3", "glasses", "moon_survival", (6, 9, 12)),
        _row("4", "glasses", "lost_at_sea", (12, 15, 18)),
    ]
    result = build_task_score_individual_analysis(mode="two_conditions", task_id="all", rows=rows)

    no_assistance = next(item for item in result.individual_stats if item.condition == "no_assistance")
    expected = sum(row["result_json"]["ais"] for row in rows[:2]) / 2
    assert no_assistance.mean == expected


def test_task_filter_and_condition_mode_are_respected() -> None:
    result = build_task_score_individual_analysis(
        mode="two_conditions",
        task_id="moon_survival",
        rows=[
            _row("1", "no_assistance", "moon_survival", (10, 12, 14)),
            _row("2", "glasses", "moon_survival", (8, 9, 10)),
            _row("3", "app_notification", "moon_survival", (5, 6, 7)),
            _row("4", "glasses", "winter_survival", (20, 21, 22)),
        ],
    )

    assert result.total_groups == 2
    assert {item.task_id for item in result.observations} == {"moon_survival"}
    assert {item.condition for item in result.observations} == {"no_assistance", "glasses"}


def test_invalid_group_is_excluded_without_affecting_valid_groups() -> None:
    invalid = _row("bad", "no_assistance", "moon_survival", (10, 12, 14))
    invalid["result_json"]["individual_scores"] = invalid["result_json"]["individual_scores"][:2]
    result = build_task_score_individual_analysis(
        mode="two_conditions",
        task_id="all",
        rows=[invalid, _row("ok", "glasses", "moon_survival", (8, 9, 10))],
    )

    assert result.total_groups == 1
    assert result.total_individuals == 3
    assert len(result.excluded_entries) == 1
    assert result.excluded_entries[0].reason == "invalid_individual_scores"


def test_ais_mismatch_is_flagged_and_excluded() -> None:
    invalid = _row("bad", "no_assistance", "moon_survival", (10, 12, 14))
    invalid["result_json"]["ais"] = 99
    result = build_task_score_individual_analysis(
        mode="two_conditions",
        task_id="all",
        rows=[invalid, _row("ok", "glasses", "moon_survival", (8, 9, 10))],
    )

    assert result.total_groups == 1
    assert result.ais_consistency.status == "warning"
    assert any(item.reason == "ais_mismatch" for item in result.excluded_entries)


def test_cluster_permutation_test_uses_groups_and_returns_result() -> None:
    rows = []
    for index in range(4):
        rows.append(_row(f"n{index}", "no_assistance", "moon_survival", (28 + index, 30 + index, 32 + index)))
        rows.append(_row(f"g{index}", "glasses", "moon_survival", (8 + index, 10 + index, 12 + index)))
    result = build_task_score_individual_analysis(mode="two_conditions", task_id="all", rows=rows)

    assert result.statistical_test.status == "ok"
    assert result.statistical_test.cluster_unit == "group"
    assert result.statistical_test.p_value is not None
    assert result.statistical_test.effect_size is not None


def test_three_conditions_return_holm_adjusted_pairwise_tests() -> None:
    rows = []
    for index in range(4):
        rows.append(_row(f"n{index}", "no_assistance", "moon_survival", (28 + index, 30 + index, 32 + index)))
        rows.append(_row(f"g{index}", "glasses", "moon_survival", (18 + index, 20 + index, 22 + index)))
        rows.append(_row(f"a{index}", "app_notification", "moon_survival", (8 + index, 10 + index, 12 + index)))
    result = build_task_score_individual_analysis(mode="three_conditions", task_id="all", rows=rows)

    assert len(result.pairwise_tests) == 3
    assert all(item.p_value_adjusted is not None for item in result.pairwise_tests)
    assert all(item.mean_difference is not None for item in result.pairwise_tests)


if __name__ == "__main__":
    tests = [value for name, value in globals().items() if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
    print(f"{len(tests)} individual task-score tests passed")
