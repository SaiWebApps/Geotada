# Red Team: Beat & POI Metadata Enrichment

**Date:** 2026-04-11
**Reviewed:** `02-spec.md` and `03-scopes.md` in this folder
**Thinking mode: Adversarial reviewer**

---

## 1. Blockers

### B-1: Upload skill will silently drop enrichment fields

**Problem:** The upload skill (`.claude/commands/upload.md`, Step 3) explicitly lists only 3 fields to send when creating NarrativeBeat nodes:

```
POST /api/nodes/NarrativeBeat with:
- script_body
- duration_sec
- kid_friendly
```

Even if `beats.json` and export files contain all 6 enrichment fields, the upload skill will **ignore them** because its spec doesn't mention them. The enriched data reaches the JSON files but never reaches Neo4j.

**Resolution:** Update `.claude/commands/upload.md` Step 3 to include all enrichment fields in the NarrativeBeat payload, and add `poi_role` to the POI payload in Step 2. Do this as part of Scope 3 implementation.

### B-2: Export-validate field list doesn't include enrichment fields

**Problem:** The export-validate skill (`.claude/commands/export-validate.md`) defines what fields to include on each beat in the export JSON. The 6 enrichment fields are not in the include list OR the strip list. Depending on how the skill is executed, it will either pass them through silently or strip them as unknown fields.

**Resolution:** Update `.claude/commands/export-validate.md` to explicitly include the 6 beat enrichment fields and `poi_role` on POIs. Do this as part of Scope 3 implementation.

### B-3: Scope 3 verification uses a nonexistent API endpoint

**Problem:** The Scope 3 verification command for AC-7 calls `POST /api/v1/graph/query` with arbitrary Cypher. This endpoint does not exist. The graph routes (`src/api/routes/graph.py`) only expose:
- `GET /graph` (full dump)
- `GET /graph/poi/{poi_name}/beats`
- `GET /graph/area/{area_name}/beats`
- `GET /graph/area/{area_name}/contents`

**Resolution:** Two options:
1. **(Recommended)** Verify AC-7 directly against Neo4j via `cypher-shell` or the Neo4j browser, not via the API. This is a one-time verification, not a runtime feature.
2. Create a dedicated `GET /api/v1/graph/entity-overlap` endpoint. But this is scope creep for a verification command.

**Updated verification for AC-7:**
```bash
# Run directly against Neo4j
echo "MATCH (p1:POI)-[:HAS_BEAT]->(b1:NarrativeBeat), (p2:POI)-[:HAS_BEAT]->(b2:NarrativeBeat)
WHERE p1 <> p2 AND any(e IN b1.entities WHERE e IN b2.entities)
RETURN p1.name AS poi1, p2.name AS poi2, [e IN b1.entities WHERE e IN b2.entities] AS shared
LIMIT 20" | cypher-shell -u neo4j -p password
```

---

## 2. Risks

### R-1: Classification consistency across batches (Likelihood: MEDIUM)

The spec says batching by POI produces better results. But classification quality may drift across the ~119 POI batches — the model may be stricter with `hook` labeling early and looser later, or vice versa. Temperature 0 reduces randomness but doesn't guarantee cross-batch consistency for subjective judgments like `emotional_register`.

**Mitigation:** After the full backfill run, do a distribution check:
```python
# Expect roughly: no field should have >70% of beats in a single value
from collections import Counter
for field in ['narrative_function', 'beat_type', 'emotional_register']:
    dist = Counter(b[field] for b in beats)
    print(f"{field}: {dict(dist)}")
```
If any enum value has >70% of beats, the classification prompt is likely under-discriminating and needs tightening.

### R-2: Entity extraction noisiness (Likelihood: MEDIUM)

The spec says extract proper nouns — but the boundary between "entity worth tracking" and "mentioned place name" is fuzzy. A beat about the Louvre might extract `["Louvre", "Philippe-Auguste", "Seine", "Paris"]`. Including `Paris` and `Seine` in every beat dilutes the cross-POI signal — everything shares those.

**Mitigation:** The classification prompt should instruct: "Include people, specific historical events, specific buildings/monuments, and named groups. Exclude the city name itself, common geographic features (Seine, Left Bank), and the POI's own name unless the beat discusses it as a subject rather than a location." Add this guidance to the prompt design in Scope 2.

### R-3: `sensory_anchor` accuracy without ground truth (Likelihood: LOW)

The AI classifier reads `script_body` text and infers whether something is currently visible. It has no ground truth about what's actually there in 2026. Notre-Dame's interior was reopened Dec 2024 but specific features may have changed. Demolished buildings, moved statues, renovated facades — the model can't verify these.

**Mitigation:** The spec already requires a spot-check of 20 `sensory_anchor: true` beats (AC-3). Keep this as a manual human verification step. For Notre-Dame specifically, apply the exterior-visibility rule from the spec's open question #2.

---

## 3. Open questions

### OQ-1: Should Scope 2 produce a classification skill or a one-time script?

The spec says "build and run the classification pass." Two interpretations:
1. Write a reusable Claude Code skill (`.claude/commands/beat-enrich.md`) that can be re-run on new beats
2. Write a one-time Python script that processes `beats.json`

**Recommendation:** Build a reusable skill. The companion scope (pipeline-spatial-precision) needs the same classification logic for future beats. A skill is reusable; a script is throwaway. The one-time backfill run IS the first invocation of the skill.

---

## 4. Codebase conflicts

### C-1: NarrativeBeat CRUD SET loop handles new fields correctly — CONFIRMED

`src/api/crud/nodes.py` line 115: `for key in params: if key != "script_body": set_parts.append(...)`. This loop already handles arbitrary properties. New fields will be SET without CRUD code changes. Confirmed.

