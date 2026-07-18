"""$0 offline regression suite for the RESIDUAL-DUPLICATE bug: the compose de-dup
passes ran ONLY inside ``_assemble`` (the composed stream), i.e. BEFORE the gate's
repair steps, and the repaired script was served WITHOUT re-running them. So when
the SURGICAL repair spliced a beat's grounded STITCH back in
(``repair_composed_surgical``), a duplicate the raw stitch carries — one the
composed path would have removed — shipped past a PASSING gate to the tourist.

This mirrors the class observed in the real delivered tour
``data/paris/tours/opus-ile-de-la-cite-60min.md`` (the "September Massacres"
retelling voiced twice near-verbatim in one stop), though that artifact is
label-free so the exact mechanism there is not provable.

The fix (proven RED-first here): de-dup each REPAIR CANDIDATE via a FAIL-OPEN pass
(``_prefer_deduped``) and de-dup ``compose_script``'s composed stream — both
DOWNSTREAM of the coverage baseline, so a drop that would lose a fact fails verify
and is undone. The stitch root is deliberately NOT de-duped (see generation.py):
the same-beat near-verbatim pass is token-similarity only and could silently drop a
superset sentence there, before any coverage check exists.

Tests here are coupled to specific changes by isolated mutation: reverting the
surgical ``_prefer_deduped`` reddens the repair/fail-open/recompute tests; reverting
``compose_script``'s de-dup reddens the persisted-path test; stubbing
``_recompute_fully`` reddens the diagnostic-label test.

Runs the REAL ``compose_script_per_chapter`` with deterministic stubs — no LLM,
no Neo4j, $0.
"""

from __future__ import annotations

from src.tour.claim_dedup import (
    suppress_repeated_claims,
    suppress_same_beat_near_duplicates,
)
from src.tour.compose import compose_script, compose_script_per_chapter
from src.tour.contract import (
    POI,
    BeatRef,
    BeatSequence,
    POIBeats,
    Route,
    TourInput,
    TransitSegment,
)
from src.tour.generation import generate

# beat bD voices ONE fact as two near-verbatim sentences (rapidfuzz token_set_ratio
# ~97, well above the pass's 90 threshold), so the stitch carries a same-beat pair.
_DUP_A = "Marie Gredeler was the only woman executed at this prison"
_DUP_B = "Marie Gredeler was the only woman executed at this very prison"
_STOP0_CLAIM = "Henri IV completed the Place des Vosges in 1612"
_SOLO_CLAIM = "Napoleon crowned himself emperor of the French in 1804"


def _poi(pid):
    return POI(id=pid, name=pid, tier=5, poi_role="stop", lat=48.85, lng=2.36)


def _beat(bid, poi_id, claim, script_body=None):
    body = script_body if script_body is not None else claim
    return BeatRef(
        id=bid,
        poi_id=poi_id,
        script_body=body,
        word_count=len(body.split()),
        key_claims=(claim,),
    )


def _route(walks):
    pois = tuple(_poi(f"p{i}") for i in range(len(walks)))
    transits = tuple(
        TransitSegment(
            from_poi_id=None if i == 0 else pois[i - 1].id,
            to_poi_id=p.id,
            distance_m=100.0,
            walk_seconds=walks[i],
        )
        for i, p in enumerate(pois)
    )
    return Route(
        pois=pois,
        transits=transits,
        total_walk_distance_m=100.0 * len(pois),
        total_walk_seconds=sum(walks),
    )


def _seq(stops):
    return BeatSequence(
        poi_beats=tuple(
            POIBeats(
                poi_id=f"p{i}",
                poi_name=f"p{i}",
                ordering_strategy="sub_location",
                beats=tuple(beats),
            )
            for i, beats in enumerate(stops)
        )
    )


