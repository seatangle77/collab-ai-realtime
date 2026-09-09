"""Persist final-version exclusions in existing AI correction metadata."""
import json

SCOPE_MARKER = "\n[final-version-excluded]"


def scope_reason(reason: str, excluded_ids: list[str]) -> str:
    if not excluded_ids:
        return reason
    return reason + SCOPE_MARKER + json.dumps(excluded_ids, ensure_ascii=False, separators=(",", ":"))


def excluded_ids_from_reasons(reasons) -> set[str]:
    result = set()
    for reason in reasons:
        if not reason or not reason.startswith("AI 整场匹配") or SCOPE_MARKER not in reason:
            continue
        try:
            ids = json.loads(reason.split(SCOPE_MARKER, 1)[1])
        except (ValueError, TypeError):
            continue
        if isinstance(ids, list):
            result.update(item for item in ids if isinstance(item, str))
    return result


def final_scope_exclusions(matches, live_items):
    assigned = {i for match in matches for i in match["transcript_ids"]}
    positions = [item["position"] for item in live_items if item["transcript_id"] in assigned or item["is_corrected"]]
    if not positions:
        return [], []
    # live_items begins at the user's paired anchor; only the unmatched suffix
    # after the last aligned row is outside the recording-backed final body.
    last = max(positions)
    excluded, outside = [], []
    for item in live_items:
        if item["is_corrected"] or item["transcript_id"] in assigned:
            continue
        (excluded if item["position"] <= last else outside).append(item["transcript_id"])
    return excluded, outside
