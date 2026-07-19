"""Deterministic verify-layer primitives (Scope 2 of
specs/2026-07-13-compose-correct-dont-reject — 04b D2a/D2c, 02-spec Never-fabricate).

Four PURE functions, unit-tested, with NO compose-loop wiring (Scope 3 wires
them; the Scope-2 calibration battery runs them so the battery measures the
exact gate production will run — the Stage-5 structural decision):

1. ``salient_tokens`` — the pre-gate token class: 4-digit years, standalone
   numbers, century tokens (word-form ordinals included, verify_gate-LOCAL —
   claim_dedup's ``_signature`` is untouched because it feeds route-level
   dedup), and proper-noun tokens.
2. ``pregate_violations`` — fail-closed, zero-LLM: any salient token of a
   sentence absent from its cited bodies' union is a violation.
3. ``is_valid_trim`` — mechanical acceptance of an LLM-executed trim: no
   added tokens AND every removed content token is in the flagged
   unsupported set; anything else is NOT a trim (04b D2c — a tidied-away
   hedge clause is a full rewrite, not a trim).
4. ``route_flagged_sentence`` — under-cited (declared bodies do not cover
   the sentence's salient tokens) routes to the floor, never to correction.

RECORDED LIMITS (04b + the 2026-07-16 skeptic pass): salient tokens shorter
than 3 characters ("WH", "II") are invisible to the proper-noun class; a
SENTENCE-INITIAL proper noun is skipped (initial capitalization is positional,
not evidential); and WORD-FORM cardinals ("two hundred and forty-two") are
invisible to the number class (only ordinal CENTURIES are canonicalized).
Each is covered by entailment + the Scope-3b quote rule, measured by dedicated
FP battery items, not fixed here.
"""

from __future__ import annotations

import re
from typing import Literal

from .claim_dedup import _canonicalize_dates
from .validation import _CAP_TOKEN_RE, _SENTENCE_HEAD_WORDS

# Word-form ordinal centuries, e.g. "nineteenth century" -> "19th century",
# so claim_dedup._canonicalize_dates folds both phrasings to the same c19ad
# token. LOCAL to verify_gate (the Stage-5 flagged decision): extending
# claim_dedup._signature would silently change route-level dedup behavior.
_ORDINAL_WORDS: dict[str, int] = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
    "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14,
    "fifteenth": 15, "sixteenth": 16, "seventeenth": 17, "eighteenth": 18,
    "nineteenth": 19, "twentieth": 20, "twenty-first": 21,
}
_WORD_ORDINAL_CENTURY_RE = re.compile(
    r"\b(" + "|".join(_ORDINAL_WORDS) + r")\s+century\b", re.IGNORECASE
)

_YEAR_RE = re.compile(r"\b1[0-9]{3}\b|\b20[0-2][0-9]\b")
_NUMBER_RE = re.compile(r"\b\d+\b")
_CENTURY_TOKEN_RE = re.compile(r"\bc\d{1,2}(?:ad|bc)\b")

RouteDecision = Literal["under_cited", "correctable"]


def _canonicalize(text: str) -> str:
    """Fold word-form ordinal centuries to digit form, then apply
    claim_dedup's date canonicalization — both sides of every comparison run
    through this, so "nineteenth century" == "19th century" == c19ad."""

    def _fold(m: re.Match[str]) -> str:
        return f"{_ORDINAL_WORDS[m.group(1).lower()]}th century"

    return _canonicalize_dates(_WORD_ORDINAL_CENTURY_RE.sub(_fold, text))


# Typographic apostrophe (U+2019), common in the corpus — folded to ASCII so
# possessives tokenize identically on both sides of every comparison.
_TYPOGRAPHIC_APOSTROPHE = "\u2019"


def _fold_apostrophes(text: str) -> str:
    return text.replace(_TYPOGRAPHIC_APOSTROPHE, "'")


def _word_tokens(text: str) -> frozenset[str]:
    """Casefolded word tokens of a text (apostrophes/hyphens split), the
    membership universe pre-gate tokens are checked against."""
    return frozenset(re.findall(r"[a-z0-9]+", _fold_apostrophes(text).casefold()))


