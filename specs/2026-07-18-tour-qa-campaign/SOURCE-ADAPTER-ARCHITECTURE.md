# Source Adapter Architecture — Ondoway multi-source city onboarding

Design produced 2026-07-18 (opus Plan agent, read-only audit of the real pipeline).
Companion docs: `LONDON-EXTRACTION-FIX.md` (which sections to extract),
`PHASE-C-RESULTS.md` (why this matters — London stops scored NEGATIVE craft because
the corpus has nothing to build with).

## 0. Findings that change the shape of the plan

**F1 — There are two source layers. Only one has an abstraction, and it is the wrong one.**

- **Layer A, city-level POI discovery** (`src/onboard/sources/*`) is already well-built: a pure
  Protocol (`sources/base.py:22`), a single network door with a registrable-domain allowlist
  (`fetch.py:24-35`, `:63`), a required-licence model wall (`models.py:34-51`), per-item
  public-domain gates already fail-closed (`sources/internet_archive.py:39`, `gutenberg.py`),
  and a dict-based registry (`flow.py:57-72`). Six connectors exist.
- **Layer B, per-POI content acquisition** (`src/onboard/extract.py`) has **no abstraction at
  all**. One hardcoded function against en.wikipedia with `"exintro": 1` at `extract.py:125`,
  producing `WikiExtract` (`assemble.py:225-237`), a Wikipedia-shaped record keyed on `revid`.

London's corpus is 100% `book_slug: "wikipedia"` because Layer B is single-source. The task is
to promote Layer A's proven pattern into Layer B — extend existing contracts, don't invent new.

**F2 — Adding sources today would silently WEAKEN the grounding contract.**
`scripts/validate_beats.py` has exactly two grounding paths: `_check_wikipedia_grounding:152`
(keyed on `book_slug == "wikipedia"`) and `_check_book_grounding:234`. At `:257-258`:

```python
chunk_text = text_cache[key]
if chunk_text is None:
    continue  # chunk file not locatable — soft-skip (don't break commits)
```

Any new adapter writing chunks elsewhere resolves to `None` and is **ungrounded by default
while validate_beats still exits 0**. Closing this is P0, before any adapter.

**F3 — Acquisition alone CANNOT move the acceptance metric.**
`src/onboard/beat_draft.py:206-210` hardcodes `"entities": []`, `"physical_cues": []`,
`"key_claims": []`, `"sensory_anchor": False` on every auto-drafted beat. London is 0/561
partly because **no code path ever populates those fields on the auto path**. Ship six perfect
adapters and London still measures 0%. The first slice MUST include the enrichment seam.

Measured today (`data/*/beats.json`):

| city | beats | physical_cues | entities | distinct book_slugs |
|---|---|---|---|---|
| london | 561 | 0 (0%) | 0 (0%) | 1 (wikipedia) |
| paris | 1562 | 1156 (74%) | 1356 (86%) | 8 |
| new_york | 2005 | 1304 (65%) | 1822 (90%) | 6 |

**F4 — `src/onboard/sources/shadow_discovery.py` already exists** and names Anna's Archive.
Metadata-only and genuinely well-walled: no text field on `DiscoveryPointer`, `extra="forbid"`,
an AST test proving it cannot import a fetcher, hosts absent from the allowlist. It never
ingests. Recommendation: KEEP it — discovery-only satisfies the constraint and feeds the legal
`owned_local_file` path (know what exists, acquire it lawfully).

**F5 — No rate limiting, caching, concurrency, or retry exists anywhere.**
`src/api/routes/onboard.py:151` consults sources with a serial list comprehension.

**F6 — Partial-failure tolerance and progress streaming already exist and are good.**
`flow.py:144-152` degrades a source failure to a visible event; `JobStore` + SSE already stream
per-source events; `OnboardEventKind` (`models.py:80-88`) already includes an unused
`rate_limited`. Extend, don't rebuild.

## 1. The adapter contract

### 1.1 Two protocols, not one

Keep `SourceConnector` (`sources/base.py:22`) for city-level discovery. Add a parallel protocol
for per-POI content — same purity discipline, same single-network-door rule:

