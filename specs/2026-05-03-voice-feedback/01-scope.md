# Voice Feedback → GitHub Issues

## Problem
Beta testers need a frictionless way to report bugs, request features, and give feedback from anywhere in the app — including before login. Voice is the lowest-friction input. Issues should land in GitHub where the dev team already works.

## Scope
A persistent floating button on every screen (including login) that:
1. Records voice via device microphone
2. Transcribes speech to text on-device
3. Lets the tester edit the transcription before submitting
4. Sends it to a backend endpoint that creates a GitHub issue
5. Auto-attaches device metadata (platform, OS, app version, current screen)

## Out of scope
- Storing feedback in Neo4j (GitHub Issues is the system of record)
- Screenshot capture (future enhancement)
- Audio file upload (transcription only)
- Any changes to the auth flow
- Making the repo public (token stays server-side)

## Success criteria
- A beta tester on the login page can tap the button, speak, and see a GitHub issue created within 5 seconds
- Every issue includes: transcribed text, device info, current route, and user email (if logged in)
- Zero interaction required from the developer to triage — issues are pre-labeled `beta-feedback`