def _proper_noun_subtokens(text: str) -> frozenset[str]:
    """Proper-noun subtokens of a text: capitalized 3+-letter tokens
    (validation's ``_CAP_TOKEN_RE``) EXCEPT the sentence-INITIAL token, whose
    capitalization is positional, not evidential (a sentence opening with a
    real name — "Dickens stayed…" — is the recorded blind spot; entailment
    still checks it). Head words (the/there/…) are filtered wherever they
    appear capitalized (quote-initial "There sat…"). Tokens split on
    hyphen/apostrophe so "Saint-Germain" checks as {saint, germain} and
    "Empress's" as {empress}; subtokens under 3 chars drop ("II", "WH")."""
    out: set[str] = set()
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        sentence = sentence.strip()
        for m in _CAP_TOKEN_RE.finditer(sentence):
            if m.start() == 0:
                continue  # sentence-initial capitalization proves nothing
            if m.group(0).lower() in _SENTENCE_HEAD_WORDS:
                continue
            for sub in re.findall(r"[a-z0-9]{3,}", _fold_apostrophes(m.group(0)).casefold()):
                out.add(sub)
    return frozenset(out)


def salient_tokens(text: str) -> frozenset[str]:
    """The pre-gate salient-class tokens of a text, canonicalized: years,
    standalone numbers, century tokens, and proper-noun subtokens."""
    canon = _canonicalize(text)
    tokens: set[str] = set(_NUMBER_RE.findall(canon))
    tokens |= set(_CENTURY_TOKEN_RE.findall(canon.casefold()))
    tokens |= _proper_noun_subtokens(canon)
    return frozenset(tokens)


# Quoted spans: an opening double-quote mark (ASCII " or typographic “ U+201C)
# through the next closing double-quote mark (ASCII " or typographic ” U+201D) —
# the interior (no embedded quote mark) is captured; the marks are not part of
# the span. M1 (judge): a SINGLE character class on each side catches MIXED-STYLE
# spans too — a curly-open/ascii-close (“…") or ascii-open/curly-close ("…”),
# which the old two-alternation form (matched pairs only) never checked, so an
# altered quote could ship unflagged behind a mismatched close-mark.
# RECORDED LIMIT: a lone apostrophe / single quote (ASCII or typographic) is
# DELIBERATELY not a delimiter — it is overwhelmingly a possessive/contraction in
# this corpus, so treating it as a quote open would mis-span most sentences.
# Single-quoted citations are the residual blind spot, backstopped by entailment
# + the salient-token / new-proper-noun scans.
_QUOTE_SPAN_RE = re.compile(r'["“]([^"“”]*)["”]')


def _normalize_for_verbatim(text: str) -> str:
    """Whitespace/case fold so 'appears verbatim' is robust to line wrapping and
    trivial spacing (identical to verify._normalize_for_verbatim; duplicated here
    so verify_gate stays import-free of verify — verify imports verify_gate)."""
    return " ".join(text.split()).casefold()


def quote_violations(sentence_text: str, cited_bodies: tuple[str, ...]) -> tuple[str, ...]:
    """Quoted spans of ``sentence_text`` (inside ASCII " " or curly “ ”) that do
    NOT appear verbatim (whitespace/case-normalized) in the cited bodies' union
    — deterministic, zero-LLM, fails closed (04b BL-V4). This is the stage that
    rewrites quotes: the salient-token classes are blind to lowercase quote
    interiors and paraphrase-tolerant entailment misses a word changed inside
    the marks, so a quote ships verbatim or not as a quote. Each violation is
    the offending span text; an empty result means every quoted span is
    body-verbatim (it says nothing about the prose OUTSIDE the marks)."""
    haystack = _normalize_for_verbatim("\n".join(cited_bodies))
    violations: list[str] = []
    for m in _QUOTE_SPAN_RE.finditer(sentence_text):
        span = m.group(1)
        norm = _normalize_for_verbatim(span)
        if not norm:
            continue  # empty quotes carry no claim
        if norm not in haystack:
            violations.append(span)
    return tuple(dict.fromkeys(violations))