```python
# src/onboard/sources/content.py
@runtime_checkable
class ContentAdapter(Protocol):
    """Per-POI content acquisition. discover/fetch_plan/parse are ALL PURE —
    no network, no filesystem. Only run_adapter() fetches."""
    slug: str
    config: AdapterConfig

    def discover(self, poi: dict, ctx: CityContext) -> list[ChunkRef]: ...
    def fetch_plan(self, ref: ChunkRef) -> FetchPlan: ...
    def parse(self, ref: ChunkRef, payload: object) -> list[SourceChunk]: ...
```

Three methods because per-POI acquisition is a two-hop pattern (resolve the article/entity,
then fetch it) — which `extract.py:199-219` already does informally.

### 1.2 `SourceChunk` — source-neutral replacement for `WikiExtract`

`WikiExtract` pins on `revid`, a Wikipedia concept. Generalize to a content hash; keep
`WikiExtract` as a thin alias for one release.

```python
class SourceChunk(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source_slug: str
    poi_name: str
    title: str
    url: str
    text: str
    licence: SourceLicence          # REQUIRED, closed enum
    attribution: Attribution        # REQUIRED, non-empty
    retrieved_at: str               # REQUIRED (was optional at models.py:50)
    content_sha256: str             # REQUIRED — the pin, replaces revid
    section: str | None = None      # section-aware ingest
    period: Period | None = None    # staleness (§5); REQUIRED when historical
    meta: dict = {}                 # provenance SCALARS only, never text
```

### 1.3 The licence enum — widen it

`models.py:24` today: `Literal["public_domain", "cc_by_sa", "user_provided"]`. Target:

```python
SourceLicence = Literal[
    "public_domain",    # PD works, CC0 (Wikidata)
    "cc_by",
    "cc_by_sa",         # Wikipedia, Wikivoyage
    "odbl",             # OpenStreetMap — see note
    "open_gov",         # OGL v3: Historic England, London Datastore
    "api_licensed",     # commercial API under contract
    "owned_local_file", # renamed from user_provided; the Books/ path
]
```

`odbl` is a deliberate addition: OSM is ODbL 1.0, a share-alike *database* licence — not
`open_gov`, not `cc_by_sa`. Mislabelling defeats the point of a machine-checkable field.

### 1.4 The ingest gate — one chokepoint, no per-source branching

```python
# src/onboard/ingest_gate.py
class IngestRefused(Exception): ...
def admit(chunk: SourceChunk, *, spec: AdapterSpec) -> None:
    """Raise IngestRefused unless admissible. Called by the ONLY chunk-write path."""
```

Fail-closed checks in order: (1) licence in enum; (2) licence matches the adapter's registry
spec; (3) attribution present with non-empty holder + source_name; (4) `retrieved_at` ISO-8601;
(5) `sha256(text) == content_sha256` (text not swapped after pinning); (6) URL host passes
`fetch.is_ingest_host_allowed` — except `owned_local_file`, which must resolve under `Books/`;
(7) if `spec.requires_pd_check`, the §5 PD gate.

Proving tests: an adapter with no/unknown/mismatched licence is refused; attribution-less and
hash-mismatched chunks refused. Plus an AST boundary test (house style of
`tests/test_onboard_boundary.py`): no module other than the chunk writer may call
`_atomic_write_text` for a source chunk — so no second path to disk skips `admit`.

### 1.5 The registry — workbench-enumerable

```python
@dataclass(frozen=True)
class AdapterSpec:
    slug: str
    kind: Literal["discovery", "content", "both"]
    licence: SourceLicence
    attribution_template: str
    endpoint_host: str
    enabled: bool = True
    priority: int = 50            # lower wins ties in dedup
    rate_limit_rps: float = 1.0
    burst: int = 1
    timeout_s: float = 30.0
    requires_pd_check: bool = False
    cache_ttl_days: int = 30
    period_default: Period | None = None
```

Exposed as `GET /onboard/sources` (spec list + per-source health) so the workbench renders a
source panel with toggles. `MODE_CONNECTORS` (`flow.py:51`) collapses into registry queries.

### 1.6 Making `validate_beats` source-neutral (closes F2)

One resolver-driven check. Chunk paths:

