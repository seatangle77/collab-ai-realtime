import asyncio
import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import pytest
from fastapi import HTTPException
from backend.app.admin import recording_final_versions as f
from backend.tests.test_transcript_alignment import _reference, _live


def inputs():
    refs = [_reference(i, text, i * 10) for i, text in enumerate(['录音第一句。', '录音第二句。', '录音第三句。'])]
    live = [_live(i, text, i * 10) for i, text in enumerate(['前面的原文', '第一个碎片', '胡乱识别', '最后的碎片', '后面的原文'])]
    return refs, live


@pytest.mark.parametrize('run', [None, {'session_id':'s', 'status':'failed', 'matches':[]}])
def test_all_recording_text_survives_zero_matches_and_failed_ai(run):
    refs, live = inputs()
    original = copy.deepcopy((refs, live))
    doc = f.compose_document('s', refs, live, 'tr2', 'tr4', run)
    assert [s['text'] for s in doc['segments']] == ['前面的原文'] + [r['content'] for r in refs] + ['后面的原文']
    assert doc['pending_count'] == 3
    assert doc['replaced_count'] == 3
    assert all(s['speaker_name'] for s in doc['segments'] if s['kind']=='recording')
    assert (refs, live) == original


def test_many_to_many_links_never_duplicate_or_rewrite_recording_text():
    refs, live = inputs()
    run={'session_id':'s', 'matches':[{'reference_orders':[1,2,3], 'transcript_ids':['tr2','tr4'], 'corrected_text':'\n'.join(r['content'] for r in refs), 'confidence_level':'high'}]}
    doc=f.compose_document('s',refs,live,'tr2','tr4',run)
    assert [s['text'] for s in doc['segments'] if s['kind']=='recording']==[r['content'] for r in refs]
    assert doc['pending_count']==0
    live[3]['speaker_name']='另一位成员'
    assert f.compose_document('s',refs,live,'tr2','tr4',run)['pending_count']==3


def test_stale_or_foreign_links_do_not_assign_speakers():
    refs,live=inputs()
    for run in [{'session_id':'elsewhere','matches':[]}, {'session_id':'s','matches':[{'reference_orders':[1], 'transcript_ids':['tr2'], 'corrected_text':'不存在的录音'}]}]:
        assert f.compose_document('s',refs,live,'tr2','tr4',run)['pending_count']==3


@pytest.mark.parametrize('start,end', [('tr4','tr2'),('missing','tr4'),('tr2','missing')])
def test_invalid_boundaries_are_rejected(start,end):
    refs,live=inputs()
    with pytest.raises(HTTPException): f.compose_document('s',refs,live,start,end)


class Result:
    def __init__(self,row=None): self.row=row
    def mappings(self):return self
    def first(self):return self.row
    def one(self):return self.row
    def all(self):return self.row or []


class MemoryDB:
    def __init__(self, occupied=None, fail_members=False):
        self.stored = []
        self.occupied = occupied or []
        self.fail_members = fail_members
        self.queries = []
        self.commit = AsyncMock()
        self.rollback = AsyncMock(side_effect=self.stored.clear)

    async def execute(self, query, params=None):
        sql = str(query)
        self.queries.append(sql)
        if 'SELECT cs.started_at' in sql:return Result({'started_at':None,'created_at':'2026-09-08T00:00:00Z'})
        assert 'recording_final_versions' not in sql
        assert not any(op + ' coi_utterances' in sql for op in ['UPDATE', 'DELETE FROM', 'INSERT INTO'])
        if 'INSERT INTO speech_transcript_corrections' in sql:
            self.stored.append({'id':params['id'], 'corrected_text':params['corrected_text'],
                'correction_reason':params['reason'], 'created_by':None,'created_at':'2026-09-08T00:00:00Z'})
            return Result({'created_at':'2026-09-08T00:00:00Z'})
        if 'INSERT INTO speech_transcript_correction_members' in sql:
            if self.fail_members: raise RuntimeError('simulated failed member insert')
            self.members = params
            return Result()
        if 'SELECT c.id, c.corrected_text' in sql: return Result(self.stored)
        if 'SELECT c.id, m.transcript_id' in sql: return Result(self.occupied)
        return Result()


def test_save_pending_document_and_reload_from_existing_tables_without_redis():
    refs, live = inputs()
    db = MemoryDB()
    async def scenario():
        with patch.object(f, '_load_alignment_source', AsyncMock(return_value=({},refs,live))):
            doc = await f.make_preview(db,'s',f.PreviewIn(start_transcript_id='tr2',end_transcript_id='tr4'))
            payload = f.SaveIn(start_transcript_id='tr2',end_transcript_id='tr4', source_hash=doc['source_hash'],preview_hash=doc['preview_hash'],boundary_confirmed=True)
            output = await f.save_final_version('s',payload,db)
            with patch.object(f, '_load_run', side_effect=AssertionError('Redis must not be read')):
                reopened = await f.get_final_version('s',db)
            assert output == reopened and output['document']['pending_count'] == 3
            assert db.stored[0]['corrected_text'] == '\n'.join(r['content'] for r in refs)
            assert [r['transcript_id'] for r in db.members] == ['tr2','tr3','tr4']
    asyncio.run(scenario())
    db.commit.assert_awaited_once()


