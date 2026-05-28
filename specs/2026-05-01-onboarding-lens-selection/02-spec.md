# 02 — Spec: Onboarding Lens Selection + Bottom Navbar

**Date:** 2026-05-01
**Status:** Draft — awaiting user review
**Decisions from user:** Auto-derive profile name, rich welcome animation, Spotify/Apple Music-style tile grid, auto-save on tap, vibrant palette

---

## 1. Welcome Animation

**Trigger:** First sign-in only (user has no profile with PREFERS_LENS edges).

**Sequence (2.5 seconds total):**
1. **0.0s** — Screen is solid dark (#0D0D0D). Ondoway wordmark fades in at center (opacity 0→1 over 400ms, slight scale 0.9→1.0).
2. **0.6s** — Wordmark slides up to top-third. Below it, "Welcome, {firstName}" fades in (firstName derived from email prefix, capitalized — e.g., "sairam@..." → "Sairam").
3. **1.2s** — Subtitle fades in below: "Let's find the stories that move you."
4. **2.0s** — Whole screen crossfades to the lens selection page (500ms transition).

**No tap-to-skip.** It's short enough that a skip button adds clutter without saving meaningful time. If the animation feels slow in testing, we shorten it — don't add a button.

**Return users:** Skip straight to Explore tab. Detection: user has a profile with at least 1 PREFERS_LENS edge.

---

## 2. Lens Selection Screen

### Layout: Vibrant Tile Grid

Inspired by Spotify's genre picker — each lens is a colored tile with rounded corners. Not a list. Not checkboxes. A visual identity for each lens.

**Structure:**
- Scrollable column
- Section header for each parent category (subtle, not dominant — e.g., "HISTORY" in small caps, muted text)
- Below each header: 2-column grid of lens tiles
- Sticky header at top: "What stories interest you?" (onboarding) or "Your Lenses" (edit mode)
- Sticky footer: selection count + continue button (onboarding) or auto-saved indicator (edit mode)

### Tile Design

Each tile:
- **Size:** ~half screen width, aspect ratio ~1.4:1 (landscape-ish rectangle)
- **Background:** Solid vibrant color (unique per lens — see palette below)
- **Corner radius:** 16px
- **Content:** Lens display name in white, bold, 16pt, bottom-left aligned with 12px padding
- **Unselected state:** Full color, no border
- **Selected state:** White checkmark badge (top-right corner, 24px circle), subtle white border (2px), slight scale pulse animation (1.0→1.05→1.0 over 200ms) on tap
- **Deselect:** Reverse animation, checkmark fades out

### Color Palette (18 lens tiles)

| Lens | Color | Hex |
|------|-------|-----|
| Hidden History | Deep Indigo | `#3D5AFE` |
| War & Conflict | Crimson | `#D32F2F` |
| Dark History | Charcoal Purple | `#4A148C` |
| Social Change | Amber | `#FF8F00` |
| Historic Architecture | Teal | `#00897B` |
| Modern & Contemporary Design | Electric Blue | `#0288D1` |
| Music Heritage | Hot Pink | `#C2185B` |
| Visual Art | Saffron | `#F57C00` |
| Street Art | Lime | `#689F38` |
| Film & TV Locations | Royal Purple | `#7B1FA2` |
| Historic Cuisine | Warm Red | `#E64A19` |
| Markets & Street Food | Coral | `#FF7043` |
| Local Legends & Folklore | Emerald | `#2E7D32` |
| Literary Heritage | Slate Blue | `#455A64` |
| Famous Residents | Gold | `#FFA000` |
| Historic Houses of Worship | Deep Teal | `#00695C` |
| Sacred Traditions | Mauve | `#8E24AA` |
| Parks & Gardens | Forest Green | `#388E3C` |
| Waterways & Views | Ocean Blue | `#0277BD` |
| Historic Markets & Shopping | Burnt Orange | `#E65100` |
| Science & Technology | Steel Blue | `#1565C0` |

Category headers use muted gray (#9E9E9E) small caps text. Background is near-black (#121212) for maximum tile contrast.

### Onboarding Mode (first time)

- Header: "What stories interest you?"
- Subheader: "Pick at least 3 — you can always change these later."
- Footer: sticky bottom bar with:
  - Left: "{n} selected" counter (updates live)
  - Right: "Continue" button — disabled + grayed until 3+ selected, then vibrant blue (#3D5AFE)
- Tapping "Continue":
  1. Creates default Profile (display_name = email prefix, capitalized)
  2. Creates HAS_PROFILE edge (User → Profile)
  3. Creates PREFERS_LENS edges (Profile → each selected Lens)
  4. Navigates to Explore tab

### Edit Mode (return visits via Lenses tab)

- Header: "Your Lenses"
- No subheader
- No footer bar — selections auto-save on tap
- Pre-checked with current PREFERS_LENS edges
- Tap to add → creates PREFERS_LENS edge immediately (optimistic UI, spinner on failure)
- Tap to remove → deletes PREFERS_LENS edge immediately
- Minimum 1 lens enforced (last lens can't be deselected — show toast: "You need at least one lens")
- No "Continue" button — user just navigates away via bottom nav

---

## 3. Bottom Navigation Bar

### Tabs (3)

| Position | Icon | Label | Route | Content |
|----------|------|-------|-------|---------|
| Left | Compass | Explore | `/explore` | Placeholder: "Your first tour starts here" + city illustration |
| Center | Grid/Sparkle | Lenses | `/lenses` | Lens selection grid (edit mode) |
| Right | Person | Profile | `/profile` | Email display + logout button |

### Behavior
- Standard Material `NavigationBar` (Material 3)
- Active tab: vibrant blue icon + label (#3D5AFE)
- Inactive tab: muted gray icon + label (#9E9E9E)
- Background: near-black (#1A1A1A) to match app dark theme
- Shown on Explore, Lenses, Profile pages
- Hidden during welcome animation and onboarding lens selection (those are full-screen flows)
- Persists across tab switches (each tab maintains its own scroll state)

### Navigation Structure (GoRouter)

```
/login          → LoginPage (no nav bar)
/auth           → CallbackPage (no nav bar)
/auth/callback  → CallbackPage (no nav bar)
/welcome        → WelcomePage (no nav bar, first-time only)
/onboarding     → LensSelectionPage in onboarding mode (no nav bar)
/shell          → ShellPage with bottom nav bar
  /explore      → ExplorePage (tab 0)
  /lenses       → LensSelectionPage in edit mode (tab 1)
  /profile      → ProfilePage (tab 2)
```

After login:
- First-time user → `/welcome` → `/onboarding` → `/shell/explore`
- Return user → `/shell/explore`

---

## 4. Profile Auto-Creation

**Trigger:** User completes onboarding lens selection ("Continue" tap).

**Steps (single transaction):**
1. `POST /api/v1/nodes` — Create Profile node: `{"label": "Profile", "properties": {"display_name": "{FirstName}"}}`
2. `POST /api/v1/edges` — Create HAS_PROFILE: `{"source": {"label": "User", "id": "{user_id}"}, "target": {"label": "Profile", "id": "{profile_id}"}}`
3. For each selected lens: `POST /api/v1/edges` — Create PREFERS_LENS: `{"source": {"label": "Profile", "id": "{profile_id}"}, "target": {"label": "Lens", "id": "{lens_id}"}}`

**Failure handling:** If any call fails, show error toast and let user retry. Don't partially create — but since the backend doesn't support transactions via REST, we accept eventual consistency. Profile without lenses is better than no profile.

**Email prefix derivation:** `email.split("@")[0]`, capitalize first letter. "sairam@ondoway.com" → "Sairam". "john.doe@gmail.com" → "John.doe" (keep it simple, don't parse dots — user can edit later).

---

## 5. State Management

### New Providers

**ProfileService (ChangeNotifier):**
- `Profile? currentProfile` — user's active profile
- `List<String> selectedLensIds` — current PREFERS_LENS lens IDs
- `bool isFirstTime` — true if no profile exists
- `fetchProfile()` — called after auth, checks for existing profile + preferences
- `createProfileWithLenses(String name, List<String> lensIds)` — onboarding
- `addLens(String lensId)` — edit mode, creates edge immediately
- `removeLens(String lensId)` — edit mode, deletes edge immediately

**LensService (ChangeNotifier):**
- `List<Lens> allLenses` — fetched once on app start
- `Map<String, List<Lens>> lensesByParent` — grouped for UI
- `fetchLenses()` — GET /nodes?label=Lens, groups by parent

### Auth flow extension

After `verifyMagicLink()` succeeds:
1. AuthService stores tokens + fetches /me (existing)
2. ProfileService.fetchProfile() — check if user has profile + lenses
3. If `isFirstTime` → navigate to `/welcome`
4. If not → navigate to `/shell/explore`

---

## 6. Dark Theme

The entire app uses a dark theme to make the vibrant lens tiles pop:

- **Background:** #121212 (screens), #1A1A1A (nav bar, cards)
- **Surface:** #1E1E1E (elevated elements)
- **Primary:** #3D5AFE (buttons, active nav, links)
- **On-background:** #FFFFFF (primary text), #9E9E9E (secondary text)
- **Error:** #CF6679

This applies globally — login page, welcome screen, all tabs.

---

## 7. What this does NOT include

- Multiple profiles (MVP = 1 per user)
- Profile editing (name, avatar)
- Lens illustrations or icons (colored tiles with text only)
- Tour generation or explore content
- Haptic feedback
- Offline lens caching
- Analytics/tracking

---

## 8. Acceptance Criteria

1. First-time user sees welcome animation → lens selection → lands on Explore tab with bottom nav
2. Return user skips welcome + onboarding, lands directly on Explore tab
3. Lens grid shows 18 lenses in 8 categories, tiles are colored per palette
4. User must select 3+ lenses to continue (button disabled until met)
5. Tapping a tile shows selected state with checkmark + scale animation
6. Profile + PREFERS_LENS edges created in Neo4j after onboarding
7. Lenses tab (bottom nav) shows same grid in edit mode, pre-checked
8. Auto-save on tap in edit mode (optimistic UI)
9. Can't deselect last lens in edit mode (toast warning)
10. Bottom nav shows 3 tabs: Explore, Lenses, Profile
11. All tests pass (existing 1,419 + new Flutter tests for onboarding flow)
