from backend.app.admin.transcript_alignment import _calibrate_live_times, _build_chunks
from backend.tests.test_transcript_alignment import _reference, _live


def test_corroborated_late_drift_recovers_candidates_without_changing_sources():
    texts = ['氧气是维持生命所必需的第一项物资', '指南针在月球表面可能无法正常使用', '可以用降落伞材料来捆绑运输物品']
    refs = [_reference(i, text, time) for i, (text, time) in enumerate(zip(texts, [0, 300, 420]))]
    live = [_live(i, text, time) for i, (text, time) in enumerate(zip(texts, [0, 370, 490]))]
    calibrated = _calibrate_live_times(refs, live, 0)
    assert [t['relative_seconds'] for t in live] == [0, 370, 490]
    assert [t['relative_seconds'] for t in calibrated] == [0, 300, 420]
    assert [t['transcript_id'] for t in _build_chunks(refs[1:], calibrated, 0)[0]['live_items']] == ['tr2', 'tr3']


def test_single_coincidence_cannot_move_timestamps():
    refs = [_reference(0, '指南针在月球表面可能无法正常使用', 100)]
    live = [_live(0, refs[0]['content'], 170)]
    assert _calibrate_live_times(refs, live, 0) == live


def test_repeated_text_cannot_establish_drift():
    refs = [_reference(i, '指南针在月球表面可能无法正常使用', i * 50) for i in range(2)]
    live = [_live(i, refs[0]['content'], i * 50 + 70) for i in range(2)]
    assert _calibrate_live_times(refs, live, 0) == live
