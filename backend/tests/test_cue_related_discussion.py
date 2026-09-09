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


def test_empty_input_does_not_call_ai(monkeypatch):
    monkeypatch.setattr(service.nlp_settings, 'qwen_api_key', '')
    result = asyncio.run(service.find_related(NS(push_log_id='cue'), [], 2))
    assert result.analyzed_count == 0 and result.matches == []


def test_no_matches_is_success(monkeypatch):
    assert run_lookup(monkeypatch, '{"matches":[]}').matches == []
