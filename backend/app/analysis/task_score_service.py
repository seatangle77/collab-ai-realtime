from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from ..api_model import ApiModel
from .task_score_config import TASK_SCORE_CONFIG, get_task_score_config


class TaskScoreIndividualAnswer(ApiModel):
    participant_id: str
    participant_name: str | None = None
    ordered_items: list[str]


class TaskScoreGroupAnswer(ApiModel):
    ordered_items: list[str]


class TaskScoreAnswers(ApiModel):
    individual: list[TaskScoreIndividualAnswer] = Field(min_length=3, max_length=3)
    group_final: TaskScoreGroupAnswer


class TaskScoreIndividualResult(ApiModel):
    participant_id: str
    participant_name: str | None = None
    score: int


class TaskScoreResult(ApiModel):
    individual_scores: list[TaskScoreIndividualResult]
    ais: float
    best_is: int
    best_participant_id: str
    gs: int
    weak_synergy: float
    strong_synergy: int
    item_count: int
    score_direction: str = "lower_is_better"


def _validate_ordered_items(task_id: str, ordered_items: list[str], label: str) -> None:
    if task_id not in TASK_SCORE_CONFIG:
        raise ValueError(f"task_id 无效: {task_id}")
    config = get_task_score_config(task_id)
    valid_keys = {item["key"] for item in config["items"]}
    item_count = config["item_count"]

    if len(ordered_items) != item_count:
        raise ValueError(f"{label} 需要填写 {item_count} 个物品")

    unique_items = set(ordered_items)
    if len(unique_items) != len(ordered_items):
        raise ValueError(f"{label} 存在重复物品")

    invalid_items = sorted(unique_items - valid_keys)
    if invalid_items:
        raise ValueError(f"{label} 包含不属于 {task_id} 的物品: {invalid_items}")


def validate_task_score_answers(task_id: str, answers: TaskScoreAnswers) -> None:
    participant_ids = [answer.participant_id for answer in answers.individual]
    if len(set(participant_ids)) != len(participant_ids):
        raise ValueError("个人答案中 participant_id 不能重复")

    for index, answer in enumerate(answers.individual, start=1):
        _validate_ordered_items(task_id, answer.ordered_items, f"成员 {index}")
    _validate_ordered_items(task_id, answers.group_final.ordered_items, "小组最终")


def _score_ordered_items(task_id: str, ordered_items: list[str]) -> int:
    config = get_task_score_config(task_id)
    expert_ranks = {item["key"]: item["expert_rank"] for item in config["items"]}
    return sum(
        abs(rank_order - expert_ranks[item_key])
        for rank_order, item_key in enumerate(ordered_items, start=1)
    )


def calculate_task_score_result(task_id: str, answers: TaskScoreAnswers) -> TaskScoreResult:
    validate_task_score_answers(task_id, answers)
    config = get_task_score_config(task_id)

    individual_scores = [
        TaskScoreIndividualResult(
            participant_id=answer.participant_id,
            participant_name=answer.participant_name,
            score=_score_ordered_items(task_id, answer.ordered_items),
        )
        for answer in answers.individual
    ]
    gs = _score_ordered_items(task_id, answers.group_final.ordered_items)
    ais = sum(item.score for item in individual_scores) / len(individual_scores)
    best = min(individual_scores, key=lambda item: item.score)

    return TaskScoreResult(
        individual_scores=individual_scores,
        ais=round(ais, 2),
        best_is=best.score,
        best_participant_id=best.participant_id,
        gs=gs,
        weak_synergy=round(ais - gs, 2),
        strong_synergy=best.score - gs,
        item_count=config["item_count"],
    )


class TaskScoreEntryPayload(ApiModel):
    group_id: str
    task_id: str
    answers: TaskScoreAnswers

    @model_validator(mode="after")
    def validate_answers_for_task(self) -> "TaskScoreEntryPayload":
        validate_task_score_answers(self.task_id, self.answers)
        return self


def model_to_jsonable(value: ApiModel) -> dict[str, Any]:
    return value.model_dump(mode="json")
