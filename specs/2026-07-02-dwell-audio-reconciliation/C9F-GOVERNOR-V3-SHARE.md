# Governor v3 — share-of-DELIVERED cap (supersedes the budget÷3 emission cap)

Status: DESIGN. Ratified by the user 2026-07-04 after the User-agent baseline +
3-model panel proved the budget÷3 cap (v1/v2) is a **no-op on every real Paris
tour**: gov(60)=597s but the UC5 dominating incidental 'Ile de la Cite' emits
363s (38.9% of the 931s DELIVERED), so 363 < 597 → never capped. Real tours
under-deliver (~52% of target), so ⅓-of-TARGET ≈ 64% of DELIVERED — nearly 2× the
"⅓ of the tour" the user intended. The cap must be a share of DELIVERED audio.

## Product rule (user-ratified 2026-07-04)
No INCIDENTAL (non-exempt) stop's emitted audio may exceed **SHARE = ⅓ of the
tour's total DELIVERED audio**. Exempt (may dominate): the positional
start-anchor (`start_anchor_poi_id`) and the fixed-end / pulled-endpoint
(`fixed_end_poi_id`). Scope: end=None only (A→B keeps Phase-2 tier-dwell,
byte-identical). "The tour's total" = the full delivered audio INCLUDING exempt
anchors (that is what the walker experiences as "the tour").

## Where it applies — EMISSION only, post-selection
The delivered set + per-stop audio are known only after select_route finishes, so
the re-balance lives in `build_poi_beat_plans_capped` (the shipped C9f-i seam,
currently uncapped). Selection is NOT changed — the greedy keeps its C9e currency
for seating decisions; emission re-balances the final delivered route and C8 /
delivered_thin measure the emission (the honest, played truth). Selection-vs-
emission divergence is a seating-quality wrinkle, never a reporting-honesty bug,
because reported minutes read the emitted output.

## Algorithm — fixed point (converges; monotone-decreasing T)
```
a_i   = uncapped audio of stop i  (planned_audio_seconds of the merged plan)
exempt = {start_anchor_poi_id, fixed_end_poi_id} - {None}   (end=None only)
c_i   = a_i                          # start uncapped
repeat:
    T       = sum(c_i over ALL stops)          # total delivered incl exempt
    ceiling = floor(SHARE * T)                 # SHARE = 1/3
    for each NON-exempt stop i:  c_i = min(a_i, ceiling)
until T stops changing (or N iters; caps only shrink T, so it converges)
# then govern_poi_beats(plan_i, c_i) -> (kept_i, overflow_i) per non-exempt stop
# exempt stops: govern_poi_beats(plan_i, None) -> full plan, () overflow
```
Convergence: each pass only lowers `c_i` for over-ceiling incidentals, which
lowers T, which lowers the ceiling — a contraction; ≤ len(pois) iterations, and in
practice 2-3. If the ceiling would drop below a stop's first beat, `govern_poi_beats`
keeps beat[0] (bounded one-beat overshoot, beat_select.py) — a stop always speaks.

### Worked check — UC5 (Notre-Dame start, 60-min RT), live measured
exempt = {Notre-Dame 396s}. incidentals: Crypte 56, Hotel-Dieu 74, Ile 363,
Shakespeare 42. Fixed point on Ile: c = (E + other_incidentals + c)/3 where
E+others = 396+56+74+42 = 568 → 2c = 568 → **c ≈ 284s**. Ile 363→284s (6.0→4.7
min), share 284/852 = 33.3%, now BELOW the exempt anchor (396s) — no longer
dominates. Overflow 79s → keep-exploring extras. Crypte/Hotel-Dieu/Shakespeare
untouched (already under ceiling). This is the utility fix the tourist wanted.

## delivered_thin — measure the SAME emitted artifact (sonnet's fix)
Do NOT reselect via `planned_capped_audio_seconds` (which re-caps the UNMERGED
pool — a different currency). Call `build_poi_beat_plans_capped` once, sum
`planned_audio_seconds(kept_i)` over its output for the delivered total, and reuse
that for both delivered_thin and (later) C8 reported minutes. One artifact, one
currency.

## Overflow → C9g (ships together)
Every non-exempt stop's `overflow_i` is the beats cut past its share ceiling.
C9g threads it to `ScriptPOI.overflow_beat_ids`; keep-exploring surfaces it. C9f
(v3 cap) + C9g ship in ONE release so no capped beat is ever silently dropped.

## What v3 KEEPS from the shipped C9f-i (cdeedda)
- The exempt-anchor identity on the Route + per-flavour options_json + compose
  restore + legacy fail-open. All still required (the cap reads the exempt set,
  and must not cap-the-anchor at compose or on legacy trips).
- The single wrapper seam. v3 only changes the wrapper BODY (uncapped → share
  re-balance) + the delivered_thin currency.