@pytest.mark.parametrize('failure', ['cross_boundary', 'member_insert'])
def test_boundary_conflict_and_failed_insert_do_not_commit(failure):
    refs,live=inputs()
    db=MemoryDB(occupied=[{'id':'old','transcript_id':'tr1'}] if failure=='cross_boundary' else [],fail_members=failure=='member_insert')
    async def scenario():
        with patch.object(f,'_load_alignment_source',AsyncMock(return_value=({},refs,live))):
            doc=await f.make_preview(db,'s',f.PreviewIn(start_transcript_id='tr2',end_transcript_id='tr4'))
            payload=f.SaveIn(start_transcript_id='tr2',end_transcript_id='tr4',source_hash=doc['source_hash'],preview_hash=doc['preview_hash'],boundary_confirmed=True)
            with pytest.raises((HTTPException,RuntimeError)):await f.save_final_version('s',payload,db)
    asyncio.run(scenario())
    db.commit.assert_not_awaited()
    assert not db.stored
    if failure=='member_insert':db.rollback.assert_awaited_once()
    else:assert not any('DELETE' in q or 'INSERT' in q for q in db.queries)


@pytest.mark.parametrize('failure', ['source_changed','preview_changed','concurrent_save'])
def test_save_conflicts_do_not_write_document(failure):
    refs,live=inputs()
    doc=f.compose_document('s',refs,live,'tr2','tr4')
    payload=f.SaveIn(start_transcript_id='tr2',end_transcript_id='tr4',source_hash=doc['source_hash'],preview_hash=doc['preview_hash'],boundary_confirmed=True)
    if failure=='unconfirmed':payload.boundary_confirmed=False
    if failure=='source_changed':payload.source_hash='stale'
    if failure=='preview_changed':payload.preview_hash='stale'
    db=SimpleNamespace(execute=AsyncMock(),commit=AsyncMock())
    with patch.object(f,'latest',AsyncMock(return_value={'id':'new'} if failure=='concurrent_save' else None)), patch.object(f,'_load_alignment_source',AsyncMock(return_value=({},refs,live))):
        with pytest.raises(HTTPException):asyncio.run(f.save_final_version('s',payload,db))
    assert not any('INSERT' in str(call.args[0]) for call in db.execute.call_args_list)
    db.commit.assert_not_awaited()


def test_document_metadata_roundtrip_and_stale_legacy_edit_detection():
    from backend.app.admin.recording_document_metadata import encode_document, decode_document, public_reason
    refs, live = inputs()
    doc = f.compose_document('s', refs, live, 'tr2', 'tr4')
    reason = encode_document(doc)
    assert decode_document(reason, '\n'.join(r['content'] for r in refs)) == doc
    assert decode_document(reason, 'legacy edit changed the body') is None
    assert public_reason(reason) == '录音完整修订'


def test_cue_reader_emits_recording_body_once_without_invented_speaker():
    from backend.app.admin.cue_uptake_coding import _collapse_context_transcripts
    refs,live=inputs()
    doc=f.compose_document('s',refs,live,'tr2','tr4')
    body='\n'.join(r['content'] for r in refs)
    rows=[{'transcript_id':id,'source_transcript_ids':['tr2','tr3','tr4'], 'is_merged':True,
        'correction_id':'c', 'speaker_name':name,'speaker_user_id':'u', 'text':body,
        'correction_reason':f.encode_document(doc)} for id,name in [('tr2','甲'),('tr3','乙'),('tr4','丙')]]
    result=_collapse_context_transcripts(rows)
    assert len(result)==1 and result[0].text==body
    assert result[0].speaker_name=='录音修订（说话人见最终版本）'
    assert result[0].speaker_user_id is None
    assert result[0].correction_reason=='录音完整修订'


def test_automatic_range_and_grouped_placement_need_no_manual_boundaries():
    from backend.app.admin.recording_placement import place_recording
    refs,live=inputs()
    for r in refs:r['start_time']+=10
    doc=f.compose_document('s',refs,live,None,None,offset=0)
    assert (doc['start_transcript_id'],doc['end_transcript_id'])==('tr2','tr4')
    assert [s['text'] for s in doc['segments']]==['前面的原文']+[r['content'] for r in refs]+['后面的原文']
    assert all(s['transcript_ids'] and s['correspondence_status']=='grouped' for s in doc['segments'] if s['kind']=='recording')
    positions,_,_=place_recording(refs,live,offset=0)
    assert [p['transcript_ids'][0] for p in positions]==['tr2','tr3','tr4']


