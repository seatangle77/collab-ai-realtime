"""Recording documents stored in existing correction_reason text; COI is read-only."""
import json

PREFIX = '录音完整修订'
MARKER = '\n[recording-document-v1]'


def encode_document(document):
    return PREFIX + MARKER + json.dumps(document, ensure_ascii=False, separators=(',', ':'))


def decode_document(reason, corrected_text=None):
    if not isinstance(reason, str) or not reason.startswith(PREFIX + MARKER):
        return None
    try:
        doc = json.loads(reason.split(MARKER, 1)[1])
        if not isinstance(doc, dict) or not isinstance(doc.get('segments'), list):
            return None
        body = '\n'.join(s['text'] for s in doc['segments'] if s['kind'] == 'recording')
        if corrected_text is not None and body != corrected_text:
            return None
        return doc
    except (ValueError, KeyError, TypeError):
        return None


def public_reason(reason):
    return reason.split(MARKER, 1)[0] if reason else reason