```
data/{city}/sources/{source_slug}/{poi_slug}-{sha256[:12]}.txt   # new, all adapters
data/{city}/wikipedia/{poi_slug}-rev-{revid}.txt                 # legacy alias, kept
Books/{City}/{book-slug}/{chunk}.txt                             # owned_local_file
```

Then change the soft-skip: a chunk whose `source_slug` is in `REGISTRY` and is not locatable →
**hard error `SOURCE_MISSING`**. Soft-skip survives only for an explicit legacy list, mirroring
the `grounding_grandfathered.json` pattern (`validate_beats.py:219-231`). Adding an adapter then
costs zero lines in validate_beats, and a new source cannot be silently ungrounded.

## 2. The concrete adapter set

| slug | endpoint | licence | rps | notes |
|---|---|---|---|---|
| `wikipedia_full` | en.wikipedia.org/w/api.php | cc_by_sa | 5 | **drop `exintro`** |
| `wikivoyage` | en.wikivoyage.org/w/api.php | cc_by_sa | 2 | listings + prose |
| `wikidata` | query.wikidata.org/sparql | public_domain | 1 | CC0; WDQS strict |
| `osm_physical` | overpass-api.de/api/interpreter | odbl | 0.5 | physical_cues fuel |
| `gutenberg` | gutendex.com / gutenberg.org | public_domain | 1 | PD gate exists |
| `archive_org` | archive.org | public_domain | 0.5 | PD wall exists |
| `historic_england` | historicengland.org.uk | open_gov | 1 | **new host** |
| `london_blue_plaques` | data.london.gov.uk | open_gov | 1 | **new host** |
| `owned_books` | local fs | owned_local_file | n/a | no network |

New hosts must be added to `INGEST_DOMAIN_ALLOWLIST` (`fetch.py:24-35`) in the same commit as
their adapter — the allowlist stays the outer wall.

**`wikipedia_full`** — one `ChunkRef` per section, so `SourceChunk.section` is real rather than
the hardcoded `"section": "Lead"` at `beat_draft.py:222`. Reuse the existing wrong-article
geo-verification (`extract.py:181-187`) unchanged.

**`osm_physical`** — the only source that directly supplies physical_cues: `building:material`,
`building:levels`, `height`, `roof:material`, `roof:shape`, `start_date`, `architect`,
`heritage`, `listed_status`. Overpass returns tags, not prose, and a synthesized sentence would
fail the grounding gate (`extract_validators.source_grounding_gate:347`). Resolution: the
adapter serialises tags into a **deterministic fact-sheet text file** which IS the pinned chunk:

```
Portland stone is recorded as the building material.
The building has 4 levels.
The recorded height is 32 m.
Construction start date is recorded as 1710.
```

The beat's `source_passage` then quotes that file verbatim — grounding works with zero
special-casing. The serialiser must be pure and deterministic so the hash is stable.

**PD adapters** — belt-and-braces publication-date gate in `admit`:

```python
def passes_pd_gate(period: Period) -> bool:
    """Fail-closed. Explicit PD status from the provider AND a publication year
    old enough that life+70 cannot still apply."""
    if period.published_year is None:
        return False                       # unknown year is NEVER admitted
    return period.published_year <= date.today().year - 96
```

96 = 70 (life+70) + 26 (conservative floor for authorial lifespan post-publication). Admits
Baedeker, Dickens's *Dictionary of London* (1879), Ward Lock, pre-1930 Blue Guides; refuses
anything modern regardless of provider metadata. Both gates must pass.

**`OpenRegisterAdapter`** — government/heritage registers are all the same shape (geo/ID query,
JSON/CSV, field map, OGL-family licence). One base class + per-city config makes Edinburgh,
Dublin, or NYC LPC a config entry rather than a new module.

## 3. Crawler / orchestration

New `src/onboard/crawl.py`. Per-POI fan-out across enabled content adapters.

- **Concurrency**: bounded pool (default 8) over the (POI × adapter) product. Per-*host*
  semaphores from `rate_limit_rps` — a token bucket keyed on `endpoint_host`, so two adapters
  on one host share a budget. Concurrency never overrides politeness.
