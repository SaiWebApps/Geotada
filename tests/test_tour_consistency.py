"""Cross-stop consistency + dedup (src/tour/tour_consistency.py) — REPORT ONLY. Reproduces
the two live Phase-C defects (specs/2026-07-18-tour-qa-campaign/PHASE-C-RESULTS.md) as
fixtures with FAKE decomposers/judges (offline, $0, mirrors the tests/test_author.py style):

- CONTRADICTION: NYC Broadway "thirteen miles" (stop 2, NMAI) vs "twelve miles" (stop 3,
  Bowling Green) — PHASE-C-RESULTS.md:92,102.
- REPEAT: Paris Ile "the Pont Neuf is the oldest bridge in Paris" voiced first in passing at
  Square du Vert-Galant (stop 4) and again as the Pont Neuf stop's own headline (stop 5) —
  PHASE-C-RESULTS.md:40,44.
"""

from __future__ import annotations

import json
import types

from src.tour.tour_consistency import (
    AuthoredStop,
    CrossStopReport,
    HaikuCrossStopJudge,
    cross_stop_report,
    find_cross_stop_contradictions,
    find_cross_stop_repeats,
    format_cross_stop_report,
)

# --- fakes (mirror tests/test_author.py's _SubstringEntailer / _RuleDecomposer style) ---


class _MapDecomposer:
    """Fake ClaimDecomposer: looks up pre-baked claims by the EXACT stop text it is handed
    (stands in for a real semantic decomposition pass, offline and deterministic)."""

    def __init__(self, claims_by_text: dict[str, tuple[str, ...]]) -> None:
        self._claims_by_text = claims_by_text
        self.calls = 0

    def decompose(self, narration: str) -> tuple[str, ...]:
        self.calls += 1
        return self._claims_by_text.get(narration, ())


class _ScriptedJudge:
    """Fake CrossStopJudge: a caller-supplied function decides the (kind, claim_a, claim_b,
    rationale) tuples for a stop pair. Records every call so tests can assert call COUNT
    (the O(stops^2), not O(claims^2), cost architecture) and call ARGUMENTS."""

    def __init__(self, fn) -> None:
        self._fn = fn
        self.calls: list[tuple[str, tuple[str, ...], str, tuple[str, ...]]] = []

    def compare(self, a_label, a_claims, b_label, b_claims):
        self.calls.append((a_label, a_claims, b_label, b_claims))
        return self._fn(a_label, a_claims, b_label, b_claims)


class _AlwaysCleanJudge:
    def compare(self, a_label, a_claims, b_label, b_claims):
        return ()


# --- real-data fixtures (verbatim excerpts, PHASE-C-RESULTS.md) ---

_NMAI_TEXT = (
    "Look down at your feet: this is the foot of Broadway, and the road you're standing on "
    "runs thirteen miles from here to the top of Manhattan. A Dutch fort once stood on this "
    "very ground. Now something grander rises above it."
)
_NMAI_CLAIMS = (
    "Broadway runs thirteen miles from the foot of Broadway to the top of Manhattan.",
    "A Dutch fort once stood on the site of the National Museum of the American Indian.",
)
_BOWLING_GREEN_TEXT = (
    "Stand here and face north, up Broadway, toward the bull. That avenue runs twelve miles, "
    "the longest in America, though for a long stretch it barely began — until the second "
    "quarter of the nineteenth century, the city went no farther than City Hall."
)
_BOWLING_GREEN_CLAIMS = (
    "Broadway runs twelve miles and is the longest avenue in America.",
    "Bowling Green Park was laid out in 1733 as the city's first official park.",
)


def _broadway_stops() -> tuple[AuthoredStop, AuthoredStop]:
    nmai = AuthoredStop(2, "National Museum of the American Indian", _NMAI_TEXT,
                         beat_ids=("frommers-nyc-2024-chunk-09-broadway",))
    bowling_green = AuthoredStop(3, "Bowling Green Park", _BOWLING_GREEN_TEXT,
                                  beat_ids=("big-onion-chunk-01-broadway",))
    return nmai, bowling_green


def _broadway_decomposer() -> _MapDecomposer:
    return _MapDecomposer({_NMAI_TEXT: _NMAI_CLAIMS, _BOWLING_GREEN_TEXT: _BOWLING_GREEN_CLAIMS})


