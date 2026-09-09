"""Recording-first final documents; correspondence never controls text coverage."""
from __future__ import annotations

import copy
import hashlib
import json
import uuid
from collections import Counter
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..api_model import ApiModel
from ..db import get_db
from .deps import require_admin
from .recording_placement import place_recording
from .recording_document_metadata import PREFIX, encode_document, decode_document
from .transcript_alignment import _load_alignment_source, _load_run, _relative_seconds

router = APIRouter(prefix="/api/admin/transcript-corrections", tags=["recording-final-versions"], dependencies=[Depends(require_admin)])


class PreviewIn(ApiModel):
    start_transcript_id: str | None = None
    end_transcript_id: str | None = None
    alignment_run_id: str | None = None
    alignment_offset_seconds: float | None = None


class SaveIn(PreviewIn):
    source_hash: str
    preview_hash: str
    boundary_confirmed: bool = True
    base_version_id: str | None = None
    created_by: str | None = Field(default=None, max_length=200)


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def source_hash(refs, live):
    # Ignore legacy correction metadata; source text, order, times and speakers matter.
    return digest({"recording": refs, "live": [{k: item.get(k) for k in
        ("transcript_id", "text", "speaker_name", "speaker_key", "relative_seconds", "position")}
        for item in live]})


def compose_document(session_id, refs, live, start_id, end_id, run=None, offset=None):
    if not refs:
        raise HTTPException(409, "该会话没有录音文字，无法生成最终正文")
    placements, auto_start, auto_end = place_recording(refs, live, (run or {}).get('matches', []) if (run or {}).get('session_id') == session_id else [], offset)
    automatic = start_id is None or end_id is None
    if automatic:start_id,end_id=auto_start,auto_end
    indexes = {item["transcript_id"]: index for index, item in enumerate(live)}
    if start_id not in indexes or end_id not in indexes:
        raise HTTPException(409, "替换起止位置已变化，请重新选择")
    start, end = indexes[start_id], indexes[end_id]
    if start > end:
        raise HTTPException(422, "替换终点不能早于起点")
    inside = {item["transcript_id"]: item for item in live[start:end + 1]}
    by_order = {item["order_index"]: item for item in refs}
    links: dict[int, list[dict]] = {}
    if run and run.get("session_id") == session_id:
        for match in run.get("matches", []):
            orders, ids = match.get("reference_orders", []), match.get("transcript_ids", [])
            if not orders or not ids or not set(orders).issubset(by_order) or not set(ids).issubset(inside):
                continue
            expected = "\n".join(by_order[o]["content"].strip() for o in orders)
            original = match.get("_reference_source_text", match.get("corrected_text", ""))
            if original != expected:
                continue  # Stale or invented correspondence cannot annotate current text.
            for order in orders:
                links.setdefault(order, []).append(match)
    def original(item, part):
        return {"id": item["transcript_id"], "kind": part, "text": item["text"],
                "speaker_name": item["speaker_name"], "time": item["relative_seconds"],
                "transcript_ids": [item["transcript_id"]], "correspondence_status": "original"}
    segments = [original(item, "before") for item in live[:start]]
    pending = 0
    for ref in refs:
        candidates = links.get(ref["order_index"], [])
        ids = list(dict.fromkeys(i for match in candidates for i in match["transcript_ids"]))
        speakers = {inside[i].get("speaker_key") or inside[i]["speaker_name"] for i in ids}
        certain = bool(ids) and len(speakers) == 1 and all(not m.get("review_required") and m.get("confidence_level") != "low" for m in candidates)
        placement = next((p for p in placements if p['reference_order'] == ref['order_index']), None)
        status = "linked" if certain else "grouped"
        if not certain:
            ids = [i for i in (placement or {}).get('transcript_ids', []) if i in inside]
            if not ids: ids = [start_id]

        known_names = {r.get('speaker_name') for r in live} - {None, '', '未知说话人'}
        guess = (run or {}).get('speaker_guesses', {}).get(str(ref['order_index'])) if (run or {}).get('session_id') == session_id else None
        speaker = guess if guess in known_names else None
        speaker_method = 'ai_estimate' if speaker else 'matched'
        if not speaker:
            candidates_names = [inside[i]['speaker_name'] for i in ids if inside[i].get('speaker_name') in known_names]
            if candidates_names:speaker = Counter(candidates_names).most_common(1)[0][0]
            if not speaker and known_names:
                position = next((i for i,r in enumerate(live) if r['transcript_id'] == ids[0]), 0)
                neighbors = sorted(enumerate(live), key=lambda p:abs(p[0]-position))
                speaker = next((r['speaker_name'] for _,r in neighbors if r.get('speaker_name') in known_names), None)
            if not certain:speaker_method = 'context_estimate'
        pending += int(not certain)
        segments.append({"id": f"recording-{ref['order_index']}", "kind": "recording",
                         "recording_order": ref["order_index"], "text": ref["content"],
                         "time": ref["start_time"], "speaker_name": speaker, "speaker_assignment": speaker_method,
                         "transcript_ids": ids, "correspondence_status": status})
    segments.extend(original(item, "after") for item in live[end + 1:])
    # Every recording row enters exactly once, as-is, independently of the AI result.
    recording = [item for item in segments if item["kind"] == "recording"]
    if [(item['recording_order'], item['text']) for item in recording] != [(item['order_index'], item['content']) for item in refs]:
        raise HTTPException(500, "录音正文完整性检查失败")
    doc = {"session_id": session_id, "start_transcript_id": start_id, "end_transcript_id": end_id,
           "segments": segments, "recording_count": len(refs), "pending_count": pending,
           "replaced_count": end - start + 1, "before_count": start, "after_count": len(live) - end - 1,
           "source_hash": source_hash(refs, live)}
    doc["preview_hash"] = digest(doc)
    return doc