- **Caching**: content-addressed at `data/.cache/{source_slug}/{sha256(url+params)}.json` with
  `retrieved_at` + `cache_ttl_days`. Re-onboarding refetches nothing within TTL; `--refresh`
  forces revalidation. This is what makes iterating on London cheap.
- **Retry/backoff**: exponential + jitter, 3 attempts, on 429/500/502/503/504 and timeouts;
  honour `Retry-After`; emit the already-defined `rate_limited` event so the workbench shows
  throttling instead of appearing hung.
- **Partial failure**: extend `flow.py:144-152` — an adapter failure emits a visible error and
  yields zero chunks; the POI and city proceed. Config errors still propagate. Add a run-level
  floor: if every adapter fails or median sources-per-POI is 0, fail loudly (the acquisition
  analogue of `assemble.py:927-931` refusing thin cities).
- **Progress**: reuse `JobStore.append_event`; new scalar-only payloads `poi_start`,
  `chunk_pinned`, `poi_done`, `rate_limited`. **`_SSE_MAX_SECONDS = 60.0` (`onboard.py:67`)
  must be raised** — a real multi-source crawl of 50+ POIs exceeds 60s and the stream would cut
  mid-run. Make it spec-derived with a heartbeat frame.
- **API hook** inside `_run_onboard` (`onboard.py:140-176`), replacing the single
  `build_extract_index` call at `:156`.

## 4. Dedup and cross-source conflict

Existing guards are all exact-match: `HASH_COLLISION` (`validate_beats.py:72-88`), the run-wide
`seen_hashes`/`seen_passages` skip (`beat_draft.py:400-414`), same-article dedup
(`extract.py:259-266`). None touch cross-source near-duplicates — "completed in 1625" and
"erected in 1625" hash differently and both ship.

New `src/onboard/cross_source.py`, modelled on `src/tour/tour_consistency.py`. Two carried-over
rules, both load-bearing:

1. **Lexical methods for candidate generation ONLY; every decision semantic.** MinHash LSH
   blocks candidate pairs cheaply; the judgement is made only by an injected `CrossSourceJudge`.
2. **Judge once per (POI, source-pair), passing full claim lists** — never per claim pair
   (~2500× cheaper; the cost note in `tour_consistency.py` is explicit).

On `SAME_FACT`: keep the higher-priority source, prefer modern over historical, record the
dropped source in `meta.corroborated_by` — a collapse that *increases* provenance. This finally
satisfies Pipeline Guardrail #1 (two-source minimum), unsatisfiable on a single-source corpus.