def _broadway_judge() -> _ScriptedJudge:
    def fn(a_label, a_claims, b_label, b_claims):
        return (
            (
                "contradiction",
                "Broadway runs thirteen miles from the foot of Broadway to the top of Manhattan.",
                "Broadway runs twelve miles and is the longest avenue in America.",
                "both claims give Broadway's total length but disagree on the number of miles",
                "neither",  # ownership never applies to a contradiction
            ),
        )

    return _ScriptedJudge(fn)


_VERT_GALANT_TEXT = (
    "Such triumphs as the elegant Pont Neuf — the \"new bridge\" is the oldest bridge in "
    "Paris — the Place Dauphine opposite the bridge, and the Place Royale show his genius as "
    "architect and urban visionary."
)
_VERT_GALANT_CLAIMS = (
    "The Pont Neuf is the oldest bridge in Paris.",
    "Henri IV built the Place Dauphine.",
)
_PONT_NEUF_TEXT = (
    "Now look at the span beneath you. They call it Pont Neuf, the New Bridge, yet it's the "
    "oldest bridge in Paris—the first Paris bridge built of stone, and the first left free of "
    "houses."
)
_PONT_NEUF_CLAIMS = (
    "The Pont Neuf is the oldest bridge in Paris.",
    "The Pont Neuf is the first Paris bridge built of stone.",
)


def _bridge_stops() -> tuple[AuthoredStop, AuthoredStop]:
    vert_galant = AuthoredStop(4, "Square du Vert-Galant", _VERT_GALANT_TEXT)
    pont_neuf = AuthoredStop(5, "Pont Neuf", _PONT_NEUF_TEXT)
    return vert_galant, pont_neuf


def _bridge_decomposer() -> _MapDecomposer:
    return _MapDecomposer({
        _VERT_GALANT_TEXT: _VERT_GALANT_CLAIMS,
        _PONT_NEUF_TEXT: _PONT_NEUF_CLAIMS,
    })


def _bridge_judge() -> _ScriptedJudge:
    def fn(a_label, a_claims, b_label, b_claims):
        return (
            (
                "repeat",
                "The Pont Neuf is the oldest bridge in Paris.",
                "The Pont Neuf is the oldest bridge in Paris.",
                "both stops state the Pont Neuf is the oldest bridge in Paris",
                "B",  # the judge names the Pont Neuf stop (b) as the fact's true owner
            ),
        )

    return _ScriptedJudge(fn)


# --- tests ---


def test_broadway_twelve_vs_thirteen_miles_is_flagged_as_contradiction():
    """The real NYC defect: stop 2 says Broadway runs thirteen miles, stop 3 (100m away) says
    twelve — both faithfully grounded, corpus disagrees with itself.
    UNDO: make find_cross_stop_contradictions return () -> RED."""
    nmai, bowling_green = _broadway_stops()
    result = find_cross_stop_contradictions(
        (nmai, bowling_green), decomposer=_broadway_decomposer(), judge=_broadway_judge()
    )
    assert len(result) == 1
    issue = result[0]
    assert issue.kind == "contradiction"
    assert issue.stop_a == 2 and issue.stop_b == 3
    assert "thirteen miles" in issue.claim_a
    assert "twelve miles" in issue.claim_b


def test_oldest_bridge_repeat_across_stops_is_flagged():
    """The real Paris Ile defect: the Pont Neuf's 'oldest bridge in Paris' headline was
    already voiced in passing at the previous stop, so the reveal lands dead.
    UNDO: drop the 'repeat' kind from the judge dispatch -> RED."""
    vert_galant, pont_neuf = _bridge_stops()
    result = find_cross_stop_repeats(
        (vert_galant, pont_neuf), decomposer=_bridge_decomposer(), judge=_bridge_judge()
    )
    assert len(result) == 1
    issue = result[0]
    assert issue.kind == "repeat"
    assert issue.stop_a == 4 and issue.stop_b == 5
    assert issue.claim_a == "The Pont Neuf is the oldest bridge in Paris."
    assert issue.claim_b == "The Pont Neuf is the oldest bridge in Paris."


