# Lens Default Selection — spec

**Status:** agreed draft · 2026-06-01
**Applies when:** a profile has no lenses — at onboarding ("Use a starter set") *or* at generation time for any profile that skipped lens selection. Instead of generating with no lens bias, apply a computed default set.

## Goal

Seed a small, varied, well-covered set of lenses that (1) **guarantees a substantive first tour** (never thin/empty) and (2) **doubles as discovery** — teaching the user what lenses do so they come back and choose deliberately.

## Selection

Pick **3 lenses** (configurable, 2–3), scoped to the **city** — narrowed to the **start area / candidate route** for on-demand tours. Computed **at generation time** for on-demand (use the lenses that light up *this* route), city-level for planned.

### 1. Coverage floor — eligibility (the part of "most content" that's right)

A lens is eligible only if it has **≥ N qualifying POIs + stories** in scope (N tunable; start ≈ 8). Below the floor → ineligible. This is what guarantees no thin tour.
*If fewer than 3 lenses clear the floor (thin area), use what passes (1–2) rather than padding with weak lenses.*

### 2. Score the eligible lenses

```
score = w1·demand + w2·content + w3·editorial
```

- **demand** — selection rate among users who *did* choose lenses, weighted by that lens's avg rating / completion. The true meaning of "popular." Primary weight once data exists.
- **content** — POI/story density & quality for the lens in scope. Cold-start bootstrap + tiebreaker (this is the supply metric; useful, but not the whole story).
- **editorial** — optional per-city curator boost (hand-tuned launch cities).
- **At launch (no demand data): `w1 = 0`** — rank on content + editorial. As usage accrues, raise `w1` so the default comes to mean *what people actually like*, with content demoted to floor + tiebreaker.

### 3. Diversity constraint

The chosen 3 must span **≥ 2 (ideally 3) categories**. Greedy: take the top lens, then the top lens from a *new* category, etc. Prevents a monotone default (e.g., three flavors of "old buildings"), which pure "most content" would produce.

### 4. Transparency & re-prompt

- **Name** the chosen lenses on screen ("Starting you with Hidden History · Historic Architecture · Local Legends"), not applied invisibly.
- **Reveal** them in the first tour so the default teaches.
- Mark profile `lens_source = default`; gently re-prompt later to choose deliberately.

## Rules / edges

- **Recompute per city** — never reuse one city's defaults in another.
- **On-demand** computes from the candidate route at generation; **planned** uses city (or start area).
- **Naming:** while the mechanism is coverage/editorial (pre-demand), label it "starter set" / "recommended" — reserve "popular" for when it's genuinely demand-driven, so the label doesn't fib.

## Forward note — profiles

Each lens **profile** under an account reuses this logic independently: a profile with no lenses gets its own computed default for the city/route. The same fallback also fires when a profile's lens has no beat at a given POI (relevant to per-listener narration).
