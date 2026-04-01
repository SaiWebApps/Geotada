# TTS Audio Pipeline for Travlr — Options & Cost Analysis

## Context

Travlr needs to convert `NarrativeBeat.script_body` text into audio files for GPS-triggered playback. The data model already has `audio_url` and `duration_sec` fields — the generation pipeline is the missing piece. The NORTHSTAR locks ElevenLabs as the audio engine, but this analysis explores the full landscape so we can make an informed commitment (or confirm the existing one).

**Key constraint:** This is a **pre-generation** workflow, not real-time TTS. Scripts are authored in the Editorial Workbench, audio is generated once, stored in S3, and served to many users. This fundamentally changes the cost equation — per-character costs are one-time, not per-listen.

---

## Volume Estimate (Boston Launch)

| Metric | Conservative | Aggressive |
|--------|-------------|------------|
| POIs | 100 | 150 |
| Avg beats per POI | 3 | 5 |
| Total beats | 300 | 750 |
| Avg chars per beat | 350 | 500 |
| **Total characters** | **105,000** | **375,000** |
| Avg audio per beat | 30–60s | 30–60s |
| **Total audio** | **2.5–5 hrs** | **6–12 hrs** |

Re-generation (edits, new versions) adds ~20–30% over the initial batch.

---

## Option Comparison

### Tier 1: Premium Voice Quality (Best for storytelling)

#### 1. ElevenLabs (Current NORTHSTAR choice)
- **Quality:** Best-in-class. Expressive, natural, handles narrative tone well.
- **Pricing:** ~$0.18–0.30/1K characters depending on plan.
  - Pro ($99/mo): 500K chars/mo included, then overage.
  - Scale ($330/mo): 2M chars/mo included.
  - Pay-as-you-go also available.
- **Boston launch cost (one-time generation):** $20–110 depending on plan & volume.
- **Ongoing cost:** Minimal — only re-gen on edits. S3 serving is pennies.
- **Voice cloning:** Yes — could create a consistent "Travlr narrator" voice.
- **SSML:** Limited — uses their own markup for pauses/emphasis.
- **Latency:** ~2–5s per beat (fine for pre-gen).
- **Dev effort:** Simple REST API. Python SDK available. Straightforward integration.
- **Risk:** Pricing changes, rate limits, voice quality changes between model versions.

#### 2. PlayHT
- **Quality:** Very close to ElevenLabs. Good for long-form narration.
- **Pricing:** ~$0.05–0.15/1K characters. Cheaper than ElevenLabs.
- **Boston launch cost:** $5–55.
- **Voice cloning:** Yes.
- **Dev effort:** REST API, Python SDK.
- **Risk:** Smaller company, less battle-tested at scale.

#### 3. OpenAI TTS
- **Quality:** Good, natural. Limited voice selection (6 voices).
- **Pricing:** tts-1: ~$15/1M chars. tts-1-hd: ~$30/1M chars.
- **Boston launch cost:** $1.50–11.
- **Voice cloning:** No.
- **SSML:** No.
- **Dev effort:** Very simple API (already familiar if using OpenAI elsewhere).
- **Risk:** No voice cloning limits brand consistency. Limited expressiveness control.

### Tier 2: Cloud Provider TTS (Cheap, reliable, less expressive)

#### 4. Google Cloud TTS
- **Quality:** Good. WaveNet/Neural2 voices are solid. Journey voices are newer, designed for long-form.
- **Pricing:** WaveNet/Neural2: $16/1M chars. Standard: $4/1M chars.
- **Boston launch cost:** $0.40–6.
- **SSML:** Full support — pauses, emphasis, pronunciation, speed control.
- **Dev effort:** Python SDK (`google-cloud-texttospeech`). Well-documented.
- **Risk:** Sounds more "synthetic" than Tier 1 for storytelling. Acceptable for utility, not for emotional engagement.

#### 5. Amazon Polly
- **Quality:** Good. Neural voices decent. "Long-form" engine designed for narration.
- **Pricing:** Neural: $16/1M chars. Long-form: $100/1M chars. Standard: $4/1M chars.
- **Boston launch cost:** $0.40–37 (depending on engine choice).
- **SSML:** Full support + Polly-specific tags (whispering, breathing).
- **Dev effort:** `boto3` — already in AWS ecosystem for S3. Tightest integration path.
- **Risk:** Long-form engine is expensive. Neural voices less expressive than Tier 1.

#### 6. Microsoft Azure TTS
- **Quality:** Very good neural voices. Emotion/style controls (cheerful, sad, narration style).
- **Pricing:** Neural: $15/1M chars. Custom Neural Voice: $24/1M chars.
- **Boston launch cost:** $1.50–9.
- **SSML:** Best-in-class SSML with emotion tags (`<mstts:express-as style="narration-professional">`).
- **Dev effort:** Python SDK. More complex setup than others.
- **Risk:** Adds Azure dependency when already on AWS.

### Tier 3: Open Source / Self-Hosted (No per-character cost)

#### 7. Coqui XTTS / Piper / Bark
- **Quality:** Varies. XTTS is best for cloned voices. Bark is most expressive. Piper is fastest.
- **Pricing:** $0 per character. GPU hosting cost: ~$50–200/mo for a small GPU instance.
- **Boston launch cost:** $0 generation + GPU hosting.
- **Voice cloning:** XTTS supports it with ~6 seconds of reference audio.
- **Dev effort:** HIGH. Model hosting, GPU provisioning, output quality tuning, format conversion. Significant ops burden.
- **Risk:** Quality gap is real for storytelling. Maintenance burden. GPU costs can exceed API costs at low volume.

---

## Cost Summary Table (Boston Launch, One-Time Generation)