def pregate_violations(sentence_text: str, cited_bodies: tuple[str, ...]) -> tuple[str, ...]:
    """Salient-class tokens of ``sentence_text`` absent from the cited bodies'
    union — deterministic, zero-LLM, fails closed. Each violation is
    ``"<class>:<token>"`` (class ∈ year|number|century|proper_noun). An empty
    result means the sentence's salient tokens are all body-covered; it says
    nothing about relations (entailment's job)."""
    allowed = _word_tokens(_canonicalize("\n".join(cited_bodies)))
    canon = _canonicalize(sentence_text)
    violations: list[str] = []
    for num in _NUMBER_RE.findall(canon):
        if num not in allowed:
            cls = "year" if _YEAR_RE.fullmatch(num) else "number"
            violations.append(f"{cls}:{num}")
    for century in _CENTURY_TOKEN_RE.findall(canon.casefold()):
        if century not in allowed:
            violations.append(f"century:{century}")
    for noun in sorted(_proper_noun_subtokens(canon)):
        if noun not in allowed:
            violations.append(f"proper_noun:{noun}")
    return tuple(dict.fromkeys(violations))


# Function words whose removal alongside a trimmed clause carries no factual
# content of its own (the clause's content words still gate the trim).
_TRIM_FUNCTION_WORDS: frozenset[str] = frozenset(
    [
        "the", "a", "an", "and", "but", "or", "so", "yet", "of", "to", "in",
        "on", "at", "by", "for", "with", "as", "from", "that", "this",
        "these", "those", "it", "its", "his", "her", "their", "there",
        "here", "was", "were", "is", "are", "be", "been", "has", "had",
        "have", "though", "although", "while", "when", "where", "who",
        "whom", "whose", "which",
    ]
)


def _token_sequence(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", _fold_apostrophes(text).casefold())


def _is_subsequence(needle: list[str], haystack: list[str]) -> bool:
    it = iter(haystack)
    return all(tok in it for tok in needle)


def is_valid_trim(original: str, trimmed: str, flagged_tokens: frozenset[str]) -> bool:
    """Mechanical trim acceptance (04b D2c): a trim is a pure DELETION — the
    trimmed token sequence must be an ORDER-PRESERVING subsequence of the
    original (no additions, and no reordering: a bag-of-words check would
    certify a relation-INVERTING permutation, the exact class the calibrated
    entailment exists to catch — 2026-07-16 skeptic finding), and every
    REMOVED content token (any non-function-word token — numbers and short
    tokens included; strictness fails toward the full rewrite) must be in the
    flagged unsupported set. Anything else counts as the attempt-2 full
    rewrite. A hedge clause tidied away fails here — its content words are not
    in the flagged set (the dispute-flatten guard). Trim output still re-enters
    the full gate (02-spec Outputs item 2); this check only decides whether the
    attempt consumed the trim slot or the rewrite slot."""
    orig_seq = _token_sequence(original)
    trim_seq = _token_sequence(trimmed)
    if not _is_subsequence(trim_seq, orig_seq):
        return False  # added or reordered tokens — never a trim
    flagged = frozenset(
        sub
        for tok in flagged_tokens
        for sub in re.findall(r"[a-z0-9]+", _fold_apostrophes(tok).casefold())
    )
    removed_content = {
        t for t in (frozenset(orig_seq) - frozenset(trim_seq)) if t not in _TRIM_FUNCTION_WORDS
    }
    return removed_content <= flagged


def route_flagged_sentence(
    sentence_text: str,
    declared_bodies: tuple[str, ...],
    stop_union_bodies: tuple[str, ...] = (),
) -> RouteDecision:
    """Correction-router decision (02-spec Outputs item 2): UNDER-CITED iff a
    salient token uncovered by the declared citations' bodies is OWNED by the
    stop union — the fact exists at the stop but the citation set missed it, so
    the sentence routes straight to the floor of the owning beats, never to
    correction (fact-preserving rule: under-cited is NEVER correction-stripped).

    Everything else is correctable: all-tokens-covered (relation/hedge
    entailment failures → trim then rewrite) AND uncovered tokens owned by NO
    stop beat (separable unsourced garnish — the exact class the D2c trim
    exists for; flooring it would ship nothing, since no beat owns the tokens).
    Ownership semantics per 02-spec ("the floor of the stop-union beats owning
    its uncovered tokens"): without them the trim path is dead code and every
    world-knowledge garnish sentence would floor."""
    uncovered = pregate_violations(sentence_text, declared_bodies)
    if not uncovered:
        return "correctable"
    union_tokens = _word_tokens(_canonicalize("\n".join(stop_union_bodies)))
    owned = any(v.split(":", 1)[1] in union_tokens for v in uncovered)
    return "under_cited" if owned else "correctable"


__all__ = [
    "RouteDecision",
    "is_valid_trim",
    "pregate_violations",
    "quote_violations",
    "route_flagged_sentence",
    "salient_tokens",
]