class _StrictHaikuLikeChecker:
    """Entails ONLY when a claim appears near-verbatim (substring) in the
    sentence — the realistic over-rejection of a bold fusion, as in the live
    Haiku gate. Forces the failing fusion → drop → surgical-restore path."""

    def entails(self, key_claims, sentence_text):
        return any(c in sentence_text for c in key_claims)


class _DupBeatClient:
    """Stop 0: light reword (claim kept as a substring → entails, composed).
    Interior stop 1: reword the SOLO beat keeping its claim (→ entails, survives),
    and collapse beat bD's two near-verbatim stitch sentences into ONE bold fusion
    that quotes no claim verbatim (→ the strict checker rejects it → dropped →
    bD's claim uncovered → the surgical repair splices bD's grounded stitch —
    BOTH near-verbatim sentences — back in)."""

    def compose(self, request, attempt, prev_report):
        stop = next(iter({s.stop_idx for s in request.stitched.script}))
        beat_sents = [s for s in request.stitched.script if s.source_type == "beat"]
        out = [s for s in request.stitched.script if s.source_type != "beat"]
        if stop == 0:
            out += [s.model_copy(update={"text": f"And here: {s.text}"}) for s in beat_sents]
            return tuple(out)
        seen_dup = False
        for s in beat_sents:
            if s.source_id == "bD":
                if seen_dup:
                    continue  # collapse bD's two stitch sentences into a single fusion
                seen_dup = True
                out.append(
                    s.model_copy(update={"text": "A single fresh unified telling at this stop."})
                )
            else:
                out.append(s.model_copy(update={"text": f"Notably, {s.text}."}))
        return tuple(out)


def _setup():
    stops = [
        [_beat("b0", "p0", _STOP0_CLAIM)],
        [
            _beat("bZ", "p1", _SOLO_CLAIM),
            _beat("bD", "p1", _DUP_A, script_body=f"{_DUP_A}. {_DUP_B}."),
        ],
    ]
    seq = _seq(stops)
    route = _route([10, 400])
    stitched = generate(
        seq, route, TourInput(start=(48.85, 2.36), duration_min=90, city_slug="paris")
    )
    assert stitched.validation.passed
    return seq, route, stitched


def test_stitch_intentionally_keeps_same_beat_near_dup():
    """Design guard (see generation.py): the stitch does NOT run the same-beat
    near-verbatim pass at the root. That pass is token-similarity only and
    rapidfuzz.token_set_ratio scores a SUPERSET sentence >= 90 against its subset, so
    running it before the coverage baseline exists could silently drop a sentence
    that adds a distinct fact. So the raw stitch KEEPS a beat's two near-verbatim
    tellings; the coverage-checked repair de-dup removes it downstream (next test)."""
    _, _, stitched = _setup()
    bd = [s.text for s in stitched.script if s.source_id == "bD"]
    assert len(bd) == 2, bd


def test_repair_path_ships_no_residual_same_beat_duplicate():
    """THE regression guard for the fix. The stitch feeds bD's two near-verbatim
    tellings into the surgical splice UN-de-duped; the fail-open candidate de-dup
    (_prefer_deduped) must collapse the redundant telling before serving while
    keeping the fact covered. Assert the SERVED script is de-dup-clean. Undo the
    surgical _prefer_deduped call in compose.py and this goes RED."""
    seq, route, stitched = _setup()
    served = compose_script_per_chapter(
        stitched,
        seq,
        route,
        client=_DupBeatClient(),
        faithfulness_checker=_StrictHaikuLikeChecker(),
        candidates=1,
    )
    # The surgical repair produced a verified served script...
    assert served.validation.passed
    status = {r.stop_idx: r.status for r in served.verify_report}
    assert status.get(1) in {"partially_reverted", "reverted_to_stitched"}, status

    # ...but it must not carry a duplicate the compose de-dup would have removed.
    deduped = suppress_same_beat_near_duplicates(list(served.script))
    residual = [s.text for s in served.script if s not in deduped]
    assert len(deduped) == len(served.script), (
        f"repair path shipped {len(served.script) - len(deduped)} residual same-beat "
        f"near-duplicate(s) past the gate: {residual}"
    )