| Provider | Engine | ~Cost for 200K chars | Quality (storytelling) | Dev Effort |
|----------|--------|---------------------|----------------------|------------|
| **ElevenLabs** | Multilingual v2 | $36–60 | Excellent | Low |
| **PlayHT** | PlayHT 2.0 | $10–30 | Very Good | Low |
| **OpenAI** | tts-1-hd | $6 | Good | Very Low |
| **Google** | WaveNet/Journey | $3.20 | Good | Low |
| **Amazon Polly** | Neural | $3.20 | Good | Low |
| **Amazon Polly** | Long-form | $20 | Better | Low |
| **Azure** | Neural | $3 | Very Good | Medium |
| **Open Source** | XTTS/Bark | $0 + hosting | Variable | High |

---

## Key Insight: Pre-Generation Makes This Cheap

At Travlr's scale (hundreds of beats, not millions), **every option is affordable.** The Boston launch is a one-time batch of ~200K characters. Even ElevenLabs at its most expensive is under $100 for the entire city. The real cost driver is:

1. **Re-generation frequency** — How often do scripts get edited/versioned?
2. **City expansion rate** — Each new city is another batch.
3. **Quality bar** — Does the audio need to feel like a podcast or a GPS voice?

At 10 cities × 500 beats × 400 chars = 2M characters/year:
- ElevenLabs: ~$360–600/year
- Google/Polly: ~$32/year
- Open source: ~$600–2400/year (GPU hosting)

**Open source is more expensive than APIs at this scale.** It only makes sense at millions of characters/month.

---

## Decisions (Locked)

1. **Standard TTS API, not Conversational AI.** The NORTHSTAR says "ElevenLabs Conversational AI" but the product has no real-time back-and-forth — both Planner and Wanderer modes play pre-recorded NarrativeBeat audio triggered by GPS proximity. Standard TTS API is cheaper, gives full output format control, and is the right tool. **Update NORTHSTAR to read "ElevenLabs Text-to-Speech API."**

2. **Keep stereo 256kbps MP3.** Per NORTHSTAR spec. No relaxation.

3. **Dual-provider architecture.** OpenAI TTS for development/testing (cheap, simple). ElevenLabs for production audio. Abstract behind a `TTSProvider` interface so switching is a config change.

---

## Recommendation

### Confirm ElevenLabs (with dual-provider dev architecture)

The NORTHSTAR choice is well-justified. For an entertainment product where audio IS the product, voice quality is non-negotiable. The cost difference between ElevenLabs and Google at this scale is ~$50/city — trivial against the quality uplift.

**Architecture principles:**

1. **Provider abstraction.** A `TTSProvider` protocol with `generate(text, voice_id) -> bytes`. Two implementations: `OpenAITTSProvider` (dev) and `ElevenLabsTTSProvider` (prod). Selected by env var `TTS_PROVIDER=openai|elevenlabs`.

2. **Use a fixed narrator voice** from each provider's library. Consistency across all beats in a city matters for immersion.

3. **Generate at Editorial Workbench "Commit to Live" time.** When an editor finalizes a beat → trigger TTS → upload to S3 → update `audio_url`. No separate batch pipeline needed.

4. **Cache aggressively.** A beat at version N with a given script_body always produces the same audio. Only re-generate when script_body or voice config changes.

5. **Consider a hybrid for cost optimization later:** Use ElevenLabs for Gravity 4–5 beats (anchors, flagship content) and a cheaper provider for Gravity 1–2 beats (background flavor). The provider abstraction makes this trivial to implement.

---

## Development Plan

### Pipeline: `script_body → TTS Provider → MP3 → S3 → audio_url`

**New files to create:**
- `src/audio/__init__.py` — Package init
- `src/audio/provider.py` — `TTSProvider` protocol + `OpenAITTSProvider` + `ElevenLabsTTSProvider`
- `src/audio/storage.py` — S3 upload helper (upload MP3, return public URL)
- `src/audio/pipeline.py` — Orchestrator (fetch beat → generate → upload → update Neo4j)
- `src/api/routes/audio.py` — API endpoints to trigger generation
- `tests/test_audio_provider.py` — Unit tests (mocked providers)
- `tests/test_audio_pipeline.py` — Pipeline integration tests

**Config additions (.env):**
- `TTS_PROVIDER=openai` (dev) or `elevenlabs` (prod)
- `OPENAI_API_KEY` (dev)
- `ELEVENLABS_API_KEY` (prod)
- `ELEVENLABS_VOICE_ID` (prod)
- `AWS_S3_BUCKET` (e.g., `travlr-audio`)
- `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` (or use IAM roles)

**Dependencies to add:**
- `openai` (dev TTS)
- `elevenlabs` (prod TTS — official Python SDK)
- `boto3` (AWS S3)

**API endpoints:**
- `POST /audio/generate/{beat_id}` — Generate audio for a single beat
- `POST /audio/generate-batch` — Generate for all beats without audio (or with stale versions)
- `GET /audio/status/{beat_id}` — Check if audio exists and is current

**NORTHSTAR update:**
- Change "ElevenLabs Conversational AI (~$15–20 per 60-min tour)" → "ElevenLabs Text-to-Speech API (~$36–60 per city launch, one-time)"

### Testing approach:
- Unit tests: mock both providers, verify correct parameters sent, verify provider abstraction works
- Integration test: generate one beat with OpenAI (cheap), verify MP3 is valid stereo 256kbps
- E2E: Workbench commit → audio generated → S3 URL updated → playable

### Verification:
1. Run `make test` — all existing tests still pass
2. Run new audio unit tests with mocked providers
3. Generate a test beat with OpenAI TTS, verify MP3 format (stereo, 256kbps, 44.1kHz)
4. Upload to S3 (or local mock), verify URL is accessible
5. Verify Neo4j `audio_url` is updated on the NarrativeBeat node
