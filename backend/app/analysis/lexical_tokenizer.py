"""Isolated tokenizer: no mutation of the live perception pipeline or its dictionaries."""
from importlib.metadata import version
from threading import Lock

from .lexical_diversity_service import fingerprint

_LOCK = Lock()
_PIPELINE = None
_METADATA = None


def analyze_with_hanlp(rows, task_filter):
    global _PIPELINE, _METADATA
    from .lexical_diversity_service import build_analysis
    # Lazy load in a worker, once. Failed loading is an error, never a silent tokenizer fallback.
    with _LOCK:
        if not rows or not any(r.get('content', '').strip() for r in rows if r.get('content')):
            return build_analysis(rows, lambda _: [], task_filter=task_filter,
                                  tokenizer_metadata={'status': 'not_needed_no_text'})
        if _PIPELINE is None:
            import hanlp
            from ..nlp.lexicon_loader import load_custom_words, load_candidate_words
            pipeline = hanlp.load(hanlp.pretrained.mtl.CLOSE_TOK_POS_NER_SRL_DEP_SDP_CON_ELECTRA_SMALL_ZH)
            forced, combined = sorted(load_custom_words()), sorted(load_candidate_words())
            if forced:
                pipeline['tok/fine'].dict_force = set(forced)
            if combined:
                pipeline['tok/fine'].dict_combine = set(combined)
            _METADATA = dict(library='HanLP', version=version('hanlp'),
                             model=hanlp.pretrained.mtl.CLOSE_TOK_POS_NER_SRL_DEP_SDP_CON_ELECTRA_SMALL_ZH,
                             task='tok/fine', dictionary_hash=fingerprint([forced, combined]),
                             forced_words=forced, combined_words=combined)
            _PIPELINE = pipeline
        from .lexical_diversity_service import clean_text
        texts = sorted({clean_text(r['content']) for r in rows if r.get('content')})
        texts = [s for s in texts if s]
        tokenized = {}
        for start in range(0, len(texts), 32):
            batch = texts[start:start+32]
            results = _PIPELINE(batch, tasks=['tok/fine'])['tok/fine']
            if len(results) != len(batch):
                raise ValueError('Tokenizer returned an unexpected batch size')
            tokenized.update(zip(batch, results))
        def tokenize(value):
            return tokenized[value] if value else []
        return build_analysis(rows, tokenize, task_filter=task_filter, tokenizer_metadata=_METADATA)