async def latest(db, session_id):
    rows = (await db.execute(text("""
        SELECT c.id, c.corrected_text, c.correction_reason,
               c.corrected_by AS created_by, c.updated_at AS created_at
        FROM speech_transcript_corrections c
        WHERE c.correction_reason LIKE :prefix
          AND EXISTS (
              SELECT 1 FROM speech_transcript_correction_members m
              JOIN speech_transcripts t ON t.transcript_id = m.transcript_id
              WHERE m.correction_id = c.id AND t.session_id = :session_id
          )
        ORDER BY c.updated_at DESC, c.id DESC
    """), {"session_id": session_id, "prefix": PREFIX + '%'})).mappings().all()
    for row in rows:
        doc = decode_document(row['correction_reason'], row['corrected_text'])
        if doc and doc.get('session_id') == session_id:
            return {"id": row['id'], "document": doc, "created_by": row['created_by'], "created_at": row['created_at']}
    return None


@router.get("/sessions/{session_id}/final-version/source")
async def get_source(session_id: str, db: AsyncSession = Depends(get_db)):
    _, refs, live = await _load_alignment_source(db, session_id)
    return {"recording": refs, "transcripts": live, "source_hash": source_hash(refs, live)}


@router.get("/sessions/{session_id}/final-version")
async def get_final_version(session_id: str, db: AsyncSession = Depends(get_db)):
    session = (await db.execute(text("""
        SELECT cs.started_at, cs.created_at FROM chat_sessions cs
        JOIN groups g ON g.id = cs.group_id
        WHERE cs.id = :session_id AND g.condition IN ('glasses', 'app_notification')
    """), {'session_id': session_id})).mappings().first()
    if not session:
        raise HTTPException(404, '辅助条件会话不存在')
    version = await latest(db, session_id)
    live = []
    if version and any(s['kind'] == 'recording' and not s.get('speaker_name') for s in version['document']['segments']):
        # Older saved results may need names, but never load recording or correction bodies.
        live = (await db.execute(text("""
            SELECT t.transcript_id, COALESCE(u.name,t.speaker,'未知说话人') AS speaker_name,
                   COALESCE(t.start,t.created_at) AS source_time
            FROM speech_transcripts t
            LEFT JOIN users_info u ON u.id = COALESCE(t.speaker_user_id,t.user_id,NULLIF(BTRIM(t.speaker),''))
            WHERE t.session_id = :session_id ORDER BY t.start NULLS LAST,t.created_at,t.transcript_id
        """), {'session_id': session_id})).mappings().all()
        live = [{**dict(row), 'relative_seconds': _relative_seconds(row['source_time'], session['started_at'] or session['created_at'])} for row in live]
    if version:
        version = copy.deepcopy(version)
        by_id = {r['transcript_id']: r for r in live}
        known = [r for r in live if r.get('speaker_name') not in (None, '', '未知说话人')]
        for segment in version['document']['segments']:
            if segment['kind'] != 'recording' or segment.get('speaker_name'):
                continue
            candidates = [by_id[i] for i in segment.get('transcript_ids', []) if i in by_id and by_id[i] in known]
            if not candidates and known:
                timestamp = segment.get('time')
                candidates = [min(known, key=lambda r: abs((r.get('relative_seconds') or 0)-(timestamp or 0)))]
            if candidates:
                segment['speaker_name'] = Counter(r['speaker_name'] for r in candidates).most_common(1)[0][0]
                segment['speaker_assignment'] = 'context_estimate'
    return version