def test_repeat_keep_recommends_the_owning_poi_stop_not_the_first():
    """Locks failure mode 4: keep must be the Pont Neuf stop (the reveal), NOT the first
    occurrence (the Vert-Galant passing mention) — the claim_dedup.py keep-first precedent is
    WRONG here. UNDO: switch _owning_stop_idx to keep-first (always return a_stop_idx) ->
    RED (keep would become 4, not 5)."""
    vert_galant, pont_neuf = _bridge_stops()
    result = find_cross_stop_repeats(
        (vert_galant, pont_neuf), decomposer=_bridge_decomposer(), judge=_bridge_judge()
    )
    assert result[0].keep == pont_neuf.stop_idx  # 5, not 4


def test_contradiction_reports_no_auto_keep_and_names_both_source_beats():
    """Locks failure mode 5 and CLAUDE.md Pipeline Guardrail #4 (never auto-resolve a
    superlative/factual disagreement): a contradiction NEVER picks a winner, and both source
    beat ids are named in the rationale so the fix is an actionable corpus repair.
    UNDO: have the contradiction path pick a winner (set keep=stop_a) -> RED."""
    nmai, bowling_green = _broadway_stops()
    result = find_cross_stop_contradictions(
        (nmai, bowling_green), decomposer=_broadway_decomposer(), judge=_broadway_judge()
    )
    issue = result[0]
    assert issue.keep is None
    assert issue.beats_a == ("frommers-nyc-2024-chunk-09-broadway",)
    assert issue.beats_b == ("big-onion-chunk-01-broadway",)
    assert "frommers-nyc-2024-chunk-09-broadway" in issue.rationale
    assert "big-onion-chunk-01-broadway" in issue.rationale
    assert "corpus repair" in issue.rationale.lower()


def test_distinct_facts_about_the_same_subject_are_not_flagged():
    """No-over-firing guard: 'the oldest bridge in Paris' and 'the first Paris bridge built
    of stone' are both true, both about the Pont Neuf, but are DIFFERENT facts — neither a
    repeat nor a contradiction. Only the genuine oldest-bridge repeat is reported."""
    vert_galant, pont_neuf = _bridge_stops()
    result = find_cross_stop_repeats(
        (vert_galant, pont_neuf), decomposer=_bridge_decomposer(), judge=_bridge_judge()
    )
    claims_seen = {(i.claim_a, i.claim_b) for i in result}
    oldest_bridge = "The Pont Neuf is the oldest bridge in Paris."
    assert (oldest_bridge, oldest_bridge) in claims_seen
    assert not any(
        "first Paris bridge built of stone" in i.claim_a
        or "first Paris bridge built of stone" in i.claim_b
        for i in result
    )


def test_deliberate_callback_is_not_flagged_as_contradiction():
    """A deliberate threading callback ('as you saw at Notre-Dame') restates a fact on
    purpose — at most a repeat, NEVER a contradiction. Keeps the two relations from bleeding
    into each other."""
    notre_dame_text = "Here the two imperial-purple rose windows pour that brightness in."
    sainte_chapelle_text = (
        "When the sun finds them, it throws blue and red across everything — the same "
        "imperial-purple glow you saw at Notre-Dame."
    )
    notre_dame_claim = "The rose windows at Notre-Dame are imperial purple."
    sainte_chapelle_claim = "The glass at Notre-Dame glows imperial purple, as seen earlier."
    stops = (
        AuthoredStop(0, "Notre-Dame Cathedral", notre_dame_text),
        AuthoredStop(1, "Sainte-Chapelle", sainte_chapelle_text),
    )
    decomposer = _MapDecomposer({
        notre_dame_text: (notre_dame_claim,),
        sainte_chapelle_text: (sainte_chapelle_claim,),
    })

    def fn(a_label, a_claims, b_label, b_claims):
        return (
            ("repeat", notre_dame_claim, sainte_chapelle_claim, "deliberate callback", "A"),
        )

    judge = _ScriptedJudge(fn)
    contradictions = find_cross_stop_contradictions(stops, decomposer=decomposer, judge=judge)
    repeats = find_cross_stop_repeats(stops, decomposer=decomposer, judge=judge)
    assert contradictions == ()
    assert len(repeats) == 1 and repeats[0].kind == "repeat"


