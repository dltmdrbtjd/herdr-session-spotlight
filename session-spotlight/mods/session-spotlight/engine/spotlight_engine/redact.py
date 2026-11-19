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
_ASSIGNMENT = re.compile(
    r"(?i)\b((?:[A-Z0-9_]*_)?(?:password|passwd|pwd|secret|api[_\-]?key|access[_\-]?key|"
    r"access[_\-]?token|auth[_\-]?token|refresh[_\-]?token|client[_\-]?secret|private[_\-]?key|"
    r"session[_\-]?token)[A-Z0-9_]*)(\s*[:=]\s*)([\"']?)([^\s\"',;]{6,})"
)
_URL_CREDENTIALS = re.compile(r"(\b[a-z][a-z0-9+.\-]*://[^\s/:@]+:)([^\s/@]+)(@)")


def redact(text: str) -> str:
    if not text:
        return text
    for pattern in _TOKEN_PATTERNS:
        text = pattern.sub(MASK, text)
    text = _BEARER.sub(lambda m: f"{m.group(1)}{m.group(2)}{MASK}", text)
    text = _ASSIGNMENT.sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}{MASK}", text)
    text = _URL_CREDENTIALS.sub(lambda m: f"{m.group(1)}{MASK}{m.group(3)}", text)
    return text