async def make_preview(db, session_id, payload):
    _, refs, live = await _load_alignment_source(db, session_id)
    run = await _load_run(payload.alignment_run_id) if payload.alignment_run_id else None
    doc = compose_document(session_id, refs, live, payload.start_transcript_id, payload.end_transcript_id, run, payload.alignment_offset_seconds if payload.alignment_offset_seconds is not None else (run or {}).get('alignment_offset_seconds'))
    if payload.start_transcript_id is None or payload.end_transcript_id is None:
        indexes = {r['transcript_id']: i for i, r in enumerate(live)}
        left, right = indexes[doc['start_transcript_id']], indexes[doc['end_transcript_id']]
        # Keep an existing merged correction intact when replacing its range.
        while True:
            correction_ids = {r.get('existing_correction_id') for r in live[left:right+1]} - {None}
            positions = [i for i,r in enumerate(live) if r.get('existing_correction_id') in correction_ids]
            next_left, next_right = min([left]+positions), max([right]+positions)
            if (next_left,next_right)==(left,right):break
            left,right=next_left,next_right
        doc = compose_document(session_id, refs, live, live[left]['transcript_id'], live[right]['transcript_id'], run, payload.alignment_offset_seconds if payload.alignment_offset_seconds is not None else (run or {}).get('alignment_offset_seconds'))
    # Detect edits to existing corrections between preview and save as well.
    doc['corrections_hash'] = digest([(r['transcript_id'], r.get('existing_correction_id'), r.get('manual_corrected_text')) for r in live])
    doc['preview_hash'] = digest({k: v for k, v in doc.items() if k != 'preview_hash'})
    return doc


@router.post("/sessions/{session_id}/final-version/preview")
async def preview_final_version(session_id: str, payload: PreviewIn, db: AsyncSession = Depends(get_db)):
    return await make_preview(db, session_id, payload)


@router.post("/sessions/{session_id}/final-version")
async def save_final_version(session_id: str, payload: SaveIn, db: AsyncSession = Depends(get_db)):
    # Serialize saves and lock source rows against concurrent correction FK writes.
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:session_id))"), {"session_id": session_id})
    await db.execute(text("SELECT transcript_id FROM speech_transcripts WHERE session_id = :session_id ORDER BY transcript_id FOR UPDATE"), {"session_id": session_id})
    await db.execute(text("""
        SELECT c.id FROM speech_transcript_corrections c
        WHERE EXISTS (SELECT 1 FROM speech_transcript_correction_members m
          JOIN speech_transcripts t ON t.transcript_id = m.transcript_id
          WHERE m.correction_id = c.id AND t.session_id = :session_id)
        ORDER BY c.id FOR UPDATE OF c
    """), {'session_id': session_id})
    current = await latest(db, session_id)
    if (current["id"] if current else None) != payload.base_version_id:
        raise HTTPException(409, "已有新的保存版本，请刷新后再保存")
    doc = await make_preview(db, session_id, payload)
    if doc["source_hash"] != payload.source_hash:
        raise HTTPException(409, "录音或实时转写已变化，请刷新来源并重新预览")
    if doc["preview_hash"] != payload.preview_hash:
        raise HTTPException(409, "对应信息已变化，请重新预览后保存")
    _, _, live = await _load_alignment_source(db, session_id)
    indexes = {r['transcript_id']: i for i, r in enumerate(live)}
    ids = [r['transcript_id'] for r in live[indexes[doc['start_transcript_id']]:indexes[doc['end_transcript_id']] + 1]]
    # Include every member of each occupied correction before deciding to replace it.
    occupied = (await db.execute(text("""
        SELECT c.id, m.transcript_id
        FROM speech_transcript_corrections c
        JOIN speech_transcript_correction_members m ON m.correction_id = c.id
        WHERE c.id IN (
            SELECT correction_id FROM speech_transcript_correction_members
            WHERE transcript_id = ANY(:ids)
        ) OR c.transcript_id = ANY(:ids)
        ORDER BY c.id, m.order_index
        FOR UPDATE OF c
    """), {'ids': ids})).mappings().all()
    if any(r['transcript_id'] not in ids for r in occupied):
        raise HTTPException(409, '已有合并修订跨越替换边界，请调整起止位置以包含该合并修订')
    old_ids = list(dict.fromkeys(r['id'] for r in occupied))
    if current and current['id'] not in old_ids:
        raise HTTPException(409, '新的替换范围需要包含已保存的录音修订范围，请调整起止位置')
    ident = 'stc' + uuid.uuid4().hex[:12]
    # All deletes and inserts share one transaction. Failures restore old corrections.
    try:
        if old_ids:
            await db.execute(text('DELETE FROM speech_transcript_corrections WHERE id = ANY(:ids)'), {'ids': old_ids})
        row = (await db.execute(text("""
            INSERT INTO speech_transcript_corrections
                (id, transcript_id, corrected_text, correction_reason, corrected_by, created_at, updated_at)
            VALUES (:id, NULL, :corrected_text, :reason, :created_by, NOW(), NOW())
            RETURNING created_at
        """), {'id': ident, 'corrected_text': '\n'.join(s['text'] for s in doc['segments'] if s['kind'] == 'recording'),
               'reason': encode_document(doc), 'created_by': payload.created_by})).mappings().one()
        await db.execute(text("""
            INSERT INTO speech_transcript_correction_members (correction_id, transcript_id, order_index)
            VALUES (:correction_id, :transcript_id, :order_index)
        """), [{'correction_id': ident, 'transcript_id': value, 'order_index': i} for i, value in enumerate(ids)])
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return {'id': ident, 'document': doc, 'created_by': payload.created_by, 'created_at': row['created_at']}