**Disagreement — quarantine, never adjudicate** (Guardrail #4 forbids auto-resolving): write a
`SourceConflict` to `data/{city}/source_conflicts.json`, stamp BOTH beats
`fact_check.status = "disputed"`, and the upload path already excludes disputed beats — so a
contradicted fact structurally cannot ship until a human resolves it. The cost of an unresolved
conflict becomes a missing beat, not a confidently wrong one. (This is the Battery Park
1623-vs-1625 class, caught at ingest instead of at tour time.)

## 5. Staleness for historical public-domain sources

Failure mode: a 1900s Baedeker vividly describes a building demolished in 1940, shipped as
present-tense fact.

```python
class Period(BaseModel):
    published_year: int | None = None
    observed_from: int | None = None
    observed_to: int | None = None
    @property
    def is_historical(self) -> bool:
        return self.published_year is not None and \
               self.published_year < date.today().year - 50
```

An adapter with `requires_pd_check=True` that cannot supply `published_year` is REFUSED —
unknown provenance is never admitted. A beat whose primary chunk `is_historical` must carry
`temporal_frame: "historical"` and attribute in-text ("In 1879, Dickens's *Dictionary of London*
described…"), enforced by a new hard check `HISTORICAL_UNFRAMED`. This is a structural check on
a field, not tense-detection by regex — deliberately, since that is the banned lexical shortcut.

A historical beat asserting present existence requires a modern corroborating chunk
(`wikipedia_full`, `wikidata`, or `osm_physical`). `osm_physical` is the cheapest existence
oracle: no feature at the coords + a Wikipedia "demolished" mention is a strong demolition
signal, landing as a `SourceConflict` for human review rather than an auto-deletion.

## 6. Acceptance criterion and regression guard

New `scripts/corpus_richness.py` (style of `validate_beats.py`: scoreboard to stdout, non-zero
exit on failure).

```
make corpus-richness CITY=london            # report
make corpus-richness CITY=london ENFORCE=1  # exit 1 below floor
```

| metric | floor | paris | nyc | london today |
|---|---|---|---|---|
| physical_cues coverage | ≥ 40% | 74% | 65% | **0%** |
| entities coverage | ≥ 60% | 86% | 90% | **0%** |
| distinct sources per POI, median | ≥ 3 | — | — | **1** |
| tier≥3 POIs with ≥2 sources | ≥ 80% | — | — | **0%** |
| anchor-candidate POIs (≥3 beats, tier≥3) | ≥ 20 | — | — | ok |

The last row reuses the engine constant `ANCHOR_CANDIDATE_BEAT_COUNT_MIN = 3`
(`src/tour/density.py`) rather than inventing a number.

`tests/test_corpus_richness.py`: (1) unit tests proving each floor bites; (2) every registered
city meets the floors OR appears in `data/richness_grandfathered.json` (London goes on it today
with a dated reason, comes off when fixed — the shrinking-backlog pattern already used at
`validate_beats.py:219-231`); (3) **a test asserting the grandfather list never GROWS**, so a
newly-onboarded cue-less city cannot be waved through.

## 7. Build order

| # | Work | Hours |
|---|---|---|
| **P0** | Trunk: widen `SourceLicence` (+odbl); `SourceChunk`/`Attribution`/`Period`; `ingest_gate.admit` + refusal tests; `registry.py`; source-neutral chunk paths + legacy alias; **generalise validate_beats, close the soft-skip (F2)**; AST boundary test | 10–14 |
| **P1** | `osm_physical` adapter + deterministic fact-sheet serialiser + fixtures + tests | 5–7 |
| **P1** | **Enrichment seam (F3)** — populate physical_cues/entities/key_claims instead of `beat_draft.py:206-210`'s hardcoded `[]` | 5–8 |
| **P2** | `wikipedia_full` section-aware adapter (drop `exintro`) — see LONDON-EXTRACTION-FIX.md | 5–7 |
| **P3** | Crawler: pool, token buckets, cache, retry, partial failure, progress events, `GET /onboard/sources`, raise `_SSE_MAX_SECONDS` | 10–14 |
| **P4** | Cross-source dedup + conflict quarantine + `source_conflicts.json` + disputed marking | 10–14 |
| **P5** | Period tagging, PD hard gate, `HISTORICAL_UNFRAMED`, modern cross-check | 6–8 |
| **P6** | `corpus_richness.py` + floors + regression guard + grandfather list | 5–7 |
| **P7** | Remaining adapters: wikivoyage, wikidata, gutenberg/IA full text, `OpenRegisterAdapter` + Historic England + Blue Plaques | 16–24 |

**Total ≈ 70–95 h.**

### First shippable slice — P0 + P1 (~20–29 h)

**"Trunk plus Overpass plus enrichment, measured on London."** Not the Wikipedia full-article
change, despite it yielding the most raw text:

1. **P0 must precede everything** — ship any adapter before the validator is generalised and it
   lands ungrounded-but-passing (F2). Worse than shipping nothing.
2. **Overpass is the only source that directly supplies physical_cues** (material, height,
   levels, roof, architect). Wikipedia lead text yields history prose, not fabric.
3. **Without the enrichment seam the number cannot move at all** (F3) — a slice that ships
   adapters and still measures 0% would read as a failed architecture when it is an unwired field.

Exit criterion: `make corpus-richness CITY=london` reports physical_cues ≥ 40% (from 0%), median
sources-per-POI ≥ 2 (from 1), `make test` green, `validate_beats` passing with `SOURCE_MISSING`
active.

### Open decisions for the user

1. **`shadow_discovery.py`** (Anna's Archive, discovery-only) — recommendation: KEEP as-is.
2. **`odbl` as a seventh licence value** — recommended over mislabelling OSM.
3. **Enrichment ownership (F3)** — sits between this plan and the extraction fix; someone must
   own it or London stays at 0%.