def test_clean_tour_reports_zero_issues():
    """The near-APPROVE Place des Vosges tour (PHASE-C-RESULTS.md:49-75) — four distinct,
    non-overlapping stops — must come back clean."""
    texts = {
        0: ("Place des Vosges", "Find a bench near the children's play area, and watch them "
            "play à la française, the air braided with Hebrew, Yiddish, and Arabic — yet this "
            "was, for nearly two centuries, the single most fashionable square in Paris."),
        1: ("Musee Carnavalet", "For the last twenty years of her life, Madame de Sévigné "
            "lived inside these walls, the Hôtel Carnavalet, and she filled letter after "
            "letter from this very ground."),
        2: ("Rue de Rivoli", "In 1720 a riding school — a manège — rose here for young Louis "
            "XV, on what was then the edge of the Tuileries Gardens, before rue de Rivoli "
            "existed at all."),
        3: ("Rue des Rosiers", "This is the backbone of the pletzel, Yiddish for \"little "
            "square,\" the historic Jewish quarter of the Marais, its heart at the corner "
            "with Rue des Ecouffes."),
    }
    stops = tuple(AuthoredStop(i, poi, text) for i, (poi, text) in texts.items())
    claims_by_text = {text: (f"claim about {poi}",) for poi, text in texts.values()}
    report = cross_stop_report(
        stops, decomposer=_MapDecomposer(claims_by_text), judge=_AlwaysCleanJudge()
    )
    assert isinstance(report, CrossStopReport)
    assert report.clean() is True
    assert report.issue_count() == 0
    assert report.skipped is False


def test_judge_returned_claim_absent_from_inputs_is_discarded():
    """Hallucinated-pair guard: the fake judge returns a paraphrase present in NEITHER input
    claim list; it must be discarded, not reported. UNDO: remove the verbatim-membership
    filter in cross_stop_report -> the paraphrased issue leaks through -> RED."""
    text_a, text_b = "Stop A narration.", "Stop B narration."
    claims_a = ("The tower was built in 1250.",)
    claims_b = ("The tower was built in 1250, according to another source.",)
    decomposer = _MapDecomposer({text_a: claims_a, text_b: claims_b})

    def fn(a_label, a_claims, b_label, b_claims):
        return (
            (
                "repeat",
                "The tower was constructed around the year 1250.",  # paraphrase, not verbatim
                "The tower was built in 1250, according to another source.",
                "same fact, different wording",
                "A",  # irrelevant: this issue is discarded before owner is ever consulted
            ),
        )

    judge = _ScriptedJudge(fn)
    stops = (AuthoredStop(0, "Tower A", text_a), AuthoredStop(1, "Tower B", text_b))
    result = find_cross_stop_repeats(stops, decomposer=decomposer, judge=judge)
    assert result == ()


def test_judge_calls_are_quadratic_in_stops_not_in_claims():
    """4 stops x 6 claims each must produce exactly C(4,2)=6 compare calls (counting the
    fake), not ~200 — the cost-architecture guard that stops the money bug from ever
    landing. UNDO: revert to per-claim-pair judging -> RED (far more than 6 calls, or calls
    keyed by claim rather than by stop)."""
    texts = {i: f"Stop {i} unique narration filler text." for i in range(4)}
    claims_by_text = {
        text: tuple(f"stop{i} claim{j}" for j in range(6)) for i, text in texts.items()
    }
    stops = tuple(AuthoredStop(i, f"POI{i}", text) for i, text in texts.items())
    judge = _ScriptedJudge(lambda *a: ())
    decomposer = _MapDecomposer(claims_by_text)
    cross_stop_report(stops, decomposer=decomposer, judge=judge)
    assert len(judge.calls) == 6  # C(4,2), not 4*6*6=144 claim-pair calls
    assert decomposer.calls == 4  # decomposed once per stop, not once per relation


def test_report_never_mutates_stop_text():
    """The anti-hallucination invariant made mechanical: cross_stop_report must never alter
    the served narration it is reporting on."""
    stops = [
        AuthoredStop(0, "POI0", "Original text zero."),
        AuthoredStop(1, "POI1", "Original text one."),
        AuthoredStop(2, "POI2", "Original text two."),
    ]
    original_texts = [s.text for s in stops]
    decomposer = _MapDecomposer({s.text: (f"claim about {s.poi}",) for s in stops})
    cross_stop_report(stops, decomposer=decomposer, judge=_AlwaysCleanJudge())
    assert [s.text for s in stops] == original_texts


