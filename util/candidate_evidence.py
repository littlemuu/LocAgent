"""Per-tool provenance for renderer-generated finish targets.

Opaque markers survive concatenation in legacy tools. They are removed before
tracing, paging or dispatch; source text cannot manufacture unpredictable markers.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
import re
import secrets

_ACTIVE = ContextVar('candidate_evidence', default=None)


class ToolEvidence(str):
    def __new__(cls, text, spans):
        value = super().__new__(cls, text)
        value.candidate_spans = spans
        return value


class EvidenceCapture:
    def __init__(self):
        self.nonce = secrets.token_hex(24)
        self.targets = {}

    def mark(self, text, payload, kind, repeated=False):
        key = str(len(self.targets))
        self.targets[key] = (text, deepcopy(payload), kind, repeated)
        return f'[[locagent:{self.nonce}:{key}:start]]' + text + f'[[locagent:{self.nonce}:{key}:end]]'

    def unwrap(self, raw):
        pattern = re.compile(r'\[\[locagent:' + self.nonce + r':(\d+):start\]\](.*?)'
                             + r'\[\[locagent:' + self.nonce + r':\1:end\]\]', re.DOTALL)
        pieces, spans, cursor, position = [], [], 0, 0
        for match in pattern.finditer(raw):
            prefix = raw[cursor:match.start()]
            pieces.append(prefix); position += len(prefix)
            text = match.group(2)
            original, payload, kind, repeated = self.targets[match.group(1)]
            if text == original:
                spans.append({'offset': position, 'end_offset': position + len(text),
                              'payload': deepcopy(payload), 'type': kind, 'repeated': repeated})
            pieces.append(text); position += len(text)
            cursor = match.end()
        pieces.append(raw[cursor:])
        return ToolEvidence(''.join(pieces), spans)


@contextmanager
def capture_evidence():
    capture = EvidenceCapture()
    token = _ACTIVE.set(capture)
    try:
        yield capture
    finally:
        _ACTIVE.reset(token)


def mark_target(text, payload, kind):
    capture = _ACTIVE.get()
    return text if capture is None else capture.mark(text, payload, kind)


def plain_evidence(text):
    capture = _ACTIVE.get()
    return text if capture is None else str(capture.unwrap(text))


def mark_repeat(text, tagged_hint):
    """A trusted repeat notice is a reference, never fresh source evidence."""
    capture = _ACTIVE.get()
    if capture is None:
        return text
    hint = capture.unwrap(tagged_hint)
    if len(hint.candidate_spans) != 1:
        return text
    span = hint.candidate_spans[0]
    return capture.mark(text, span['payload'], span['type'], repeated=True)
