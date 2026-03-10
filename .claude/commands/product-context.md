# Travlr — Product Context Reference

This file captures the stable product knowledge that informs all 5 PM modes. It is derived from the project documents and resolved technical decisions. Load this when you need deep context beyond what SKILL.md provides.

## North Star

Travlr is a multi-city audio tour platform that transforms books and travel guides into GPS-triggered, narrative-driven walking experiences — making every city feel like it has a local storyteller in your pocket.

## 12-Month Bets

1. **Prove the Book-to-Street pipeline:** Ship Editorial Workbench + AI ingestion engine → 100 live GPS-tagged story beats for a single city, passing the Boredom Test and 3-minute editorial efficiency target.
2. **Deliver the Wanderer experience end-to-end:** Mobile app with automatic narrative beat triggers within 10m of each POI, using Golden Ratio algorithm (20% Anchors / 80% Flavour).
3. **Scale to multi-city:** Neo4j graph schema + ElevenLabs audio pipeline + S3/Postgres storage to onboard cities without rebuilding the content pipeline.

## Two Core Product Modes

- **The Planner (Structured Discovery):** Trip → ItineraryItems → POIs → Beats → Lenses
- **The Wanderer (Spontaneous Exploration):** Profile → preferred Lenses → matching Beats → nearby POIs + spatial filter

## Scoreboard (MVP Metrics)

| Metric | Target |
|--------|--------|
| Synthesis Density | AI extracts ≥70% of viable POIs from source text |
| Editorial Efficiency | Editor verifies one AI beat in <3 min |
| Narrative Quality | Beat passes internal Boredom Test |
| Trigger Reliability | Audio triggers within 10m radius during live walk |
| GPS Accuracy Threshold | Warn user if accuracy >25m |

## Resolved Technical Decisions (Locked for MVP)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Audio engine | ElevenLabs Conversational AI | ~$15–20 per 60-min tour, best narrative quality |
| Audio chunking | AI timestamps method | S3 storage + Postgres index |
| Audio format | MP3, 256kbps, Stereo, 44.1kHz | Stored on AWS S3 |
| Geocoding (MVP) | OpenStreetMap (free) | Switch to Google Maps at launch |
| Geocoding confidence | Auto-flag <70% | Show confidence to editors |
| GPS precision | 6 decimal places (~10cm) | GeoPoint on Neo4j POI node |
| GPS warning | >25m accuracy | Default; revisit after field test |
| GPS strategy | Adaptive polling | High-freq near POIs, low between. 10–20% battery/60–90 min |
| Editorial map | OpenStreetMap/Leaflet | Editor pin drag-and-drop |
| Database | Neo4j graph (Schema v3) | 3 domains: Vault, Atlas, Bridge |
| Geofence radius | 10m fixed | Consistent across all POIs for MVP |
| Gravity Score | Deep research pipeline | Gemini grounding + prompt rubric. Lensing attached post-scoring |
| Lens system | Simple config file | Hardcoded distances, no embeddings for MVP |
| Beat duration | Gravity × 60 seconds | Gravity 5 = 300 sec max |
| MVP scope | Single city, 100 POIs | Max 1 beat per lens per POI (max 12 beats per POI) |

## Current Stack

| Layer | Technology |
|-------|------------|
| Database | Neo4j Graph Database (Schema v3) |
| Audio generation | ElevenLabs Conversational AI |
| Audio storage | AWS S3 + Postgres (timestamp index) |
| Geocoding (MVP) | OpenStreetMap |
| Geocoding (launch) | Google Maps API |
| Editorial map | OpenStreetMap / Leaflet |
| Mobile framework | Expo (TypeScript) |
| Backend | Supabase (Postgres + Auth + Edge Functions) |
| Cache | Upstash Redis |
| AI | Gemini API |
| File uploads | Max 50MB, PDF 1.4+, EPUB 2.0/3.0 |

## Neo4j Domain Architecture

### Domain 1: The Traveler's Vault
- **User** — auth & account basics
- **Profile** — persona "bubbles" linked to devices (enables family sharing)
- **Trip** — master trip container with owner + members

### Domain 2: The Global Atlas
- **POI** — physical locations with geofencing and metadata
- **NarrativeBeat** — versioned story content with audio
- **Lens** — thematic layers for interest-based filtering (12 lenses for MVP)

### Domain 3: The Execution Bridge
- **ItineraryItem** — per-device content assignments with scheduling

### Domain 4: Gamification & Rewards (Post-MVP)
- Badges, achievements, challenge completions

## The 12 Lenses (MVP)

1. Hidden History
2. Architecture & Design
3. Local Legends & Folklore
4. Food & Culinary Culture
5. Art & Street Culture
6. Dark History (crime, espionage, scandal)
7. Literary & Film Locations
8. Religious & Spiritual Sites
9. Music & Nightlife History
10. Revolutionary Moments
11. Nature & Green Spaces
12. Shopping & Markets

## Golden Ratio Algorithm

- 20% Anchors (Gravity 5): Major sights as waypoints
- 80% Flavour (Gravity 1–4): Local connective tissue between anchors
- Start at highest-Gravity POI in radius
- End with a "bang" at a high-impact location
- Linear tour (not circular)
- Dynamic resequencing if user deviates from route

## Content Pipeline (Book-to-Street)

1. **Source Ingestion** — PDF/EPUB upload
2. **AI Deconstruction** — entity extraction, gravity scoring, lens mapping, story beat generation, narrative styling
3. **Editorial Workbench** — staging area, split-screen editor, map pin validation, gravity/lens confirmation
4. **Commit to Live** — staging → production database
5. **Audio Generation** — fallback TTS at ingestion; NotebookLM-style tour audio on-demand when user starts tour

## MVP Scope Boundaries

**IN:** Single city, 100 POIs, Book-to-Street pipeline, Wanderer mode, email/password auth, graceful degradation, Golden Ratio algorithm

**OUT:** Social/sharing, payments, turn-by-turn nav, multi-language, POI photos, full offline packs, haptic feedback, gamification nodes

## Team

- **Adam** — Backend/AI
- **Sairam** — Mobile/Frontend

## Timeline

10 weeks to MVP launch. Paris first, then NYC and London post-MVP.
