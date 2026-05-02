# Universal Links — Implementation Plan

**Date:** 2026-05-01
**Status:** In progress — paused for resume tomorrow
**Conversation ID:** 42a13c8c-cc03-4851-9637-0de04dcc6a9f

---

## Context

Magic link auth flow is built and tested (705 tests, 0 skip, 0 fail). Current flow uses a custom URL scheme (`ondoway://`) with a browser redirect page as intermediary. User wants to upgrade to Apple Universal Links so clicking a magic link in email opens the app directly — no Safari intermediate step.

## Known Values

- **Domain:** `ondoway.com` (registered on Namecheap, no hosting yet)
- **Apple Team ID:** `BC7F6Q48GB` (Apple Developer Program enrolled, $99/yr paid)
- **Bundle ID:** `com.ondoway.app`
- **App ID for AASA:** `BC7F6Q48GB.com.ondoway.app`
- **Deployment platform:** Railway (recommended, not yet set up — auto-HTTPS via Let's Encrypt)

## Current Chain (working, custom URL scheme)

```
Email: http://localhost:8000/auth?token=...
  → Browser loads FastAPI /auth route → serves frontend/auth.html
    → auth.html JS redirects to ondoway://auth/callback?token=...
      → iOS intercepts ondoway:// scheme (registered in Info.plist)
        → Flutter GoRouter matches /auth/callback, extracts ?token=
          → CallbackPage calls authService.verifyMagicLink(token)
            → AuthService POSTs to /api/v1/auth/magic-link/verify
              → Stores access_token + refresh_token in FlutterSecureStorage
                → context.go('/home') → HomePage shows "Welcome!" + email
```

## Target Chain (universal links)

```
Email: https://ondoway.com/auth?token=...
  → iOS checks AASA file → opens app directly (no browser)
    → Flutter GoRouter matches /auth, extracts ?token=
      → CallbackPage calls authService.verifyMagicLink(token)
        → (same from here down)
  → Fallback (app not installed): browser loads /auth → frontend/auth.html
```

## What Exists Already

| Component | File | Status |
|-----------|------|--------|
| Magic link email sender | `src/api/auth/email.py` | ✅ Uses `FRONTEND_URL` config |
| Token verify endpoint | `src/api/auth/routes.py` | ✅ POST /api/v1/auth/magic-link/verify |
| Redirect page (fallback) | `frontend/auth.html` | ✅ Serves at /auth, fires ondoway:// deep link |
| FastAPI /auth route | `src/api/app.py` | ✅ FileResponse for auth.html |
| iOS URL scheme | `mobile/ios/Runner/Info.plist` | ✅ `ondoway` scheme registered |
| GoRouter /auth/callback | `mobile/lib/router.dart` | ✅ Extracts token from query params |
| CallbackPage | `mobile/lib/pages/callback_page.dart` | ✅ Verifies token, navigates to /home |
| AuthService | `mobile/lib/services/auth_service.dart` | ✅ verifyMagicLink(), token storage, /me fetch |
| Session restore | `mobile/lib/main.dart` | ✅ tryRestoreSession() on startup |
| Home page | `mobile/lib/pages/home_page.dart` | ✅ Shows email, logout button |

## What Needs to Be Built

### Scope 1: Backend — AASA endpoint

**File: `src/api/app.py`**
- Add `GET /.well-known/apple-app-site-association` route
- Return JSON with `Content-Type: application/json` (no file extension, Apple requires this)
- AASA content:
```json
{
  "applinks": {
    "apps": [],
    "details": [
      {
        "appID": "BC7F6Q48GB.com.ondoway.app",
        "paths": ["/auth", "/auth/*"]
      }
    ]
  }
}
```

**File: `src/api/auth/config.py`**
- Add `APPLE_TEAM_ID: str = os.getenv("APPLE_TEAM_ID", "")` 
- AASA route uses this + bundle ID to construct appID dynamically

**File: `.env.example`**
- Add `APPLE_TEAM_ID=BC7F6Q48GB`

**Tests:**
- AASA returns 200 with correct content-type
- AASA JSON structure is valid (applinks.details[0].appID matches config)
- AASA paths include /auth

### Scope 2: iOS — Entitlements + Xcode project

**New file: `mobile/ios/Runner/Runner.entitlements`**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "...">
<plist version="1.0">
<dict>
    <key>com.apple.developer.associated-domains</key>
    <array>
        <string>applinks:ondoway.com</string>
    </array>
</dict>
</plist>
```

**File: `mobile/ios/Runner.xcodeproj/project.pbxproj`**
- Add `Runner.entitlements` as PBXFileReference
- Add to Runner group's children
- Set `CODE_SIGN_ENTITLEMENTS = Runner/Runner.entitlements` in all 3 Runner build configs (Debug, Release, Profile)
- Set `DEVELOPMENT_TEAM = BC7F6Q48GB` in all 3 Runner build configs

**Key constraint:** Associated Domains capability requires a paid Apple Developer Program account ($99/yr), which is now enrolled (Team ID `BC7F6Q48GB`).

### Scope 3: Flutter — GoRouter universal link route

**File: `mobile/lib/router.dart`**
- Add `/auth` route (universal link path) alongside existing `/auth/callback` (custom scheme fallback):
```dart
GoRoute(
  path: '/auth',
  builder: (context, state) {
    final token = state.uri.queryParameters['token'] ?? '';
    return CallbackPage(token: token);
  },
),
```
- Both `/auth` and `/auth/callback` point to CallbackPage — same handler, two entry points
- Verify `initialLocation: '/login'` doesn't override incoming deep links on cold start (go_router v14 should handle this correctly — platform route info takes precedence)

### Scope 4: Deployment (blocks real universal link testing)

1. **Railway setup:**
   - Connect GitHub repo
   - Set env vars (NEO4J_URI, JWT_SECRET_KEY, etc.)
   - Deploy → get Railway URL (e.g., `ondoway-production.up.railway.app`)

2. **Namecheap DNS:**
   - Add CNAME record: `ondoway.com` → Railway's provided domain
   - Railway auto-provisions Let's Encrypt SSL

3. **Config:**
   - Set `FRONTEND_URL=https://ondoway.com` in Railway env
   - Set `APPLE_TEAM_ID=BC7F6Q48GB` in Railway env

4. **Verify:**
   - `curl https://ondoway.com/.well-known/apple-app-site-association` returns valid AASA
   - Apple's CDN caches AASA within 24hrs of first app install
   - Test: click magic link in email → app opens directly

### Scope 5: AuthService base URL (dev vs prod)

**File: `mobile/lib/services/auth_service.dart`**
- Currently hardcoded: `static const _baseUrl = 'http://localhost:8000/api/v1/auth'`
- Needs to be configurable: localhost for simulator dev, `https://ondoway.com` for production
- Options: Flutter `--dart-define`, env config file, or `String.fromEnvironment`
- Simplest: `const _baseUrl = String.fromEnvironment('API_BASE_URL', defaultValue: 'http://localhost:8000/api/v1/auth')`

## Potential Issues to Watch

1. **Deployment** — Need to deploy backend to a hosting provider with custom domain support and HTTPS. The app connects to AuraDB (already live), so only the FastAPI process needs hosting.

2. **AASA caching** — Apple CDNs cache the AASA file. Changes can take up to 24 hours to propagate. First install triggers the fetch.

3. **`initialLocation: '/login'` vs deep link** — go_router v14 should let platform deep links override initialLocation on cold start. Needs live verification on simulator.

4. **Simulator limitations** — Universal links don't work in the iOS Simulator the same way as on device. Custom URL scheme (`xcrun simctl openurl`) is the main dev testing path. Real universal link testing requires a physical device + deployed domain.

## Files I Had Open When Paused

All read and ready for editing:
- `src/api/app.py` (lines 1-74) — add AASA route here
- `src/api/auth/config.py` (lines 1-25) — add APPLE_TEAM_ID
- `mobile/ios/Runner.xcodeproj/project.pbxproj` (lines 1-754) — add entitlements ref + DEVELOPMENT_TEAM
- `mobile/ios/Runner/Info.plist` (lines 1-83) — no changes needed (URL scheme stays as fallback)
- `mobile/lib/router.dart` (lines 1-41) — add /auth route
- `mobile/lib/services/auth_service.dart` (lines 1-149) — make _baseUrl configurable
- `mobile/lib/pages/callback_page.dart` (lines 1-79) — no changes needed
- `mobile/lib/main.dart` (lines 1-40) — no changes needed
- `.env.example` (lines 1-30) — add APPLE_TEAM_ID

## Resume Instructions

Start with Scopes 1-3 (backend AASA, iOS entitlements, GoRouter route). These are all code changes that can be built and tested without deployment. Scope 4 (Railway deploy) and Scope 5 (base URL config) come after.

Run `make test` after backend changes. Run `make flutter-test` after Flutter changes (if test targets exist). The test bar is full suite, 0 fail, 0 skip.