def test_single_stop_tour_is_skipped_not_reported_clean():
    """Locks failure mode 13: scripts/author_tour.py --stop authors <2 stops, and printing
    'CROSS-STOP ISSUES: none' there would be a false all-clear."""
    stops = (AuthoredStop(0, "Only POI", "The only stop's narration."),)
    report = cross_stop_report(
        stops, decomposer=_MapDecomposer({}), judge=_AlwaysCleanJudge()
    )
    assert report.skipped is True
    assert report.clean() is False  # skipped is NOT the same as verified-clean
    assert report.repeats == () and report.contradictions == ()
    assert "skipped" in format_cross_stop_report(report).lower()


def test_money_guard_cross_stop_judge_is_offline_stub_in_suite():
    """MONEY-GUARD (mirrors tests/test_author.py:55): HaikuCrossStopJudge is a SEPARATE
    billing client living in a module invisible to the author-engine money-guard arm — it
    needs its own conftest patch, else `make test` could construct the real anthropic client.
    UNDO: delete the new conftest arm -> the real anthropic client is built -> RED (and
    `make test` would bill)."""
    from src.tour.tour_consistency import HaikuCrossStopJudge as _Judge

    assert type(_Judge()).__name__ == "_OfflineCrossStopJudge"


def test_stitch_sourced_issues_are_marked_unfixable():
    """Locks failure mode 7: an issue touching a grounded-stitch stop (corpus-verbatim,
    cannot be rewritten at the narration layer) is tagged so reviewers can triage it as a
    corpus/engine fix rather than drowning in unactionable narration noise."""
    stitch_text = "Grounded stitch narration, corpus-verbatim."
    authored_text = "Authored prose about the same fact."
    stitch_claim = "The tower was built in 1685."
    authored_claim = "The tower was built in 1685."
    stops = (
        AuthoredStop(0, "Stitch POI", stitch_text, grounded_fallback=True),
        AuthoredStop(1, "Authored POI", authored_text, grounded_fallback=False),
    )
    decomposer = _MapDecomposer({stitch_text: (stitch_claim,), authored_text: (authored_claim,)})

    def fn(a_label, a_claims, b_label, b_claims):
        return (("repeat", stitch_claim, authored_claim, "same fact", "A"),)

    result = find_cross_stop_repeats(stops, decomposer=decomposer, judge=_ScriptedJudge(fn))
    assert len(result) == 1
    rationale = result[0].rationale.upper()
    assert "GROUNDED-STITCH" in rationale
    assert "STOP 0" in rationale


# --- killer-defect regression: ownership must be the judge's OWN verdict, never a POI-name
# substring/lexical match (the banned shortcut a hostile verifier found in _owning_stop_idx).
# Both cases below reproduce scenarios the verifier ran directly against the substring
# implementation and got the WRONG answer from (see must-fix list item 1 / ATTACK 4 evidence).


def test_owner_from_judge_decides_keep_when_poi_name_form_differs_from_the_claim():
    """The POI is stored as 'Notre-Dame Cathedral'; the claim (as a real decomposed narration
    claim would) names it just 'Notre-Dame' — the exact name-form gap the substring heuristic
    silently mishandled (it required the FULL stored POI name to appear verbatim in the claim
    text). The owner must come from the judge's own verdict, not a string match.
    UNDO: make the keep decision re-derive ownership via `a.poi.lower() in combined` /
    `b.poi.lower() in combined` (the old heuristic) instead of trusting `owner` -> RED (neither
    POI's full stored name is a substring of the claim, so it falls through to keep-first,
    stop 0 the passing Sainte-Chapelle mention, not stop 1 Notre-Dame Cathedral itself)."""
    sainte_chapelle_text = (
        "The glass throws that same deep color you already noticed at Notre-Dame."
    )
    notre_dame_text = "The rose windows here glow with that same famous deep color."
    claim = "Notre-Dame's rose windows are famed for their deep color."
    stops = (
        AuthoredStop(0, "Sainte-Chapelle", sainte_chapelle_text),
        AuthoredStop(1, "Notre-Dame Cathedral", notre_dame_text),  # POI name != claim's naming
    )
    decomposer = _MapDecomposer({sainte_chapelle_text: (claim,), notre_dame_text: (claim,)})

    def fn(a_label, a_claims, b_label, b_claims):
        # The judge names Notre-Dame Cathedral (stop B) as the fact's true subject, regardless
        # of the claim text using the shorter 'Notre-Dame' form.
        return (("repeat", claim, claim, "same fact, restated across stops", "B"),)

    result = find_cross_stop_repeats(stops, decomposer=decomposer, judge=_ScriptedJudge(fn))
    assert len(result) == 1
    assert result[0].keep == 1  # Notre-Dame Cathedral (stop B) — the judge's owner verdict


