"""Masks credentials before text reaches the index.

The adapters already leave out tool calls, tool output, environment blocks and
attachments. This is the second line: a prompt or an answer that quotes a key
still never stores it. The patterns are deliberately conservative (long,
structured tokens and explicit `key=value` pairs) so ordinary prose survives.
"""

from __future__ import annotations

import re

MASK = "[REDACTED]"

_TOKEN_PATTERNS = [
    # PEM private keys, whole block.
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----"),
    # Cloud and SaaS tokens with a recognizable shape.
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(r"\bsk-(?:ant-|proj-|live-|test-)?[A-Za-z0-9_\-]{20,}"),
    re.compile(r"\b(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{16,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}"),
    re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"\bxox[abposr]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{35}"),
    re.compile(r"\bnpm_[A-Za-z0-9]{36}\b"),
    # JSON Web Tokens.
    re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"),
]

_BEARER = re.compile(r"(?i)\b(bearer|token)(\s+)([A-Za-z0-9._\-+/=]{20,})")
_SECRET_NAME = (
    r"(?:[A-Z0-9_]*[_\-])?(?:password|passwd|pwd|secret|api[_\-]?key|access[_\-]?key|access[_\-]?token|auth[_\-]?token|"
    r"refresh[_\-]?token|client[_\-]?secret|private[_\-]?key|session[_\-]?token)[A-Z0-9_]*"
)
# key=value, key: value, "key": "value", 'key' = 'value'. A quoted value is masked whole, however
# long, up to its closing quote or, if that was cut off, the end of the line; a bare one needs 6+
# characters so prose survives.
_ASSIGNMENT = re.compile(
    r"(?i)([\"']?)\b(" + _SECRET_NAME + r")\1(\s*[:=]\s*)"
    r"(?:\"((?:[^\"\\\n]|\\.)*)(?:\"|(?=\n)|$)|'((?:[^'\\\n]|\\.)*)(?:'|(?=\n)|$)|([^\s\"',;]{6,}))"
)


def _mask_assignment(m: "re.Match") -> str:
    head = f"{m.group(1)}{m.group(2)}{m.group(1)}{m.group(3)}"
    if m.group(4) is not None:
        return f'{head}"{MASK}"'
    if m.group(5) is not None:
        return f"{head}'{MASK}'"
    return f"{head}{MASK}"


_URL_CREDENTIALS = re.compile(r"(\b[a-z][a-z0-9+.\-]*://[^\s/:@]+:)([^\s/@]+)(@)")


def redact(text: str) -> str:
    if not text:
        return text
    for pattern in _TOKEN_PATTERNS:
        text = pattern.sub(MASK, text)
    text = _BEARER.sub(lambda m: f"{m.group(1)}{m.group(2)}{MASK}", text)
    text = _ASSIGNMENT.sub(_mask_assignment, text)
    text = _URL_CREDENTIALS.sub(lambda m: f"{m.group(1)}{MASK}{m.group(3)}", text)
    return text