# ---- Step 2: the persisted /trips/{id}/compose path (compose_script) ----


class _EchoClient:
    """Composes a beat as TWO near-verbatim sentences (same source_id) — the
    composer-introduced same-beat echo that ``compose_script`` must collapse before
    serving. Stop 0 lightly reworded (entails); the echo also entails (claim kept
    as a substring), so WITHOUT the de-dup the gate passes and both echoes ship."""

    def compose(self, request, attempt, prev_report):
        out = [s for s in request.stitched.script if s.source_type != "beat"]
        for s in request.stitched.script:
            if s.source_type != "beat":
                continue
            out.append(s.model_copy(update={"text": f"{s.text}."}))
            out.append(s.model_copy(update={"text": f"{s.text}, to put it plainly."}))
        return tuple(out)


def _simple_setup():
    stops = [[_beat("b0", "p0", _STOP0_CLAIM)], [_beat("bE", "p1", _SOLO_CLAIM)]]
    seq = _seq(stops)
    route = _route([10, 400])
    stitched = generate(
        seq, route, TourInput(start=(48.85, 2.36), duration_min=90, city_slug="paris")
    )
    assert stitched.validation.passed
    return seq, route, stitched


def test_compose_script_persisted_path_de_dups_composed_echo():
    """The persisted /compose path (compose_script, repair=False) must not ship a
    composer echo. RED before Step 2 (compose_script ran zero de-dup on any path);
    GREEN after de-dup is applied to its composed stream before verify."""
    seq, route, stitched = _simple_setup()
    served = compose_script(
        stitched,
        seq,
        route,
        client=_EchoClient(),
        faithfulness_checker=_StrictHaikuLikeChecker(),
    )
    assert served.validation.passed
    be = [s.text for s in served.script if s.source_id == "bE"]
    assert len(be) == 1, be  # the echo was collapsed, not shipped twice
    deduped = suppress_same_beat_near_duplicates(list(served.script))
    assert len(deduped) == len(served.script), [s.text for s in served.script]


# ---- Step 3: fail-open de-dup of a SAME-BEAT CLAIM repeat left by a splice ----
#
# The class Step 1 (stitch same-beat NEAR-verbatim pass) does NOT catch: one beat
# voicing ONE claim in two DIFFERENTLY-worded sentences (token_set_ratio < 90, so
# the near-dup pass misses) that both realize the same key_claim. The stitch keeps
# both (its claim pass is cross-beat only; near-dup misses; not byte-identical), so
# a splice serves the repeat raw. Only the fail-open candidate de-dup — which runs
# suppress_repeated_claims(include_same_beat=True) on the repair candidate — removes
# it.
_CLAIM_Y = "over thirteen hundred prisoners were killed in the September Massacres"
_Y_SENT1 = "In the September Massacres more than thirteen hundred prisoners were killed."
_Y_SENT2 = "The killing during those September days took over thirteen hundred prisoners' lives."
_FACT_X = "Marie Gredeler was the only woman among this prison's victims"


class _SameBeatClaimRepeatClient:
    """Stop 0 reworded (entails). Stop 1: rewords beat bX keeping its claim (→
    survives), and collapses beat bY into ONE bold fusion quoting no claim (→
    rejected → dropped → bY uncovered → the surgical repair splices bY's stitch
    back: BOTH sentences, which restate bY's SAME claim in different words). Only
    the fail-open candidate de-dup collapses that same-beat claim repeat."""

    def compose(self, request, attempt, prev_report):
        stop = next(iter({s.stop_idx for s in request.stitched.script}))
        beat_sents = [s for s in request.stitched.script if s.source_type == "beat"]
        out = [s for s in request.stitched.script if s.source_type != "beat"]
        if stop == 0:
            out += [s.model_copy(update={"text": f"And here: {s.text}"}) for s in beat_sents]
            return tuple(out)
        seen_y = False
        for s in beat_sents:
            if s.source_id == "bY":
                if seen_y:
                    continue  # collapse bY's two stitch sentences into one fusion
                seen_y = True
                out.append(s.model_copy(update={"text": "A bold fused telling at this stop."}))
            else:
                out.append(s.model_copy(update={"text": f"Notably, {s.text}."}))
        return tuple(out)