def test_owner_from_judge_decides_keep_across_nfc_nfd_accented_name_forms():
    """Unicode variant of the same defect: the POI's stored name and the claim's naming of it
    can be different Unicode normalization forms of the SAME accented name (NFC precomposed
    'é' vs NFD 'e' + combining accent) — this corpus is overwhelmingly accented French, and
    plain `.lower()` does not normalize across forms, so the substring heuristic silently
    mismatched here too.
    UNDO: same as above (re-derive ownership from a POI-name substring match) -> RED, because
    the NFD-stored POI name is never a substring of the NFC claim text."""
    import unicodedata

    nfc_name = unicodedata.normalize("NFC", "Musée Carnavalet")  # single precomposed 'é'
    nfd_name = unicodedata.normalize("NFD", "Musée Carnavalet")  # 'e' + combining acute accent
    assert nfc_name != nfd_name  # sanity: genuinely different code points, same rendered text

    vosges_text = "Locals still just call it 'the museum on the corner' out of habit."
    carnavalet_text = "This building has told Paris's own story since it became a museum."
    claim = f"{nfc_name} occupies the Hôtel Carnavalet."
    stops = (
        AuthoredStop(0, "Place des Vosges", vosges_text),
        AuthoredStop(1, nfd_name, carnavalet_text),  # POI's stored name is NFD-normalized
    )
    decomposer = _MapDecomposer({vosges_text: (claim,), carnavalet_text: (claim,)})

    def fn(a_label, a_claims, b_label, b_claims):
        return (("repeat", claim, claim, "same fact, restated across stops", "B"),)

    result = find_cross_stop_repeats(stops, decomposer=decomposer, judge=_ScriptedJudge(fn))
    assert len(result) == 1
    assert result[0].keep == 1  # the museum stop (B) — the judge's owner verdict, not stop 0


def test_failed_judge_pair_is_not_reported_clean():
    """Locks failure mode 4 (fail-open masquerading as verified-clean): a pair the judge could
    not parse (``compare`` returns ``None``, e.g. empty/malformed live response) must be
    counted in ``failed_pairs`` and make ``clean()`` False — the SAME false-all-clear risk
    ``CrossStopReport.skipped`` already guards against for the whole-report case, just
    per-pair. UNDO: treat a ``None`` compare() result the same as an empty tuple in
    ``cross_stop_report`` -> RED (clean() wrongly becomes True, 'none' is wrongly printed)."""
    stops = (
        AuthoredStop(0, "POI0", "Some narration zero."),
        AuthoredStop(1, "POI1", "Some narration one."),
    )
    decomposer = _MapDecomposer({
        "Some narration zero.": ("claim zero",),
        "Some narration one.": ("claim one",),
    })

    class _FailingJudge:
        def compare(self, a_label, a_claims, b_label, b_claims):
            return None  # simulates an empty/malformed live judge response

    report = cross_stop_report(stops, decomposer=decomposer, judge=_FailingJudge())
    assert report.failed_pairs == 1
    assert report.clean() is False
    assert report.repeats == () and report.contradictions == ()
    rendered = format_cross_stop_report(report)
    assert "none" not in rendered.lower().split("cross-stop issues")[-1].strip().split("\n")[0]
    assert "could not be judged" in rendered.lower()
    assert "1" in rendered


