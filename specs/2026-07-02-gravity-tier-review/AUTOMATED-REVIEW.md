# Paris POI Tier Review — Gravity Rescore Contamination (commit 10e63e5)

> **DO NOT APPLY WITHOUT HUMAN SIGN-OFF.**
> This document PREPARES the human review required by the pipeline guardrail ("tier changes are applied only after human review"). Nothing in this document authorizes a write to `data/paris/poi-raw.json` or Neo4j. An applier session may act on Section 5 only after a human has signed off below.

**Reviewer sign-off:** ______________________ (name / date) — *empty means NOT approved.*

---

## 1. Executive Summary

**Scope.** Commit 10e63e5's gravity rescore overwrote `raw_composite` with cohort-clone values on top of stale reasoning strings. Several POIs were promoted to tier 4/5 purely on guidebook/trends proxies with **zero hard signals** (`official_visitors` null, `google_review_count` null, `s1_used_proxy` and `s2_used_proxy` both true). Tier drives the tour engine's anchor selection, dwell time, and endpoint-pull ranking; Rue Cler's proxy tier-5 + 39 beats already caused the one-stop-tour bug (now guarded at the engine level, but the data is still wrong).

**Verdict counts (clear candidates, each reviewed by an independent researcher and a hostile judge):**

| Verdict | Count |
|---|---|
| DEMOTE (all to tier 3, all high confidence) | **14** |
| KEEP | 0 |
| ESCALATE | 0 |
| Borderline (flagged, not individually reviewed — Section 4) | 21 |

**The contamination signature** (present on all 14): `raw_composite` is a byte-identical clone value shared across a cohort (observed clone values: **100.0, 88.0, 74.6, 71.0, 69.2, 64.2**), sitting directly above a reasoning string that records a *different* composite (mostly `"Composite 55.0: gb=PRESENT"` — itself verbatim-duplicated across 33+ POIs), with both hard signals null and both proxy flags true. In several records `gravity_audit.guidebook_presence` ("UBIQUITOUS") contradicts the original `gravity_signals.guidebook_presence` ("PRESENT"), and the `_poi_role_reasoning` still names the pre-rescore tier.

**Headline corrections to the corpus's own evidence, found by live web research during this review:**

