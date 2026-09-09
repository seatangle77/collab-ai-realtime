import asyncio
from unittest.mock import AsyncMock, patch
from backend.app.admin import transcript_alignment as a
from backend.tests.test_transcript_alignment import _reference, _live


def fixtures():
    refs = [_reference(i, f'录音正文第{i}段', i * 10) for i in range(3)]
    live = [_live(i, f'实时正文第{i}段', i * 10) for i in range(3)]
    return refs, live


def match(refs, ids):
    return {'reference_orders': refs, 'transcript_ids': ids}


def test_repair_can_expand_but_cannot_drop_existing_coverage():
    refs, live = fixtures()
    old = [match([1, 2], ['tr1', 'tr2'])]
    assert a._adopt_repair(old, [match([1, 2, 3], ['tr1', 'tr2', 'tr3'])], refs, live) != old
    assert a._adopt_repair(old, [match([2, 3], ['tr2', 'tr3'])], refs, live) == old


def test_repair_cannot_cross_or_duplicate_other_groups():
    refs, live = fixtures()
    old = [match([1], ['tr1']), match([3], ['tr3'])]
    assert a._adopt_repair(old, [match([2], ['tr3'])], refs, live) == old
    assert a._adopt_repair(old, [match([2], ['tr2']), match([2], ['tr2'])], refs, live) == old


def test_repair_calls_only_incomplete_chunks_and_sends_gap_details():
    refs, live = fixtures()
    existing = [match([1], ['tr1'])]
    raw = [{'reference_orders': [1, 2, 3], 'transcript_ids': ['tr1', 'tr2', 'tr3'], 'confidence': .9}]
    model = AsyncMock(return_value=(raw, 100))
    progress = AsyncMock()
    with patch.object(a, '_call_alignment_model', model):
        result = asyncio.run(a._repair_missing_matches(None, existing, {'references': refs, 'live_items': live}, 0, progress))
    assert len(result) == 1 and result[0]['transcript_ids'] == ['tr1', 'tr2', 'tr3']
    chunk = model.call_args.args[1]
    assert chunk['repair_missing_references'] == [2, 3]
    assert '本段是在补查遗漏' in a._build_prompt(chunk, 0)
    model.reset_mock()
    with patch.object(a, '_call_alignment_model', model):
        asyncio.run(a._repair_missing_matches(None, result, {'references': refs, 'live_items': live}, 0, progress))
    model.assert_not_called()


def test_failed_repair_keeps_existing_results():
    refs, live = fixtures()
    existing = [match([1], ['tr1'])]
    with patch.object(a, '_call_alignment_model', AsyncMock(side_effect=RuntimeError('offline'))):
        assert asyncio.run(a._repair_missing_matches(None, existing, {'references': refs, 'live_items': live}, 0, AsyncMock())) == existing


def test_calibration_is_alternative_not_replacement_for_source_time():
    refs = [_reference(0, '明确相关原文', 100)]
    live = [_live(0, '明确相关原文', 40)]
    live[0]['original_relative_seconds'] = 100
    chunk = a._build_chunks(refs, live, 0)[0]
    assert len(chunk['live_items']) == 1
    assert a._validate_model_matches([{'reference_orders':[1], 'transcript_ids':['tr1']}], chunk, refs, live, 0)
