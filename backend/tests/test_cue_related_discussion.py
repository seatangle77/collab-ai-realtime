"""No database or paid AI calls: verify time isolation and model references."""
import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

import pytest
from fastapi import HTTPException
from backend.app.admin import cue_related_discussion as service

NOW = datetime(2026, 9, 8, tzinfo=timezone.utc)


def transcript(ident, ids=None, text='相关物品'):
    return NS(transcript_id=ident, source_transcript_ids=ids or [ident], text=text, speaker_name='甲', end=NOW + timedelta(seconds=10))


def test_time_boundary_checks_all_merged_members():
    rows = [transcript('before'), transcript('equal'), transcript('unknown'), transcript('merged', ['after', 'before']), transcript('missing', ['after', 'absent']), transcript('after')]
    starts = {'before': NOW - timedelta(seconds=1), 'equal': NOW, 'unknown': None, 'after': NOW + timedelta(seconds=1)}
    eligible, excluded = service.eligible_transcripts(rows, starts, NOW)
    assert [item.transcript_id for item in eligible] == ['after']
    assert excluded == 5


@pytest.mark.parametrize('naive_cutoff', [False, True])
@pytest.mark.parametrize('final_version', [False, True])
def test_mixed_timezones_preserve_boundary_and_sorting(naive_cutoff, final_version):
    # Pure in-memory time checks: no database writes or AI requests.
    shanghai = timezone(timedelta(hours=8))
    rows = [transcript(ident) for ident in ['later', 'equal', 'unknown', 'before', 'after']]
    for item in rows:
        item.end = (NOW + timedelta(seconds=10)).replace(tzinfo=None)
        if final_version:
            item.final_version_id = 'version'
            item.source_transcript_ids = ['unrelated-original']
    starts = {
        'before': (NOW - timedelta(seconds=1)).replace(tzinfo=None),
        'equal': NOW.astimezone(shanghai),
        'unknown': None,
        'after': (NOW + timedelta(seconds=1)).replace(tzinfo=None),
        'later': (NOW + timedelta(seconds=2)).astimezone(shanghai),
    }
    cutoff = NOW.replace(tzinfo=None) if naive_cutoff else NOW.astimezone(shanghai)
    eligible, excluded = service.eligible_transcripts(rows, starts, cutoff)
    assert [item.transcript_id for item in eligible] == ['after', 'later']
    assert excluded == 3


