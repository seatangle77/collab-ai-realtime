from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from openai import AsyncOpenAI

from ..settings import QWEN_CHAT_EXTRA_BODY, nlp_settings

logger = logging.getLogger(__name__)


class IcebreakerEvaluationError(RuntimeError):
    pass


ICEBREAKER_MVP_TITLES = [
    "全场最会圆奖",
    "剧情急救员",
    "硬接大师",
    "反转制造机",
    "气氛续命王",
    "临场补设定大师",
]

ICEBREAKER_COMMENTS = [
    "离谱，但居然接住了。",
    "剧情很野，逻辑先下班了。",
    "像临时起意，但气氛是有的。",
    "圆得有点辛苦，不过没崩。",
    "很难评，但确实挺好笑。",
]


def _get_async_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=nlp_settings.qwen_api_key,
        base_url=nlp_settings.qwen_base_url,
    )


def _strip_json_markdown(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


def _fallback_evaluation(turns: list[dict[str, Any]]) -> dict[str, Any]:
    first_user = turns[0] if turns else {}
    return {
        "polished_story": " ".join(str(t.get("text", "")).strip() for t in turns if str(t.get("text", "")).strip()),
        "score": 78,
        "comment": ICEBREAKER_COMMENTS[0],
        "mvp_user_id": first_user.get("user_id", ""),
        "mvp_title": ICEBREAKER_MVP_TITLES[0],
        "mvp_reason": "一句话把快散架的剧情扶住了。",
    }


_SYSTEM_PROMPT = (
    "你是一个懂年轻人语气的破冰游戏点评员。"
    "根据三人小组的故事接龙内容，生成轻松、短、像朋友吐槽的评价。"
    "不要像老师点评，不要写长文，不要说教。"
    "必须从给定成员里选一个 MVP，mvp_user_id 必须真实存在。"
    "只返回 JSON，不要 markdown。"
)

_USER_TEMPLATE = (
    "故事开头：{story_opening}\n\n"
    "成员：\n{members}\n\n"
    "故事接龙记录：\n{turns}\n\n"
    "请输出 JSON：\n"
    "{{\n"
    '  "polished_story": "把6段接龙整理成一段顺畅中文故事，去掉口头禅和重复，但保留原意",\n'
    '  "score": 65到95之间的整数,\n'
    '  "comment": "一句中文短评，8到18字，像朋友吐槽",\n'
    '  "mvp_user_id": "获奖成员user_id",\n'
    '  "mvp_title": "称号，例如全场最会圆奖/剧情急救员/硬接大师",\n'
    '  "mvp_reason": "一句中文理由，12到24字"\n'
    "}}"
)


def _format_members(members: list[dict[str, Any]]) -> str:
    lines = []
    for member in members:
        user_id = str(member.get("user_id", "")).strip()
        name = str(member.get("user_name") or user_id).strip()
        if user_id:
            lines.append(f"- {name} ({user_id})")
    return "\n".join(lines) or "（无成员）"


def _format_turns(turns: list[dict[str, Any]]) -> str:
    lines = []
    for turn in turns:
        user_id = str(turn.get("user_id", "")).strip()
        name = str(turn.get("user_name") or user_id).strip()
        round_no = turn.get("round", "?")
        turn_index = turn.get("turn_index", "?")
        text = str(turn.get("text", "")).strip()
        lines.append(f"- 第{round_no}轮 第{turn_index}棒 {name}({user_id})：{text}")
    return "\n".join(lines) or "（暂无接龙内容）"


def _brief_turns(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    brief: list[dict[str, Any]] = []
    for turn in turns:
        text = str(turn.get("text", "")).strip()
        brief.append(
            {
                "user_id": turn.get("user_id"),
                "user_name": turn.get("user_name"),
                "round": turn.get("round"),
                "turn_index": turn.get("turn_index"),
                "text_len": len(text),
                "text_preview": text[:60],
            }
        )
    return brief


def _normalize_result(result: dict[str, Any], turns: list[dict[str, Any]]) -> dict[str, Any]:
    valid_user_ids = {str(t.get("user_id", "")).strip() for t in turns if str(t.get("user_id", "")).strip()}
    fallback = _fallback_evaluation(turns)

    try:
        score = int(result.get("score", fallback["score"]))
    except (TypeError, ValueError):
        score = fallback["score"]
    score = max(0, min(100, score))

    comment = str(result.get("comment") or fallback["comment"]).strip()[:40]
    polished_story = str(result.get("polished_story") or "").strip()
    if not polished_story:
        polished_story = " ".join(str(t.get("text", "")).strip() for t in turns if str(t.get("text", "")).strip())
    polished_story = polished_story[:800]
    mvp_user_id = str(result.get("mvp_user_id") or fallback["mvp_user_id"]).strip()
    if valid_user_ids and mvp_user_id not in valid_user_ids:
        mvp_user_id = fallback["mvp_user_id"]

    mvp_title = str(result.get("mvp_title") or fallback["mvp_title"]).strip()[:24]
    mvp_reason = str(result.get("mvp_reason") or fallback["mvp_reason"]).strip()[:60]

    return {
        "polished_story": polished_story,
        "score": score,
        "comment": comment,
        "mvp_user_id": mvp_user_id,
        "mvp_title": mvp_title,
        "mvp_reason": mvp_reason,
    }


async def evaluate_icebreaker_story(
    *,
    story_opening: str,
    members: list[dict[str, Any]],
    turns: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    破冰专用 AI 评价。无状态，不入库，不依赖正式讨论分析链路。
    """
    if not turns:
        raise IcebreakerEvaluationError("empty_turns")

    run_id = f"ib-ai-{uuid.uuid4().hex[:8]}"
    logger.info(
        "[IcebreakerAI] evaluate request run_id=%s story_len=%d members=%s turns=%s",
        run_id,
        len(story_opening or ""),
        [{"user_id": m.get("user_id"), "user_name": m.get("user_name")} for m in members],
        _brief_turns(turns),
    )

    if not nlp_settings.qwen_api_key:
        logger.warning("[IcebreakerAI] NLP_QWEN_API_KEY 未配置，返回兜底评价")
        fallback = _fallback_evaluation(turns)
        logger.info("[IcebreakerAI] evaluate fallback run_id=%s output=%s", run_id, fallback)
        return fallback

    prompt = _USER_TEMPLATE.format(
        story_opening=story_opening or "（无故事开头）",
        members=_format_members(members),
        turns=_format_turns(turns),
    )

    try:
        client = _get_async_client()
        response = await client.chat.completions.create(
            model=nlp_settings.fast_model,
            max_tokens=320,
            extra_body=QWEN_CHAT_EXTRA_BODY,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        raw = _strip_json_markdown(response.choices[0].message.content or "")
        logger.info("[IcebreakerAI] raw response run_id=%s raw=%s", run_id, raw[:1000])
        result = json.loads(raw)
        normalized = _normalize_result(result, turns)
        logger.info("[IcebreakerAI] normalized response run_id=%s output=%s", run_id, normalized)
        return normalized
    except json.JSONDecodeError as exc:
        logger.warning("[IcebreakerAI] JSON 解析失败: %s", exc)
        fallback = _fallback_evaluation(turns)
        logger.info("[IcebreakerAI] evaluate fallback run_id=%s output=%s", run_id, fallback)
        return fallback
    except Exception as exc:
        logger.warning("[IcebreakerAI] 调用失败: %s", exc)
        fallback = _fallback_evaluation(turns)
        logger.info("[IcebreakerAI] evaluate fallback run_id=%s output=%s", run_id, fallback)
        return fallback
