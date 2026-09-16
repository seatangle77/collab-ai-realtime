"""Offline lexical diversity. Pure analysis: no database writes or online TTR changes."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import re
import unicodedata
from itertools import combinations
from typing import Callable

import numpy as np

CONDITIONS = ('no_assistance', 'glasses', 'app_notification')
TASKS = ('lost_at_sea', 'moon_survival', 'winter_survival')
WINDOW = 100
PERMUTATIONS = 4999
SEED = 20260916
FILLERS = frozenset(('嗯', '呃', '啊', '哦', '唔', '呜'))
# Remove only explicit non-speech annotations, never arbitrary bracketed speech.
ANNOTATIONS = re.compile(r'[\[【（(](?:笑声|笑|咳嗽|杂音|噪音|听不清|无法辨认|沉默)[\]】）)]')


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def clean_text(value: str) -> str:
    return ANNOTATIONS.sub(' ', unicodedata.normalize('NFKC', value)).strip()


def clean_tokens(tokens: list[str]) -> list[str]:
    return [t for token in tokens if (t := unicodedata.normalize('NFKC', token).strip().lower())
            and t not in FILLERS and any(unicodedata.category(c)[0] in ('L', 'N') for c in t)]


def mattr(tokens: list[str], window: int = WINDOW) -> float | None:
    if len(tokens) < window:
        return None
    counts = Counter(tokens[:window])
    total = len(counts)
    for i in range(window, len(tokens)):
        old = tokens[i-window]
        counts[old] -= 1
        if not counts[old]:
            del counts[old]
        counts[tokens[i]] += 1
        total += len(counts)
    return total / (window * (len(tokens) - window + 1))


def mtld(tokens: list[str], threshold: float = .72) -> float | None:
    """Bidirectional MTLD with fractional final factor; undefined != zero."""
    def direction(sequence):
        types, count, factors = set(), 0, 0.0
        for token in sequence:
            types.add(token)
            count += 1
            if len(types) / count <= threshold:
                factors += 1
                types, count = set(), 0
        if count:
            factors += (1 - len(types) / count) / (1 - threshold)
        return len(sequence) / factors if factors > 0 else None
    if len(tokens) < WINDOW:
        return None
    forward, backward = direction(tokens), direction(tokens[::-1])
    return (forward + backward) / 2 if forward is not None and backward is not None else None


def _f(values, labels):
    grand = values.mean()
    total = float(np.sum((values-grand)**2))
    within = sum(float(np.sum((values[labels == c]-values[labels == c].mean())**2)) for c in np.unique(labels))
    between = max(0., total-within)
    if total <= 1e-20:
        return 0., 0.
    if within <= 1e-20:
        return float('inf'), 1.
    k = len(np.unique(labels))
    return (between/(k-1))/(within/(len(values)-k)), between/total


def _permute(labels, tasks, rng):
    result = labels.copy()
    for task in np.unique(tasks):
        indexes = np.flatnonzero(tasks == task)
        result[indexes] = rng.permutation(labels[indexes])
    return result


def holm(values):
    result = [0.] * len(values)
    previous = 0.
    for rank, index in enumerate(sorted(range(len(values)), key=lambda i: values[i])):
        previous = max(previous, min(1., values[index] * (len(values)-rank)))
        result[index] = previous
    return result


def inference(observations, metric, permutations=PERMUTATIONS):
    rows = [r for r in observations if r[metric] is not None]
    result = dict(metric=metric, n=len(rows), status='insufficient_data', statistic=None,
                  p_value=None, eta_squared=None, pairs=[], permutations=permutations)
    tasks_present = sorted({r['task_id'] for r in rows})
    # Explicitly require comparable strata; never silently pool missing task cells.
    if not tasks_present or any(sum(r['condition'] == c and r['task_id'] == t for r in rows) < 2
                                for t in tasks_present for c in CONDITIONS):
        return result
    values = np.array([r[metric] for r in rows], dtype=float)
    labels = np.array([r['condition'] for r in rows])
    tasks = np.array([r['task_id'] for r in rows])
    statistic, eta = _f(values, labels)
    rng = np.random.default_rng(SEED)
    exceed = sum(_f(values, _permute(labels, tasks, rng))[0] >= statistic - 1e-12 for _ in range(permutations))
    p = (exceed+1)/(permutations+1)
    result.update(status='ok', statistic=float(statistic) if np.isfinite(statistic) else None,
                  p_value=p, eta_squared=float(eta))
    if not np.isfinite(statistic):
        result['status'] = 'zero_within_variance'
    if p >= .05:
        return result
    for a, b in combinations(CONDITIONS, 2):
        mask = np.isin(labels, [a, b])
        v, lab, task = values[mask], labels[mask], tasks[mask]
        # Equal task weights avoid unequal task mixtures masquerading as condition effects.
        def difference(ls):
            return float(np.mean([v[(ls == b) & (task == t)].mean() - v[(ls == a) & (task == t)].mean() for t in tasks_present]))
        diff = difference(lab)
        exceed = sum(abs(difference(_permute(lab, task, rng))) >= abs(diff)-1e-12 for _ in range(permutations))
        draws = []
        for _ in range(1999):
            draws.append(np.mean([rng.choice(v[(lab == b) & (task == t)], size=sum((lab == b) & (task == t)), replace=True).mean()
                                  - rng.choice(v[(lab == a) & (task == t)], size=sum((lab == a) & (task == t)), replace=True).mean()
                                  for t in tasks_present]))
        low, high = np.quantile(draws, [.025, .975])
        result['pairs'].append(dict(condition_a=a, condition_b=b, difference=diff,
                                    p_value=(exceed+1)/(permutations+1), p_adjusted=None,
                                    ci_low=float(low), ci_high=float(high)))
    for pair, adjusted in zip(result['pairs'], holm([p['p_value'] for p in result['pairs']])):
        pair['p_adjusted'] = adjusted
    return result


def build_analysis(rows: list[dict], tokenize: Callable[[str], list[str]], *, task_filter='all',
                   tokenizer_metadata=None, permutations=PERMUTATIONS):
    """Rows include left-joined empty sessions, so absent sources stay visible."""
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row['group_id'], row.get('session_id'))].append(row)
    session_counts = Counter(g for g, s in grouped if s is not None)
    observations, excluded = [], []
    for (gid, sid), parts in sorted(grouped.items(), key=lambda p: str(p[0])):
        first = parts[0]
        task_ids = list(dict.fromkeys(first.get('task_ids') or []))
        task = task_ids[0] if len(task_ids) == 1 and task_ids[0] in TASKS else None
        if task_filter != 'all' and task is not None and task != task_filter:
            continue
        base = dict(group_id=gid, group_name=first['group_name'], condition=first['condition'],
                    session_id=sid, session_title=first.get('session_title'), task_id=task)
        ordered = sorted(parts, key=lambda r: (r.get('order_index') or 0, str(r.get('utterance_id') or '')))
        texts = [r['content'] for r in ordered if r.get('content') and r['content'].strip()]
        reason = ('missing_session' if sid is None else 'multiple_sessions' if session_counts[gid] != 1
                  else 'missing_text' if not texts else 'ambiguous_task' if task is None else None)
        source_hash = fingerprint([(r.get('utterance_id'), r.get('order_index'), r.get('content')) for r in ordered])
        if reason:
            excluded.append(dict(**base, reason=reason, token_count=None, source_hash=source_hash))
            continue
        tokens = [token for content in texts for token in clean_tokens(tokenize(clean_text(content))) ]
        if len(tokens) < WINDOW:
            excluded.append(dict(**base, reason='short_text', token_count=len(tokens), source_hash=source_hash))
            continue
        observations.append(dict(**base, token_count=len(tokens), type_count=len(set(tokens)),
                                 ttr=len(set(tokens))/len(tokens), mattr_100=mattr(tokens), mtld=mtld(tokens),
                                 window_count=len(tokens)-WINDOW+1, utterance_count=len(texts),
                                 source_hash=source_hash, token_hash=fingerprint(tokens)))
    summaries = []
    for metric in ('mattr_100', 'mtld', 'token_count', 'type_count', 'ttr'):
        for condition in CONDITIONS:
            values = [r[metric] for r in observations if r['condition'] == condition and r[metric] is not None]
            summaries.append(dict(metric=metric, condition=condition, n=len(values),
                                  mean=float(np.mean(values)) if values else None,
                                  sd=float(np.std(values, ddof=1)) if len(values)>1 else None,
                                  median=float(np.median(values)) if values else None,
                                  min=min(values) if values else None, max=max(values) if values else None))
    return dict(generated_at=datetime.now(timezone.utc).isoformat(), observations=observations,
                excluded=excluded, summaries=summaries,
                tests=[inference(observations, m, permutations) for m in ('mattr_100', 'mtld')],
                parameters=dict(version='lexical-diversity-v1', source='coi_utterances', read_only=True,
                                task_filter=task_filter, window=WINDOW, stride=1, mtld_threshold=.72,
                                minimum_tokens=WINDOW, fillers=sorted(FILLERS), normalization='NFKC + lowercase',
                                punctuation_removed=True, stopwords_removed=False, single_character_words_retained=True,
                                tokenizer=tokenizer_metadata or {}, permutations=permutations, seed=SEED,
                                bootstrap_samples=1999, confidence_level=.95, ci_multiplicity_adjusted=False,
                                pairwise_adjustment='Holm within each metric',
                                primary_metric='mattr_100', robustness_metric='mtld'),
                source_hash=fingerprint(rows))
