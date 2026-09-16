"""Read-only analysis of saved primary cue labels; no new tables or writes."""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from ..api_model import ApiModel
from ..db import get_db
from ..time_utils import utc_iso
from ..analysis.cue_uptake_analysis_service import build_analysis
from .deps import require_admin
from .cue_uptake_coding import _event_select, _build_event_filters
from .recording_document_metadata import decode_document

router = APIRouter(prefix='/api/admin/cue-uptake-analysis', tags=['admin-cue-uptake-analysis'], dependencies=[Depends(require_admin)])

class Request(ApiModel):
    group_ids: list[str] | None = None
    session_ids: list[str] | None = None
    conditions: list[Literal['glasses', 'app_notification']] = Field(default_factory=lambda: ['glasses', 'app_notification'])
    design: Literal['independent'] = 'independent'

async def load_evidence(db, ids):
    """Resolve selected evidence, retaining saved final-version references."""
    evidence = {}
    originals = [i for i in ids if not i.startswith('final:')]
    if originals:
        rows = (await db.execute(text('''
            SELECT t.transcript_id, t.text AS original_text, t.speaker,
                   c.corrected_text, c.correction_reason, c.id AS correction_id
            FROM speech_transcripts t
            LEFT JOIN speech_transcript_correction_members m ON m.transcript_id=t.transcript_id
            LEFT JOIN speech_transcript_corrections c ON c.id=m.correction_id
            WHERE t.transcript_id = ANY(:ids)
        '''), {'ids': originals})).mappings().all()
        for r in rows:
            document = decode_document(r['correction_reason'], r['corrected_text']) if r['corrected_text'] else None
            if document:
                segments = [s for s in document['segments'] if r['transcript_id'] in (s.get('transcript_ids') or [])]
                content = '\n'.join(f"{s.get('speaker_name') or '未知说话人'}：{s['text']}" for s in segments)
                if not content:
                    content = f"原始发言（修订段落未匹配）：{r['original_text'] or ''}"
            else:
                content = f"{r['speaker'] or '未知说话人'}：{r['corrected_text'] if r['corrected_text'] is not None else r['original_text'] or ''}"
            evidence[r['transcript_id']] = content
    versions = list({i.split(':', 2)[1] for i in ids if i.startswith('final:') and i.count(':') >= 2})
    if versions:
        rows = (await db.execute(text('SELECT id, correction_reason, corrected_text FROM speech_transcript_corrections WHERE id = ANY(:ids)'), {'ids': versions})).mappings().all()
        for r in rows:
            document = decode_document(r['correction_reason'], r['corrected_text'])
            if document:
                for s in document['segments']:
                    evidence[f"final:{r['id']}:{s['id']}"] = f"{s.get('speaker_name') or '未知说话人'}：{s['text']}"
    return evidence

@router.post('/report')
async def report(payload: Request, db: AsyncSession = Depends(get_db)):
    where, params = _build_event_filters(coder_role='primary')
    where += ' AND g.condition = ANY(:conditions)'
    params['conditions'] = payload.conditions
    for field, column in [('group_ids', 'g.id'), ('session_ids', 'pl.session_id')]:
        value = getattr(payload, field)
        if value is not None:
            where += f' AND {column} = ANY(:{field})'
            params[field] = value
    rows = (await db.execute(text(_event_select(where) + ' ORDER BY g.name, pl.session_id, pl.id'), params)).mappings().all()
    ids = {i for r in rows for i in (r.get('coding_evidence_transcript_ids') or [])}
    evidence = await load_evidence(db, ids)
    events = []
    for r in rows:
        event = {k: r.get(k) for k in ('push_log_id', 'session_id', 'session_title', 'group_id', 'group_name', 'condition', 'target_user_name', 'push_content', 'state_type', 'received_at', 'possible_duplicate')}
        selected = list(r.get('coding_evidence_transcript_ids') or [])
        event.update(code=r.get('coding_uptake_code'), evidence_ids=selected,
                     evidence_text='\n'.join(dict.fromkeys(evidence.get(i, f'[证据未找到：{i}]') for i in selected)),
                     missing_evidence_count=sum(i not in evidence for i in selected),
                     coding_reason=r.get('coding_reason'), coded_by=r.get('coding_coded_by'), coded_at=r.get('coding_coded_at'))
        event['received_at'] = utc_iso(event['received_at'])
        event['coded_at'] = utc_iso(event['coded_at'])
        events.append(event)
    try:
        result = build_analysis(events, payload.design)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    result['scope'] = payload.model_dump()
    return result
