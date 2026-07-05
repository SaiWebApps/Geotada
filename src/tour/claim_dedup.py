"""Route-level claim-repetition suppression (backlog #22).

A route can seat several beats — often from DIFFERENT source books — that restate
the same historical fact. The canonical case: the Île de la Cité seats three
beats (from Around-and-About, Rough Guide, Frommer's) that each narrate "the
Parisii settled the island in the 3rd century BC", so the tourist hears the
founding story three times. The exact-beat-id dedup in ``generation.py`` cannot
catch this (different ids), and the within-POI ``_apply_b8_lite_dedup`` misses it
too (cross-book paraphrases with BC/century dates and divergent supporting-entity
casts evade its 4-digit-year + entity thresholds).

This pass runs over the ASSEMBLED sentence stream and drops a beat-sourced
sentence ONLY when EVERY ``key_claim`` that sentence realizes was already voiced
by an EARLIER, DIFFERENT beat anywhere in the route. It is deliberately surgical:

- CONTENT-SAFE by construction: a sentence that fuses a repeated fact with a
  NOVEL one (compound sentences are common — "settled c.300 BC by the Parisii,
  and in 52 BC overrun by the Romans, who built a palace-fortress") is kept
  INTACT, because it still realizes a novel claim. Only a PURE restatement — a
  sentence whose every claim is already voiced — is removed, so a distinct fact
  is never silently lost. (The trade: a compound restatement may voice a
  duplicated fact a second time; that is accepted to guarantee zero content loss.
  A beat that ALSO carries distinct claims keeps every sentence carrying one.)
- It NEVER empties a beat: at least one sentence per beat always survives, so the
  set of emitted beat-ids is unchanged and the golden overlap gate is not
  perturbed (it counts distinct beat source-ids, not sentences).
- It only touches ``source_type == "beat"`` sentences; glue, synthesized openers
  and reflections are never removed.

Known limits (documented, deferred): a dropped sentence does not shrink the
per-beat ``_sum_audio`` estimate (reported audio is per cited beat, so a trimmed
multi-sentence beat over-reports by the dropped sentence's share — small, since
only pure repeats drop), and ``verify._visited_claims`` still keys off the whole
beat's ``key_claims`` (a pre-existing over-licensing widened marginally here).

Detection is deterministic (no build-time LLM): each sentence is matched to the
beat's best key_claim; two claims are "the same fact" when their canonical-token
signatures have high overlap. Dates are canonicalized to centuries so
"300 BC" and "the 3rd century BC" unify.
"""

from __future__ import annotations

import re
from collections import defaultdict

from .contract import BeatSequence, Sentence

# A sentence must contain at least this fraction of a claim's tokens to be judged
# "about" that claim (overlap coefficient, so ~containment of the terse claim).
CLAIM_MATCH_MIN: float = 0.5
# Two claim signatures are the SAME fact at or above this overlap coefficient.
CLAIM_DEDUP_THRESHOLD: float = 0.7
# ...and must share at least this many tokens (guards against tiny-claim noise).
MIN_SHARED_TOKENS: int = 2

_STOPWORD_TEXT = (
    "the a an and or but of to in on at by for with from into onto over under as is "
    "was were are be been being it its this that these those their there here who whom "
    "which what when where why how then than so such not no nor only just also very can "
    "could would should may might must will shall do does did done has have had they "
    "them he she his her our your my mine you we us me one two first now still around "
    "about near between along after before during within upon out off up down"
)
_STOPWORDS: frozenset[str] = frozenset(_STOPWORD_TEXT.split())

# Ordinal century, e.g. "3rd century BC" -> c3bc ; "13th century" -> c13ad.
_ORD_CENTURY_RE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)\s+century(\s+bc)?\b", re.IGNORECASE)
# Bare year with era, e.g. "300 BC" -> its century ; "52 BC" -> c1bc.
_YEAR_BC_RE = re.compile(r"\b(\d{1,4})\s*bc\b", re.IGNORECASE)


