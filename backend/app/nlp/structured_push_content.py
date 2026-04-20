from __future__ import annotations

import json
import logging
from typing import Any, Literal

from openai import OpenAI

from ..settings import nlp_settings

logger = logging.getLogger(__name__)

MAX_CONTENT_LENGTH = 30
PERSONAL_STAGNATION = "low_participation"
SHALLOW_DISCUSSION = "shallow_discussion"
GROUP_SILENCE = "group_silence"

SYSTEM_PROMPT = """你是一个小组讨论协作引导助手。

硬性规则：
1. 不要把讨论改写成知识问答、购买建议、泛化推荐或价值排序。生成的问题必须是对已有发言的续接，而不是话题扩展。
2. content 必须能被视为对 anchor 的直接追问：要求理由、条件、例子、边界，或对某个已出现观点表态；不能脱离 anchor 单独成立。
3. anchor 必须是【发言记录】里的原话，不能改写，不能合并多句，必须同时返回说话人 ID。
4. 只返回 JSON，不要输出任何解释。
5. 禁止生成以"吗？"结尾的是非题，必须是让对方有东西可说的开放式追问。
6. 禁止把 anchor 里的具体词泛化成抽象概念，比如把"一个抠一个大方"改写成"消费观差异"，把"leader说什么就做什么"改写成"职场服从性"——这类抽象替换禁止出现在 content 里。"""


def _get_client() -> OpenAI:
    return OpenAI(
        api_key=nlp_settings.qwen_api_key,
        base_url=nlp_settings.qwen_base_url,
    )


def _format_transcript_line(transcript: dict[str, Any]) -> str:
    speaker_name = str(transcript.get("speaker_name") or "").strip()
    speaker_id = str(transcript.get("user_id") or "unknown")
    display = speaker_name if speaker_name else speaker_id
    transcript_id = str(transcript.get("transcript_id") or "").strip()
    text = str(transcript.get("text") or "").strip()
    return f"{display} | {transcript_id} | {text}"


def _transcript_text_for_prompt(transcripts: list[dict[str, Any]]) -> str:
    return "\n".join(
        _format_transcript_line(item)
        for item in transcripts
        if str(item.get("text") or "").strip()
    )


def _get_cond_flags(metrics: dict[str, Any]) -> dict[str, bool]:
    cond_a = isinstance(metrics.get("srep"), (int, float)) and isinstance(metrics.get("info_gain"), (int, float))
    cond_b = isinstance(metrics.get("ttr"), (int, float))
    cond_c = (
        isinstance(metrics.get("arg_density"), (int, float))
        or isinstance(metrics.get("has_reasoning"), bool)
        or isinstance(metrics.get("has_evidence"), bool)
    )
    return {"cond_a": cond_a, "cond_b": cond_b, "cond_c": cond_c}


