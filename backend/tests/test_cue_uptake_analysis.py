"""Offline arithmetic and read-only route tests; no database or AI requests."""
import asyncio
import json
import math
from datetime import datetime
from unittest.mock import AsyncMock
import pytest
from scipy import stats
from backend.app.analysis.cue_uptake_analysis_service import build_analysis
from backend.app.admin.cue_uptake_analysis import Request, report


def events(group, condition, codes, session='s1'):
    return [dict(push_log_id=f'{group}-{session}-{i}', group_id=group, group_name=group, condition=condition,
                 session_id=f'{group}-{session}', code=code, possible_duplicate=False) for i, code in enumerate(codes)]

A, B, C = 'not_discussed', 'discussed_not_adopted', 'discussed_adopted'


def test_denominators_and_conservation():
    r = build_analysis(events('g', 'glasses', [A, B, C, C, 'uncertain', 'not_included', None]))
    t = r['totals']
    assert t['total'] == t['valid'] + t['uncertain'] + t['not_included'] + t['uncoded'] == 7
    assert t['adoption_rate'] == .5
    assert t['discussion_rate'] == .75
    assert t['conditional_adoption_rate'] == pytest.approx(2/3)
    assert r['comparisons'][0]['p_value'] is None


def test_group_equal_weight_differs_from_pooled_and_merges_sessions():
    rows = events('g1', 'glasses', [C]) + events('g2', 'glasses', [A]*9)
    rows += events('g2', 'glasses', [A], 's2')
    r=build_analysis(rows)
    assert len(r['groups']) == 2 and len(r['sessions']) == 3
    assert r['conditions'][0]['adoption_rate'] == pytest.approx(1/11)
    assert r['conditions'][0]['stats']['adoption_rate']['mean'] == .5


@pytest.mark.parametrize('codes', [[], [None, 'uncertain', 'not_included']])
def test_empty_denominator_is_null(codes):
    r=build_analysis(events('g','glasses',codes))
    assert r['totals']['adoption_rate'] is None
    assert r['totals']['conditional_adoption_rate'] is None
    json.dumps(r, allow_nan=False)


def varied_rows():
    return (events('g1','glasses',[C,C,A,A]) + events('g2','glasses',[C,C,C,A]) + events('g3','glasses',[C,A,A,A])
            +events('a1','app_notification',[C,A,A,A])+events('a2','app_notification',[A,A,A,A])+events('a3','app_notification',[C,C,A,A]))


def test_welch_matches_scipy():
    c=build_analysis(varied_rows(),'independent')['comparisons'][0]
    ref=stats.ttest_ind([.5,.75,.25],[.25,0,.5],equal_var=False)
    assert c['difference'] == .25
    assert c['p_value'] == pytest.approx(ref.pvalue)
    assert c['t_statistic'] == pytest.approx(ref.statistic)
    assert c['degrees_of_freedom'] == pytest.approx(ref.df)
    assert c['ci_low'] == pytest.approx(ref.confidence_interval().low)
    assert c['ci_high'] == pytest.approx(ref.confidence_interval().high)


def test_paired_uses_explicit_mapping():
    pairs=[{'glasses':f'g{i}','app_notification':f'a{i}'} for i in [1,2,3]]
    c=build_analysis(varied_rows(),'paired',pairs)['comparisons'][0]
    ref=stats.ttest_rel([.5,.75,.25],[.25,0,.5])
    assert c['p_value'] == pytest.approx(ref.pvalue)
    assert c['t_statistic'] == pytest.approx(ref.statistic)
    assert c['degrees_of_freedom'] == pytest.approx(ref.df)
    assert c['ci_low'] == pytest.approx(ref.confidence_interval().low)


def test_reject_duplicate_or_partial_pairs():
    with pytest.raises(ValueError): build_analysis(varied_rows(),'paired',[{'glasses':'g1','app_notification':'a1'}])
    with pytest.raises(ValueError): build_analysis(varied_rows(),'paired',[{'glasses':'g1','app_notification':'a1'}]*3)


def test_zero_variance_no_fake_significance():
    rows=events('g1','glasses',[C])+events('g2','glasses',[C])+events('a1','app_notification',[A])+events('a2','app_notification',[A])
    r=build_analysis(rows,'independent')
    assert r['comparisons'][0]['status']=='zero_variance'
    assert r['comparisons'][0]['p_value'] is None
    json.dumps(r,allow_nan=False)


def test_unknown_labels_and_duplicate_events_fail():
    with pytest.raises(ValueError): build_analysis(events('g','glasses',['new_unknown']))
    row=events('g','glasses',[A])
    with pytest.raises(ValueError): build_analysis(row+row)


def test_pair_with_missing_labels_excludes_whole_pair():
    rows=varied_rows()+events('g4','glasses',[None])+events('a4','app_notification',[C])
    pairs=[{'glasses':f'g{i}','app_notification':f'a{i}'} for i in [1,2,3,4]]
    c=build_analysis(rows,'paired',pairs)['comparisons'][0]
    assert c['dropped_pairs']==1 and c['n_glasses']==3 and c['n_app']==3


def test_route_select_only_filters_and_utc():
    row=dict(push_log_id='offline',group_id='g',group_name='离线',condition='glasses',session_id='s',
             received_at=datetime(2026,9,16),coding_coded_at=datetime(2026,9,16),coding_uptake_code=A)
    class Result:
        def mappings(self): return self
        def all(self): return [row]
    db=AsyncMock();db.execute.return_value=Result()
    r=asyncio.run(report(Request(group_ids=['g'],session_ids=['s']),db))
    assert r['events'][0]['received_at'].endswith('Z')
    db.commit.assert_not_called()
    sql, params=db.execute.call_args.args
    assert str(sql).strip().startswith('SELECT')
    assert params['group_ids']==['g'] and params['session_ids']==['s'] and params['coder_role']=='primary'
    assert "pl.delivery_status = 'delivered'" in str(sql)
    assert r['totals']['not_discussed']==1
