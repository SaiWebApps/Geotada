"""Unit tests for TTS pronunciation normalization (backlog #23).

The normalizer runs ONLY on TTS-consumed text (inside the real providers'
``generate``), never on the stored corpus. It rewrites tokens a neural TTS voices
as letters/symbols into the plain English a listener expects to hear:

- regnal / papal Roman numerals: ``Louis XIV`` -> ``Louis the fourteenth``
- initials joined by a hyphen: ``J.-B.`` -> ``J. B.``

Correctness matters less than RESTRAINT: the corpus is a Paris-history text full
of ``World War II``, the pronoun ``I``, ``Chapter IV`` and ``Vatican II`` — none
of which may be touched. A curated regnal-name allow-list gates every rewrite.
"""

from __future__ import annotations

import pytest

from src.audio.tts_normalize import normalize_for_tts


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # ── regnal / papal numerals -> ordinal words ──
        ("Louis XIV was the Sun King.", "Louis the fourteenth was the Sun King."),
        ("Napoleon III rebuilt Paris.", "Napoleon the third rebuilt Paris."),
        ("Henri IV signed the edict.", "Henri the fourth signed the edict."),
        ("Charles V ruled an empire.", "Charles the fifth ruled an empire."),
        ("Louis VI the Fat.", "Louis the sixth the Fat."),
        ("Pope John XXIII opened the council.", "Pope John the twenty-third opened the council."),
        ("Napoléon Ier — accented stem.", "Napoléon Ier — accented stem."),  # 'Ier' is not roman
        # possessive + sentence-final punctuation must survive
        ("Louis XVI's head fell.", "Louis the sixteenth's head fell."),
        ("It ended under Louis XIV.", "It ended under Louis the fourteenth."),
        ("Louis I founded the line.", "Louis the first founded the line."),
        # hyphenated regnal stem
        ("Saint-Louis IX was canonized.", "Saint-Louis the ninth was canonized."),
        # ── initials joined by a hyphen (incl. chains) ──
        ("The architect J.-B. Colbert.", "The architect J. B. Colbert."),
        ("Read W.-E.-B. Du Bois.", "Read W. E. B. Du Bois."),
        # ── newly covered pope / emperor stems (skeptic-C corpus misses) ──
        ("Pope Boniface VIII issued the bull.", "Pope Boniface the eighth issued the bull."),
        ("Baldwin II sold the relics.", "Baldwin the second sold the relics."),
        # ── FALSE-POSITIVE GUARDS (must be left byte-identical) ──
        ("The Second World War II era.", "The Second World War II era."),  # 'War' not regnal
        ("Everyone whom I met agreed.", "Everyone whom I met agreed."),  # pronoun I
        ("Vatican II reformed the mass.", "Vatican II reformed the mass."),  # council, not regnal
        ("See Chapter IV for details.", "See Chapter IV for details."),  # 'Chapter' not regnal
        ("Room XIV is upstairs.", "Room XIV is upstairs."),  # 'Room' not regnal
        ("A plain sentence with no numerals.", "A plain sentence with no numerals."),
        ("", ""),
    ],
)
def test_normalize_cases(raw: str, expected: str) -> None:
    assert normalize_for_tts(raw) == expected


def test_idempotent() -> None:
    once = normalize_for_tts("Louis XIV met Napoleon III near J.-B. Colbert's atelier.")
    assert normalize_for_tts(once) == once


def test_chained_initials_idempotent() -> None:
    # Skeptic-A finding: a chain must fully resolve AND be idempotent.
    once = normalize_for_tts("A.-B.-C. Smith wrote it.")
    assert once == "A. B. C. Smith wrote it."
    assert normalize_for_tts(once) == once


def test_malformed_roman_left_alone() -> None:
    # 'IIII' / 'VX' are not canonical Roman numerals -> never rewritten.
    assert normalize_for_tts("Louis IIII imagined.") == "Louis IIII imagined."
    assert normalize_for_tts("Charles VX imagined.") == "Charles VX imagined."


def test_high_regnal_number() -> None:
    assert normalize_for_tts("Ramses II built it.") == "Ramses the second built it."
    assert normalize_for_tts("Pius XII reigned.") == "Pius the twelfth reigned."