## Test matrix (the loop + judge will demand)
- share-cap-fires-on-UC5-fixture: a marquee-start 60-min RT with an incidental
  ~39%-of-delivered stop → post-cap that incidental ≤ ⅓ of delivered AND ≤ the
  exempt anchor; the two thin real stops + finale keep their beats; overflow
  non-empty. (The pacing-improvement test tied to the User baseline.)
- exempt-never-capped: beat-rich start_anchor / fixed_end emit full plan even
  when they exceed ⅓ of delivered.
- A→B byte-identical (end_is_none=False → uncapped).
- legacy-failopen at compose (bare-list options → uncapped, no crash/wrong-cap).
- fixed-point-converges + partition: kept ∪ overflow == full merged plan, no
  dup/loss, for every stop.
- goldens: Île 16/47 · PdV 10/18. NOTE v3 MAY move these (unlike budget÷3):
  Île 90-min delivered ~33 min; ⅓ = ~11 min = 660s; every Île stop is < 660s
  (max Conciergerie 404s) EXCEPT verify none crosses — if one does, the golden
  overlap could drop and C12 (audio-aware golden relaxation) must precede. MEASURE
  before claiming 0-delta; do NOT assume as v2 wrongly did.
- delivered_thin-on-capped currency == wrapper currency (no reselect drift).
- charged(selection C9e) vs emitted(v3): document the intentional divergence;
  assert C8/delivered_thin read EMITTED, so honesty holds.
- Bar: make test 0/0 + lint 0 + golden-diff pasted + hostile panel + judge +
  live browser proof (real Notre-Dame 60-min RT before/after screenshots).

---

# Governor v4 — domination-gated + marquee exemption + C9g (SHIPPED 2026-07-04)

v3 (share-of-delivered, always-on) was refuted by a hostile panel on the
IMPLEMENTATION (2 blocking + 3 major): a demoted start-anchor dangled the exempt
id → cap-everything inversion; the exempt anchor was the greedy's proximity seed
(a thin courtyard) not the star; the always-on ⅓ cap over-trimmed BALANCED tours
(−27.6% on Pont Neuf 60 RT); capping flipped the flagship demo to delivered_thin;
and C9g wasn't shipped so capped beats were silently deleted. The user ratified a
conditional, domination-only governor. v4 delivers it:

- **Domination-gated** (`_domination_caps`): a stop is capped ONLY if it exceeds
  ⅓ of delivered AND exceeds `GOVERNOR_DOMINATION_FACTOR=1.5` × the next-largest
  non-exempt stop (a drowning outlier). Balanced tours (peers within the factor)
  are NEVER touched — fixes the −27.6% over-trim.
- **Marquee exemption by importance**: exempt = the highest-tier delivered stop
  (ties → highest audio) + the fixed destination / pulled endpoint. Always a real
  in-route POI → no dangling-id inversion; the tier-5 star is protected while a
  lower-tier dump is capped. Replaces the v3 proximity-seed exemption.
- **C9g shipped together**: `BeatSequence.overflow_by_poi` →
  `ScriptPOI.overflow_beat_ids`. Trimmed beats are SURFACED (keep-exploring),
  never deleted.
- **delivered_thin** measures the UNCAPPED available content (the overflow is
  available on demand), so capping never spuriously flips a tour to thin.

Proof (live corpus + User-agent panel, 2026-07-04): UC5 Notre-Dame 60 RT — Ile de
la Cite 363→281s (43%→37%), Notre-Dame marquee full 396s, 2 overflow, +3
enjoyment; 45-min 363→233s, +4. Balanced Pont Neuf / Louvre / open-walk tours:
ZERO caps, byte-identical audio. Musée Victor Hugo → Place des Vosges (tier-5)
full 1248s (the v3 gut to 167s does not reproduce). Goldens byte-identical (Île
16/47, PdV 10/18). `make test` 1244/0/0. Tool: `make measure-governor`.

Deferred: `start_anchor_poi_id` is now unused by the wrapper (v4 exempts by
marquee, computed in-wrapper, so it works at compose without it) — a dead-field
cleanup for a later pass, harmless meanwhile.

## Known limit (v4, judge-noted 2026-07-04)
The domination gate compares a stop to the MEAN of the OTHER non-exempt stops, so
two co-dominators no longer shield each other (the pairwise gap the judge found).
But a cluster of 3+ NEAR-EQUAL beat-rich stops converges to a balanced delivery —
only the single largest (if any) trims, because once it drops to the ceiling the
rising mean-of-others pulls the rest below the 1.5x gate. This is defensible (a
balanced cluster is not "domination"), not a bug; documented so a future panel
does not re-litigate it. If product feedback wants a hard "no stop over ⅓" even in
near-equal clusters, the lever is a second pass, not the domination gate.
