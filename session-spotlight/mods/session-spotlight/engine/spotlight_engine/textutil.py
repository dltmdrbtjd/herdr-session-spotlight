"""Text helpers shared by the adapters and the search service.

Everything here works on plain Python strings. Highlights are returned as
segments ([text, matched] pairs) instead of offsets, so the JavaScript side
never has to translate Python code-point offsets into UTF-16 ones.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Sequence, Tuple

_WS = re.compile(r"\s+")

Segment = Tuple[str, bool]


def squash(text: str) -> str:
    """Collapses runs of whitespace (newlines included) into single spaces."""
    return _WS.sub(" ", text or "").strip()


_MARKUP = [
    (re.compile(r"</?[A-Za-z][\w\-]*(?:\s[^<>]{0,120})?>"), " "),  # <pasted_content id=...>, <br>
    (re.compile(r"```[\w+\-]*"), " "),
    (re.compile(r"(\*\*|__|`)"), ""),
    (re.compile(r"(^|\s)#{1,6}\s+"), r"\1"),
    (re.compile(r"\[([^\]\n]{1,200})\]\((?:[^)\s]{1,400})\)"), r"\1"),  # [label](url) -> label
]


def plain(text: str) -> str:
    """Markdown and tag noise out, for one-line snippets."""
    for pattern, repl in _MARKUP:
        text = pattern.sub(repl, text or "")
    return text


def clip(text: str, limit: int) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def title_from_prompt(text: str, limit: int = 80) -> str:
    """A one-line title from the first meaningful line of a prompt."""
    for line in (text or "").splitlines():
        line = line.strip().lstrip("#>*-• ").strip()
        if line:
            return clip(squash(line), limit)
    return ""


def fold(text: str) -> str:
    """Case folding that keeps string length, so spans map back onto the original."""
    lowered = (text or "").lower()
    return lowered if len(lowered) == len(text or "") else _fold_per_char(text or "")


def _fold_per_char(text: str) -> str:
    out = []
    for ch in text:
        low = ch.lower()
        out.append(low if len(low) == 1 else ch)
    return "".join(out)


def find_spans(text: str, terms: Iterable[str]) -> List[Tuple[int, int]]:
    """Every occurrence of every term (already folded), merged and sorted."""
    hay = fold(text)
    spans: List[Tuple[int, int]] = []
    for term in terms:
        if not term:
            continue
        start = 0
        while True:
            at = hay.find(term, start)
            if at < 0:
                break
            spans.append((at, at + len(term)))
            start = at + max(1, len(term))
    if not spans:
        return []
    spans.sort()
    merged = [spans[0]]
    for s, e in spans[1:]:
        ls, le = merged[-1]
        if s <= le:
            merged[-1] = (ls, max(le, e))
        else:
            merged.append((s, e))
    return merged


def segments(text: str, spans: Sequence[Tuple[int, int]]) -> List[Segment]:
    if not text:
        return []
    out: List[Segment] = []
    at = 0
    for s, e in spans:
        if s > at:
            out.append((text[at:s], False))
        out.append((text[s:e], True))
        at = e
    if at < len(text):
        out.append((text[at:], False))
    return out


def highlight(text: str, terms: Iterable[str]) -> List[Segment]:
    return segments(text, find_spans(text, list(terms)))


def snippet(text: str, terms: Sequence[str], width: int = 160, lead: int = 14) -> List[Segment]:
    """A window of `text` that starts just before its first match, highlighted, one line."""
    flat = squash(plain(text))
    spans = find_spans(flat, terms)
    if not spans:
        return [(clip(flat, width), False)]
    first = spans[0][0]
    start = max(0, first - lead)
    if start > 0:
        space = flat.rfind(" ", 0, start + 1)
        if space >= 0 and start - space < 8:
            start = space + 1
    end = min(len(flat), start + width)
    window = flat[start:end]
    shifted = [(max(0, s - start), min(end, e) - start) for s, e in spans if e > start and s < end]
    segs = segments(window, shifted)
    if start > 0:
        segs.insert(0, ("…", False))
    if end < len(flat):
        segs.append(("…", False))
    return segs


def contains_all(text: str, terms: Sequence[str]) -> int:
    """How many of the folded terms occur in text."""
    hay = fold(text)
    return sum(1 for t in terms if t and t in hay)


def excerpt(text: str, terms: Sequence[str], limit: int = 1800, before: int = 160) -> str:
    """Up to `limit` characters of a message, starting a little before its first match,
    so the match is on screen when the preview opens on it."""
    spans = find_spans(text, terms) if terms else []
    if not spans or spans[0][0] <= before + 80:
        return text if len(text) <= limit else text[:limit].rstrip() + "…"
    start = max(0, spans[0][0] - before)
    nl = text.rfind("\n", 0, start + 1)
    if nl >= 0 and start - nl < 80:
        start = nl + 1
    body = text[start:start + limit].rstrip()
    return "…" + body + ("…" if start + limit < len(text) else "")
