"""Read-only cue summaries. Inferential units are groups, never individual cues."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import math
import numpy as np
from scipy import stats

CODES = ('not_discussed', 'discussed_not_adopted', 'discussed_adopted', 'uncertain', 'not_included')
CONDITIONS = ('glasses', 'app_notification')
METRICS = ('adoption_rate', 'discussion_rate', 'conditional_adoption_rate')


def summarize(events):
    counts = Counter(e.get('code') or 'uncoded' for e in events)
    a, b, c = (counts[k] for k in CODES[:3])
    n = a + b + c
    return dict(total=len(events), valid=n, **{k: counts[k] for k in (*CODES, 'uncoded')},
                duplicate_count=sum(bool(e.get('possible_duplicate')) for e in events),
                adoption_rate=c / n if n else None,
                discussion_rate=(b + c) / n if n else None,
                conditional_adoption_rate=c / (b + c) if b + c else None)


def describe(values):
    x = np.asarray([v for v in values if v is not None], dtype=float)
    return dict(n=len(x), mean=float(x.mean()) if len(x) else None,
                sd=float(x.std(ddof=1)) if len(x) > 1 else None,
                median=float(np.median(x)) if len(x) else None,
                q1=float(np.quantile(x, .25)) if len(x) else None,
                q3=float(np.quantile(x, .75)) if len(x) else None)


def compare(groups, metric, design, pairs):
    by_key = {(g['group_id'], g['condition']): g for g in groups}
    values = [[g[metric] for g in groups if g['condition'] == condition and g[metric] is not None]
              for condition in CONDITIONS]
    dropped_pairs = 0
    if design == 'paired':
        matched = [(by_key.get((p['glasses'], 'glasses')), by_key.get((p['app_notification'], 'app_notification'))) for p in pairs]
        usable = [(a[metric], b[metric]) for a, b in matched if a and b and a[metric] is not None and b[metric] is not None]
        dropped_pairs = len(pairs) - len(usable)
        values = [[p[i] for p in usable] for i in (0, 1)]
    a, b = (np.asarray(x, dtype=float) for x in values)
    result = dict(metric=metric, design=design, n_glasses=len(a), n_app=len(b),
                  dropped_pairs=dropped_pairs, difference=float(a.mean() - b.mean()) if len(a) and len(b) else None,
                  ci_low=None, ci_high=None, p_value=None, t_statistic=None, degrees_of_freedom=None, method='', status='descriptive')
    if design == 'descriptive':
        result['method'] = '小组等权均值差；尚未选择实验设计'
        return result
    result['method'] = '小组比例配对 t 检验' if design == 'paired' else '小组比例 Welch t 检验'
    if min(len(a), len(b)) < 2:
        result['status'] = 'insufficient_data'
        return result
    if design == 'paired':
        d = a - b
        se = float(d.std(ddof=1) / np.sqrt(len(d)))
        df = len(d) - 1
    else:
        va, vb = float(a.var(ddof=1) / len(a)), float(b.var(ddof=1) / len(b))
        se = math.sqrt(va + vb)
        df = (va + vb) ** 2 / (va ** 2 / (len(a)-1) + vb ** 2 / (len(b)-1)) if se else 0
    if se <= 1e-12:
        result['status'] = 'zero_variance'
        return result
    margin = float(stats.t.ppf(.975, df) * se)
    diff = result['difference']
    result.update(ci_low=diff-margin, ci_high=diff+margin, t_statistic=float(diff/se), degrees_of_freedom=float(df),
                  p_value=float(2 * stats.t.sf(abs(diff / se), df)), status='ok')
    return result


def build_analysis(events, design='descriptive', pairs=None):
    if design not in ('descriptive', 'independent', 'paired'):
        raise ValueError('未知实验设计')
    if len({e['push_log_id'] for e in events}) != len(events):
        raise ValueError('提示日志 ID 重复，请检查数据查询')
    buckets, sessions = defaultdict(list), defaultdict(list)
    for e in events:
        if e['condition'] not in CONDITIONS or (e.get('code') and e['code'] not in CODES):
            raise ValueError('存在未知条件或标签')
        buckets[(e['group_id'], e['condition'])].append(e)
        sessions[(e['group_id'], e['condition'], e['session_id'])].append(e)
    def aggregate(key, rows, session=False):
        result = dict(group_id=key[0], condition=key[1], group_name=rows[0]['group_name'],
                      session_count=len({e['session_id'] for e in rows}), **summarize(rows))
        if session:
            result.update(session_id=key[2], session_title=rows[0].get('session_title'))
        return result
    groups = [aggregate(k, v) for k, v in sorted(buckets.items())]
    if design == 'independent':
        left = {g['group_id'] for g in groups if g['condition'] == 'glasses'}
        right = {g['group_id'] for g in groups if g['condition'] == 'app_notification'}
        if left & right:
            raise ValueError('同一小组出现在两种条件中，请使用配对设计')
    pairs = pairs or []
    if design == 'paired':
        if not pairs:
            raise ValueError('请选择实际对应的小组配对')
        for condition in CONDITIONS:
            ids = [p[condition] for p in pairs]
            if len(ids) != len(set(ids)):
                raise ValueError('同一个小组不能重复配对')
            if set(ids) != {g['group_id'] for g in groups if g['condition'] == condition}:
                raise ValueError('请为当前范围内两种条件的每个小组各设置一次配对')
    conditions = []
    for condition in CONDITIONS:
        rows = [e for e in events if e['condition'] == condition]
        gs = [g for g in groups if g['condition'] == condition]
        conditions.append(dict(condition=condition, group_count=len(gs), session_count=len({e['session_id'] for e in rows}),
                               **summarize(rows), stats={m: describe([g[m] for g in gs]) for m in METRICS}))
    return dict(generated_at=datetime.now(timezone.utc).isoformat(), version='cue-uptake-v1',
                design=design, pairs=pairs, totals=summarize(events), groups=groups,
                sessions=[aggregate(k, v, True) for k, v in sorted(sessions.items())], conditions=conditions,
                comparisons=[compare(groups, m, design, pairs) for m in METRICS[:2]], events=events)