def _format_percent(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "0"
    return str(round(float(value) * 1000) / 10)


def _number_or_zero(value: Any, digits: int = 3) -> str:
    if not isinstance(value, (int, float)):
        return "0"
    return f"{float(value):.{digits}f}"


def _build_group_silence_prompt(
    silence_s: int,
    transcripts: list[dict[str, Any]],
    summary_text: str,
) -> str:
    transcript_text = _transcript_text_for_prompt(transcripts)
    has_content = bool(transcript_text.strip()) or bool(summary_text.strip())

    if not has_content:
        return ""

    return "\n".join(
        [
            f"【背景】小组已沉默 {silence_s} 秒。",
            "",
            "【当前摘要】",
            summary_text or "（暂无摘要）",
            "",
            "【最近发言（按时间顺序，格式：说话人 | transcript_id | 原话）】",
            transcript_text or "（暂无发言记录）",
            "",
            "【你的任务】",
            "请判断沉默最可能的原因，然后生成一条提示语帮助大家重新投入讨论。判断依据：",
            "- 如果最近有人抛出了观点或问题但没人回应 → 把这个观点点出来，邀请大家回应",
            "- 如果大家观点趋于一致、讨论失去张力 → 提出一个反向视角或追问",
            "- 如果话题已经说得差不多、不知道往哪走 → 基于摘要提出一个新的子问题",
            "- 如果发言很少、讨论还没真正开始 → 给一个具体低门槛的起始问题",
            "",
            “要求：①30字以内；②结尾必须是一个具体问题；③语气自然，像在场的人说话；④必须结合实际讨论内容；⑤不要提及”沉默”或”继续讨论”这类字眼。”,
            "",
            "返回格式（严格 JSON）：",
            "{",
            '  "needs_prompt": true,',
            '  "anchor": null,',
            f'  "content": "生成的提示语，不超过{MAX_CONTENT_LENGTH}字"',
            "}",
        ]
    )


def _build_shallow_prompt(
    user_id: str,
    trigger_metrics: dict[str, Any],
    transcripts: list[dict[str, Any]],
    summary_text: str,
) -> str | None:
    target_quotes = "\n".join(
        _format_transcript_line(item)
        for item in transcripts
        if str(item.get("user_id") or "") == user_id and str(item.get("text") or "").strip()
    )
    if not target_quotes:
        return None

    flags = _get_cond_flags(trigger_metrics)
    issue_labels: list[str] = []
    instruction_parts: list[str] = []

    if flags["cond_a"]:
        issue_labels.append("判断重复")
        instruction_parts.append("可以追问这个判断的前提是什么，或者在什么情况下不成立。")
    if flags["cond_b"]:
        issue_labels.append("表达模糊")
        instruction_parts.append("也可以追问这句话具体指的是什么情况。")
    if flags["cond_c"]:
        issue_labels.append("缺乏论证")
        instruction_parts.append("也可以追问这个判断的依据是什么，或者能否举一个例子支持它。")

    if not issue_labels:
        return None

    diagnosis_parts: list[str] = []
    if flags["cond_a"]:
        diagnosis_parts.append(
            f"Srep={_number_or_zero(trigger_metrics.get('srep'))}（超过0.65）且信息增益={_number_or_zero(trigger_metrics.get('info_gain'))}（低于0.3）"
        )
    if flags["cond_b"]:
        diagnosis_parts.append(f"TTR={_number_or_zero(trigger_metrics.get('ttr'))}（低于0.4）")
    if flags["cond_c"]:
        diagnosis_parts.append(f"论证词密度={_number_or_zero(trigger_metrics.get('arg_density'))}（低于0.02）")

    diagnosis_text = f"该成员同时存在{'、'.join(f'“{label}”' for label in issue_labels)}等问题。{'，'.join(diagnosis_parts)}。"
    task_instruction = (
        "请从【目标成员发言】里选一句最能体现这些问题的话，优先选最近的判断句。"
        + "".join(instruction_parts)
        + "只能围绕他说过的那句话续接，不能引入新话题。"
    )

    return "\n".join(
        [
            "【当前摘要】",
            summary_text,
            "",
            "【最近发言（全体，按时间顺序，格式：speaker_id | transcript_id | 原话）】",
            _transcript_text_for_prompt(transcripts),
            "",
            "【检测结论】",
            diagnosis_text,
            "",
            "【目标成员发言】",
            target_quotes,
            "",
            "【你的任务】",
            task_instruction,
            "",
            "返回格式（严格 JSON）：",
            "{",
            '  "needs_prompt": true/false,',
            '  "anchor": {',
            '    "transcript_id": "原话对应的 transcript id",',
            '    "speaker_id": "说话人 user_id",',
            '    "text": "原话原文"',
            "  },",
            f'  "content": "生成的建议，不超过{MAX_CONTENT_LENGTH}字"',
            "}",
        ]
    )


def _build_personal_stagnation_prompt(
    user_id: str,
    trigger_metrics: dict[str, Any],
    transcripts: list[dict[str, Any]],
    summary_text: str,
    candidate_points: list[dict[str, str]],
) -> str:
    target_display = next(
        (str(t.get("speaker_name") or "").strip() for t in transcripts if str(t.get("user_id") or "") == user_id and str(t.get("speaker_name") or "").strip()),
        user_id or "该成员",
    )
    diagnosis_text = f"该成员过去120秒发言占比 {_format_percent(trigger_metrics.get('speaking_ratio'))}%，低于15%，参与明显减少。"
    task_instruction = (
        f"以下是其他成员说过但 {target_display} 没有回应的发言（候选追问点）。"
        f"请从候选点中选一条，把那条话里最具体的词或情境直接挑出来，问 {target_display} 一个只有他自己能回答的问题。"
        "anchor 必须来自候选追问点里的某一条，不能自己另找角度。"
        "如果候选点都不适合追问，返回 needs_prompt: false。"
        "\n\n【风格参考——说明语气，不是让你照抄句式】\n"
        "anchor: \"leader说什么就做什么挺省心的\"\n"
        "✅ \"你说省心——是真的觉得舒服，还是懒得费那个劲？\"\n"
        "❌ \"你认为职场服从性会影响个人发展吗？\"\n"
        "\n"
        "anchor: \"大城市机会多但压力也大\"\n"
        "✅ \"你说机会多——你自己遇到过哪种机会是在小地方绝对碰不到的？\"\n"
        "❌ \"你认为大城市的发展优势是否值得承受压力？\"\n"
        "\n"
        "anchor: \"旅游搭子最怕一个抠一个大方\"\n"
        "✅ \"你说抠——是那种AA要算到饮料钱的程度，还是只是消费节奏不一样？\"\n"
        "❌ \"你认为消费观差异会影响搭子匹配的成功率吗？\""
    )
    formatted_candidates = "\n".join(
        f"{item.get('speaker_id', '')} | {item.get('transcript_id', '')} | {item.get('text', '')}"
        for item in candidate_points
    )

    return "\n".join(
        [
            "【当前摘要】",
            summary_text,
            "",
            "【最近发言（全体，按时间顺序，格式：speaker_id | transcript_id | 原话）】",
            _transcript_text_for_prompt(transcripts),
            "",
            "【检测结论】",
            diagnosis_text,
            "",
            "【候选追问点】",
            formatted_candidates,
            "",
            "【你的任务】",
            task_instruction,
            "",
            "返回格式（严格 JSON）：",
            "{",
            '  "needs_prompt": true/false,',
            '  "anchor": {',
            '    "transcript_id": "原话对应的 transcript id",',
            '    "speaker_id": "说话人 user_id",',
            '    "text": "原话原文"',
            "  },",
            f'  "content": "生成的建议，不超过{MAX_CONTENT_LENGTH}字"',
            "}",
        ]
    )


def _normalize_anchor(value: Any) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None

    transcript_id = str(value.get("transcript_id") or "").strip()
    speaker_id = str(value.get("speaker_id") or "").strip()
    text = str(value.get("text") or "").strip()
    if not transcript_id or not speaker_id or not text:
        return None
    return {
        "transcript_id": transcript_id,
        "speaker_id": speaker_id,
        "text": text,
    }


def _parse_json_object(text: str) -> dict[str, Any] | None:
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except Exception:
        match_start = text.find("{")
        match_end = text.rfind("}")
        if match_start < 0 or match_end < match_start:
            return None
        try:
            data = json.loads(text[match_start:match_end + 1])
            return data if isinstance(data, dict) else None
        except Exception:
            return None


def _call_model(prompt: str, require_anchor: bool = True) -> dict[str, Any]:
    if not nlp_settings.qwen_api_key:
        return {"needs_prompt": False, "anchor": None, "content": ""}

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=nlp_settings.reasoning_model,
            max_tokens=300,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        raw = response.choices[0].message.content or ""
        parsed = _parse_json_object(raw.strip())
        if not parsed:
            return {"needs_prompt": False, "anchor": None, "content": ""}

        needs_prompt = parsed.get("needs_prompt") is True
        content = str(parsed.get("content") or "").strip()

        if not needs_prompt:
            return {"needs_prompt": False, "anchor": None, "content": ""}
        if not content or len(content) > MAX_CONTENT_LENGTH:
            return {"needs_prompt": False, "anchor": None, "content": ""}

        if require_anchor:
            anchor = _normalize_anchor(parsed.get("anchor"))
            if not anchor:
                return {"needs_prompt": False, "anchor": None, "content": ""}
            return {"needs_prompt": True, "anchor": anchor, "content": content}

        return {"needs_prompt": True, "anchor": None, "content": content}
    except Exception as exc:
        logger.warning("[NLP/structured-push] 调用失败: %s", exc)
        return {"needs_prompt": False, "anchor": None, "content": ""}


def generate_structured_push_content(
    trigger_type: Literal["low_participation", "shallow_discussion", "group_silence"],
    summary: str,
    transcripts: list[dict[str, Any]],
    user_id: str,
    trigger_metrics: dict[str, Any] | None = None,
    candidate_points: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    metrics = trigger_metrics or {}
    points = candidate_points or []

    if trigger_type == GROUP_SILENCE:
        silence_s = int(metrics.get("silence_s") or 30)
        prompt = _build_group_silence_prompt(
            silence_s=silence_s,
            transcripts=transcripts,
            summary_text=summary,
        )
        if not prompt:
            return {"needs_prompt": True, "anchor": None, "content": "先聊聊你们各自最关心的是哪个方面？"}
        logger.info("[NLP/structured-push] input: trigger=%s silence_s=%d transcripts=%d", trigger_type, silence_s, len(transcripts))
        result = _call_model(prompt, require_anchor=False)
        if not result["needs_prompt"] or not result["content"]:
            return {"needs_prompt": True, "anchor": None, "content": "先聊聊你们各自最关心的是哪个方面？"}
        return result

    if trigger_type == SHALLOW_DISCUSSION:
        prompt = _build_shallow_prompt(
            user_id=user_id,
            trigger_metrics=metrics,
            transcripts=transcripts,
            summary_text=summary,
        )
        if not prompt:
            return {"needs_prompt": False, "anchor": None, "content": ""}
        logger.info("[NLP/structured-push] input: trigger=%s user=%s transcripts=%d", trigger_type, user_id, len(transcripts))
        return _call_model(prompt)

    if trigger_type == PERSONAL_STAGNATION:
        if not points:
            return {"needs_prompt": False, "anchor": None, "content": ""}
        prompt = _build_personal_stagnation_prompt(
            user_id=user_id,
            trigger_metrics=metrics,
            transcripts=transcripts,
            summary_text=summary,
            candidate_points=points,
        )
        logger.info(
            "[NLP/structured-push] input: trigger=%s user=%s transcripts=%d candidate_points=%d",
            trigger_type,
            user_id,
            len(transcripts),
            len(points),
        )
        return _call_model(prompt)

    return {"needs_prompt": False, "anchor": None, "content": ""}