def test_automatic_grouping_saves_without_boundary_confirmation_and_reopens():
    refs,live=inputs()
    for r in refs:r['start_time']+=10
    db=MemoryDB()
    async def scenario():
        with patch.object(f,'_load_alignment_source',AsyncMock(return_value=({},refs,live))):
            doc=await f.make_preview(db,'s',f.PreviewIn(alignment_offset_seconds=0))
            result=await f.save_final_version('s',f.SaveIn(alignment_offset_seconds=0,source_hash=doc['source_hash'],preview_hash=doc['preview_hash'],boundary_confirmed=False),db)
            assert (await f.get_final_version('s',db))==result
            assert [m['transcript_id'] for m in db.members]==['tr2','tr3','tr4']
    asyncio.run(scenario())


def test_automatic_range_keeps_existing_merged_correction_whole():
    refs,live=inputs()
    for r in refs:r['start_time']+=10
    live[3]['existing_correction_id']=live[4]['existing_correction_id']='old'
    with patch.object(f,'_load_alignment_source',AsyncMock(return_value=({},refs,live))):
        doc=asyncio.run(f.make_preview(MemoryDB(),'s',f.PreviewIn(alignment_offset_seconds=0)))
    assert doc['end_transcript_id']=='tr5'


def test_single_ai_pass_never_calls_gap_repair_even_with_no_matches():
    from backend.app.admin import transcript_alignment as alignment
    from unittest.mock import Mock
    refs,live=inputs()
    run={'run_id':'offline','session_id':'s','failed_chunks':[],'total_tokens':0}
    model=AsyncMock(return_value=([],0))
    repair=AsyncMock(side_effect=AssertionError('second AI pass forbidden'))
    with patch.object(alignment,'_load_run',AsyncMock(return_value=run)), patch.object(alignment,'_store_run',AsyncMock()), patch.object(alignment,'AsyncOpenAI',Mock()), patch.object(alignment,'_call_alignment_model',model), patch.object(alignment,'_repair_missing_matches',repair):
        asyncio.run(alignment._execute_alignment_run('offline',refs,live,0))
    assert run['status']=='completed'
    repair.assert_not_awaited()
    assert model.await_count==run['completed_chunks']


def test_grouped_gap_uses_neighboring_anchors_without_inventing_speaker():
    refs,live=inputs()
    matches=[{'reference_orders':[r['order_index']], 'transcript_ids':[t], 'corrected_text':r['content'],'confidence_level':'high'} for r,t in [(refs[0],'tr2'),(refs[2],'tr4')]]
    for r in refs:r['start_time']=None
    doc=f.compose_document('s',refs,live,None,None,{'session_id':'s','matches':matches})
    middle=[s for s in doc['segments'] if s['kind']=='recording'][1]
    assert middle['transcript_ids']==['tr3']
    assert middle['speaker_name'] and middle['correspondence_status']=='grouped'
    assert middle['speaker_assignment']=='context_estimate'


def test_ai_speaker_guess_is_used_without_confidence_gate():
    refs,live=inputs()
    live[2]['speaker_name']='乙'
    run={'session_id':'s','matches':[], 'speaker_guesses':{'1':'乙','2':'不存在的人'}}
    doc=f.compose_document('s',refs,live,'tr2','tr4',run)
    recording=[r for r in doc['segments'] if r['kind']=='recording']
    assert recording[0]['speaker_name']=='乙'
    assert recording[0]['speaker_assignment']=='ai_estimate'
    assert recording[1]['speaker_name']!='不存在的人'
    assert all(r['speaker_name'] for r in recording)


@pytest.mark.parametrize('aware_base', [True, False])
def test_saved_result_missing_speakers_handles_mixed_timestamp_types(aware_base):
    from datetime import datetime, timezone, timedelta
    base=datetime(2026,6,9,6,21,55,tzinfo=timezone.utc if aware_base else None)
    refs,source=inputs()
    doc=f.compose_document('s',refs,source,'tr2','tr4')
    for segment in doc['segments']:
        if segment['kind']=='recording':
            segment['speaker_name']=None
            segment['transcript_ids']=[]
            segment['time']=10
    stored={'id':'saved','document':doc,'created_by':None,'created_at':base}
    queries=[]
    async def execute(query,params=None):
        sql=str(query);queries.append(sql)
        assert 'base_time' not in (params or {})
        if 'SELECT cs.started_at' in sql:
            return Result({'started_at':base if aware_base else None,'created_at':base})
        assert 'source_time' in sql
        naive=datetime(2026,6,9,6,22,5)
        return Result([
            {'transcript_id':'near','speaker_name':'甲','source_time':naive},
            {'transcript_id':'far','speaker_name':'乙','source_time':naive.replace(tzinfo=timezone.utc)+timedelta(seconds=100)},
        ])
    with patch.object(f,'latest',AsyncMock(return_value=stored)), patch.object(f,'_load_alignment_source',side_effect=AssertionError('Must not reload full sources')):
        result=asyncio.run(f.get_final_version('s',SimpleNamespace(execute=execute)))
    assert all(s['speaker_name']=='甲' for s in result['document']['segments'] if s['kind']=='recording')
    assert all(s['speaker_name'] is None for s in stored['document']['segments'] if s['kind']=='recording')
    assert len(queries)==2