class Client:
    content = ''
    request = None
    finish = 'stop'

    def __init__(self, **kwargs):
        self.chat = NS(completions=self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def create(self, **kwargs):
        Client.request = kwargs
        return NS(choices=[NS(message=NS(content=Client.content), finish_reason=Client.finish)])


def run_lookup(monkeypatch, content, finish='stop'):
    monkeypatch.setattr(service, 'AsyncOpenAI', Client)
    monkeypatch.setattr(service.nlp_settings, 'qwen_api_key', 'test')
    try:
        data = json.loads(content)
        if isinstance(data, dict):
            data.setdefault('interpretation', '追问物品用途和比较依据。')
            data.setdefault('suggested_code', 'not_discussed')
            data.setdefault('coding_reason', '需要人工核对。')
            content = json.dumps(data)
    except ValueError:
        pass
    Client.content, Client.finish = content, finish
    return asyncio.run(service.find_related(NS(push_log_id='cue', push_content='物品用途'), [transcript('a'), transcript('b')], 0))


def test_matches_order_deduplication_and_original_text(monkeypatch):
    result = run_lookup(monkeypatch, json.dumps({'matches': [
        {'transcript_id': 'b', 'reason': '同义表达'}, {'transcript_id': 'a', 'reason': '物品'}, {'transcript_id': 'b', 'reason': '同一物品'}]}))
    assert [item.transcript_id for item in result.matches] == ['a', 'b']
    assert result.matches[0].text == '相关物品'
    assert Client.request['model'] == service.nlp_settings.reasoning_model


@pytest.mark.parametrize('content,finish', [
    ('{"matches":[{"transcript_id":"before","reason":"越界"}]}', 'stop'),
    ('{"matches":[]}', 'length'), ('not json', 'stop'), ('{}', 'stop'),
])
def test_invalid_results_fail_instead_of_showing_no_matches(monkeypatch, content, finish):
    with pytest.raises(HTTPException) as exc:
        run_lookup(monkeypatch, content, finish)
    assert exc.value.status_code == 502


def test_empty_discussion_still_explains_question(monkeypatch):
    monkeypatch.setattr(service, 'AsyncOpenAI', Client)
    monkeypatch.setattr(service.nlp_settings, 'qwen_api_key', 'test')
    Client.finish = 'stop'
    Client.content = json.dumps(dict(matches=[], interpretation='追问比较依据', suggested_code='not_discussed', coding_reason='没有后续文本'))
    result = asyncio.run(service.find_related(NS(push_log_id='cue', push_content='物品用途'), [], 2))
    assert result.interpretation == '追问比较依据'
    assert result.suggested_code is None
    assert result.analyzed_count == 0 and result.matches == []


def test_no_matches_is_success(monkeypatch):
    assert run_lookup(monkeypatch, '{"matches":[]}').matches == []


@pytest.mark.parametrize('content,finish', [('{"matches":[]}', 'stop'), ('invalid json', 'stop'), ('partial output', 'length')])
def test_raw_response_logged_before_validation(monkeypatch, caplog, content, finish):
    caplog.set_level('INFO', logger=service.__name__)
    try:
        run_lookup(monkeypatch, content, finish)
    except HTTPException:
        assert content != '{"matches":[]}'
    record = next(record.getMessage() for record in caplog.records if 'AI response cue=' in record.getMessage())
    choices = json.loads(record.split(' choices=', 1)[1])
    assert choices[0]['content'] == Client.content
    assert choices[0]['finish_reason'] == finish
    assert 'cue=cue' in record


def test_truncation_has_specific_error_and_safe_usage_log(monkeypatch, caplog):
    with pytest.raises(HTTPException) as exc:
        run_lookup(monkeypatch, '{"matches":[]}', finish='length')
    assert '长度上限' in exc.value.detail
    assert 'finish_reason=length' in caplog.text
    assert 'input_chars=' in caplog.text
    assert '物品用途' not in caplog.text


def test_missing_evidence_is_not_reported_as_token_limit(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        run_lookup(monkeypatch, json.dumps(dict(matches=[], suggested_code='discussed_adopted')))
    assert '没有返回对应的后续发言证据' in exc.value.detail
    assert '长度上限' not in exc.value.detail


@pytest.mark.parametrize('update', [
    {'suggested_code': 'invented'}, {'interpretation': ''},
    {'coding_reason': None}, {'suggested_code': 'discussed_adopted'},
    {'suggested_code': 'discussed_not_adopted'},
])
def test_rejects_invalid_or_unsupported_recommendations(monkeypatch, update):
    with pytest.raises(HTTPException) as exc:
        run_lookup(monkeypatch, json.dumps(dict(matches=[], **update)))
    assert exc.value.status_code == 502


def test_generation_basis_is_background_not_candidate_evidence(monkeypatch):
    monkeypatch.setattr(service, 'AsyncOpenAI', Client)
    monkeypatch.setattr(service.nlp_settings, 'qwen_api_key', 'test')
    Client.finish = 'stop'
    Client.content = json.dumps(dict(matches=[dict(transcript_id='before', reason='原发言')], interpretation='追问理由', suggested_code='discussed_adopted', coding_reason='对应发言'))
    cue = NS(push_log_id='cue', push_content='为什么？', generation_analysis='需要展开', generation_anchor=NS(model_dump=lambda: {'transcript_id': 'before', 'text': '之前的发言'}))
    with pytest.raises(HTTPException):
        asyncio.run(service.find_related(cue, [transcript('after')], 0))
    payload = json.loads(Client.request['messages'][1]['content'])
    assert payload['生成理由（仅辅助理解意图）'] == '需要展开'
    assert [item['id'] for item in payload['后续讨论']] == ['after']


def test_task_dictionary_is_scoped_and_only_includes_mentioned_letters():
    assert service.task_letter_context('moon', 'A和M') == '物品编号（仅辅助理解，不是排名或采纳证据）：A=火柴;M=氧气'
    assert service.task_letter_context('sea', 'A和M') == '物品编号（仅辅助理解，不是排名或采纳证据）：A=收音机;M=六分仪'
    assert service.task_letter_context('winter', 'Ａ和ｉ') == '物品编号（仅辅助理解，不是排名或采纳证据）：A=航空地图;I=火柴'
    assert service.task_letter_context('winter', 'AI NASA FM 普通讨论 M') == ''


def test_request_requires_valid_task():
    from pydantic import ValidationError
    for payload in ({}, {'task_type': 'unknown'}):
        with pytest.raises(ValidationError):
            service.RelatedDiscussionIn.model_validate(payload)


def test_task_mapping_reaches_model_without_ids_becoming_letters(monkeypatch):
    monkeypatch.setattr(service, 'AsyncOpenAI', Client)
    monkeypatch.setattr(service.nlp_settings, 'qwen_api_key', 'test')
    Client.content = json.dumps({'interpretation': '比较物品', 'coding_reason': '待核对', 'suggested_code': 'not_discussed', 'matches': []})
    Client.finish = 'stop'
    asyncio.run(service.find_related(NS(push_log_id='cue', push_content='A有用吗'), [transcript('b')], 0, 'sea'))
    content = Client.request['messages'][1]['content']
    assert 'A=收音机' in content
    assert 'B=尼龙绳' not in content
    assert 'A=火柴' not in content


@pytest.mark.parametrize('text', ['AJ为什么是美学院的？', 'ＡＪ为什么是美学院的？'])
def test_joined_item_letters_are_possible_references(text):
    context = service.task_letter_context('moon', text)
    assert 'A=火柴' in context
    assert 'J=星象图' in context
    assert 'AJ=A+J' in context
    assert '可能' in context
    assert 'B=尼龙绳' not in context
    sea = service.task_letter_context('sea', text)
    assert 'A=收音机' in sea and 'J=饮用水' in sea


def test_joined_letters_do_not_split_english_or_identifiers():
    assert service.task_letter_context('moon', 'AI FM NASA LED ID APP JACK abc plAJ32 user_AJ') == ''
    assert service.task_letter_context('winter', 'AM AZ MN') == ''
    assert 'C=食物浓缩包' in service.task_letter_context('moon', 'ABC怎么排序')


def test_joined_letter_mapping_is_sent_to_ai(monkeypatch):
    monkeypatch.setattr(service, 'AsyncOpenAI', Client)
    monkeypatch.setattr(service.nlp_settings, 'qwen_api_key', 'test')
    Client.content = json.dumps({'interpretation': '措辞不明，需核对', 'coding_reason': '待核对', 'suggested_code': 'not_discussed', 'matches': []})
    Client.finish = 'stop'
    asyncio.run(service.find_related(NS(push_log_id='cue', push_content='AJ为什么是美学院的？'), [], 0, 'moon'))
    content = Client.request['messages'][1]['content']
    assert 'A=火柴;J=星象图' in content
    assert 'AJ=A+J' in content
    assert 'AJ为什么是美学院的？' in content


@pytest.mark.parametrize('code', ['uncertain', 'not_included'])
def test_ai_cannot_recommend_non_core_codes(monkeypatch, code):
    with pytest.raises(HTTPException):
        run_lookup(monkeypatch, json.dumps({'matches': [], 'suggested_code': code}))


def test_prompt_uses_observable_behavior_without_causal_requirement(monkeypatch):
    run_lookup(monkeypatch, json.dumps({'matches': []}))
    prompt = Client.request['messages'][0]['content']
    assert '仅推荐以下三类之一' in prompt
    assert '不要求证明由AI引起' in prompt
    assert 'uncertain=' not in prompt
    assert '则判无法判断' not in prompt