### C-2: List property serialization — CONFIRMED

`_serialize_props()` at line 19 handles lists: `elif isinstance(val, list): serialized[key] = val`. The `name_variations: list[str]` on POI is existing precedent. `entities: list[str]` will serialize identically. Confirmed.

### C-3: No conflict with existing NarrativeBeatCreate model

Current model (`src/api/models/nodes.py` line 108-114) has 6 fields. Adding 6 optional fields with defaults is additive — existing code that creates beats without enrichment fields will continue to work.

---

## 5. North star check

**Alignment: GOOD.**

- North star commits to "expensive at ingest, cheap at runtime" — this scope is exactly that pattern.
- North star says "extraction philosophy: constraints belong at the database layer, not the extraction layer." This scope adds properties (not constraints) and validates via prompt (not schema enforcement). Aligned.
- North star says "max 1 beat per taggable lens per POI." Enrichment doesn't touch this constraint. No conflict.
- North star says "content primitive: NarrativeBeat — versioned, lensed, gravity-scored." Adding classification metadata extends the primitive without changing its identity. Aligned.

**One note:** The north star's lens count is slightly outdated (says "16 taggable" but `definitions.py` has 21 universal children). Not caused by this scope, but worth a north star update at debrief.

---

## 6. Scope review

### Scope 1: Schema & Model Updates

- **Boundaries:** Clean. Only touches Pydantic models, no CRUD changes needed.
- **Verification:** Sufficient — tests model instantiation and existing test suite.
- **Risk:** Very low. Purely additive optional fields.

### Scope 2: Classification Backfill

- **Boundaries:** Clean. Reads/writes JSON files only, no database interaction.
- **Verification:** Good — validates all fields, checks computation correctness, includes regression tests.
- **Gap:** Missing a distribution-check verification (see R-1 above). Add:
  ```bash
  # Distribution check — no single value should dominate >70%
  .venv/bin/python -c "
  import json
  from collections import Counter
  beats = json.load(open('data/paris/beats.json'))
  for f in ['narrative_function', 'beat_type', 'emotional_register']:
      dist = Counter(b[f] for b in beats)
      total = len(beats)
      for val, count in dist.most_common():
          pct = count/total*100
          print(f'  {f}: {val} = {count} ({pct:.0f}%)')
      print()
  "
  ```
- **Ordering:** Independent of Scope 1. Can run in parallel. Correct.

### Scope 3: Export, Upload & Verify

- **Boundaries:** Has a hidden dependency — requires updating export-validate AND upload skill specs (B-1, B-2). These updates should be listed as explicit tasks.
- **Verification:** The `POST /api/v1/graph/query` command will fail (B-3). Fix per resolution above.
- **Ordering:** Correctly depends on Scopes 1 and 2.

---

## 7. Best Practices Audit

### A) Project Security & Privacy Constraints (SECURITY_PRIVACY_PRACTICES.md)

| Section | Status | Notes |
|---|---|---|
| 1. Data Classification & Minimization | **Pass** | Enrichment fields are derived metadata about content (not user data). No new PII collected. |
| 2. Consent & Transparency | **N/A** | No user-facing data collection. |
| 3. Authentication & Authorization | **N/A** | No new endpoints. Existing auth unchanged. |
| 4. Secure Session Management | **N/A** | No session changes. |
| 5. Secrets & Credentials | **Pass** | AI classification uses existing API keys. No new secrets introduced. |
| 6. Encryption | **N/A** | No new data transport paths. |
| 7. Logging & Monitoring | **Pass** | No PII in enrichment fields (entities are historical figures, not users). |
| 8. Data Retention & Deletion | **Pass** | Enrichment metadata has same lifecycle as the beat it's attached to. No separate retention needed. |
| 9. Third-Party Risk | **Pass** | Uses existing Anthropic API integration. No new third-party services. |
| 10. Secure Development Lifecycle | **Pass** | Spec-driven, red-teamed, code-reviewed. |
| 11. Input Validation & Output Encoding | **Pass** | Enum values validated in classification prompt. Pydantic models validate on create. No user-supplied input path. |
| 12. Infrastructure & Network Security | **N/A** | No infrastructure changes. |
| 13. Privacy by Design | **Pass** | No user data involved. All enrichment is on editorial content. |
| 14. Incident Response | **N/A** | No new incident vectors. |
| 15. Testing & Verification | **Pass** | Verification commands defined per scope. Existing regression tests preserved. |
| 16. Compliance & Documentation | **Note** | New data fields require data inventory update per line 88 of the security doc. Add `entities`, `sensory_anchor`, `est_spoken_seconds`, `narrative_function`, `beat_type`, `emotional_register`, `poi_role` to the inventory as "derived editorial metadata, no retention limit, no PII." |

### B) Best Practices Library

| Domain | Status | Notes |
|---|---|---|
| Security | **Pass** | No auth, no user input, no new endpoints. Pure content metadata. |
| Privacy | **Pass** | No user data touched. Historical entities are not PII. |
| Performance | **Pass** | Neo4j list properties (`entities`) should be indexed if cross-POI entity queries become a runtime path. For now (one-time verification only), no index needed. Flag for tour builder scope. |
| Accessibility | **N/A** | No UI changes. |
| UX | **N/A** | No user-facing changes. |

---

## Blocker Resolutions Summary

| Blocker | Resolution | Owner |
|---|---|---|
| B-1: Upload skill drops fields | Update `upload.md` Step 3 + Step 2 | Scope 3 implementation |
| B-2: Export-validate missing fields | Update `export-validate.md` include list | Scope 3 implementation |
| B-3: Nonexistent graph/query endpoint | Use `cypher-shell` for AC-7 verification | Update Scope 3 verification commands |