# --- real HaikuCrossStopJudge coverage (not just fakes) — the conftest money-guard explicitly
# allows constructing it with an injected fake SDK client and keeps the suite offline (see
# test_money_guard_cross_stop_judge_is_offline_stub_in_suite above). Mirrors the precedent at
# tests/test_factcheck.py:189-205 (_fake_haiku + HaikuFaithfulnessJudge(client=...)).


def _fake_cross_stop_client(reply_text: str):
    """Stand-in anthropic client (mirrors tests/test_factcheck.py's ``_fake_haiku``): records
    the request kwargs and returns ``reply_text`` as the model's raw response text — exercises
    HaikuCrossStopJudge's prompt formatting + response parsing offline (no SDK, no network, no
    spend)."""
    box: dict = {}

    def create(**kw):
        box["kw"] = kw
        return types.SimpleNamespace(content=[types.SimpleNamespace(text=reply_text)])

    return types.SimpleNamespace(messages=types.SimpleNamespace(create=create)), box


def test_haiku_cross_stop_judge_parses_a_well_formed_issues_payload():
    """The real judge class end to end: request formatting (both POI labels + claim lists in
    the prompt) and response parsing (kind/claim_a/claim_b/rationale/owner) — offline via a
    fake SDK client, exercising code that otherwise only runs on the paid live path."""
    payload = json.dumps({
        "issues": [
            {
                "kind": "repeat",
                "claim_a": "The tower was built in 1889.",
                "claim_b": "The tower was built in 1889.",
                "rationale": "same fact, restated",
                "owner": "B",
            }
        ]
    })
    client, box = _fake_cross_stop_client(payload)
    judge = HaikuCrossStopJudge(client=client)
    result = judge.compare(
        "Stop A POI", ("The tower was built in 1889.",),
        "Stop B POI", ("The tower was built in 1889.",),
    )
    assert result == (
        ("repeat", "The tower was built in 1889.", "The tower was built in 1889.",
         "same fact, restated", "B"),
    )
    assert judge.calls == 1
    sent = box["kw"]["messages"][0]["content"]
    assert "Stop A POI" in sent and "Stop B POI" in sent
    assert "The tower was built in 1889." in sent


def test_haiku_cross_stop_judge_empty_content_signals_failure_not_clean():
    """Empty model output -> None (a judge FAILURE signal), never an empty tuple (which the
    caller would read as verified-clean) — the real-judge-class half of failure mode 4."""
    client, _ = _fake_cross_stop_client("")
    judge = HaikuCrossStopJudge(client=client)
    result = judge.compare("A", ("claim a",), "B", ("claim b",))
    assert result is None
    assert judge.calls == 1


def test_haiku_cross_stop_judge_malformed_json_signals_failure_not_clean():
    """Truncated/invalid JSON -> None, same failure signal as empty content."""
    client, _ = _fake_cross_stop_client("{not valid json at all")
    judge = HaikuCrossStopJudge(client=client)
    result = judge.compare("A", ("claim a",), "B", ("claim b",))
    assert result is None


def test_haiku_cross_stop_judge_discards_issue_with_non_string_claim_a():
    """A well-formed JSON response whose claim_a is not a string (a malformed live reply,
    e.g. the model emitted a number) is dropped, not raised or passed through raw."""
    payload = json.dumps({
        "issues": [
            {"kind": "repeat", "claim_a": 123, "claim_b": "claim b", "rationale": "x",
             "owner": "A"}
        ]
    })
    client, _ = _fake_cross_stop_client(payload)
    judge = HaikuCrossStopJudge(client=client)
    result = judge.compare("A", ("claim a",), "B", ("claim b",))
    assert result == ()


def test_haiku_cross_stop_judge_discards_issue_with_unknown_kind():
    """A 'kind' outside {'repeat', 'contradiction'} (a malformed live reply) is dropped."""
    payload = json.dumps({
        "issues": [
            {"kind": "sidebar", "claim_a": "claim a", "claim_b": "claim b", "rationale": "x",
             "owner": "A"}
        ]
    })
    client, _ = _fake_cross_stop_client(payload)
    judge = HaikuCrossStopJudge(client=client)
    result = judge.compare("A", ("claim a",), "B", ("claim b",))
    assert result == ()