- **Rue Cler has no English Wikipedia article** — enwiki API returns "missing"; only a 5.7 KB French stub exists. The corpus's `wikipedia_depth` proxy promoted it anyway.
- **Palais du Luxembourg is not open "one Saturday/month"** (stale corpus note) — senat.fr confirms access is September Heritage Days only (23,709 visitors for the *entire* two-day 2024 event, greenhouses included) plus senator-arranged groups.
- **Hôtel Matignon's monthly garden opening was annulled under Vigipirate** — access is now ~2 registration-only events/year (~7–10k annual footfall), stricter than the corpus recorded.
- **UNESCO HQ has no walk-in access and publishes no attendance statistics** — confirmed verbatim from unesco.org/en/guided-tours (pre-booked tours only, names + DOB 3 days ahead, official ID).
- **Le Bon Marché's only published visitor figure (3M/yr) is for La Grande Épicerie alone**, and the building is *not* a classified monument historique (local Type A only).
- **Crypte Archéologique has real, retrievable hard data**: 157,120 visitors (Paris Musées 2023), corroborated by FR Wikipedia's 2001–2017 attendance table — *below* the weakest hard-data tier-4 comparable. Recommend backfilling `official_visitors` on apply.
- **Wikimedia pageview spot-checks matched researcher claims to the digit**: Rue Montorgueil 35,285 (below its T3 peer Rue Mouffetard's 49,506); L'Hôtel 9,681 (~5x below tier-3 exemplars).
- **TripAdvisor/Google spot-checks matched exactly**: Champ de Mars #125 of 4,258 (1,428 reviews); La Rotonde 4,640 Google reviews (least-reviewed of the historic-café class whose *stronger* members — Deux Magots, Procope — sit at T3).
- **Wikivoyage negative checks confirmed**: École Militaire has no See entry in the 7th-arr guide; Stravinsky Fountain is omitted from the 4th-arr guide; Fontaine Médicis appears only as one clause inside the Jardin du Luxembourg listing.

**Two second-order findings for follow-up (not part of this apply batch):** (a) the `"Composite 55.0: gb=PRESENT"` reasoning string is stale boilerplate spanning tiers 1–5 corpus-wide, so it is *not* itself a trustworthy score — it is evidence the clone values are baseless, not a replacement value; (b) **64.2** (the exact T4 floor) is stamped on 35 POIs straddling the T3/T4 boundary and warrants a dedicated sweep (the 21 borderline POIs in Section 4 partially overlap this cohort).

---

## 2. Verdict Table

| POI | Tier: current → verdict | Confidence | One-line rationale |
|---|---|---|---|
| Rue Cler | 5 → **3** | high | T5 rests on clone composite 74.6 over honest "Composite 55.0"; no EN Wikipedia (live-checked); mid-T3 beside Mouffetard/Buci market-street peers. |
| Champ de Mars | 5 → **3** | high | Clone composite 100.0 over "55.0"; zero hard signals; TA #125/4,258 live-verified; all real T4/T5 parks earned it with 22k–122k reviews; footfall is borrowed Eiffel gravity. |
| Palais du Luxembourg | 5 → **3** | high | Clone 88.0 (shared by 9 other POIs) over "55.0"; senat.fr confirms near-zero public access; garden's fame already a separate T5 POI; lands beside functional twin Assemblée Nationale (T3). |
| Le Bon Marché | 5 → **3** | high | Clone 88.0 over "55.0"; no published store attendance (3M figure is Grande Épicerie only); not a classified MH; T5 store comparable Samaritaine has 5M published visitors. |
| École Militaire | 4 → **3** | high | Clone 71.0 (shared with UNESCO HQ, Matignon) with zero hard signals; no Wikivoyage See entry (live-checked); closed military campus; access-profile twin of T3 Assemblée Nationale. |
| Hôtel Matignon | 4 → **3** | high | Clone 71.0 over "55.0"; garden openings annulled (Vigipirate, live-checked), ~7–10k/yr footfall; name-fame already priced into prior T3 walk_by_only role. |
| UNESCO Headquarters Paris | 4 → **3** | high | Clone 71.0 (shared by ~35 all-null T4 POIs); pre-booked tours only, no walk-ins, no published attendance (live-checked); own record says walk_by_only / "Tier 2". |
| Fontaine Médicis | 4 → **3** | high | Clone 69.2 over "55.0"; fame accrues to T5 parent Luxembourg Gardens (97,251 reviews); the three fountains sharing its exact reasoning string are all T3. |
| La Rotonde | 4 → **3** | high | Clone 69.2 over "55.0"; 4,640 Google reviews (live-verified) — least-reviewed of a café class whose stronger members (Deux Magots 10.5k, Procope 19.8k) sit at T3. |
| Rue Montorgueil | 4 → **3** | high | Clone 64.2 (shared by 35 POIs); pageviews 35,285 < T3 peer Mouffetard's 49,506 (live-verified to the digit); role reasoning still says "Tier 3 named street". |
| Stravinsky Fountain | 4 → **3** | high | Clone 64.2; omitted from EN Wikivoyage 4th-arr guide (live-checked); walk-past fame, free 5-min dwell; own prior_reasoning already describes a T3 landmark. |
| Crypte Archéologique de l'Île de la Cité | 4 → **3** | high | Boundary-clone 64.2 (exact T4 floor); real data exists — 157,120 visitors 2023, below weakest hard-data T4 (Victor Hugo 260k); attendance is Notre-Dame spillover. Backfill official_visitors on apply. |
| Hôtel de la Monnaie | 4 → **3** | high | Clone 64.2 vs reasoning "Composite 65.7" mismatch; FR wiki visiteurs field empty (live-checked); museum closed 2010–17, no mainstream guidebook footprint; role reasoning says T3. |
| L'Hôtel Paris | 4 → **3** | high | Clone 64.2 vs "65.7"; 9,681 EN pageviews 2025 (live-verified, ~5x below T3 exemplars); 20-room private hotel — hard signals structurally unattainable; Wilde fame is beat content. |

---

## 3. Per-POI Rationales (researcher + hostile judge, verbatim)

### 3.1 Rue Cler — DEMOTE 5 → 3 (high)
The T5 rests solely on the cohort-clone raw_composite 74.6, which contradicts the record's own reasoning string ("Composite 55.0: gb=PRESENT" — verbatim-duplicated on Marché Saint-Germain and Le Bon Marché, confirming the clone bug), was computed with both proxy flags true and both hard signals null, and would rank a market street above Les Invalides (70.62, 32,189 reviews, extensive wiki). Live spot-check confirmed the research's strongest claim: enwiki API returns "missing" for Rue Cler; only a 5.7KB French stub exists. Its genuine Rick-Steves-driven fame is already captured by the guidebook signal and supports at most T4; the internally consistent composite 55.0 lands mid-T3, exactly between functional peers Rue Mouffetard (49.2, T3) and Rue de Buci Market (57.6, T3), with Marché Bastille (51.0, T3) alongside — no outlier at T3. The corpus's own _poi_role_reasoning still says "Tier 3". No independent signal supports T5; signals converge rather than conflict.

### 3.2 Champ de Mars — DEMOTE 5 → 3 (high)
Research verified, not overreached: live spot-check of the load-bearing TripAdvisor signal matched exactly (#125 of 4,258, 4.1/5, 1,428 reviews). Corpus record confirms the cohort-clone bug (raw_composite 100.0/T5 over honest recorded reasoning "Composite 55.0: gb=PRESENT", official_visitors=null, google_review_count=null, both proxies true). Researcher's one error — calling Pont Alexandre III corpus T4 when it is corpus T3 — strengthens the demotion: a T3 comparable with 29,486 Google reviews and TA #16 dwarfs Champ de Mars on every hard signal. Other direction fails: all corpus parks at T4/T5 earned it with hard signals (Luxembourg 97k, Tuileries 95k, Trocadero 122k Google reviews; Monceau 22k = T4); Champ de Mars has none, its wiki is measured-moderate (10.7 kB), guidebook honestly PRESENT, and its footfall is borrowed from the adjacent hard-signal T5 Eiffel Tower (24 beats) and T5 Trocadero — a third T5 on the same lawn recreates the anchor double-counting behind the Rue Cler one-stop-tour bug. T3 is no outlier: honest composite 55.0 sits beside Musée Rodin (54.7), Buttes-Chaumont (54.4, the closest structural comparable), and Pont Alexandre III (61.9); its 10 beats carry the historical narrative regardless of tier.

### 3.3 Palais du Luxembourg — DEMOTE 5 → 3 (high)
Every load-bearing claim verified. Corpus (data/paris/poi-raw.json): raw_composite 88.0 contradicts the POI's own recorded reasoning "Composite 55.0: gb=PRESENT"; official_visitors and google_review_count both null; s1_used_proxy and s2_used_proxy both true; _poi_role_reasoning still says "Tier 4" under the tier-5 stamp; and 88.0 is a verbatim cohort-clone value shared by 9 other POIs (Institut de France, Le Bon Marché, Rue Saint-Honoré, Rue Lepic, Pont d'Iéna, Opéra Bastille, Colonne de Juillet, Bourse de Commerce, Arc de Triomphe du Carrousel) in a batch with 82 tier-4/5 POIs carrying zero hard signals. Live spot-check of senat.fr/visite confirmed the researcher's strongest hard signal exactly: no regular individual public visits — only September Heritage Days (23,709 visitors for the ENTIRE 2024 two-day event, including the garden greenhouses) plus senator-arranged groups; access is stricter than the corpus's stale "one Saturday/month" note. Other direction considered: the palace's genuine fame is as the backdrop of the Jardin du Luxembourg, which is already a separate tier-5 corpus POI (97,251 Google reviews) — tier 5 on the palace double-counts that gravity onto a building tourists cannot enter. Comparables: corpus tier bands are T3=42.75–64.2, T4=64.2–71.0, T5=71.0+; the recorded 55.0 composite sits mid-T3, next to the functional twin Assemblée Nationale (tier 3, 48.0, same restricted-access parliament profile, same wiki=extensive), Musée Rodin (tier 3, 15k reviews) and Pont Alexandre III (tier 3, 29k reviews), while tier-4 Panthéon/Invalides carry 32–47k reviews vs the palace's ~1.2k on TripAdvisor. Every hard signal points to 3; only clone/proxy artifacts point to 5. No genuine signal conflict, so no human escalation needed beyond the standard review this workflow feeds.

### 3.4 Le Bon Marché — DEMOTE 5 → 3 (high)
Research verified with no overreach. Corpus record confirms the 10e63e5 contamination signature: raw_composite 88.0 contradicts its own reasoning string 'Composite 55.0: gb=PRESENT' (a clone string shared by 33 POIs including Rue Cler, the known bug); both hard signals null with s1/s2_used_proxy=true; gravity_audit 'UBIQUITOUS' contradicts gravity_signals 'PRESENT'; stale 'Tier 4' role stamp. Independent spot-check at fr.wikipedia confirmed the decisive negative claim: infobox has no attendance figure for the store, the only published number (3M/yr) is for La Grande Épicerie alone, and the building is NOT a classified monument historique (local Type A only). Counter-direction fails: genuine historical fame (first modern department store, Zola) is already priced into the honest composite 55.0 via wiki=extensive and trends=high; guidebook presence is shopping-section (Rick Steves shopping article, Time Out 'Shopping | Department stores'), and the surviving T5 store comparable (Samaritaine) has 5M published visitors. Comparables: recomputed uncontaminated corpus bands give T3=42.8–64.2 (median 57.6), T4 floor 64.2, T5 floor 71.0; 55.0 lands mid-T3, bracketed by Musée Rodin (50.4, T3, 15k reviews) and Pont Alexandre III (61.9, T3, 29k reviews), both with more hard signal than Le Bon Marché. At T5 it would be the only zero-hard-signal member besides fellow suspect Galeries Lafayette; at T3 it is not an outlier. Demote 5 → 3.

### 3.5 École Militaire — DEMOTE 4 → 3 (high)
Research verified, not overreached. Corpus record confirms tier 4 rests on a fabricated cohort-clone raw_composite=71.0 (identical value, reasoning string 'Composite 55.0: gb=PRESENT', and rescored_at shared with UNESCO HQ and Hotel Matignon, all null official_visitors and null google_review_count, s1/s2 proxies) — while genuinely tier-4/5 POIs at rc~71 (Les Invalides 70.62, Sainte-Chapelle 71.83) carry 32k–35k Google reviews. One refinement: the '55.0' reasoning string is stale boilerplate spanning tiers 1–5 corpus-wide, so it is not itself an honest score — but that only deepens the finding that rc=71.0 has zero evidentiary basis. Spot-check performed: Wikivoyage 7th-arr guide fetched directly this run — École Militaire has NO See entry (Metro stop + photo caption only) while Eiffel Tower/Invalides/Rodin get full entries, exactly as the researcher claimed; TripAdvisor count remained unretrievable via three engines, corroborating the researcher's stated constraint, and a T4-rescuing count (~30k+) is implausible for a building tourists cannot enter outside Heritage Days. Other direction considered: its real fame signals (Eiffel sightline terminus, Napoleon, extensive Wikipedia, Metro-station name recognition) are visibility/story/name-collision signals, not attraction gravity — the sightline value already lives in Champ de Mars and stories live in beats. Comparables are decisive: keeping T4 ranks a closed military campus above Musée Rodin (15,078 reviews), Carnavalet, Cluny, and Saint-Sulpice (all T3); at T3 it sits exactly beside Assemblée Nationale (T3, grand limited-access government building, null/null hard signals), the corpus's cleanest access-profile twin. Demote to tier 3.

### 3.6 Hôtel Matignon — DEMOTE 4 → 3 (high)
The T4 tier rests solely on raw_composite 71.0, a cohort-clone artifact of commit 10e63e5 (byte-identical to Conciergerie's 71.0) sitting beside the record's own reasoning string 'Composite 55.0: gb=PRESENT' — squarely T3 band. Zero hard signals: official_visitors null, google_review_count null, s1/s2 both proxy. Spot-check confirmed the researcher's strongest claim via FR Wikipedia: the monthly garden opening was annulled under Vigipirate; access is now ~2 registration-only events/year (~7–10k annual footfall), even more restricted than the corpus recorded. Counter-direction considered: high name fame (PM-office metonymy, extensive EN+FR Wikipedia) is real but already priced into the prior T3 ('not open to public, iconic only by name') and its walk_by_only role; fame without visitability, reviews, or guidebook headline status does not clear a T4 anchor bar. Comparables: at T4 Matignon is a stark outlier, outranking Musée Rodin (T3, ~700k visitors/yr, 15,078 reviews, composite 54.7) two blocks away and sitting beside Invalides (T4, 32,189 reviews, composite 74.5); at T3 its true composite 55.0 lands exactly with Assemblée Nationale (48.0) and Musée Rodin — a more consistent placement. Evidence is decisive and mutually corroborating; no genuine signal conflict warrants escalation.

### 3.7 UNESCO Headquarters Paris — DEMOTE 4 → 3 (high)
Evidence is decisive on all three tests. (1) Research supports demotion and is corroborated by the corpus itself: raw_composite 71.0 sits over a reasoning string reading "Composite 55.0: gb=PRESENT", both s1/s2 are proxies, official_visitors and google_review_count are null, and 71.0 is a cohort-clone value shared by ~35 tier-4 POIs with all-null hard signals (École Militaire, Hôtel Matignon, Palais de Justice...) — the exact 10e63e5 bug signature. Spot-checked the strongest external claim against unesco.org/en/guided-tours: access is strictly pre-booked guided tours (names + dates of birth max 3 days before, official ID, no on-site tickets, no walk-ins), and no attendance statistics are published — confirmed verbatim. (2) Other direction: UNESCO's fame is organizational/architectural, not visited-attraction gravity; with no walk-ins, ~72 aggregator reviews, and absence from top-attraction rankings it cannot function as a tier-4 anchor alongside Invalides (32,189 reviews), Panthéon (46,541), or Pompidou (55,770). The record's own poi_role is walk_by_only with reasoning "Tier 2 — minor landmark". (3) Comparables: tier 3 is a near-perfect fit next to Assemblée Nationale (T3, composite 48.0/52.7 — famous restricted-access institutional building, extensive Wikipedia, no hard signals) and below Musée Rodin (T3, 54.7, 15k reviews); the honest composite 55.0 lands squarely in the T3 band, making T3 conservative rather than an outlier. Batch note: École Militaire (T4, clone 71.0) and Institut de France (T5, 88.0, walk_by_only) show the same clone signature, and 64.2 appears to be a second clone value worth sweeping.

### 3.8 Fontaine Médicis — DEMOTE 4 → 3 (high)
Research verified with no overreach: corpus confirms null official_visitors, null google_review_count, s1/s2_used_proxy=true, and honest reasoning "Composite 55.0: gb=PRESENT" beneath a cloned raw_composite 69.2 shared byte-identical with La Rotonde/Rue des Francs-Bourgeois/Rue des Rosiers (the 10e63e5 clone cohort). Independent spot-check of the strongest claim (Wikivoyage 6th arr.) returned the researcher's quoted sentence verbatim — one clause inside the garden listing, no standalone entry. The only pro-T4 signal, cached gb=UBIQUITOUS, is contradicted by the original gravity_signals (PRESENT), the reasoning string (gb=PRESENT), and the audit's own evidence ("covered... as part of Jardin du Luxembourg"); the fountain's real fame accrues to its T5 parent (Luxembourg Gardens, composite 88.2, 97,251 reviews). Comparables are decisive: the three fountains with the identical "Composite 55.0: gb=PRESENT" reasoning (Quatre-Parties-du-Monde, Quatre Saisons, Fontaine de Mars) are all T3; T3 holds Musée Rodin (15,078 reviews, composite 54.7) and Pont Alexandre III (29,486 reviews); T4 hard-signal peers are Panthéon (46,541 reviews), Centre Pompidou (3.2M visitors), Catacombs (550K), Père Lachaise (3.5M) — a free, unticketed garden sub-feature with zero hard signals is an outlier there and consistent at T3. The record's own _poi_role_reasoning already says "Tier 3 discrete building/monument". Demotion to 3 restores the honest composite band and the fountain ladder (Saint-Michel T5 > Stravinsky T4 > Médicis T3 > Innocents T2). *(Note: the fountain-ladder aside predates the Stravinsky verdict below, which itself demotes Stravinsky to T3 — no conflict; both land at their honest bands.)*

### 3.9 La Rotonde — DEMOTE 4 → 3 (high)
Research verified without overreach: spot-check of the load-bearing review-count claim (restaurantguru.com) matched exactly — Google 4.3/5 with 4,640 reviews, TripAdvisor 2,155, Foursquare 297. Counter-direction checked: La Rotonde's real fame (Picasso/Modigliani/Lenin lore, 13 wiki languages, Macron 2017 dinner) is exactly the fame class the corpus prices at T3 — Les Deux Magots (10,544 reviews, extensive wiki, UBIQUITOUS guidebooks) and Le Procope (19,832 reviews, UBIQUITOUS) are more famous on every axis and both sit at T3; no visitor stats exist or ever will for a private brasserie, so the nulls hide nothing. Comparables: at T4 it is the least-reviewed member of the historic-café class (4,640 vs Lipp 7,537 / Deux Magots 10,544 / Procope 19,832) a full tier above all hard-data peers; at T3 it slots naturally below them (the only same-class T4, Café de Flore, is itself a null-signal proxy-scored member of the same suspect cohort and cannot legitimize it). The T4 is a documented clone artifact: raw_composite 69.2 contradicts the entry's own reasoning string 'Composite 55.0: gb=PRESENT', and gravity_audit gb='UBIQUITOUS' contradicts gravity_signals gb='PRESENT' (researcher confirmed no Michelin entry; guidebook presence is eat-listing level). 55.0 sits squarely in the observed T3 band (62.86→T3, 64.2→T4). Demotion to T3 is decisive.

### 3.10 Rue Montorgueil — DEMOTE 4 → 3 (high)
Every checkable research claim verified against the corpus and one live spot-check. Corpus: raw_composite=64.2 is a degenerate clone value shared by 35 POIs (researcher undercounted at 6 — the error strengthens the demotion case), with identical proxy profile trends=moderate/wiki=moderate/gb=COMMON; official_visitors and google_review_count are both null; s1/s2_used_proxy both true; signal_source=zerogap_backfill. The corpus's own _poi_role_reasoning still says 'Tier 3 named street' — a fossil showing T4 came from the buggy proxy rescore, not evidence. Spot-check (Wikimedia REST API, 2025 user pageviews): Montorgueil en+fr = 35,285, matching the researcher's ~35.3k exactly, and BELOW its closest T3 peer Rue Mouffetard at 49,506 (~49.5k claimed, also exact). Researcher's one mislabel — calling Pont Alexandre III a T4 exemplar when the corpus holds it at T3 with 29,486 real reviews — cuts further toward demotion. Comparables: genuine T4 streets (Rue des Rosiers, Rue des Francs-Bourgeois) hold 69.2 with UBIQUITOUS guidebook presence; Montorgueil's 64.2/COMMON profile is byte-identical to T3 streets Rue de Lappe and Rue Saint-Antoine. Counter-direction examined: Monet painting is real cachet but not headline status; Stohrer (the street's strongest asset) is already a separate tier-1 POI; EN Wikipedia is a 2.4k-byte stub; no Rick Steves feature or Lonely Planet attraction page. At T3 it sits at the top of its exact class (Mouffetard/Lappe/Saint-Antoine/Buci); at T4 it is an outlier sustained only by the clone artifact. Evidence is decisive.

### 3.11 Stravinsky Fountain — DEMOTE 4 → 3 (high)
Research verified on every checkable claim; corpus check strengthened it: raw_composite 64.2 is a cohort-clone stamp shared verbatim by 35 POIs (incl. Café de Flore, Parc Montsouris), with s1/s2 proxies true, null hard signals, and an internal 64.2-vs-65.7 inconsistency. Its cloned score outranks hard-signal tier-3 Pont Alexandre III (61.92, 29,486 reviews) while tier-4 exemplars (Pompidou 68.98/3.2M visitors; Invalides 70.62/32,189 reviews) are plainly a different class. Web spot-check confirmed the falsifiable negative claim: English Wikivoyage 4th-arr guide omits the fountain while listing Tour St Jacques and Hôtel de Sully. Counter-direction considered: genuine fame exists (12-language Wikipedia, EUR 2M 2023 restoration) but it is walk-past tier-3 fame — absent from Rick Steves and both Wikivoyage guides, free 5-min dwell. At tier 3 it slots coherently between Fontaine de Mars (57.6) and Pont Alexandre III (61.92), well above tier-2 fountains (Innocents 41.2). The record's own _poi_role_reasoning and prior_reasoning already describe a tier-3 landmark. No conflicting signals; the only pro-tier-4 evidence is the demonstrably meaningless proxy stamp.

### 3.12 Crypte Archéologique de l'Île de la Cité — DEMOTE 4 → 3 (high)
Tier 4 rests entirely on a boundary-clone artifact: raw_composite stamped exactly 64.2 (the T4 floor) by zerogap_backfill with both signals proxied and null official_visitors/google_review_count (verified in poi-raw.json line 9502; 'Jardins du Musée de Cluny' carries the identical 64.2 at tier 3). The researcher's hard data survives hostile spot-checking: FR Wikipedia's attendance table (independently fetched) shows 89.5k–223k/yr across 2001–2017, corroborating the Paris Musées 2023 figure of 157,120 — below the weakest hard-data tier-4 comparable (Musée Victor Hugo, 260k, composite 64.82), ~1/4 of Catacombs (550k corpus, tier 4), and below tier-3 museums Carnavalet (1.06M) and Rodin (~700k). The reverse case fails: no standalone EN Wikipedia article, guidebook presence is a Notre-Dame add-on only, and FR Wikipedia itself describes attendance as 'essentially spontaneous, entrance poorly signposted' — spillover from Notre-Dame (a separate anchor POI), not destination pull. The corpus's own _poi_role_reasoning ('Tier 3 discrete building/monument') and prior_reasoning already classed it tier 3 before the proxy promotion. At tier 3 it is not an outlier in either direction. **Apply-time extra: backfill official_visitors=157120 (Paris Musées 2023 frequentation communiqué).**

### 3.13 Hôtel de la Monnaie — DEMOTE 4 → 3 (high)
All corpus claims independently re-verified in poi-raw.json: zero hard signals (null visitors, null reviews, both proxy flags), raw_composite 64.2 vs reasoning-string 'Composite 65.7' mismatch, stale prior_reasoning, and role reasoning that itself says 'Tier 3 discrete building/monument'. The 64.2 value is a clone stamped on 35 POIs straddling the T3/T4 boundary (T4 range 64.2–71.0); identical-composite peers (Musée du Luxembourg, Musée Delacroix) already sit at T3. Spot-check confirmed the FR Wikipedia museum infobox 'visiteurs' field is empty in raw wikitext with no attendance figure anywhere — no published visitor data exists. Fame-despite-missing-stats fails: museum closed 2010–2017, small specialist collection, no mainstream guidebook footprint found (Rick Steves/Fodor's/Lonely Planet all absent; Michelin unverifiable but non-dispositive). Comparables are decisive: T4 peers Invalides (70.6, 32k reviews) and Panthéon (68.0, 46k reviews) dwarf it; T3 peers Pont Alexandre III (61.9, 29k reviews) and Musée Rodin (50.4, 15k reviews, ~700k visitors) are stronger than Monnaie on every hard signal. T3 fits its real profile: monumental Seine-front walk-past landmark with a niche museum. Signals do not genuinely conflict — the only pro-T4 evidence is the provably artifactual clone composite.

### 3.14 L'Hôtel Paris — DEMOTE 4 → 3 (high)
Every corpus claim verified byte-for-byte in data/paris/poi-raw.json: raw_composite 64.2 contradicts its own reasoning string ('Composite 65.7'), signal_source=zerogap_backfill, both proxies used, hard signals null (structurally unattainable for a 20-room private hotel). The 64.2 stamp is shared by 35 POIs split 14/21 across tiers 4 and 3 — zero discriminating information; tier 4 rests entirely on this clone. Spot-checked the researcher's strongest external claim via the Wikimedia pageviews API: EN 'L'Hôtel' drew exactly 9,681 views in 2025, matching the research to the digit and sitting ~5x below tier-3 exemplars. No countervailing signal supports tier 4: the Wilde death site is beat/story content on a tourist-inaccessible facade, and guidebook presence is as lodging plus literary walk-past, never a headline sight. Tier 3 is fully consistent with comparables (27 Rue de Fleurus, Musée Delacroix, Les Deux Magots/Le Procope which hold tier 3 with 10k–20k reviews L'Hôtel lacks) and with the POI's own _poi_role_reasoning ('Tier 3 discrete building/monument, default stop').

---

## 4. Borderline List (flagged, NOT individually reviewed — no action this batch)

All 21 share the pattern: tier held on proxies only (visitors/reviews null, s1+s2 proxy), tier **unchanged since b4c4155** (so not a 10e63e5 rescore artifact), flagged for a role-stamp/tier contradiction. Proposed = current pending a future review pass. Extraction notes inline.

| POI | Tier (current=proposed) | Beats | Notes |
|---|---|---|---|
| Fontaine Saint-Michel | 5 | 1 | Largest role/tier gap in corpus (T5 stop vs "Tier 2 walk_by_only" role); wiki only moderate; reasoning composite 81.6 = T5 band. |
| Institut de France | 5 | 5 | Role says "Tier 2 walk_by_only"; reasoning composite 90.9 = T5 band. Also carries the 88.0 clone value (see UNESCO batch note) — highest-priority borderline. |
| Val-de-Grâce | 4 | 12 | Role says "Tier 2 walk_by_only"; 12 beats give real dwell weight either way. |
| Théâtre de l'Odéon | 4 | 4 | Role says "Tier 2 walk_by_only". |
| École des Beaux-Arts | 4 | 3 | Role says "Tier 2 walk_by_only". |
| Collège de France | 4 | 1 | Role says "Tier 2 walk_by_only"; only 1 beat. |
| Institut du Monde Arabe | 4 | 2 | Role says "Tier 2 walk_by_only" — BUT ticketed museum with published attendance; **hard signals retrievable, cheapest borderline to resolve.** |
| Saint-Germain-l'Auxerrois | 4 | 8 | Stale "Tier 3" role stamp; reasoning composite 75.0 = T5 band. |
| Église Saint-Gervais-Saint-Protais | 4 | 15 | Role says "Tier 3". **Highest beat count in group — demotion would materially change dwell.** |
| Rue des Rosiers | 4 | 12 | Role says "Tier 3, large footprint area"; wiki only moderate. **Same street-with-many-beats shape as Rue Cler — check endpoint-pull effects.** |
| Priory of Saint-Martin-des-Champs | 4 | 8 | Role says "Tier 3". |
| Hôtel-Dieu | 4 | 8 | Role says "Tier 3"; a working hospital with no visitor-attraction hard signals. |
| Saint-Paul-Saint-Louis | 4 | 5 | Role says "Tier 3". |
| Hôtel Le Meurice | 4 | 4 | Role says "Tier 3"; luxury hotel — guidebook presence but no attraction hard signals. |
| Porte Saint-Martin | 4 | 4 | Role says "Tier 3". |
| Hôtel de Sens | 4 | 4 | Role says "Tier 3". |
| Saint-Louis-en-l'Île Church | 4 | 3 | Role says "Tier 3". |
| Place des Victoires | 4 | 2 | Role says "Tier 3". |
| Comédie-Française | 4 | 2 | Role says "Tier 3". |
| La Tour d'Argent | 4 | 1 | Role says "Tier 3"; a restaurant — guidebook fame, no attraction signals, 1 beat. |
| Grands Boulevards | 4 | 1 | Role says "Tier 3, large footprint area"; large-area POI with 1 beat. |

**Suggested borderline triage order for a future pass:** (1) Institut du Monde Arabe (hard data retrievable), (2) Institut de France (88.0 clone + T5), (3) Saint-Gervais-Saint-Protais and Rue des Rosiers (beat weight / Rue-Cler shape), then the rest.

---

## 5. Apply Plan (mechanical, for the applier session — ONLY after Section 6 sign-off)

### 5.1 Field paths (verified against `data/paris/poi-raw.json` structure this run)

Per demoted POI, update exactly these fields:

1. `importance_tier` (top-level) → **3**
2. `_pipeline.gravity_audit.assigned_gravity` → **3**
3. `_pipeline.gravity_audit.formula_version` → append suffix **`_manual_review_2026_07_02`** to the existing value (do not replace the existing string)
4. Add `_pipeline.gravity_audit.manual_review_note` (new field) → the per-POI note in the table below
5. **Do NOT rewrite `raw_composite`.** The clone values are contaminated, but the `"Composite 55.0"` reasoning strings are themselves stale boilerplate (per the École Militaire finding) and are not a trustworthy replacement. Leave `raw_composite` as-is; the note field documents the contamination. A future clean rescore with hard signals supersedes it.
6. **Crypte Archéologique only:** additionally set `_pipeline.gravity_audit.official_visitors` → **157120** and include the source in its note.

### 5.2 Recommended apply order

Order by engine impact (anchor selection + endpoint pull), T5 demotions first. Apply as **one atomic commit** after the whole batch is edited, with `make test` green (the tier-guard and tour-engine tests must pass against the new tiers).

| # | POI | importance_tier / assigned_gravity | manual_review_note (verbatim) |
|---|---|---|---|
| 1 | Rue Cler | 5 → 3 | "Demoted 5→3, manual review 2026-07-02: raw_composite 74.6 was a 10e63e5 cohort-clone over reasoning 'Composite 55.0'; zero hard signals (visitors/reviews null, s1+s2 proxy); no EN Wikipedia (live-checked); T3 beside market-street peers Mouffetard/Buci. Caused the one-stop-tour bug." |
| 2 | Champ de Mars | 5 → 3 | "Demoted 5→3, manual review 2026-07-02: raw_composite 100.0 clone over 'Composite 55.0'; zero hard signals; TA #125/4,258 with 1,428 reviews (live-verified); footfall is adjacent Eiffel/Trocadéro gravity; T4/T5 parks all have 22k–122k reviews." |
| 3 | Palais du Luxembourg | 5 → 3 | "Demoted 5→3, manual review 2026-07-02: raw_composite 88.0 clone (shared by 9 POIs) over 'Composite 55.0'; zero hard signals; senat.fr confirms Heritage-Days-only access (23,709 for entire 2024 event); garden fame already on separate T5 Jardin du Luxembourg POI." |
| 4 | Le Bon Marché | 5 → 3 | "Demoted 5→3, manual review 2026-07-02: raw_composite 88.0 clone over 'Composite 55.0'; zero hard signals; no published store attendance (3M is Grande Épicerie only, live-checked); not a classified MH; T5 store peer Samaritaine has 5M published visitors." |
| 5 | École Militaire | 4 → 3 | "Demoted 4→3, manual review 2026-07-02: raw_composite 71.0 clone (shared with UNESCO HQ, Matignon) with zero hard signals; no Wikivoyage See entry (live-checked); closed military campus; access twin of T3 Assemblée Nationale." |
| 6 | Hôtel Matignon | 4 → 3 | "Demoted 4→3, manual review 2026-07-02: raw_composite 71.0 clone over 'Composite 55.0'; zero hard signals; garden openings annulled under Vigipirate, ~2 events/yr (live-checked); name fame already priced into walk_by_only role." |
| 7 | UNESCO Headquarters Paris | 4 → 3 | "Demoted 4→3, manual review 2026-07-02: raw_composite 71.0 clone (~35-POI cohort); zero hard signals; pre-booked tours only, no walk-ins, no published attendance (unesco.org live-checked); own role says walk_by_only." |
| 8 | Fontaine Médicis | 4 → 3 | "Demoted 4→3, manual review 2026-07-02: raw_composite 69.2 clone over 'Composite 55.0'; zero hard signals; guidebook coverage is one clause in Jardin du Luxembourg listings (live-checked); fame accrues to T5 parent garden; sibling fountains with identical reasoning are all T3." |
| 9 | La Rotonde | 4 → 3 | "Demoted 4→3, manual review 2026-07-02: raw_composite 69.2 clone over 'Composite 55.0'; 4,640 Google reviews (live-verified) — least-reviewed of the historic-café class whose stronger members (Deux Magots, Procope) sit T3; audit gb=UBIQUITOUS contradicts signals gb=PRESENT." |
| 10 | Rue Montorgueil | 4 → 3 | "Demoted 4→3, manual review 2026-07-02: raw_composite 64.2 clone (35-POI cohort, zerogap_backfill); zero hard signals; pageviews 35,285 < T3 peer Mouffetard 49,506 (live-verified); role reasoning still 'Tier 3 named street'; profile byte-identical to T3 streets Lappe/Saint-Antoine." |
| 11 | Stravinsky Fountain | 4 → 3 | "Demoted 4→3, manual review 2026-07-02: raw_composite 64.2 clone; zero hard signals; omitted from EN Wikivoyage 4th-arr guide (live-checked); walk-past fame, free 5-min dwell; own prior_reasoning describes a T3 landmark." |
| 12 | Crypte Archéologique de l'Île de la Cité | 4 → 3 | "Demoted 4→3, manual review 2026-07-02: raw_composite 64.2 boundary-clone (zerogap_backfill); real attendance 157,120 (Paris Musées 2023, corroborated by FR Wikipedia 2001–2017 table) is below weakest hard-data T4 (Victor Hugo 260k); attendance is Notre-Dame spillover. official_visitors backfilled 157120 (source: Paris Musées 2023 frequentation communiqué)." |
| 13 | Hôtel de la Monnaie | 4 → 3 | "Demoted 4→3, manual review 2026-07-02: raw_composite 64.2 clone vs reasoning 'Composite 65.7'; zero hard signals; FR Wikipedia visiteurs field empty (live-checked); museum closed 2010–17, no mainstream guidebook footprint; role reasoning says Tier 3." |
| 14 | L'Hôtel Paris | 4 → 3 | "Demoted 4→3, manual review 2026-07-02: raw_composite 64.2 clone vs reasoning 'Composite 65.7' (zerogap_backfill); hard signals structurally unattainable for a 20-room private hotel; EN pageviews 9,681/2025 (live-verified), ~5x below T3 exemplars; Wilde fame is beat content; role reasoning says Tier 3." |

### 5.3 Applier checklist

- [ ] Human sign-off present in Section 6 (name + date) — **hard stop if empty**
- [ ] Edit all 14 records in `data/paris/poi-raw.json` per 5.1/5.2 (poi-raw.json is the canonical POI source of truth)
- [ ] Crypte: `official_visitors` backfilled to 157120
- [ ] No other fields touched (diff review: exactly 4 fields per POI, 5 for Crypte)
- [ ] Re-export / re-upload path per standard pipeline (export-validate → upload) so Neo4j reflects new tiers
- [ ] `make test` full bar green (tour-engine anchor/endpoint tests against new tiers)
- [ ] Spot-build one tour through the Rue Cler / Champ de Mars corridor and confirm multi-stop output
- [ ] Borderline list (Section 4) left untouched — separate future pass
- [ ] Commit message references commit 10e63e5, this review doc, and lists all 14 POIs

---

## 6. ⛔ DO NOT APPLY WITHOUT HUMAN SIGN-OFF ⛔

**No tier in this document may be written to `data/paris/poi-raw.json`, to any export, or to Neo4j until a human has reviewed Sections 1–5 and signed below.** This is the pipeline guardrail — tier changes are applied only after human review. The automated researcher + hostile-judge pipeline that produced these verdicts is evidence-gathering, not authorization.

- **Approved POIs (list names or "ALL 14"):** ______________________
- **Rejected/held POIs:** ______________________
- **Signed:** ______________________ **Date:** ______________