def test_fail_open_dedup_removes_same_beat_claim_repeat_from_splice():
    """Step 3, end to end through the real gate. Precondition: bY's two stitch
    sentences restate one claim but are NOT near-verbatim (so Step 1 leaves them),
    and both survive stitching. The bold fusion is dropped, bY is spliced back with
    both, and the fail-open candidate de-dup collapses the repeat while keeping bY's
    claim covered and bX's composed line. RED before Step 3; GREEN after; the
    partially_reverted / restored_beats diagnostic stays accurate."""
    from rapidfuzz import fuzz

    assert fuzz.token_set_ratio(_Y_SENT1, _Y_SENT2) < 90  # Step 1 cannot catch this
    stops = [
        [_beat("b0", "p0", _STOP0_CLAIM)],
        [
            _beat("bX", "p1", _FACT_X),
            _beat("bY", "p1", _CLAIM_Y, script_body=f"{_Y_SENT1} {_Y_SENT2}"),
        ],
    ]
    seq = _seq(stops)
    route = _route([10, 400])
    stitched = generate(
        seq, route, TourInput(start=(48.85, 2.36), duration_min=90, city_slug="paris")
    )
    assert stitched.validation.passed
    # Precondition: the stitch KEPT both of bY's tellings (Step 1 didn't catch them).
    assert len([s for s in stitched.script if s.source_id == "bY"]) == 2

    served = compose_script_per_chapter(
        stitched,
        seq,
        route,
        client=_SameBeatClaimRepeatClient(),
        faithfulness_checker=_StrictHaikuLikeChecker(),
        candidates=1,
    )
    assert served.validation.passed
    # The served script carries no residual same-beat claim repeat: re-running the
    # include_same_beat claim pass removes nothing.
    deduped = suppress_repeated_claims(list(served.script), seq, include_same_beat=True)
    residual = [s.text for s in served.script if s not in deduped]
    assert len(deduped) == len(served.script), residual
    # bX's surviving composed line kept the stop partially (not fully) reverted, and
    # the diagnostic still names bY as the restored beat.
    status = {r.stop_idx: r for r in served.verify_report}
    assert status[1].status == "partially_reverted", status[1]
    assert status[1].restored_beats == ("bY",), status[1].restored_beats


# ---- §4b cascade dup: splice-beside-surviving-twin (single-source REPLACE) ----
#
# The class NONE of Steps 1-3 catch: an uncovered beat whose SURVIVING composed
# sentence still cites ONLY that beat (a shortened/reframed telling that kept claim-1
# but dropped claim-2). The omitted-outright splice appended the beat's FULL stitch
# BESIDE the survivor -> claim-1 voiced twice; the near-dup pass misses it
# (token_set_ratio 75.8 < 90) and the claim pass keeps both (the stitch carries the
# novel claim-2, the earlier survivor is never dropped forward-only). Confirmed on
# current committed code before the fix. Fix (a) REPLACE: drop the single-source
# survivor, use the fact-complete stitch.
_CATH_C1 = "the cathedral's foundation stone was laid in eleven sixty three"
_CATH_C2 = "its spire fell in a great storm in eighteen sixty"
_CATH_BODY = f"Here, {_CATH_C1}, and {_CATH_C2}."
_CATH_SURVIVOR = f"Remarkably, {_CATH_C1}, a detail still celebrated by visitors today."


