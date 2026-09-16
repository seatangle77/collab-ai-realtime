"""Numerical, exclusion, and database read-only contracts; no live database needed."""
import asyncio
from copy import deepcopy
import math

import numpy as np
import pytest
from fastapi import HTTPException
from backend.app.analysis.lexical_diversity_service import (
    mattr, mtld, clean_text, clean_tokens, build_analysis, inference, holm, CONDITIONS,
)
from backend.app.admin.lexical_diversity import load_rows


def row(g='g1', **kwargs):
    return dict(group_id=g, group_name=g, condition='no_assistance', session_id='s'+g,
                task_ids=['moon_survival'], utterance_id='u'+g, order_index=1,
                content=' '.join(['水','火','绳','氧气']*30), **kwargs)


def test_mattr_matches_naive_sliding_windows():
    tokens=['水','火','水','绳','火','氧气','水']*35
    expected=np.mean([len(set(tokens[i:i+100]))/100 for i in range(len(tokens)-99)])
    assert mattr(tokens) == pytest.approx(expected)
    assert mattr(['水']*100) == .01
    assert mattr([str(i) for i in range(100)]) == 1.
    assert mattr(['水']*99) is None


def test_mtld_fractional_tail_and_bidirectionality():
    # 100 identical tokens produce 50 factors of two tokens in each direction.
    assert mtld(['水']*100) == 2.
    assert mtld(['水']*101) == pytest.approx(101/50)
    assert mtld([str(i) for i in range(100)]) is None
    tokens=['水','水','火','绳','氧气']*21
    assert mtld(tokens) == pytest.approx(mtld(tokens[::-1]))


def test_cleaning_preserves_meaningful_single_characters_and_function_words():
    assert clean_text('（笑声）水（重要）Ａ') == '水(重要)A'
    assert clean_tokens(['水','火','绳','的','因为','水','，','嗯','Ａ','１２']) == ['水','火','绳','的','因为','水','a','12']


def test_source_is_unchanged_and_fingerprints_reproducible():
    rows=[row()]; original=deepcopy(rows)
    a=build_analysis(rows,str.split,permutations=19)
    b=build_analysis(rows,str.split,permutations=19)
    assert rows == original
    assert a['source_hash'] == b['source_hash']
    assert a['observations'][0]['window_count'] == 21
    rows[0]['content'] += ' 新词'
    c=build_analysis(rows,str.split,permutations=19)
    assert a['source_hash'] != c['source_hash']
    assert a['observations'][0]['token_hash'] != c['observations'][0]['token_hash']


def test_exclusions_and_task_filter_do_not_silently_drop_invalid_sources():
    rows=[row('good'),row('empty'),row('short'),row('unknown'),row('multiple'),row('multiple'),row('other'),row('none')]
    rows[1]['content']=None
    rows[2]['content']='水 火'
    rows[3]['task_ids']=['moon_survival','lost_at_sea']
    rows[5]['session_id']='second'
    rows[6]['task_ids']=['winter_survival']
    rows[7]['session_id']=None
    result=build_analysis(rows,str.split,task_filter='moon_survival',permutations=19)
    assert [o['group_id'] for o in result['observations']] == ['good']
    assert {o['reason'] for o in result['excluded']} == {'missing_text','short_text','ambiguous_task','multiple_sessions','missing_session'}


def test_task_only_difference_is_not_a_condition_effect():
    observations=[dict(condition=c,task_id=t,mattr_100=value) for c in CONDITIONS
                  for t,value in [('moon_survival',.3),('winter_survival',.8)] for _ in range(3)]
    result=inference(observations,'mattr_100',99)
    assert result['p_value'] == 1
    assert result['pairs'] == []


def test_condition_difference_has_holm_pairs_and_reproducible_intervals():
    observations=[dict(condition=c,task_id='moon_survival',mattr_100=.1+.3*i+.001*j)
                  for i,c in enumerate(CONDITIONS) for j in range(5)]
    result=inference(observations,'mattr_100',199)
    assert result['p_value'] < .05
    assert len(result['pairs']) == 3
    assert result == inference(observations,'mattr_100',199)
    for pair in result['pairs']:
        assert pair['p_adjusted'] >= pair['p_value']
        assert pair['ci_low'] <= pair['difference'] <= pair['ci_high']
    assert holm([.01,.04,.03]) == pytest.approx([.03,.06,.06])


def test_missing_task_cell_and_undefined_mtld_are_not_zero_imputed():
    observations=[dict(condition=c,task_id='moon_survival',mattr_100=.5,mtld=None) for c in CONDITIONS for _ in range(2)]
    assert inference(observations,'mtld',19)['n']==0
    observations.pop()
    assert inference(observations,'mattr_100',19)['status']=='insufficient_data'
    result=build_analysis([],str.split,permutations=19)
    assert result['observations']==[] and len(result['summaries'])==15


class FakeResult:
    def __init__(self, rows): self.rows=rows
    def mappings(self): return self
    def all(self): return self.rows


class FakeDb:
    def __init__(self, rows): self.rows=rows; self.statements=[]
    async def execute(self, statement, params=None):
        self.statements.append(str(statement).strip())
        return FakeResult(self.rows)


def test_database_contract_read_only_and_no_source_updates():
    db=FakeDb([row()])
    result=asyncio.run(load_rows(db, {'no_assistance':['g1']}))
    assert result[0]['group_id']=='g1'
    assert db.statements[0]=='SET TRANSACTION READ ONLY'
    assert len(db.statements)==2 and db.statements[1].startswith('SELECT')
    assert 'LEFT JOIN coi_utterances' in db.statements[1]


def test_condition_mismatch_is_rejected():
    with pytest.raises(HTTPException) as error:
        asyncio.run(load_rows(FakeDb([row()]), {'glasses':['g1']}))
    assert error.value.status_code==422
