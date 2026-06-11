# Auth Migration — Spec + Claude-Code Forcing Protocol

Replace the custom auth (`src/api/auth/`, magic-link + Google + Apple) with a managed provider — and structure the work so Claude Code **can't** botch it. Do this **after** the July-3 gate (swapping auth right before the validation walks is needless risk).

---

## 1. Provider — decided: **Firebase Auth**

| Option | Verdict | Why (researched, June 2026) |
|---|---|---|
| **Firebase Auth** | ✅ **Use** | first-class Flutter for **email-link + Google + Apple** — your exact three — free, and the most ubiquitous, most-documented pattern in existence, so it's the **lowest-hallucination, hardest-to-botch** choice. FastAPI verifies Firebase ID tokens with `firebase-admin`. |
| Clerk | alternative (premium) | official Flutter SDK only since **public beta, Mar 2025** ([changelog](https://clerk.com/changelog/2025-03-26-flutter-sdk-beta)); lovely user-management DX, but the SDK is newer and Clerk's prebuilt-UI strength is web-first. Pick it only if you want managed user profiles/orgs and accept a younger Flutter SDK. |
| Auth0 | ⚠️ avoid for this | Google/Apple are solid, but **magic-link is not supported in Universal Login and the Flutter SDK lacks first-class passwordless** ([open issue](https://github.com/auth0/auth0-flutter/issues/231)) — your #1 method is its weakest spot. |
| WorkOS | ❌ wrong tool | a B2B **SSO/SCIM** platform; weak for consumer social/passwordless and no clear Flutter mobile path. |

The protocol below is provider-agnostic — only the SDK names change if you choose Clerk.

---

## 2. The forcing protocol — why Claude Code wrecks auth, and the rule that stops each

| Failure mode (where the week goes) | The forcing rule |
|---|---|
| **Stale / invented SDK calls** — auth SDKs move fast; the model writes deprecated or made-up APIs | **Docs-first + pinned versions.** Pin exact versions (§5). Before writing a line it must read the *current* Flutter+Firebase quickstart and cite it. Rule: *every SDK call traces to the pinned docs; if it isn't there, STOP and fetch — never invent.* |
| **Big-bang wiring** — frontend + backend + provider + tokens at once; when it breaks there are ten suspects | **Tracer bullet + thin slices with gates** (§4). Ship ONE method end-to-end first. *Do not start the next slice until the current slice's check is green.* |
| **Invisible config** — provider console, redirect URIs, Apple Service ID, Xcode capabilities, bundle IDs, universal links | **Human-completed prerequisites checklist, first** (§3). Claude Code's *first* output is the exact console/Xcode/Apple steps + the values it needs, then it **stops** until you confirm. (Your `CLAUDE.md` already mandates "list ALL prerequisites upfront, caveat what you can't see" — enforce it here.) |
| **No verification loop** — it can't see the live login, so it declares "done" untested | **E2E test first; "done" = it's green against the real provider** (§6). It must *run* the check and paste the output, not assert success. |
| **Risky cutover** — replaces live auth, breaks everyone | **Flag + parallel run.** New provider behind a flag, both paths live, verify, flip, *then* delete the custom layer. |
| **"Looks done" ≠ works** | Per-slice "done-when" is an observable check, never "I implemented X." |

> **The one-sentence version:** force it to (1) read current docs + pin versions, (2) make *you* finish the invisible config first, (3) work one verifiable slice at a time, and (4) prove each slice with a real end-to-end test before moving on.

---

## 3. Prerequisites — you do these (Claude Code lists the values, then stops)

- [ ] Firebase project; register the iOS app (bundle ID); add `GoogleService-Info.plist`.
- [ ] Enable providers: **Email Link (passwordless)**, **Google**, **Apple**.
- [ ] Email-link: configure the dynamic/universal link + authorized domains *(the magic-link week-eater)*.
- [ ] **Apple:** "Sign in with Apple" capability in Xcode; Apple **Service ID** + key; return URLs.
- [ ] Email: decide whether Firebase sends the link or you keep **Resend** — before slice 1.

---

## 4. Build order — slices (each is one gated Claude Code session)

| # | Slice | Done when (the gate) |
|---|---|---|
| 1 | **Tracer bullet** — magic-link only, full loop | real magic-link login → Firebase session → FastAPI verifies the ID token → one protected endpoint returns **200**, proven by a green e2e test |
| 2 | Backend: Firebase **ID-token verification** middleware replaces custom JWT on protected routes | every protected route accepts a Firebase token; custom path still behind a flag |
| 3 | **Google** sign-in (mobile) | Google login reaches Home on a device |
| 4 | **Apple** sign-in (mobile) — the gotcha-heavy one | Apple login works on a **real device** |
| 5 | Session refresh + sign-out + `/me` | refresh + logout verified |
| 6 | **User migration** — map Firebase `uid` → existing Neo4j users; backfill | existing users resolve to their data via `uid` |
| 7 | **Flagged cutover** → delete custom auth | all three methods green in prod; `src/api/auth/` removed; rollback flag documented |

---

## 5. Pinned versions (read each README before calling it)

Flutter: `firebase_core`, `firebase_auth`, `google_sign_in`, `sign_in_with_apple`. Backend: `firebase-admin` (FastAPI token verification). Pin exact versions in `pubspec.yaml` / `pyproject.toml`; the agent reads the current README/quickstart for each before use.

## 6. Definition of done = the e2e test

One integration test (or a scripted manual run with exact expected output per step) that performs a **real login and hits a protected endpoint**. No slice is done until its portion is green; the migration is done only when all three methods pass the e2e test in prod behind the flag and the custom layer is deleted.