class _TwoClaimShortenClient:
    """Stop 0 reworded (entails). Stop 1 (single beat bV, ONE stitched sentence with
    TWO key_claims): emit ONE survivor that keeps claim-1 verbatim (-> entails,
    survives) but DROPS claim-2 and is <90 token_set_ratio to the full stitch. So
    claim-2 is uncovered, bV is spliced back with its FULL stitch, and without the fix
    it lands BESIDE the survivor -> claim-1 twice."""

    def compose(self, request, attempt, prev_report):
        stop = next(iter({s.stop_idx for s in request.stitched.script}))
        beat_sents = [s for s in request.stitched.script if s.source_type == "beat"]
        out = [s for s in request.stitched.script if s.source_type != "beat"]
        if stop == 0:
            out += [s.model_copy(update={"text": f"And here: {s.text}"}) for s in beat_sents]
            return tuple(out)
        out.append(beat_sents[0].model_copy(update={"text": _CATH_SURVIVOR}))
        return tuple(out)


def test_surgical_splice_replaces_single_source_survivor_no_duplicate():
    """§4b REGRESSION. repair_composed_surgical must NOT splice a beat's full stitch
    beside a surviving composed sentence that cites ONLY that (uncovered) beat — that
    voices the shared fact twice, the exact #22 duplication, which neither dedup pass
    removes here (near-dup 75.8 < 90; claim pass keeps both). The (a) REPLACE fix drops
    the single-source incomplete survivor and uses the fact-complete stitch. Assert
    claim-1 is voiced EXACTLY ONCE and claim-2 is present. UNDO: revert the REPLACE
    branch in repair_composed_surgical -> claim-1 voiced twice -> RED."""
    from rapidfuzz import fuzz

    assert fuzz.token_set_ratio(_CATH_SURVIVOR, _CATH_BODY) < 90  # near-dup pass can't catch it
    bv = BeatRef(
        id="bV",
        poi_id="p1",
        script_body=_CATH_BODY,
        word_count=len(_CATH_BODY.split()),
        key_claims=(_CATH_C1, _CATH_C2),
    )
    seq = _seq([[_beat("b0", "p0", _STOP0_CLAIM)], [bv]])
    route = _route([10, 400])
    stitched = generate(
        seq, route, TourInput(start=(48.85, 2.36), duration_min=90, city_slug="paris")
    )
    assert stitched.validation.passed
    served = compose_script_per_chapter(
        stitched,
        seq,
        route,
        client=_TwoClaimShortenClient(),
        faithfulness_checker=_StrictHaikuLikeChecker(),
        candidates=1,
    )
    assert served.validation.passed
    stop1 = [s.text for s in served.script if s.stop_idx == 1 and s.source_type == "beat"]
    c1_count = sum(1 for t in stop1 if _CATH_C1 in t)
    assert c1_count == 1, f"claim-1 voiced {c1_count}x (dup): {stop1}"
    assert any(_CATH_C2 in t for t in stop1), f"claim-2 lost: {stop1}"