def _canonicalize_dates(text: str) -> str:
    """Fold date phrasings to a shared century token so paraphrases unify.

    "300 BC" and "the 3rd century BC" both -> "c3bc"; "52 BC" -> "c1bc";
    "13th century" -> "c13ad". 4-digit AD years are left as their own digit token.
    """

    def _ord(match: re.Match[str]) -> str:
        n = int(match.group(1))
        era = "bc" if match.group(2) else "ad"
        return f" c{n}{era} "

    def _bc_year(match: re.Match[str]) -> str:
        n = int(match.group(1))
        century = (n - 1) // 100 + 1
        return f" c{century}bc "

    text = _ORD_CENTURY_RE.sub(_ord, text)
    text = _YEAR_BC_RE.sub(_bc_year, text)
    return text


def _signature(text: str) -> frozenset[str]:
    """Canonical salient-token set of a claim or sentence."""
    text = _canonicalize_dates(text.lower())
    tokens = re.findall(r"[a-z0-9]+", text)
    return frozenset(t for t in tokens if len(t) >= 3 and t not in _STOPWORDS)


def _overlap(a: frozenset[str], b: frozenset[str]) -> float:
    """Overlap coefficient: |a∩b| / min(|a|,|b|). 0 if either is empty."""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def _realized_claim_signatures(
    sentence_text: str, claim_signatures: list[frozenset[str]]
) -> list[frozenset[str]]:
    """Every key_claim signature this sentence realizes (overlap ≥ CLAIM_MATCH_MIN).

    A compound sentence realizes MORE THAN ONE claim; we must see all of them so a
    novel claim riding alongside a repeated one keeps the sentence alive.
    """
    s_sig = _signature(sentence_text)
    if not s_sig:
        return []
    # fraction of each terse claim present in the sentence (~containment)
    return [c_sig for c_sig in claim_signatures if _overlap(c_sig, s_sig) >= CLAIM_MATCH_MIN]


def suppress_repeated_claims(
    sentences: list[Sentence], beat_sequence: BeatSequence
) -> list[Sentence]:
    """Drop beat sentences that restate a claim already voiced by an earlier beat.

    Pure. Preserves order, never empties a beat, and only ever removes
    ``source_type == "beat"`` sentences.
    """
    beats_by_id = {b.id: b for plan in beat_sequence.poi_beats for b in plan.beats}
    claim_sigs_by_beat: dict[str, list[frozenset[str]]] = {
        bid: [sig for c in b.key_claims if (sig := _signature(c)) and len(sig) >= MIN_SHARED_TOKENS]
        for bid, b in beats_by_id.items()
    }

    voiced: list[tuple[str, frozenset[str]]] = []  # (beat_id, claim_sig) from kept sentences

    def _already_voiced(sig: frozenset[str], own_beat: str) -> bool:
        return any(
            bid != own_beat
            and _overlap(sig, vsig) >= CLAIM_DEDUP_THRESHOLD
            and len(sig & vsig) >= MIN_SHARED_TOKENS
            for bid, vsig in voiced
        )

    drop: set[int] = set()
    for i, s in enumerate(sentences):
        if s.source_type != "beat":
            continue
        claim_sigs = claim_sigs_by_beat.get(s.source_id)
        if not claim_sigs:
            continue
        realized = _realized_claim_signatures(s.text, claim_sigs)
        if not realized:
            continue
        novel = [sig for sig in realized if not _already_voiced(sig, s.source_id)]
        if not novel:
            # PURE restatement — every claim it realizes is already voiced elsewhere.
            drop.add(i)
        else:
            # A novel claim keeps the sentence; record it so later beats can dedup.
            voiced.extend((s.source_id, sig) for sig in novel)

    if not drop:
        return sentences

    # Never empty a beat: if every one of a beat's sentences was dropped, restore
    # its first dropped sentence so the emitted beat-id set (and goldens) hold.
    kept_by_beat: dict[str, int] = defaultdict(int)
    for i, s in enumerate(sentences):
        if s.source_type == "beat" and i not in drop:
            kept_by_beat[s.source_id] += 1
    for i, s in enumerate(sentences):
        if s.source_type == "beat" and kept_by_beat[s.source_id] == 0 and i in drop:
            drop.discard(i)
            kept_by_beat[s.source_id] = 1  # only the first dropped sentence is restored

    return [s for i, s in enumerate(sentences) if i not in drop]


__all__ = ["suppress_repeated_claims"]
