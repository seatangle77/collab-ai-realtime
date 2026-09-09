import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from backend.app.admin import transcript_alignment as a
from backend.app.admin.transcript_final_scope import final_scope_exclusions, scope_reason, excluded_ids_from_reasons
from backend.app.admin import transcript_corrections as c
from backend.tests.test_transcript_alignment import _reference, _live


def test_only_internal_noise_is_excluded_suffix_stays_original():
    live = [_live(i, '原始转写', i * 10) for i in range(1, 6)]
    matches = [{'transcript_ids':['tr3']}, {'transcript_ids':['tr5']}]
    excluded, outside = final_scope_exclusions(matches, live)
    assert excluded == ['tr2', 'tr4']  # paired anchor is tr2; earlier rows were sliced out
    assert outside == ['tr6']
    assert all(t['text'] == '原始转写' for t in live)


def test_metadata_survives_saved_reason_roundtrip():
    reason = scope_reason('AI 整场匹配（run=test）', ['noise1', 'noise2'])
    assert excluded_ids_from_reasons([reason, reason]) == {'noise1', 'noise2'}
    assert excluded_ids_from_reasons(['人工修订', 'AI 整场匹配\n[final-version-excluded]broken']) == set()


def test_complete_recording_with_unused_middle_asr_passes_but_missing_recording_fails():
    refs = [_reference(0, '录音第一句。', 0), _reference(1, '录音第二句。', 20)]
    live = [_live(i, '实时', i * 10) for i in range(3)]
    matches = [{'reference_orders':[1], 'transcript_ids':['tr1'], 'corrected_text':'录音第一句。'},
               {'reference_orders':[2], 'transcript_ids':['tr3'], 'corrected_text':'录音第二句。'}]
    assert a._alignment_structure_error(matches, refs, live, []) is None
    assert a._alignment_structure_error(matches[:1], refs, live, []) == '准确录音文字存在未分配段落'


class Result:
    def __init__(self, rows=()): self.rows = rows
    def first(self): return True
    def scalar_one(self): return 1
    def mappings(self): return self
    def all(self): return self.rows


def test_reloaded_page_uses_scope_outside_current_filtered_page():
    row = dict(transcript_id='noise', group_id='g', session_id='s', speaker_name='甲', original_text='胡言乱语', effective_text='胡言乱语', is_corrected=False, source_transcript_ids=['noise'])
    async def execute(query, params=None):
        sql = str(query)
        if 'SELECT DISTINCT tc.correction_reason' in sql:
            return Result([{'correction_reason':scope_reason('AI 整场匹配', ['noise'])}])
        if 't.text AS original_text' in sql: return Result([row])
        return Result()
    db = SimpleNamespace(execute=execute)
    result = asyncio.run(c.list_correctable_transcripts('s', page=1, page_size=100, correction_status=None, speaker=None, keyword=None, db=db))
    assert result.items[0].final_excluded
    assert result.items[0].original_text == '胡言乱语'


def test_save_accepts_internal_unused_asr_and_persists_exclusions_transactionally():
    class Transaction:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
    inserts = []
    replacement_scopes = []
    async def execute(query, params=None):
        sql = str(query)
        if 'SELECT order_index, content' in sql:
            return Result([{'order_index':1, 'content':'录音正文。'}])
        if 'SELECT t.transcript_id' in sql:
            return Result([{'transcript_id':'tr1', 'speaker_name':'甲', 'speaker_key':'甲'}])
        if 'SELECT member.transcript_id' in sql:
            replacement_scopes.append(params['transcript_ids'])
            return Result([])
        if 'INSERT INTO speech_transcript_corrections (' in sql:
            inserts.append(params)
        return Result([])
    db = SimpleNamespace(execute=execute, begin_nested=Transaction, commit=AsyncMock(), rollback=AsyncMock())
    run = {'run_id':'test', 'logic_version':a.ALIGNMENT_LOGIC_VERSION, 'session_id':'s', 'status':'completed', 'model':'qwen3-max',
           'summary':{'unmatched_transcripts':1, 'unmatched_references':0},
           'excluded_transcript_ids':['noise'], 'out_of_scope_transcript_ids':['suffix'],
           'matches':[{'match_id':'m1','reference_orders':[1],'transcript_ids':['tr1'],'corrected_text':'录音正文。','confidence':.9,'saved':False}]}
    with patch.object(a, '_load_run', AsyncMock(return_value=run)), patch.object(a, '_store_run', AsyncMock()):
        output = asyncio.run(a.save_alignment_run('test', a.SaveAlignmentRunIn(match_ids=['m1']), db))
    assert output.saved_matches == 1
    assert excluded_ids_from_reasons([inserts[0]['correction_reason']]) == {'noise'}
    assert replacement_scopes == [['tr1', 'noise']]
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()