def test_surgical_never_deletes_a_fused_beats_fact_when_stitch_lacks_it():
    """§4b never-delete INVARIANT (hostile-review Repro 1). A surviving composed sentence
    that FUSES an uncovered beat (bidB) with ANOTHER beat (bidA) whose grounded stitch is
    NOT seated at this stop must NOT be deleted by the (b) whole-stop revert — that would
    drop bidA's fact, which only this composed sentence carries. The revert fires ONLY
    when the stop's stitch re-represents every beat the twins cite; here it does not, so
    the fix keeps the fused sentence and splices bidB's stitch (a harmless duplicate at
    worst). This guards the class where a composed sentence's stop_idx is mis-bucketed vs
    its beat's true stop (a pre-existing compose.py gap). UNDO: make the fused branch
    `revert_stops.add(k)` unconditionally -> bidA's fact deleted -> RED."""
    from src.tour.compose_gate import repair_composed_surgical
    from src.tour.contract import Script, Sentence, ValidationReport

    a_stitch = Sentence(
        text="Fact A grounded stitch stands here.", source_id="bidA", source_type="beat", stop_idx=0
    )
    b_stitch = Sentence(
        text="Fact B one grounded, and fact B two grounded.",
        source_id="bidB",
        source_type="beat",
        stop_idx=1,
    )
    stitched = Script.model_construct(script=(a_stitch, b_stitch))
    # bidB's composed stop keeps ONE fused sentence carrying bidA's fact + bidB fact-one
    # (drops fact-two -> bidB uncovered). It survives verify (not in drop_report).
    fused = Sentence(
        text="Fact A grounded stitch stands here, and fact B one grounded.",
        source_id="bidB",
        source_type="beat",
        stop_idx=1,
        also_cites=("bidA",),
    )
    composed = Script.model_construct(script=(fused,))  # bidA's fact lives ONLY in the fused twin
    drop_report = ValidationReport()  # nothing flagged for dropping
    uncovered_report = ValidationReport(coverage_failures=(("bidB", "fact B two grounded"),))
    repaired, _restored, _fully = repair_composed_surgical(
        composed, stitched, drop_report, uncovered_report
    )
    texts = [s.text for s in repaired.script]
    # The fused sentence (the ONLY carrier of bidA's fact) must survive, not be reverted away.
    assert fused.text in texts, f"the fused sentence carrying bidA's fact was DELETED: {texts}"


# ---- _recompute_fully: keep the reverted-vs-partial diagnostic honest ----

_W_C1 = "The tower held prisoners in the fourteenth century"
_W_C2 = "Iron spikes lined the tower's oubliettes"
_W_C1_SENT = f"{_W_C1}."
_W_C2_SENT = f"{_W_C2}."


class _FailBeforeSurvivorClient:
    """Stop 0 reworded (entails). Stop 1 (single beat bW, two claims): emit bW as
    TWO sentences IN THIS ORDER — first a bold fusion that quotes no claim (rejected
    → dropped → the splice for bW's uncovered claim lands at THIS position, i.e.
    BEFORE the survivor), then a near-verbatim restatement of bW's C1 stitch line
    that DOES entail (survives). So after the splice the composed survivor sits AFTER
    the spliced C1 stitch and the fail-open de-dup drops the SURVIVOR — leaving the
    stop fully stitch. Only _recompute_fully then relabels it reverted_to_stitched."""

    def compose(self, request, attempt, prev_report):
        stop = next(iter({s.stop_idx for s in request.stitched.script}))
        beat_sents = [s for s in request.stitched.script if s.source_type == "beat"]
        out = [s for s in request.stitched.script if s.source_type != "beat"]
        if stop == 0:
            out += [s.model_copy(update={"text": f"And here: {s.text}"}) for s in beat_sents]
            return tuple(out)
        first = beat_sents[0]
        out.append(first.model_copy(update={"text": "A bold unified telling here."}))
        out.append(first.model_copy(update={"text": f"{_W_C1}, notably."}))
        return tuple(out)


def test_recompute_fully_relabels_stop_when_dedup_drops_last_composed():
    """_recompute_fully guard. The fail-open de-dup drops the stop's only surviving
    composed sentence (a near-verbatim restatement of the spliced C1 stitch), so the
    stop is now ENTIRELY grounded stitch. The diagnostic must say
    reverted_to_stitched, not partially_reverted. Stub _recompute_fully to return an
    empty set and this goes RED (the label stays the stale, pre-de-dup value)."""
    from rapidfuzz import fuzz

    assert fuzz.token_set_ratio(_W_C1_SENT, f"{_W_C1}, notably.") >= 90
    bw = BeatRef(
        id="bW",
        poi_id="p1",
        script_body=f"{_W_C1_SENT} {_W_C2_SENT}",
        word_count=len(f"{_W_C1_SENT} {_W_C2_SENT}".split()),
        key_claims=(_W_C1, _W_C2),
    )
    seq = _seq([[_beat("b0", "p0", _STOP0_CLAIM)], [bw]])
    route = _route([10, 400])
    stitched = generate(
        seq, route, TourInput(start=(48.85, 2.36), duration_min=90, city_slug="paris")
    )
    assert stitched.validation.passed
    assert len([s for s in stitched.script if s.source_id == "bW"]) == 2

    served = compose_script_per_chapter(
        stitched,
        seq,
        route,
        client=_FailBeforeSurvivorClient(),
        faithfulness_checker=_StrictHaikuLikeChecker(),
        candidates=1,
    )
    assert served.validation.passed
    # The de-dup dropped the composed survivor; stop 1 is now entirely stitch.
    assert all(s.source_type != "beat" or "notably" not in s.text for s in served.script)
    status = {r.stop_idx: r for r in served.verify_report}
    assert status[1].status == "reverted_to_stitched", status[1]


# ---- best-of-N reliability: craft_score breaks fact-equal ties toward the well-written ----

_BELL_CLAIM = "the great bell was forged in 1685"


class _CraftBestOfClient:
    """Per stop, returns a FLAT monotone candidate FIRST, then a WELL-WRITTEN one — both
    carrying the beat's key_claim VERBATIM (equal fact-penalty), differing only in craft."""

    def __init__(self):
        from collections import defaultdict

        self._n = defaultdict(int)

    def compose(self, request, attempt, prev_report):
        stop = next(iter({s.stop_idx for s in request.stitched.script}))
        beat_sents = [s for s in request.stitched.script if s.source_type == "beat"]
        out = [s for s in request.stitched.script if s.source_type != "beat"]
        i = self._n[stop]
        self._n[stop] += 1
        if i == 0:  # FLAT, monotone, no percussion
            txt = (f"This is a bell in the south tower. Records show {_BELL_CLAIM}. "
                   "The bell is very large. The bell is really quite old indeed.")
        else:  # WELL-WRITTEN: a short punch + a longer flowing line (SAME fact)
            txt = (f"Look up. Above you {_BELL_CLAIM}, and it has tolled only for the "
                   "city's darkest mornings ever since.")
        out.append(beat_sents[0].model_copy(update={"text": txt}))
        return tuple(out)


def test_best_of_n_keeps_the_higher_craft_candidate_among_fact_equal():
    """RELIABILITY LEVER: with candidates>1, among FACT-SAFE candidates best-of-N keeps the
    one with the higher craft_score — so a flat/monotone sample loses to a well-written one
    and quality varies less run-to-run. Both candidates here carry the beat's key_claim
    verbatim (equal fact-penalty), differing only in craft. UNDO: rank by _local_penalty
    alone (drop the craft tiebreak in _run_best_of_n) -> the FLAT first candidate is kept
    -> RED."""
    bell = BeatRef(id="bell", poi_id="p1", script_body=f"Here, {_BELL_CLAIM}.",
                   word_count=8, key_claims=(_BELL_CLAIM,))
    seq = _seq([[_beat("b0", "p0", _STOP0_CLAIM)], [bell]])
    route = _route([10, 400])
    stitched = generate(
        seq, route, TourInput(start=(48.85, 2.36), duration_min=90, city_slug="paris")
    )
    assert stitched.validation.passed
    served = compose_script_per_chapter(
        stitched, seq, route, client=_CraftBestOfClient(),
        faithfulness_checker=_StrictHaikuLikeChecker(), candidates=2,
    )
    assert served.validation.passed
    stop1 = " ".join(s.text for s in served.script if s.stop_idx == 1 and s.source_type == "beat")
    assert _BELL_CLAIM in stop1  # fact kept either way
    assert "Look up." in stop1, f"best-of-N did not keep the well-written candidate: {stop1!r}"
