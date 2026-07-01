"""Playwright UI test suite for the Editorial Review Workbench (review.html).

Systematically exercises the workbench through its complete workflow and
produces a markdown bug report with screenshots. Auto-starts a FastAPI
server on localhost:8000 for the duration of the module.

Usage:
    pytest tests/test_workbench_ui.py -v --tb=short

Requires: playwright, pytest, Neo4j running
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Page, sync_playwright

# ---------------------------------------------------------------------------
# DOM Selectors — single source of truth (Risk R1 mitigation)
# ---------------------------------------------------------------------------

# IDs
CITY_OVERLAY = "#cityOverlay"
CITY_INPUT = "#cityInput"
CITY_SUBMIT = "#citySubmitBtn"
CITY_LABEL = "#cityLabel"
LOAD_JSON_BTN = "#loadJsonBtn"
FILE_INPUT = "#fileInput"
WORKLIST = "#worklist"
DUP_OVERLAY = "#dupOverlay"
DUP_RESOLVE_BTN = "#dupResolveBtn"
DETAIL_VIEW = "#detailView"
DETAIL_TITLE = "#detailTitle"
DETAIL_EMPTY = "#detailEmpty"
DEFER_BTN = "#deferBtn"
MARK_COMPLETE_BTN = "#markCompleteBtn"
NEXT_BTN = "#nextBtn"
PREV_ROW_BTN = "#prevRowBtn"
NEXT_ROW_BTN = "#nextRowBtn"
ERROR_TOAST = "#errorToast"
SUCCESS_TOAST = "#successToast"
MAP = "#map"

# CSS classes
WORKLIST_ROW = ".worklist-row"
BADGE_PENDING = ".badge-pending"
BADGE_COMPLETE = ".badge-complete"
BADGE_DEFERRED = ".badge-deferred"
BADGE_FLAGGED = ".badge-flagged"
BADGE_UPLOADED = ".badge-uploaded"
BEAT_CARD = ".beat-card"
BEAT_CONFLICT_BADGE_HARD = ".beat-conflict-badge-hard"
BEAT_CONFLICT_BADGE_REVIEW = ".beat-conflict-badge-review"
BEAT_CONFLICT_BADGE = ".beat-conflict-badge"
CONFLICT_SIDE = ".conflict-side"
MERGE_OVERLAY = ".merge-overlay"
FIELD_WARNING = ".field-warning"
FIELD_WARN_YELLOW = ".field-warn-yellow"
AUDIT_NOTES_BOX = ".audit-notes-box"
POI_AUDIT_NOTES_BOX = ".poi-audit-notes-box"
BEAT_WARNING = ".beat-warning"
MAP_WARNING = ".map-warning"
MAP_WARN_GEOFENCE = ".map-warn-geofence"

# Data attributes
DATA_FIELD = '[data-field="{}"]'
DATA_BEAT_FIELD = '[data-beat-field="{}"]'
DATA_BEAT_INDEX = '.beat-card[data-beat-index="{}"]'
DATA_POI_IDX = '.worklist-row[data-poi-idx="{}"]'
DUP_INPUT = 'input[data-dup-idx="{}"]'

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_BASE = "http://localhost:8000/api/v1"
# The ONLY Neo4j port this suite may run against. conftest pins the pytest
# process (and thus any uvicorn we *start*) to this port via .env.test; the
# api_server fixture additionally probes /healthz to validate any *externally*
# running server on :8000, so a dev API (make api → 7687) can never be reused
# and seeded with test rows. Keep in sync with conftest._TEST_PORT_ALLOWLIST.
TEST_NEO4J_PORT = 7688
WORKBENCH_URL = (Path(__file__).parent.parent / "frontend" / "review.html").resolve().as_uri()
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "ui_test_fixture.json"
REPORT_DIR = Path(__file__).parent / "reports"
SCREENSHOT_DIR = REPORT_DIR / "screenshots"


def _find_chromium() -> str | None:
    """Find a cached Playwright Chromium binary if the default isn't installed."""
    cache_dir = Path.home() / "Library" / "Caches" / "ms-playwright"
    if not cache_dir.exists():
        return None
    for d in sorted(cache_dir.glob("chromium-*"), reverse=True):
        candidate = (
            d
            / "chrome-mac-arm64"
            / "Google Chrome for Testing.app"
            / "Contents"
            / "MacOS"
            / "Google Chrome for Testing"
        )
        if candidate.exists():
            return str(candidate)
    return None


# Seed data constants
SEED_POI_NAME = "UI Test Seed \u2014 Sacr\u00e9-C\u0153ur Basilica"
SEED_BEATS = [
    {
        "lens_slug": "hidden_history",
        "gravity": 4,
        "script_body": (
            "The Sacr\u00e9-C\u0153ur Basilica dome held a beacon of white stone on that fateful "
            "autumn day in 1914. Workers climbed the dark narrow stairs "
            "while Parisians gathered on the hill below. The basilica one if by "
            "land two if by river changed the spirit of Montmartre forever. Those "
            "bells became the most famous chimes in the arrondissement "
            "calling every neighborhood along the Seine and "
            "its banks."
        ),
    },
    {
        "lens_slug": "revolutionary_moments",
        "gravity": 3,
        "script_body": (
            "Camille Desmoulins rallied through the Paris boulevards warning "
            "citizens that royal troops were massing toward the Bastille "
            "and the Tuileries. His impassioned call covered roughly twelve blocks of narrow "
            "streets and crowded quarters. At every caf\u00e9 he pounded on tables "
            "shouting aux armes citoyens. Danton and Marat "
            "joined the uprising but only Danton made it all the way to the Convention."
        ),
    },
    {
        "lens_slug": "dark_history",
        "gravity": 2,
        "script_body": (
            "Prussian soldiers besieged Paris for months during the Franco-Prussian War "
            "turning parks into camps and homes into barracks. The occupiers "
            "patrolled cobblestone streets enforcing harsh laws on Parisian citizens. "
            "Tensions boiled over at the Commune uprising when soldiers fired into "
            "a crowd killing scores of communards."
        ),
    },
]

# ── Eiffel conflict seed ──────────────────────────────────────────────────
# A second seed POI at the Eiffel Tower's GPS, named so it does NOT auto-merge
# with the incoming "UI Test Seed — Eiffel Tower" entry (name similarity < 0.5,
# so mergeIncomingIntoDbPois leaves the incoming POI in the worklist and the
# proximity-match panel is shown instead). Its three beats are tuned — Jaccard
# verified offline against review.html's jaccardSimilarity — so the incoming
# POI's five beats land in every conflict band once the editor clicks "Same
# Place" (which runs runBeatConflictDetection against this POI):
#   incoming beat 0 hidden_history -> HARD      (same lens as seed beat 0)
#   incoming beat 1 music_heritage -> NET-NEW   (no lens match, Jaccard ~0.03)
#   incoming beat 2 science_tech   -> SOFT      (Jaccard ~0.80 vs seed beat 1)
#   incoming beat 3 street_art     -> REVIEW    (Jaccard ~0.36 vs seed beat 2)
#   incoming beat 4 parks_gardens  -> PASS-THRU (no lens match, Jaccard ~0.02)
EIFFEL_SEED_NAME = "UI Test — Champ de Mars Landmark"
EIFFEL_SEED_COORDS = (48.8584, 2.2945)
EIFFEL_SEED_BEATS = [
    {
        "lens_slug": "hidden_history",
        "gravity": 3,
        "script_body": (
            "The tower demands sixty tonnes of fresh paint applied by hand every seven "
            "years to shield its puddled iron lattice from rust. A crew suspended on ropes "
            "brushes three graduated shades onto the metal so the whole structure reads as "
            "a single uniform bronze when seen from the ground far below."
        ),
    },
    {
        "lens_slug": "historic_arch",
        "gravity": 4,
        "script_body": (
            "Gustave Eiffel himself maintained a private apartment at the summit of the "
            "tower where he entertained distinguished guests including Thomas Edison. The "
            "apartment was furnished with velvet settees, a grand piano, and scientific "
            "instruments. Parisians who had mocked the tower as a metal monstrosity begged "
            "for invitations. Eiffel refused nearly all of them, preferring to use the "
            "space for quiet study."
        ),
    },
    {
        "lens_slug": "war_conflict",
        "gravity": 2,
        "script_body": (
            "When the tower was first unveiled, Parisian artists erupted in fury. A "
            "petition signed by Guy de Maupassant, Alexandre Dumas, and Charles Garnier "
            "called it a disgrace, a factory chimney disfiguring the city skyline. The "
            "artists insisted the new iron structure had no place in Paris. Years later "
            "their loud protest slowly faded as the public embraced it."
        ),
    },
]

# Taggable lenses — derived from definitions.py (single source of truth)
import contextlib

from src.schema.definitions import DAG_CHILD_LENSES, MVP_LENSES, TAGGABLE_LENSES

LENS_SLUGS = list(TAGGABLE_LENSES)

LENS_DISPLAY_LABELS = {}
for _l in MVP_LENSES:
    if not _l.get("is_parent"):
        LENS_DISPLAY_LABELS[_l["name"]] = _l["display_label"]
for _c in DAG_CHILD_LENSES:
    LENS_DISPLAY_LABELS[_c["name"]] = _c["display_label"]


# ---------------------------------------------------------------------------
# Bug Reporter
# ---------------------------------------------------------------------------


class BugReporter:
    """Accumulates UI issues and generates a markdown bug report."""

    def __init__(self) -> None:
        self.issues: list[dict[str, Any]] = []
        self.tests_run = 0
        self.screenshots: list[str] = []

    def log_issue(
        self,
        severity: str,
        title: str,
        flow: str,
        steps: list[str],
        expected: str,
        actual: str,
        screenshot_path: str | None = None,
    ) -> None:
        self.issues.append(
            {
                "severity": severity,
                "title": title,
                "flow": flow,
                "steps": steps,
                "expected": expected,
                "actual": actual,
                "screenshot": screenshot_path,
            }
        )
        if screenshot_path:
            self.screenshots.append(screenshot_path)

    def increment_tests(self) -> None:
        self.tests_run += 1

    def save_report(self) -> Path:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

        date_str = datetime.now().strftime("%Y-%m-%d")
        report_path = REPORT_DIR / f"workbench-ui-bugs-{date_str}.md"

        critical = sum(1 for i in self.issues if i["severity"] == "Critical")
        major = sum(1 for i in self.issues if i["severity"] == "Major")
        minor = sum(1 for i in self.issues if i["severity"] == "Minor")

        lines = [
            f"# Editorial Workbench UI Bug Report \u2014 {date_str}\n",
            "## Summary\n",
            f"- Tests run: {self.tests_run}",
            f"- Issues found: {len(self.issues)} ({critical} critical, {major} major, {minor} minor)",
            f"- Screenshots captured: {len(self.screenshots)}\n",
        ]

        if not self.issues:
            lines.append("## No issues found \u2014 all checks passed.\n")
        else:
            lines.append("## Issues\n")
            for issue in self.issues:
                lines.append(f"### [{issue['severity']}] {issue['title']}\n")
                lines.append(f"- **Flow:** {issue['flow']}")
                lines.append("- **Steps:**")
                for j, step in enumerate(issue["steps"], 1):
                    lines.append(f"  {j}. {step}")
                lines.append(f"- **Expected:** {issue['expected']}")
                lines.append(f"- **Actual:** {issue['actual']}")
                if issue["screenshot"]:
                    rel = Path(issue["screenshot"]).name
                    lines.append(f"- **Screenshot:** [screenshots/{rel}](screenshots/{rel})")
                lines.append("")

        report_path.write_text("\n".join(lines), encoding="utf-8")
        return report_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _api_request(method: str, path: str, json_data: dict | None = None) -> dict | list | None:
    """Make an API request and return parsed JSON (or None on error)."""
    url = f"{API_BASE}{path}"
    body = None
    headers = {}
    if json_data is not None:
        body = json.dumps(json_data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else None
    except urllib.error.HTTPError as exc:
        return {
            "_error": True,
            "_status": exc.code,
            "_body": exc.read().decode("utf-8", errors="replace"),
        }
    except Exception:
        return None


def _api_get(path: str) -> dict | list | None:
    return _api_request("GET", path)


def _api_post(path: str, json_data: dict | None = None) -> dict | list | None:
    return _api_request("POST", path, json_data)


def _api_delete(path: str) -> dict | list | None:
    return _api_request("DELETE", path)


def _take_screenshot(page: Page, name: str) -> str:
    """Capture a screenshot and return the file path."""
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%H%M%S")
    path = SCREENSHOT_DIR / f"{name}-{ts}.png"
    page.screenshot(path=str(path), full_page=True)
    return str(path)


def _safe_assert(
    reporter: BugReporter,
    condition: bool,
    severity: str,
    title: str,
    flow: str,
    steps: list[str],
    expected: str,
    actual: str,
    page: Page | None = None,
    screenshot_name: str | None = None,
) -> bool:
    """Assert a real expectation, logging the issue (+ screenshot) AND failing the test.

    Made FATAL 2026-06-14: previously this only recorded to the BugReport and returned
    False, so every check built on it was non-fatal — the suite stayed green even when a
    UI expectation was violated ("green while broken"). It now raises after logging, so a
    recorded issue is a real test failure. No caller depends on the bool return.
    """
    reporter.increment_tests()
    if not condition:
        ss_path = None
        if page and screenshot_name:
            ss_path = _take_screenshot(page, screenshot_name)
        reporter.log_issue(severity, title, flow, steps, expected, actual, ss_path)
        raise AssertionError(f"[{severity}] {title} — expected {expected!r}, got {actual!r}")
    return True


def _load_fixture() -> list[dict]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Fixtures — API Server + Seed Data Setup / Teardown
# ---------------------------------------------------------------------------


def _port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex((host, port)) == 0


def _server_neo4j_port(api_base: str, *, retries: int = 1, delay: float = 0.5) -> int | None:
    """Probe ``{api_base}/healthz`` and return the Neo4j port the API is bound to.

    Returns ``None`` if the server has no ``/healthz`` (a build predating the
    guard) or the probe fails — both of which the caller treats as "unverifiable".
    ``retries`` exists so a server we just started has a grace period to finish
    its FastAPI lifespan startup before we give up.
    """
    url = f"{api_base}/healthz"
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            port = data.get("neo4j_port")
            if port is not None:
                return int(port)
        except Exception:
            pass
        if attempt < retries - 1:
            time.sleep(delay)
    return None


def _assert_server_is_test_db(api_base: str, *, source: str, retries: int = 1) -> None:
    """Fail fast unless the API at ``api_base`` is on the test Neo4j (7688).

    Guards the data-corruption bug where a dev ``make api`` (Neo4j port 7687) is
    already listening on :8000: the suite would otherwise seed test POIs into —
    and assert against — the dev graph (observed: dev POI count 371 → 373).
    ``source`` ('external' / 'managed') is woven into the message so the failure
    says exactly which server was rejected and how to fix it. Raises
    ``RuntimeError`` (mirroring conftest._assert_test_port) so the fixture
    propagates a clear, fatal error.
    """
    port = _server_neo4j_port(api_base, retries=retries)
    if port == TEST_NEO4J_PORT:
        return
    if port is None:
        raise RuntimeError(
            f"API on :8000 ({source}) did not answer GET {api_base}/healthz with a "
            f"Neo4j port, so it cannot be confirmed to point at the test database "
            f"(port {TEST_NEO4J_PORT}). Refusing to seed test data into an unknown "
            f"graph. Stop whatever is on :8000 and re-run (the suite will start its "
            f"own server), or start a test-DB API with `make api-test`."
        )
    raise RuntimeError(
        f"API on :8000 ({source}) is connected to Neo4j port {port}, not the test "
        f"database (port {TEST_NEO4J_PORT}). A dev server (`make api` → 7687) is "
        f"almost certainly running on :8000; reusing it would seed test POIs into "
        f"the dev graph. Stop it, then re-run `make test-workbench` (or use "
        f"`make api-test` for a reusable test-DB server on :8000)."
    )


@pytest.fixture(scope="module")
def api_server():
    """Provide an API server on :8000 that is verified to point at the test DB.

    Reuses an already-running server on :8000 ONLY after /healthz confirms it is
    connected to the test database (port 7688); otherwise it fails fast rather
    than seed a dev/prod graph. A server we start ourselves is verified too,
    proving it inherited the .env.test (7688) config from conftest.
    """
    if _port_open("127.0.0.1", 8000):
        _assert_server_is_test_db(API_BASE, source="external", retries=3)
        yield "external"
        return

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "src.api.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    for _ in range(30):
        if _port_open("127.0.0.1", 8000):
            break
        time.sleep(0.5)
    else:
        proc.terminate()
        pytest.fail("API server failed to start on port 8000 within 15 seconds")

    try:
        # The socket opens before lifespan startup finishes, so give /healthz a
        # grace window. This also proves the managed server connected to 7688.
        _assert_server_is_test_db(API_BASE, source="managed", retries=20)
    except BaseException:
        proc.terminate()
        proc.wait(timeout=5)
        raise

    yield "managed"

    proc.terminate()
    proc.wait(timeout=5)


@pytest.fixture(scope="module")
def reporter():
    """Module-scoped bug reporter shared across all tests."""
    return BugReporter()


@pytest.fixture(scope="module")
def seed_data(api_server):
    """Seed test data into Neo4j via the API server and clean up after all tests."""
    resp = _api_get("/nodes/Lens?limit=1")
    if resp is None:
        pytest.fail(f"API not reachable at {API_BASE} despite server being {api_server}")
    if isinstance(resp, dict) and resp.get("_error"):
        pytest.fail(f"API error: {resp.get('_status')}")

    created_ids: dict[str, list[str]] = {
        "poi": [],
        "beat": [],
        "edge_has_beat": [],
        "edge_tagged_with": [],
        "lens": [],
    }
    lenses_seeded_by_us = False

    def _is_ok(resp: dict | list | None) -> bool:
        if resp is None:
            return False
        return not (isinstance(resp, dict) and resp.get("_error"))

    def _get_id(data: dict) -> str:
        return data.get("id", data.get("_id", ""))

    # --- Check/Seed Lenses (Risk R4) ---
    resp = _api_get("/nodes/Lens?limit=50")
    # API returns {"items": [...], "total": N} — extract the items list
    if _is_ok(resp) and isinstance(resp, dict) and "items" in resp:
        existing_lenses = resp["items"]
    elif _is_ok(resp) and isinstance(resp, list):
        existing_lenses = resp
    else:
        existing_lenses = []
    existing_slugs = set()
    lens_id_map: dict[str, str] = {}

    for lens in existing_lenses:
        # NodeResponse shape: {"id": "...", "labels": [...], "properties": {"name": "slug", ...}}
        props = lens.get("properties", {})
        slug = props.get("name", "") or lens.get("slug") or lens.get("name", "")
        existing_slugs.add(slug)
        lens_id_map[slug] = _get_id(lens)

    missing_slugs = [s for s in LENS_SLUGS if s not in existing_slugs]
    if missing_slugs:
        lenses_seeded_by_us = True
        for slug in missing_slugs:
            label = LENS_DISPLAY_LABELS.get(slug, slug)
            # API expects LensCreate: {"name": slug, "display_label": label}
            data = _api_post("/nodes/Lens", {"name": slug, "display_label": label})
            if _is_ok(data) and isinstance(data, dict):
                lid = _get_id(data)
                lens_id_map[slug] = lid
                created_ids["lens"].append(lid)

    def _create_seed_poi(name: str, lat: float, lng: float, beats: list[dict]) -> str:
        """Create one seed POI plus its beats, HAS_BEAT edges, and lens tags."""
        poi_resp = _api_post(
            "/nodes/POI",
            {
                "name": name,
                "city_name": "Paris",
                "latitude": lat,
                "longitude": lng,
                "short_description": "Seed POI for UI conflict detection tests",
                "importance_tier": 1,
                "trigger_radius": 10,
                "typical_duration_min": 30,
                "kid_friendly": "yes",
            },
        )
        if not _is_ok(poi_resp) or not isinstance(poi_resp, dict):
            pytest.skip(f"Failed to create seed POI {name!r}: {poi_resp}")

        pid = _get_id(poi_resp)
        created_ids["poi"].append(pid)

        for beat_def in beats:
            beat_resp = _api_post(
                "/nodes/NarrativeBeat",
                {
                    "script_body": beat_def["script_body"],
                    "gravity": beat_def["gravity"],
                    "lens": beat_def["lens_slug"],
                },
            )
            if not _is_ok(beat_resp) or not isinstance(beat_resp, dict):
                continue
            bid = _get_id(beat_resp)
            created_ids["beat"].append(bid)

            # Link beat to POI
            edge_resp = _api_post(
                "/edges/HAS_BEAT",
                {
                    "source": {"label": "POI", "id": pid},
                    "target": {"label": "NarrativeBeat", "id": bid},
                },
            )
            if _is_ok(edge_resp) and isinstance(edge_resp, dict):
                created_ids["edge_has_beat"].append(_get_id(edge_resp))

            # Tag beat with lens
            lens_slug = beat_def["lens_slug"]
            if lens_slug in lens_id_map:
                tag_resp = _api_post(
                    "/edges/TAGGED_WITH",
                    {
                        "source": {"label": "NarrativeBeat", "id": bid},
                        "target": {"label": "Lens", "id": lens_id_map[lens_slug]},
                    },
                )
                if _is_ok(tag_resp) and isinstance(tag_resp, dict):
                    created_ids["edge_tagged_with"].append(_get_id(tag_resp))
        return pid

    # --- Create Seed POIs ---
    # 1) Sacré-Cœur: an incoming fixture entry sits at the same GPS with a similar name,
    #    so mergeIncomingIntoDbPois auto-merges it (exercises the merge path).
    # 2) Champ de Mars: same GPS as the incoming Eiffel entry but a dissimilar name, so it
    #    does NOT auto-merge — the conflict test resolves the proximity match as "Same Place"
    #    and walks all five beat-conflict bands against this POI's seeded beats.
    poi_id = _create_seed_poi(SEED_POI_NAME, 48.8867, 2.3431, SEED_BEATS)
    _create_seed_poi(EIFFEL_SEED_NAME, *EIFFEL_SEED_COORDS, EIFFEL_SEED_BEATS)

    yield {
        "poi_id": poi_id,
        "created_ids": created_ids,
        "lens_id_map": lens_id_map,
    }

    # --- Teardown: Clean ALL test data (Risk R3) ---
    # Delete all POIs with "UI Test" prefix
    try:
        resp = _api_get("/nodes/POI?limit=200")
        # API returns {"items": [...]} — extract the items list
        if _is_ok(resp) and isinstance(resp, dict) and "items" in resp:
            poi_list = resp["items"]
        elif _is_ok(resp) and isinstance(resp, list):
            poi_list = resp
        else:
            poi_list = []
        for poi in poi_list:
            props = poi.get("properties", {})
            name = props.get("name", "") or poi.get("name", poi.get("poi_name", ""))
            if name.startswith("UI Test"):
                pid = _get_id(poi)
                if pid:
                    _api_delete(f"/nodes/POI/{pid}")
    except Exception:
        pass

    # Delete lenses we seeded (if any)
    if lenses_seeded_by_us:
        for lid in created_ids["lens"]:
            with contextlib.suppress(Exception):
                _api_delete(f"/nodes/Lens/{lid}")


@pytest.fixture(scope="module")
def browser_page(seed_data, reporter):
    """Launch a headless Chromium browser for the test suite."""
    chromium_path = _find_chromium()
    with sync_playwright() as p:
        launch_opts: dict[str, Any] = {"headless": True, "slow_mo": 300}
        if chromium_path:
            launch_opts["executable_path"] = chromium_path
        browser = p.chromium.launch(**launch_opts)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        yield page, seed_data, reporter
        # Save bug report before closing
        report_path = reporter.save_report()
        print(f"\n\nBug report saved to: {report_path}")
        browser.close()


# ---------------------------------------------------------------------------
# Test: api_server DB-isolation guard (regression for dev-graph seeding)
# ---------------------------------------------------------------------------


def _stub_healthz_server(neo4j_port: int | None):
    """Start a real localhost HTTP server that mimics the API's /healthz.

    If ``neo4j_port`` is None the handler 404s /healthz (a build predating the
    guard). Returns ``(server, base_url)``; caller must ``server.shutdown()``.
    """
    import http.server
    import threading

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.endswith("/healthz") and neo4j_port is not None:
                body = json.dumps(
                    {
                        "status": "ok",
                        "neo4j_uri": f"bolt://localhost:{neo4j_port}",
                        "neo4j_port": neo4j_port,
                        "neo4j_database": "neo4j",
                        "neo4j_connected": True,
                    }
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *args: Any) -> None:  # silence request logging
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}/api/v1"
    return server, base_url


class TestApiServerGuard:
    """Proves api_server refuses to reuse a non-test server on :8000.

    Regression for the data-corruption bug: a dev `make api` (Neo4j port 7687)
    already listening on :8000 was reused by this suite, which then seeded test
    POIs into — and asserted against — the dev graph (observed: 371 → 373).
    These tests need no Neo4j and no browser, so they run fast and always.
    """

    def test_guard_rejects_dev_pointed_server(self):
        server, base = _stub_healthz_server(7687)
        try:
            assert _server_neo4j_port(base) == 7687
            with pytest.raises(RuntimeError, match="7687"):
                _assert_server_is_test_db(base, source="external")
        finally:
            server.shutdown()

    def test_guard_accepts_test_pointed_server(self):
        server, base = _stub_healthz_server(TEST_NEO4J_PORT)
        try:
            assert _server_neo4j_port(base) == TEST_NEO4J_PORT
            # Must NOT raise — a test-DB server (port 7688) is reusable.
            _assert_server_is_test_db(base, source="external")
        finally:
            server.shutdown()

    def test_guard_rejects_server_without_healthz(self):
        # A pre-guard build (no /healthz) is unverifiable -> reject, don't reuse.
        server, base = _stub_healthz_server(None)
        try:
            assert _server_neo4j_port(base) is None
            with pytest.raises(RuntimeError, match="unknown graph"):
                _assert_server_is_test_db(base, source="external")
        finally:
            server.shutdown()


# ---------------------------------------------------------------------------
# Test: City Prompt + JSON Load + Duplicate Resolver (ACs #1-2) — Task 4
# ---------------------------------------------------------------------------


class TestWorkbenchLoadFlow:
    """Tests for initial load: city prompt, JSON load, duplicate resolver, worklist."""

    def test_city_prompt_and_json_load(self, browser_page):
        page, _seed_data, reporter = browser_page
        _load_fixture()

        # --- City Prompt Flow ---
        page.goto(WORKBENCH_URL)
        page.wait_for_load_state("networkidle")

        # Assert city overlay is visible
        overlay = page.locator(CITY_OVERLAY)
        overlay_visible = overlay.is_visible()
        _safe_assert(
            reporter,
            overlay_visible,
            "Critical",
            "City overlay not visible on load",
            "City Prompt",
            ["Navigate to workbench URL"],
            "City overlay (#cityOverlay) is visible",
            f"Overlay visible: {overlay_visible}",
            page,
            "ac1-city-overlay-missing",
        )

        # Type "Paris" and submit
        page.locator(CITY_INPUT).fill("Paris")
        page.locator(CITY_SUBMIT).click()

        # Wait for overlay to close (10s timeout for Nominatim — Risk R2)
        try:
            overlay.wait_for(state="hidden", timeout=15000)
            city_accepted = True
        except Exception:
            city_accepted = False
            _safe_assert(
                reporter,
                False,
                "Critical",
                "City overlay did not close after submitting 'Paris'",
                "City Prompt",
                [
                    "Navigate to workbench URL",
                    "Type 'Paris' into #cityInput",
                    "Click #citySubmitBtn",
                ],
                "Overlay closes within 10s",
                "Overlay still visible after 15s (Nominatim may be slow/down)",
                page,
                "ac1-city-timeout",
            )

        if city_accepted:
            # Verify city label
            label_text = page.locator(CITY_LABEL).text_content() or ""
            _safe_assert(
                reporter,
                "Paris" in label_text,
                "Major",
                "City label does not contain 'Paris'",
                "City Prompt",
                ["Submit 'Paris' city"],
                "'Paris' appears in #cityLabel",
                f"Label text: '{label_text}'",
                page,
                "ac1-city-label",
            )

        # --- JSON Load Flow ---
        # Capture console errors for debugging
        console_errors: list[str] = []
        page.on(
            "console",
            lambda msg: (
                console_errors.append(f"[{msg.type}] {msg.text}") if msg.type == "error" else None
            ),
        )

        # Wait for Load JSON button to be enabled (city geocoding must complete first)
        load_btn = page.locator(LOAD_JSON_BTN)
        with contextlib.suppress(Exception):
            load_btn.wait_for(state="visible", timeout=5000)

        # Use Playwright's file chooser API to properly trigger the file input
        with page.expect_file_chooser() as fc_info:
            load_btn.click()
        file_chooser = fc_info.value
        file_chooser.set_files(str(FIXTURE_PATH))

        # Wait for worklist to populate (or error toast to appear)
        page.wait_for_timeout(3000)

        # Check for errors
        if console_errors:
            _safe_assert(
                reporter,
                False,
                "Critical",
                f"Console errors during JSON load: {'; '.join(console_errors[:3])}",
                "JSON Load",
                ["Load fixture via file chooser"],
                "No console errors",
                f"{len(console_errors)} error(s): {'; '.join(console_errors[:3])}",
                page,
                "ac1-console-errors",
            )

        # Check if error toast appeared (JSON validation failure)
        error_toast = page.locator(ERROR_TOAST)
        if error_toast.count() > 0 and error_toast.first.is_visible():
            toast_text = error_toast.first.text_content() or ""
            _safe_assert(
                reporter,
                False,
                "Critical",
                f"Error toast appeared during JSON load: {toast_text[:200]}",
                "JSON Load",
                ["Load fixture via file chooser"],
                "No error toast",
                f"Toast: {toast_text[:200]}",
                page,
                "ac1-json-error-toast",
            )

        # --- Duplicate Resolver (AC #2) ---
        dup_overlay = page.locator(DUP_OVERLAY)
        try:
            dup_overlay.wait_for(state="visible", timeout=5000)
            dup_visible = True
        except Exception:
            dup_visible = False

        _safe_assert(
            reporter,
            dup_visible,
            "Major",
            "Duplicate resolver overlay did not appear",
            "Duplicate Resolver",
            [
                "Load fixture with entries #6/#7 sharing name 'UI Test — Duplicate Seine Promenade'",
            ],
            "#dupOverlay becomes visible",
            f"Overlay visible: {dup_visible}",
            page,
            "ac2-dup-overlay-missing",
        )

        if dup_visible:
            _take_screenshot(page, "ac2-dup-overlay")

            # Find the rename input for one duplicate entry and rename it
            dup_inputs = page.locator(f"{DUP_OVERLAY} input[data-dup-idx]")
            input_count = dup_inputs.count()

            if input_count >= 2:
                # Rename the second entry
                second_input = dup_inputs.nth(1)
                second_input.clear()
                second_input.fill("UI Test \u2014 Duplicate Seine Promenade (2)")

            # Click resolve
            page.locator(DUP_RESOLVE_BTN).click()

            # Wait for overlay to close
            try:
                dup_overlay.wait_for(state="hidden", timeout=5000)
                dup_resolved = True
            except Exception:
                dup_resolved = False

            _safe_assert(
                reporter,
                dup_resolved,
                "Critical",
                "Duplicate resolver overlay did not close after resolve",
                "Duplicate Resolver",
                [
                    "Rename duplicate entry",
                    "Click #dupResolveBtn",
                ],
                "Overlay closes after resolution",
                "Overlay still visible",
                page,
                "ac2-dup-not-resolved",
            )

        # --- Worklist Rendering (AC #1) ---
        # Wait for worklist rows to appear
        page.wait_for_timeout(2000)
        rows = page.locator(WORKLIST_ROW)

        with contextlib.suppress(Exception):
            rows.first.wait_for(state="visible", timeout=5000)

        # .worklist-row counts incoming AND database rows. From the 12-entry fixture, the
        # Sacre-Coeur entry auto-merges into its seeded POI (-> 11 active incoming rows), and
        # the two seeded DB POIs (Sacré-Cœur, Champ de Mars) each render a row: 11 + 2 = 13.
        row_count = rows.count()
        _safe_assert(
            reporter,
            row_count == 13,
            "Critical",
            f"Worklist shows {row_count} POIs instead of 13",
            "Worklist Rendering",
            [
                "Load 12-entry fixture (Sacre-Coeur auto-merges into its seed)",
                "Resolve duplicate names",
                "Check worklist row count (11 incoming + 2 seeded DB rows)",
            ],
            "13 .worklist-row elements visible",
            f"Found {row_count} rows",
            page,
            "ac1-worklist-count",
        )

        _take_screenshot(page, "ac1-worklist-loaded")


# ---------------------------------------------------------------------------
# Test: Detail View, Editing, Badges, Beats (ACs #3-7, #9-12) — Task 5
# ---------------------------------------------------------------------------


class TestDetailViewAndEditing:
    """Tests for POI detail rendering, editing, badges, and beat cards."""

    def test_detail_view_rendering(self, browser_page):
        """AC #3: Click each POI and verify detail view renders correct field values."""
        page, _seed_data, reporter = browser_page
        fixture = _load_fixture()

        rows = page.locator(WORKLIST_ROW)
        row_count = rows.count()

        for i in range(min(row_count, 12)):
            row = rows.nth(i)
            row.click()
            page.wait_for_timeout(500)

            # Get the POI index from the worklist row
            poi_idx = row.get_attribute("data-poi-idx")
            if poi_idx is None:
                continue

            idx = int(poi_idx)
            if idx >= len(fixture):
                continue

            expected_poi = fixture[idx]

            # Check POI name field
            name_field = page.locator(DATA_FIELD.format("poi_name"))
            if name_field.count() > 0:
                actual_name = name_field.first.input_value()
                expected_name = expected_poi["poi_name"]
                _safe_assert(
                    reporter,
                    actual_name == expected_name,
                    "Major",
                    f"POI name mismatch for entry #{idx + 1}",
                    "Detail View",
                    [
                        f"Click worklist row #{i + 1} (poi_idx={idx})",
                        "Check [data-field='poi_name'] value",
                    ],
                    f"Name: '{expected_name}'",
                    f"Name: '{actual_name}'",
                    page,
                    f"ac3-name-mismatch-{idx}",
                )

            # Check latitude
            lat_field = page.locator(DATA_FIELD.format("latitude"))
            if lat_field.count() > 0:
                actual_lat = lat_field.first.input_value()
                expected_lat = str(expected_poi["latitude"])
                _safe_assert(
                    reporter,
                    actual_lat == expected_lat,
                    "Major",
                    f"Latitude mismatch for entry #{idx + 1}",
                    "Detail View",
                    [f"Check latitude for '{expected_poi['poi_name']}'"],
                    f"Lat: {expected_lat}",
                    f"Lat: {actual_lat}",
                    page,
                    f"ac3-lat-mismatch-{idx}",
                )

            # Check longitude
            lng_field = page.locator(DATA_FIELD.format("longitude"))
            if lng_field.count() > 0:
                actual_lng = lng_field.first.input_value()
                expected_lng = str(expected_poi["longitude"])
                _safe_assert(
                    reporter,
                    actual_lng == expected_lng,
                    "Major",
                    f"Longitude mismatch for entry #{idx + 1}",
                    "Detail View",
                    [f"Check longitude for '{expected_poi['poi_name']}'"],
                    f"Lng: {expected_lng}",
                    f"Lng: {actual_lng}",
                    page,
                    f"ac3-lng-mismatch-{idx}",
                )

        reporter.increment_tests()

    def test_geofence_flag(self, browser_page):
        """AC #4: Outside-geofence POI shows flagged badge and yellow warning."""
        page, _seed_data, reporter = browser_page

        # Find entry #4 (Times Square — outside geofence)
        # It has poi_name "UI Test — Times Square Billboard"
        rows = page.locator(WORKLIST_ROW)
        found = False

        for i in range(rows.count()):
            row = rows.nth(i)
            row_text = row.text_content() or ""
            if "Tower of London" in row_text:
                # Check for flagged badge in worklist
                flagged_badge = row.locator(BADGE_FLAGGED)
                has_flagged = flagged_badge.count() > 0 and flagged_badge.first.is_visible()
                _safe_assert(
                    reporter,
                    has_flagged,
                    "Major",
                    "Outside-geofence POI missing flagged badge",
                    "Geofence Detection",
                    [
                        "Load fixture with entry #4 (New York coords)",
                        "Check worklist row for .badge-flagged",
                    ],
                    ".badge-flagged visible on worklist row",
                    f"Badge visible: {has_flagged}",
                    page,
                    "ac4-no-flagged-badge",
                )

                # Click to open detail
                row.click()
                page.wait_for_timeout(500)

                # Check for geofence warning in map area
                geofence_warn = page.locator(MAP_WARN_GEOFENCE)
                warn_visible = geofence_warn.count() > 0 and geofence_warn.first.is_visible()
                _safe_assert(
                    reporter,
                    warn_visible,
                    "Minor",
                    "No geofence warning in detail view for outside-geofence POI",
                    "Geofence Detection",
                    [
                        "Click outside-geofence POI",
                        "Check for .map-warn-geofence element",
                    ],
                    "Yellow geofence warning visible in map area",
                    f"Warning visible: {warn_visible}",
                    page,
                    "ac4-no-geofence-warning",
                )

                _take_screenshot(page, "ac4-geofence")
                found = True
                break

        if not found:
            _safe_assert(
                reporter,
                False,
                "Critical",
                "Could not find Tower of London POI in worklist",
                "Geofence Detection",
                ["Search worklist for 'Tower of London'"],
                "Entry #4 found in worklist",
                "Not found",
                page,
                "ac4-poi-not-found",
            )

    def test_invalid_coords(self, browser_page):
        """AC #5: Invalid-coords POI shows field warnings and blocks upload."""
        page, _seed_data, reporter = browser_page

        rows = page.locator(WORKLIST_ROW)
        found = False

        for i in range(rows.count()):
            row = rows.nth(i)
            row_text = row.text_content() or ""
            if "Invalid Location" in row_text:
                row.click()
                page.wait_for_timeout(500)

                # Check for field warnings near lat/lng
                warnings = page.locator(FIELD_WARNING)
                warn_count = warnings.count()
                _safe_assert(
                    reporter,
                    warn_count >= 1,
                    "Major",
                    "No field warnings for invalid coordinates (lat 999, lng -999)",
                    "Coord Validation",
                    [
                        "Click invalid-coords POI (entry #5)",
                        "Check for .field-warning elements",
                    ],
                    ".field-warning visible near coordinate fields",
                    f"Found {warn_count} warnings",
                    page,
                    "ac5-no-coord-warnings",
                )

                # Check map warning
                map_warn = page.locator(MAP_WARNING)
                map_warn_visible = False
                for j in range(map_warn.count()):
                    text = map_warn.nth(j).text_content() or ""
                    if "Invalid" in text or "removed" in text.lower():
                        map_warn_visible = map_warn.nth(j).is_visible()
                        break

                _safe_assert(
                    reporter,
                    map_warn_visible,
                    "Minor",
                    "Map does not show 'Invalid coordinates' message",
                    "Coord Validation",
                    ["Check map area for invalid coords message"],
                    "'Invalid coordinates — pin removed' message visible",
                    f"Map warning visible: {map_warn_visible}",
                    page,
                    "ac5-no-map-warning",
                )

                # Try to click Mark as Complete — should be blocked
                mc_btn = page.locator(MARK_COMPLETE_BTN)
                if mc_btn.count() > 0 and mc_btn.first.is_visible():
                    mc_btn.first.click()
                    page.wait_for_timeout(1000)

                    # Check it didn't actually upload (badge should NOT be uploaded)
                    row_after = rows.nth(i)
                    uploaded = row_after.locator(BADGE_UPLOADED)
                    was_blocked = uploaded.count() == 0 or not uploaded.first.is_visible()
                    _safe_assert(
                        reporter,
                        was_blocked,
                        "Critical",
                        "Invalid-coords POI was uploaded despite invalid coordinates",
                        "Coord Validation",
                        [
                            "Click Mark as Complete on invalid-coords POI",
                        ],
                        "Upload blocked — POI stays in non-uploaded state",
                        "POI appears to have been uploaded",
                        page,
                        "ac5-invalid-uploaded",
                    )

                _take_screenshot(page, "ac5-invalid-coords")
                found = True
                break

        if not found:
            _safe_assert(
                reporter,
                False,
                "Critical",
                "Could not find Invalid Location POI in worklist",
                "Coord Validation",
                ["Search worklist for 'Invalid Location'"],
                "Entry #5 found in worklist",
                "Not found",
                page,
                "ac5-poi-not-found",
            )

    def test_edit_persistence(self, browser_page):
        """AC #6: Edits persist when navigating away and back."""
        page, _seed_data, reporter = browser_page

        rows = page.locator(WORKLIST_ROW)
        if rows.count() < 2:
            _safe_assert(
                reporter,
                False,
                "Critical",
                "Not enough worklist rows for edit persistence test",
                "Edit Persistence",
                ["Need at least 2 POIs in worklist"],
                "2+ POIs available",
                f"Found {rows.count()}",
            )
            return

        # Click first valid POI (entry #1 — "Seine River Lighthouse")
        first_row = None
        second_row = None
        for i in range(rows.count()):
            row_text = rows.nth(i).text_content() or ""
            if "Seine Lighthouse" in row_text and first_row is None:
                first_row = i
            elif first_row is not None and second_row is None:
                second_row = i
                break

        if first_row is None or second_row is None:
            # Fallback to first two rows
            first_row, second_row = 0, 1

        # Navigate to first POI
        rows.nth(first_row).click()
        page.wait_for_timeout(500)

        # Edit POI name
        name_field = page.locator(DATA_FIELD.format("poi_name"))
        original_name = name_field.first.input_value() if name_field.count() > 0 else ""
        edited_name = original_name + " (EDITED)"
        if name_field.count() > 0:
            name_field.first.clear()
            name_field.first.fill(edited_name)
            # Trigger input event for auto-save
            name_field.first.dispatch_event("input")

        # Edit a beat's script_body
        beat_script = page.locator(DATA_BEAT_FIELD.format("script_body"))
        original_script = ""
        edited_script = ""
        if beat_script.count() > 0:
            original_script = beat_script.first.input_value()
            edited_script = original_script + " EDIT_MARKER"
            beat_script.first.clear()
            beat_script.first.fill(edited_script)
            beat_script.first.dispatch_event("input")

        page.wait_for_timeout(300)

        # Navigate to second POI
        rows.nth(second_row).click()
        page.wait_for_timeout(500)

        # Navigate back to first POI
        rows.nth(first_row).click()
        page.wait_for_timeout(500)

        # Verify edits persisted
        name_field = page.locator(DATA_FIELD.format("poi_name"))
        if name_field.count() > 0:
            current_name = name_field.first.input_value()
            _safe_assert(
                reporter,
                current_name == edited_name,
                "Major",
                "POI name edit did not persist after navigation",
                "Edit Persistence",
                [
                    "Edit POI name",
                    "Navigate to different POI",
                    "Navigate back",
                    "Check POI name",
                ],
                f"Name: '{edited_name}'",
                f"Name: '{current_name}'",
                page,
                "ac6-name-not-persisted",
            )

        beat_script = page.locator(DATA_BEAT_FIELD.format("script_body"))
        if beat_script.count() > 0 and edited_script:
            current_script = beat_script.first.input_value()
            _safe_assert(
                reporter,
                "EDIT_MARKER" in current_script,
                "Major",
                "Beat script_body edit did not persist after navigation",
                "Edit Persistence",
                [
                    "Edit beat script_body",
                    "Navigate away and back",
                    "Check script_body",
                ],
                "Script contains 'EDIT_MARKER'",
                f"Script: '{current_script[:80]}...'",
                page,
                "ac6-script-not-persisted",
            )

        # Restore original values to not pollute later tests
        if name_field.count() > 0 and original_name:
            name_field.first.clear()
            name_field.first.fill(original_name)
            name_field.first.dispatch_event("input")
        if beat_script.count() > 0 and original_script:
            beat_script.first.clear()
            beat_script.first.fill(original_script)
            beat_script.first.dispatch_event("input")

        _take_screenshot(page, "ac6-edit-persistence")

    def test_defer_and_reselect(self, browser_page):
        """AC #7: Defer a POI, badge changes to deferred, re-select and complete."""
        page, _seed_data, reporter = browser_page

        # Wait for worklist rows to be available
        rows = page.locator(WORKLIST_ROW)
        try:
            rows.first.wait_for(state="visible", timeout=5000)
        except Exception:
            _safe_assert(
                reporter,
                False,
                "Critical",
                "No worklist rows available for defer test",
                "Defer Flow",
                ["Wait for .worklist-row elements"],
                "Worklist rows visible",
                f"Count: {rows.count()}",
                page,
                "ac7-no-rows",
            )
            return

        # Find entry #3 (Quiet Garden Corner)
        target_row = None
        for i in range(rows.count()):
            row_text = rows.nth(i).text_content() or ""
            if "Quiet Garden" in row_text:
                target_row = i
                break

        if target_row is None:
            target_row = 2 if rows.count() > 2 else 0

        rows.nth(target_row).click()
        page.wait_for_timeout(500)

        # Click Defer
        defer_btn = page.locator(DEFER_BTN)
        if defer_btn.count() > 0 and defer_btn.first.is_visible():
            defer_btn.first.click()
            page.wait_for_timeout(500)

            # Check badge changed to deferred
            row = rows.nth(target_row)
            deferred_badge = row.locator(BADGE_DEFERRED)
            has_deferred = deferred_badge.count() > 0

            # Worklist may re-sort, find the row again
            if not has_deferred:
                page.wait_for_timeout(500)
                rows = page.locator(WORKLIST_ROW)
                for j in range(rows.count()):
                    rt = rows.nth(j).text_content() or ""
                    if "Quiet Garden" in rt or "Deferred" in rt:
                        deferred_badge = rows.nth(j).locator(BADGE_DEFERRED)
                        has_deferred = deferred_badge.count() > 0
                        target_row = j
                        break

            _safe_assert(
                reporter,
                has_deferred,
                "Major",
                "POI badge did not change to 'deferred' after clicking Defer",
                "Defer Flow",
                [
                    "Click entry #3 (Quiet Garden)",
                    "Click #deferBtn",
                    "Check for .badge-deferred",
                ],
                ".badge-deferred visible on worklist row",
                f"Badge found: {has_deferred}",
                page,
                "ac7-no-deferred-badge",
            )

            _take_screenshot(page, "ac7-deferred")

            # Re-select the deferred POI
            rows.nth(target_row).click()
            page.wait_for_timeout(500)

            _take_screenshot(page, "ac7-reselected")
        else:
            _safe_assert(
                reporter,
                False,
                "Critical",
                "Defer button not visible",
                "Defer Flow",
                ["Navigate to POI", "Look for #deferBtn"],
                "Defer button visible",
                "Button not found or not visible",
                page,
                "ac7-no-defer-btn",
            )

    def test_beat_rendering(self, browser_page):
        """ACs #9, #10, #12: Beat cards render all fields, multi-lens POI renders all beats."""
        page, _seed_data, reporter = browser_page
        _load_fixture()

        # Find multi-lens POI (entry #8 — Marché des Enfants Rouges, 4 beats)
        rows = page.locator(WORKLIST_ROW)
        for i in range(rows.count()):
            row_text = rows.nth(i).text_content() or ""
            if "Les Halles Multi-Lens" in row_text:
                rows.nth(i).click()
                page.wait_for_timeout(500)

                # AC #10: Check beat card count
                beats = page.locator(BEAT_CARD)
                beat_count = beats.count()
                _safe_assert(
                    reporter,
                    beat_count == 4,
                    "Major",
                    f"Multi-lens POI shows {beat_count} beat cards instead of 4",
                    "Beat Rendering",
                    [
                        "Click the Les Halles Multi-Lens POI (4 beats)",
                        "Count .beat-card elements",
                    ],
                    "4 beat cards rendered",
                    f"{beat_count} beat cards found",
                    page,
                    "ac10-beat-count",
                )

                # AC #9: Check each beat card has all 5 fields
                for bi in range(beat_count):
                    beat = beats.nth(bi)
                    for field in [
                        "script_body",
                        "physical_cue",
                        "lens",
                        "gravity",
                        "source_passage",
                    ]:
                        field_el = beat.locator(DATA_BEAT_FIELD.format(field))
                        has_field = field_el.count() > 0
                        _safe_assert(
                            reporter,
                            has_field,
                            "Major",
                            f"Beat #{bi + 1} missing field: {field}",
                            "Beat Rendering",
                            [
                                f"Check beat card #{bi + 1} for [data-beat-field='{field}']",
                            ],
                            f"Field '{field}' present in beat card",
                            "Field not found",
                            page,
                            f"ac9-missing-field-{field}-beat{bi}",
                        )

                # Check lens dropdown has 16 taggable options
                lens_selects = page.locator(DATA_BEAT_FIELD.format("lens"))
                if lens_selects.count() > 0:
                    options = lens_selects.first.locator("option")
                    option_count = options.count()
                    # Expect 16 taggable lens options + 1 "Select lens..." placeholder = 17
                    _safe_assert(
                        reporter,
                        option_count >= 16,
                        "Major",
                        f"Lens dropdown has {option_count} options instead of 16+",
                        "Beat Rendering",
                        ["Check lens select option count"],
                        "16+ options in lens dropdown",
                        f"{option_count} options found",
                        page,
                        "ac9-lens-count",
                    )

                # AC #12: Check beat count header
                beats_header = page.locator("h3:has-text('Narrative Beats')")
                if beats_header.count() > 0:
                    header_text = beats_header.first.text_content() or ""
                    _safe_assert(
                        reporter,
                        "(4)" in header_text,
                        "Minor",
                        f"Beat count header says '{header_text}' instead of containing '(4)'",
                        "Beat Rendering",
                        ["Check h3 text for beat count"],
                        "'Narrative Beats (4)' in header",
                        f"Header: '{header_text}'",
                        page,
                        "ac12-beat-header",
                    )

                _take_screenshot(page, "ac9-10-12-beats")
                break

    def test_beat_editing(self, browser_page):
        """AC #11: Beat lens and gravity edits persist after navigation."""
        page, _seed_data, reporter = browser_page

        rows = page.locator(WORKLIST_ROW)

        # Navigate to multi-lens POI (Marché des Enfants Rouges)
        target = None
        other = None
        for i in range(rows.count()):
            row_text = rows.nth(i).text_content() or ""
            if "Les Halles Multi-Lens" in row_text:
                target = i
            elif target is not None and other is None:
                other = i

        if target is None:
            return
        if other is None:
            other = (target + 1) % rows.count()

        rows.nth(target).click()
        page.wait_for_timeout(500)

        # Change first beat's gravity
        gravity_fields = page.locator(DATA_BEAT_FIELD.format("gravity"))
        if gravity_fields.count() > 0:
            original_gravity = gravity_fields.first.input_value()
            new_gravity = "3" if original_gravity != "3" else "4"
            gravity_fields.first.clear()
            gravity_fields.first.fill(new_gravity)
            gravity_fields.first.dispatch_event("input")

            page.wait_for_timeout(300)

            # Navigate away and back
            rows.nth(other).click()
            page.wait_for_timeout(500)
            rows.nth(target).click()
            page.wait_for_timeout(500)

            # Verify gravity persisted
            gravity_fields = page.locator(DATA_BEAT_FIELD.format("gravity"))
            if gravity_fields.count() > 0:
                current_gravity = gravity_fields.first.input_value()
                _safe_assert(
                    reporter,
                    current_gravity == new_gravity,
                    "Major",
                    "Beat gravity edit did not persist after navigation",
                    "Beat Editing",
                    [
                        f"Change gravity from {original_gravity} to {new_gravity}",
                        "Navigate away and back",
                        "Check gravity value",
                    ],
                    f"Gravity: {new_gravity}",
                    f"Gravity: {current_gravity}",
                    page,
                    "ac11-gravity-not-persisted",
                )

                # Restore
                gravity_fields.first.clear()
                gravity_fields.first.fill(original_gravity)
                gravity_fields.first.dispatch_event("input")

        _take_screenshot(page, "ac11-beat-edit")

    def test_beat_tts_play_decodes_audio(self, browser_page):
        """Characterize beat-TTS BEFORE the COMPOSE-era refactor: clicking a beat's
        Listen button POSTs /audio/preview (mock provider) and the <audio> actually
        DECODES (readyState>=2) from a blob: URL. Pins ttsPlayBeat's real behavior so
        the later ttsPlay-core extraction provably preserves it. Hard asserts (this
        must bite); real browser + real network, no string-grep."""
        page, _seed_data, _reporter = browser_page

        # Select the multi-lens POI that carries 4 beats with non-empty scripts
        # (verified present in tests/fixtures/ui_test_fixture.json this session).
        rows = page.locator(WORKLIST_ROW)
        selected = False
        for i in range(rows.count()):
            if "Les Halles Multi-Lens" in (rows.nth(i).text_content() or ""):
                rows.nth(i).click()
                page.wait_for_timeout(500)
                selected = True
                break
        assert selected, "expected the 'UI Test — Les Halles Multi-Lens' POI in the worklist"

        # Use the deterministic offline 'mock' provider (silent WAV, no API key).
        page.select_option("#ttsProviderSelect", "mock")

        # First beat whose Listen button is enabled (non-empty script_body).
        play_buttons = page.locator(f"{BEAT_CARD} .tts-play-btn:not([disabled])")
        assert play_buttons.count() > 0, "expected at least one beat with a playable script"
        btn = play_buttons.first
        beat_idx = btn.get_attribute("data-beat-tts")
        audio_sel = f'.tts-audio[data-beat-audio="{beat_idx}"]'

        # Clicking Listen must hit /audio/preview for real (cache is empty — no prior
        # test plays TTS); a 200 proves the fetch fired (and is non-vacuous — a cache
        # replay or error would not produce this request).
        with page.expect_response(lambda r: "/audio/preview" in r.url) as resp_info:
            btn.click()
        resp = resp_info.value
        assert resp.status == 200, f"/audio/preview returned {resp.status}"

        # preload='none' => the browser only fetches+decodes after play(); assert the
        # element reaches a blob: src AND HAVE_CURRENT_DATA via polling (this also proves
        # the audio bytes were non-empty + decodable — stronger than reading the raw body,
        # which Playwright can't retrieve once the page has consumed the stream).
        page.wait_for_function(
            "sel => { const el = document.querySelector(sel);"
            " return !!el && el.src.startsWith('blob:') && el.readyState >= 2; }",
            arg=audio_sel,
            timeout=15000,
        )
        _take_screenshot(page, "beat-tts-decode")

    def test_tour_preview_view_opens(self, browser_page):
        """Step 3: the 'Tour Preview' toolbar button opens a native tour-preview form in the
        detail panel — workbench components, empty stops, Mark-Complete/Defer hidden. Real
        browser, hard asserts (the button is enabled once the city is connected)."""
        page, _seed_data, _reporter = browser_page

        btn = page.locator("#tourPreviewBtn")
        assert btn.count() == 1, "expected a #tourPreviewBtn in the left toolbar"
        assert btn.is_enabled(), "Tour Preview button should be enabled after the city connects"
        btn.click()
        page.wait_for_timeout(300)

        # The tour-preview form renders with its inputs (built from workbench components).
        for sel in ("#tourStart", "#tourDuration", "#tourLenses", "#tourRoundTrip", "#tourGenerateBtn"):
            assert page.locator(sel).count() == 1, f"tour-preview form missing {sel}"

        # Empty state: no stops rendered before generating.
        assert page.locator("#tourStops .tour-stop").count() == 0, "expected no stops before generating"

        # Mark Complete / Defer are hidden in tour mode (not applicable to a tour preview).
        assert not page.locator(MARK_COMPLETE_BTN).is_visible(), "Mark Complete must be hidden in tour mode"
        assert not page.locator(DEFER_BTN).is_visible(), "Defer must be hidden in tour mode"
        _take_screenshot(page, "step3-tour-preview-view")

    def test_tour_preview_generates_and_plays(self, browser_page):
        """Step 4: Generate POSTs /trips/preview, renders the stops, and each stop plays via the
        shared ttsPlay (real /audio/preview decode). /trips/preview is mocked (its own API tests
        cover it; the test DB's tier-1 fixture POIs can't produce a tour) — the form->request,
        the render, and the mock-provider audio decode are all REAL."""
        page, _seed_data, _reporter = browser_page
        page.route(
            "**/trips/preview",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "stops": [
                            {"sort_order": 1, "poi_name": "Notre-Dame", "minutes": 5,
                             "narration": "Settle in. A grounded opening line."},
                            {"sort_order": 2, "poi_name": "Sainte-Chapelle", "minutes": 4,
                             "narration": "Walk on. Another grounded line."},
                        ],
                        "spine_area": "Île de la Cité",
                        "total_audio_min": 9,
                    }
                ),
            ),
        )
        try:
            page.locator("#tourPreviewBtn").click()
            page.wait_for_timeout(300)
            page.select_option("#ttsProviderSelect", "mock")
            page.locator("#tourStart").fill("48.8566,2.3522")
            with page.expect_response(lambda r: "/trips/preview" in r.url) as ri:
                page.locator("#tourGenerateBtn").click()
            assert ri.value.status == 200
            page.wait_for_timeout(300)

            stops = page.locator("#tourStops .tour-stop")
            assert stops.count() == 2, f"expected 2 rendered stops, got {stops.count()}"
            assert "Notre-Dame" in (stops.first.text_content() or ""), "stop name not rendered"

            # Play stop 0 through the shared player -> real POST /audio/preview + real decode.
            with page.expect_response(lambda r: "/audio/preview" in r.url) as ar:
                stops.first.locator('.tts-play-btn[data-tour-stop]').click()
            assert ar.value.status == 200
            page.wait_for_function(
                "sel => { const el = document.querySelector(sel);"
                " return !!el && el.src.startsWith('blob:') && el.readyState >= 2; }",
                arg='.tts-audio[data-tour-stop-audio="0"]',
                timeout=15000,
            )
            _take_screenshot(page, "step4-tour-generate-play")
        finally:
            page.unroute("**/trips/preview")

    def test_tour_preview_untourable_shows_error(self, browser_page):
        """Step 4: a 422 from /trips/preview surfaces an error toast (no silent failure)."""
        page, _seed_data, _reporter = browser_page
        page.route(
            "**/trips/preview",
            lambda route: route.fulfill(
                status=422,
                content_type="application/json",
                body=json.dumps({"detail": "No tourable route from here."}),
            ),
        )
        try:
            page.locator("#tourPreviewBtn").click()
            page.wait_for_timeout(300)
            page.locator("#tourStart").fill("48.8566,2.3522")
            with page.expect_response(lambda r: "/trips/preview" in r.url) as ri:
                page.locator("#tourGenerateBtn").click()
            assert ri.value.status == 422
            page.wait_for_timeout(300)
            assert page.locator(ERROR_TOAST).is_visible(), "expected an error toast on an untourable 422"
        finally:
            page.unroute("**/trips/preview")

    def _route_tour_preview(self, page, stops):
        """Helper: mock POST /trips/preview with the given stops payload."""
        page.route(
            "**/trips/preview",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {"stops": stops, "spine_area": "Île de la Cité",
                     "total_audio_min": sum(s.get("minutes", 0) for s in stops)}
                ),
            ),
        )

    def test_tour_stop_audio_caches_on_replay(self, browser_page):
        """Step 5 (edge): replaying a stop reuses the cached blob (no 2nd /audio/preview), and
        re-generating does NOT stack the delegated listener (a stacked one fires 2 fetches/click).
        One delegated listener + the shared ttsAudioCache are the two correctness properties here."""
        page, _seed_data, _reporter = browser_page
        # UNIQUE narration: browser_page is module-scoped, so ttsAudioCache persists across
        # tests. A narration reused by an earlier test would be a cache HIT on the "first"
        # play here (no fetch). These strings are unique to this test -> first play is a
        # guaranteed miss, replay a guaranteed hit, regardless of run order.
        self._route_tour_preview(
            page,
            [{"sort_order": 1, "poi_name": "Notre-Dame", "minutes": 5,
              "narration": "Cache-replay edge test — unique opening line for stop zero."},
             {"sort_order": 2, "poi_name": "Sainte-Chapelle", "minutes": 4,
              "narration": "Cache-replay edge test — unique line for stop one."}],
        )
        audio_calls = []
        page.on("request", lambda r: audio_calls.append(r.url) if "/audio/preview" in r.url else None)
        try:
            page.locator("#tourPreviewBtn").click()
            page.wait_for_timeout(300)
            page.select_option("#ttsProviderSelect", "mock")
            page.locator("#tourStart").fill("48.8566,2.3522")
            # Generate TWICE — the second re-render must not duplicate the delegated listener.
            for _ in range(2):
                with page.expect_response(lambda r: "/trips/preview" in r.url):
                    page.locator("#tourGenerateBtn").click()
                page.wait_for_timeout(200)
            stops = page.locator("#tourStops .tour-stop")
            assert stops.count() == 2, f"expected 2 stops after re-generate, got {stops.count()}"

            # First play of stop 0 -> exactly ONE /audio/preview (proves no stacked listener).
            with page.expect_response(lambda r: "/audio/preview" in r.url) as ar:
                stops.first.locator('.tts-play-btn[data-tour-stop]').click()
            assert ar.value.status == 200
            page.wait_for_function(
                "sel => { const el = document.querySelector(sel);"
                " return !!el && el.src.startsWith('blob:') && el.readyState >= 2; }",
                arg='.tts-audio[data-tour-stop-audio="0"]', timeout=15000)
            first_src = page.locator('.tts-audio[data-tour-stop-audio="0"]').get_attribute("src")
            assert len(audio_calls) == 1, f"expected 1 /audio/preview, got {len(audio_calls)} (listener stacked?)"

            # Replay stop 0 -> cache hit: same blob, NO new /audio/preview.
            stops.first.locator('.tts-play-btn[data-tour-stop]').click()
            page.wait_for_timeout(800)
            assert len(audio_calls) == 1, f"replay refetched ({len(audio_calls)} calls) — cache miss"
            assert page.locator('.tts-audio[data-tour-stop-audio="0"]').get_attribute("src") == first_src
            _take_screenshot(page, "step5-tour-cache-replay")
        finally:
            page.unroute("**/trips/preview")

    def test_tour_stop_long_narration_plays(self, browser_page):
        """Step 5 (edge): a long stop narration (> the 4096 TTS cap) plays through the chunked
        /audio/preview path and decodes — the UI passes the full text, no client truncation."""
        page, _seed_data, _reporter = browser_page
        long_narration = ("Settle in by the river. " * 260).strip()  # ~6000 chars, > 4096 cap
        assert len(long_narration) > 4096
        self._route_tour_preview(
            page,
            [{"sort_order": 1, "poi_name": "Notre-Dame", "minutes": 9,
              "narration": long_narration}],
        )
        try:
            page.locator("#tourPreviewBtn").click()
            page.wait_for_timeout(300)
            page.select_option("#ttsProviderSelect", "mock")
            page.locator("#tourStart").fill("48.8566,2.3522")
            with page.expect_response(lambda r: "/trips/preview" in r.url):
                page.locator("#tourGenerateBtn").click()
            page.wait_for_timeout(300)
            stops = page.locator("#tourStops .tour-stop")
            assert stops.count() == 1
            with page.expect_response(lambda r: "/audio/preview" in r.url) as ar:
                stops.first.locator('.tts-play-btn[data-tour-stop]').click()
            assert ar.value.status == 200, "long narration should chunk + return 200, not 422"
            page.wait_for_function(
                "sel => { const el = document.querySelector(sel);"
                " return !!el && el.src.startsWith('blob:') && el.readyState >= 2; }",
                arg='.tts-audio[data-tour-stop-audio="0"]', timeout=20000)
            _take_screenshot(page, "step5-tour-long-narration")
        finally:
            page.unroute("**/trips/preview")

    def test_tour_view_then_back_to_poi_restores_workbench(self, browser_page):
        """Step 6 (seamless): the tour view lives IN the existing detail pane — switching to it and
        back to a normal POI restores the standard workbench detail with no state leak (the tour
        form + tour stops are gone; the POI's beat cards return). Proves it's built as part of the
        workbench, not a bolted-on panel."""
        page, _seed_data, _reporter = browser_page
        page.locator("#tourPreviewBtn").click()
        page.wait_for_timeout(300)
        assert page.locator("#tourGenerateBtn").is_visible(), "tour form should be in the detail pane"
        assert not page.locator(MARK_COMPLETE_BTN).is_visible(), "tour view must hide Mark Complete"

        # Switch back to a normal POI — the same detail pane re-renders the standard view.
        rows = page.locator(WORKLIST_ROW)
        selected = False
        for i in range(rows.count()):
            if "Les Halles Multi-Lens" in (rows.nth(i).text_content() or ""):
                rows.nth(i).click()
                page.wait_for_timeout(500)
                selected = True
                break
        assert selected, "expected the 'UI Test — Les Halles Multi-Lens' POI in the worklist"

        assert page.locator("#tourGenerateBtn").count() == 0, "tour form leaked into the POI view"
        assert page.locator("#tourStops").count() == 0, "tour stops leaked into the POI view"
        assert page.locator(BEAT_CARD).count() > 0, "standard POI beat cards should re-render"
        _take_screenshot(page, "step6-tour-back-to-poi")

    def test_tour_preview_ab_destination_sends_end_and_renders(self, browser_page):
        """A→B (Phase 2): filling Destination sends end_lat/end_lng to /trips/preview and the
        rendered route ends at the destination. /trips/preview mocked (the engine path is unit-
        + API-tested; the test DB can't produce a real tour) — the form->request->render is REAL."""
        page, _seed_data, _reporter = browser_page
        captured = {}

        def _handler(route):
            captured["body"] = route.request.post_data
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "stops": [
                            {"sort_order": 1, "poi_name": "Hotel de Ville", "minutes": 5,
                             "lat": 48.8564, "lng": 2.3522, "narration": "Start the walk here."},
                            {"sort_order": 2, "poi_name": "Destination", "minutes": 0,
                             "lat": 48.8606, "lng": 2.3376, "narration": "End the walk here, or carry on."},
                        ],
                        "spine_area": "Île de la Cité",
                        "total_audio_min": 5,
                    }
                ),
            )

        page.route("**/trips/preview", _handler)
        try:
            page.locator("#tourPreviewBtn").click()
            page.wait_for_timeout(300)
            page.locator("#tourStart").fill("48.8566,2.3522")
            page.locator("#tourEnd").fill("48.8606,2.3376")
            with page.expect_response(lambda r: "/trips/preview" in r.url):
                page.locator("#tourGenerateBtn").click()
            page.wait_for_timeout(300)

            # The request carried the destination (A→B), not just a center.
            assert captured.get("body"), "no /trips/preview request body captured"
            sent = json.loads(captured["body"])
            assert sent.get("end_lat") == 48.8606, f"end_lat not sent: {sent}"
            assert sent.get("end_lng") == 2.3376, f"end_lng not sent: {sent}"

            stops = page.locator("#tourStops .tour-stop")
            assert stops.count() == 2, f"expected 2 stops, got {stops.count()}"
            assert "Destination" in (stops.last.text_content() or ""), "route must end at the Destination"
            # The A→B route is drawn on the persistent map: a connecting line + numbered pins.
            route = page.evaluate("() => window.__lastTourRoute")
            assert route and route.get("stops") == 2 and route.get("line") is True, (
                f"route not drawn on the map: {route}"
            )
            assert page.locator(".tour-route-pin").count() == 2, "expected 2 numbered route pins on the map"
            _take_screenshot(page, "ab-destination-route")
        finally:
            page.unroute("**/trips/preview")

    def test_tour_preview_ab_infeasible_shows_alternatives(self, browser_page):
        """A→B over budget: the Step-2.6 structured 422 renders readable loop/extend/closer_b
        alternatives in the stops area — never a raw JSON dump."""
        page, _seed_data, _reporter = browser_page
        page.route(
            "**/trips/preview",
            lambda route: route.fulfill(
                status=422,
                content_type="application/json",
                body=json.dumps(
                    {"detail": {
                        "reason": "Destination unreachable in 90 min: routed A→B leg exceeds walk budget by 2 min.",
                        "gap_minutes": 2,
                        "alternatives": [
                            {"kind": "loop", "duration_min": 90, "drop_end": True,
                             "poi_id": None, "lat": None, "lng": None},
                            {"kind": "extend", "duration_min": 95, "drop_end": False,
                             "poi_id": None, "lat": None, "lng": None},
                            {"kind": "closer_b", "duration_min": 90, "drop_end": True,
                             "poi_id": "p1", "lat": 48.8558, "lng": 2.3458},
                        ],
                    }}
                ),
            ),
        )
        try:
            page.locator("#tourPreviewBtn").click()
            page.wait_for_timeout(300)
            page.locator("#tourStart").fill("48.8566,2.3522")
            page.locator("#tourEnd").fill("48.8606,2.3376")
            with page.expect_response(lambda r: "/trips/preview" in r.url) as ri:
                page.locator("#tourGenerateBtn").click()
            assert ri.value.status == 422
            page.wait_for_timeout(300)

            refusal = page.locator("#tourStops .tour-refusal")
            assert refusal.count() == 1, "the structured refusal should render in #tourStops"
            txt = refusal.first.text_content() or ""
            assert "unreachable" in txt.lower(), "the refusal reason should be shown"
            assert "Extend to 95 min" in txt, "the extend alternative should be readable"
            assert "closer destination" in txt.lower(), "the closer_b alternative should be shown"
            assert "{" not in txt, "must not dump raw JSON to the user"
            # A refusal means no route — the map route is cleared.
            route = page.evaluate("() => window.__lastTourRoute")
            assert route and route.get("stops") == 0, f"route should be cleared on a refusal: {route}"
            _take_screenshot(page, "ab-infeasible-alternatives")
        finally:
            page.unroute("**/trips/preview")

    def test_tour_preview_surfaces_spotlight_and_coverage(self, browser_page):
        """Phase 3: the workbench shows the spotlight model's user-facing outputs —
        the per-corridor lens_coverage_note and each stop's spotlight score."""
        page, _seed_data, _reporter = browser_page
        page.route(
            "**/trips/preview",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "stops": [
                            {"sort_order": 1, "poi_name": "Notre-Dame", "minutes": 6,
                             "lat": 48.8530, "lng": 2.3499, "narration": "A grounded line.",
                             "spotlight": 5.0, "band": "dwell"},
                            {"sort_order": 2, "poi_name": "Sainte-Chapelle", "minutes": 4,
                             "lat": 48.8554, "lng": 2.3450, "narration": "Another line.",
                             "spotlight": 3.6, "band": "dwell"},
                        ],
                        "spine_area": "Île de la Cité",
                        "total_audio_min": 10,
                        "lens_coverage_note": "Only 2 places on this route speak to film & TV.",
                    }
                ),
            ),
        )
        try:
            page.locator("#tourPreviewBtn").click()
            page.wait_for_timeout(300)
            page.locator("#tourStart").fill("48.8566,2.3522")
            with page.expect_response(lambda r: "/trips/preview" in r.url):
                page.locator("#tourGenerateBtn").click()
            page.wait_for_timeout(300)
            # The per-corridor lens coverage note (Phase 3) is surfaced.
            note = page.locator("#tourStops .tour-lens-coverage")
            assert note.count() == 1, "the lens_coverage_note should render"
            assert "film & TV" in (note.first.text_content() or ""), "coverage note text should show"
            # Each stop shows its spotlight score.
            first = page.locator("#tourStops .tour-stop").first
            assert "spotlight 5.00" in (first.text_content() or ""), "per-stop spotlight should render"
            _take_screenshot(page, "phase3-spotlight-coverage")
        finally:
            page.unroute("**/trips/preview")

    def test_empty_beat_stripped_on_load(self, browser_page):
        """Edge case: Empty script_body beats are stripped during JSON load."""
        page, _seed_data, reporter = browser_page

        rows = page.locator(WORKLIST_ROW)
        for i in range(rows.count()):
            row_text = rows.nth(i).text_content() or ""
            if "Empty Script" in row_text:
                rows.nth(i).click()
                page.wait_for_timeout(500)

                # Empty beats should have been stripped during processJson
                beat_cards = page.locator(BEAT_CARD)
                _safe_assert(
                    reporter,
                    beat_cards.count() == 0,
                    "Major",
                    f"Empty-beat POI still has {beat_cards.count()} beat cards after load",
                    "Edge Cases",
                    [
                        "Click entry #9 (originally had empty script_body)",
                        "Check beat card count — empty beats should be stripped",
                    ],
                    "0 beat cards (empty beat stripped during load)",
                    f"{beat_cards.count()} beat cards found",
                    page,
                    "ec1-empty-not-stripped",
                )

                _take_screenshot(page, "ec1-empty-beat-stripped")
                break

    def test_long_text_no_overflow(self, browser_page):
        """Edge case: Long POI name and description don't overflow containers."""
        page, _seed_data, reporter = browser_page

        rows = page.locator(WORKLIST_ROW)
        for i in range(rows.count()):
            row_text = rows.nth(i).text_content() or ""
            if "Extraordinarily" in row_text:
                # Check worklist row doesn't overflow
                row = rows.nth(i)
                box = row.bounding_box()
                parent = page.locator(".left-panel")
                parent_box = parent.bounding_box() if parent.count() > 0 else None

                if box and parent_box:
                    overflow = box["x"] + box["width"] > parent_box["x"] + parent_box["width"] + 5
                    _safe_assert(
                        reporter,
                        not overflow,
                        "Minor",
                        "Long POI name overflows worklist row container",
                        "Edge Cases",
                        [
                            "Check bounding box of long-name POI row vs parent",
                        ],
                        "Row fits within .left-panel width",
                        f"Row extends {box['x'] + box['width'] - parent_box['x'] - parent_box['width']:.0f}px beyond parent",
                        page,
                        "ec3-overflow",
                    )

                rows.nth(i).click()
                page.wait_for_timeout(500)
                _take_screenshot(page, "ec3-long-text")
                break

    def test_audit_notes_rendering(self, browser_page):
        """Edge case: Audit notes render in correct containers (object + array)."""
        page, _seed_data, reporter = browser_page

        rows = page.locator(WORKLIST_ROW)
        for i in range(rows.count()):
            row_text = rows.nth(i).text_content() or ""
            if "Audited Montmartre" in row_text:
                rows.nth(i).click()
                page.wait_for_timeout(500)

                # Check POI-level audit notes
                poi_notes = page.locator(POI_AUDIT_NOTES_BOX)
                _safe_assert(
                    reporter,
                    poi_notes.count() > 0,
                    "Major",
                    "POI-level audit notes not rendered",
                    "Audit Notes",
                    [
                        "Click the Audited Montmartre POI",
                        "Check for .poi-audit-notes-box",
                    ],
                    ".poi-audit-notes-box present",
                    f"Found {poi_notes.count()} elements",
                    page,
                    "ec4-no-poi-audit",
                )

                # Check beat-level audit notes
                beat_notes = page.locator(AUDIT_NOTES_BOX)
                _safe_assert(
                    reporter,
                    beat_notes.count() > 0,
                    "Major",
                    "Beat-level audit notes not rendered",
                    "Audit Notes",
                    [
                        "Check for .audit-notes-box in beat cards",
                    ],
                    ".audit-notes-box present in beat cards",
                    f"Found {beat_notes.count()} elements",
                    page,
                    "ec4-no-beat-audit",
                )

                _take_screenshot(page, "ec4-audit-notes")
                break

    def test_gravity_boundaries(self, browser_page):
        """Edge case: Gravity 1 and 5 render without validation warnings."""
        page, _seed_data, reporter = browser_page

        rows = page.locator(WORKLIST_ROW)

        # Check high-gravity POI (entry #2 — Les Halles Anchor, gravity 5)
        for i in range(rows.count()):
            row_text = rows.nth(i).text_content() or ""
            if "Les Halles Multi-Lens" in row_text:
                rows.nth(i).click()
                page.wait_for_timeout(500)

                gravity_warnings = page.locator(f"{BEAT_CARD} {BEAT_WARNING}")
                gravity_warn_texts = []
                for j in range(gravity_warnings.count()):
                    text = gravity_warnings.nth(j).text_content() or ""
                    if "gravity" in text.lower() or "Gravity" in text:
                        gravity_warn_texts.append(text)

                _safe_assert(
                    reporter,
                    len(gravity_warn_texts) == 0,
                    "Minor",
                    "Gravity 5 shows validation warning when it shouldn't",
                    "Edge Cases",
                    [
                        "Click high-gravity POI (gravity 5)",
                        "Check for gravity-related .beat-warning",
                    ],
                    "No gravity warnings for valid gravity 5",
                    f"Found warnings: {gravity_warn_texts}",
                    page,
                    "ec2-gravity5-warning",
                )
                break

        # Check low-gravity POI (entry #3 — Quiet Garden, gravity 1)
        for i in range(rows.count()):
            row_text = rows.nth(i).text_content() or ""
            if "Quiet Garden" in row_text:
                rows.nth(i).click()
                page.wait_for_timeout(500)

                gravity_warnings = page.locator(f"{BEAT_CARD} {BEAT_WARNING}")
                gravity_warn_texts = []
                for j in range(gravity_warnings.count()):
                    text = gravity_warnings.nth(j).text_content() or ""
                    if "gravity" in text.lower() or "Gravity" in text:
                        gravity_warn_texts.append(text)

                _safe_assert(
                    reporter,
                    len(gravity_warn_texts) == 0,
                    "Minor",
                    "Gravity 1 shows validation warning when it shouldn't",
                    "Edge Cases",
                    [
                        "Click low-gravity POI (gravity 1)",
                        "Check for gravity-related .beat-warning",
                    ],
                    "No gravity warnings for valid gravity 1",
                    f"Found warnings: {gravity_warn_texts}",
                    page,
                    "ec2-gravity1-warning",
                )
                break


# ---------------------------------------------------------------------------
# Test: Upload Flow + Error Handling (ACs #8, #12a) — Task 6
# ---------------------------------------------------------------------------


class TestUploadFlow:
    """Tests for single-POI upload via Mark as Complete and error handling."""

    def test_single_poi_upload(self, browser_page):
        """AC #8: Mark a valid POI as complete, verify progressive upload."""
        page, _seed_data, reporter = browser_page

        rows = page.locator(WORKLIST_ROW)

        # Find entry #1 (Seine River Lighthouse — valid, standard)
        target = None
        for i in range(rows.count()):
            row_text = rows.nth(i).text_content() or ""
            if "Quiet Garden" in row_text:
                target = i
                break

        if target is None:
            _safe_assert(
                reporter,
                False,
                "Critical",
                "Could not find Quiet Garden POI for upload test",
                "Upload Flow",
                ["Search worklist"],
                "Entry #1 in worklist",
                "Not found",
                page,
                "ac8-poi-not-found",
            )
            return

        rows.nth(target).click()
        page.wait_for_timeout(2000)

        # Click Mark as Complete
        mc_btn = page.locator(MARK_COMPLETE_BTN)
        if mc_btn.count() == 0 or not mc_btn.first.is_visible():
            _safe_assert(
                reporter,
                False,
                "Critical",
                "Mark as Complete button not visible",
                "Upload Flow",
                ["Navigate to valid POI", "Check #markCompleteBtn"],
                "Button visible",
                "Not visible",
                page,
                "ac8-no-mc-btn",
            )
            return

        mc_btn.first.click()

        # Wait for upload to complete
        page.wait_for_timeout(3000)

        # Check for uploaded badge
        rows = page.locator(WORKLIST_ROW)
        uploaded_found = False

        for i in range(rows.count()):
            row_text = rows.nth(i).text_content() or ""
            if "Quiet Garden" in row_text:
                uploaded_badge = rows.nth(i).locator(BADGE_UPLOADED)
                if uploaded_badge.count() > 0:
                    uploaded_found = True
                break

        # Also check if success toast appeared
        success = page.locator(SUCCESS_TOAST)
        toast_appeared = success.count() > 0 and success.first.is_visible()

        _safe_assert(
            reporter,
            uploaded_found or toast_appeared,
            "Critical",
            "POI upload did not complete — no uploaded badge or success toast",
            "Upload Flow",
            [
                "Navigate to valid POI (Quiet Garden)",
                "Click Mark as Complete",
                "Wait 3s for upload",
                "Check for .badge-uploaded or #successToast",
            ],
            "POI shows uploaded badge or success toast appears",
            f"Uploaded badge: {uploaded_found}, Toast: {toast_appeared}",
            page,
            "ac8-upload-failed",
        )

        # Verify via API
        if uploaded_found or toast_appeared:
            try:
                poi_name = "UI Test \u2014 Quiet Garden Corner"
                encoded = urllib.parse.quote(poi_name, safe="")
                # city_name is a required query param on this endpoint; the workbench
                # uploads with cityName="Paris" (Nominatim display_name.split(",")[0]).
                city_q = urllib.parse.quote("Paris", safe="")
                api_resp = _api_get(f"/graph/poi/{encoded}/beats?city_name={city_q}")
                # API returns {"poi_name": "...", "beats": [...]} — extract beats list
                if isinstance(api_resp, dict) and "beats" in api_resp:
                    beat_count = len(api_resp["beats"])
                    _safe_assert(
                        reporter,
                        beat_count >= 1,
                        "Major",
                        "Uploaded POI has no beats in database",
                        "Upload Flow",
                        [
                            "GET /api/v1/graph/poi/{name}/beats",
                            "Check response",
                        ],
                        "At least 1 beat returned",
                        f"{beat_count} beats returned",
                        page,
                        "ac8-no-api-beats",
                    )
                elif isinstance(api_resp, list):
                    beat_count = len(api_resp)
                    _safe_assert(
                        reporter,
                        beat_count >= 1,
                        "Major",
                        "Uploaded POI has no beats in database",
                        "Upload Flow",
                        [
                            "GET /api/v1/graph/poi/{name}/beats",
                            "Check response",
                        ],
                        "At least 1 beat returned",
                        f"{beat_count} beats returned",
                        page,
                        "ac8-no-api-beats",
                    )
                else:
                    status = (
                        api_resp.get("_status", "unknown") if isinstance(api_resp, dict) else "null"
                    )
                    _safe_assert(
                        reporter,
                        False,
                        "Major",
                        f"API verification returned error: {status}",
                        "Upload Flow",
                        ["GET /api/v1/graph/poi/{name}/beats"],
                        "200 OK with beat data",
                        f"Response: {api_resp}",
                        page,
                        "ac8-api-error",
                    )
            except Exception as exc:
                _safe_assert(
                    reporter,
                    False,
                    "Minor",
                    f"API verification failed: {exc}",
                    "Upload Flow",
                    ["API call to verify upload"],
                    "Successful API response",
                    str(exc),
                )

        _take_screenshot(page, "ac8-uploaded")

    def test_error_toast_structure(self, browser_page):
        """AC #12a: Error toast exists in DOM with correct structure."""
        page, _seed_data, reporter = browser_page

        error_toast = page.locator(ERROR_TOAST)
        _safe_assert(
            reporter,
            error_toast.count() > 0,
            "Major",
            "Error toast element (#errorToast) not found in DOM",
            "Error Handling",
            [
                "Check DOM for #errorToast element",
            ],
            "#errorToast exists in DOM",
            f"Count: {error_toast.count()}",
            page,
            "ac12a-no-toast",
        )

        _take_screenshot(page, "ac12a-error-toast")


# ---------------------------------------------------------------------------
# Test: Conflict Detection and Resolution (ACs #13-18) — Task 7
# ---------------------------------------------------------------------------


class TestConflictDetection:
    """Tests for conflict detection across all Jaccard bands and resolution actions."""

    def test_conflict_detection_and_resolution(self, browser_page):
        """ACs #13-18: resolve the incoming-Eiffel ↔ seeded-Champ-de-Mars proximity match as
        'Same Place', then verify all five beat-conflict bands and the resolution actions."""
        page, _seed_data, reporter = browser_page

        rows = page.locator(WORKLIST_ROW)

        # The incoming "UI Test Seed — Eiffel Tower" (5 beats) sits at the seeded
        # "Champ de Mars Landmark" GPS with a dissimilar name, so it does NOT auto-merge:
        # it surfaces a PROXIMITY MATCH the editor resolves as "Same Place", which runs beat
        # conflict detection against the seed's tuned beats (all five bands checked below).
        target = None
        for i in range(rows.count()):
            if "Eiffel Tower" in (rows.nth(i).text_content() or ""):
                target = i
                break
        assert target is not None, (
            "expected the incoming 'UI Test Seed — Eiffel Tower' POI in the worklist"
        )

        rows.nth(target).click()
        page.wait_for_timeout(2000)

        # Resolve the proximity match as "Same Place" -> runs runBeatConflictDetection.
        same_btn = page.locator(PROXIMITY_SAME_BTN)
        assert same_btn.count() > 0 and same_btn.first.is_visible(), (
            "expected a proximity-match panel with a 'Same Place' button for the Eiffel POI "
            "(it must not auto-merge with the dissimilarly-named Champ de Mars seed)"
        )
        same_btn.first.click()
        page.wait_for_timeout(3000)  # Wait for beat conflict detection API calls

        _take_screenshot(page, "ac13-conflict-triggered")

        # --- AC #13: Hard conflict — Beat A (hidden_history, same lens as seed) ---
        hard_badges = page.locator(BEAT_CONFLICT_BADGE_HARD)
        has_hard = hard_badges.count() > 0
        _safe_assert(
            reporter,
            has_hard,
            "Critical",
            "No hard conflict badge found after triggering Mark as Complete",
            "Conflict Detection — Hard Match",
            [
                "Click Mark as Complete on conflict-target POI",
                "Beat A shares lens 'hidden_history' with seeded beat",
                "Check for .beat-conflict-badge-hard",
            ],
            "Red hard conflict badge visible on beat A",
            f"Hard badges found: {hard_badges.count()}",
            page,
            "ac13-no-hard-badge",
        )

        if has_hard:
            badge_text = hard_badges.first.text_content() or ""
            _safe_assert(
                reporter,
                "same lens" in badge_text.lower() or "conflict" in badge_text.lower(),
                "Minor",
                f"Hard conflict badge text unexpected: '{badge_text}'",
                "Conflict Detection — Hard Match",
                [
                    "Check badge text content",
                ],
                "Text contains 'Conflict (same lens)' or similar",
                f"Text: '{badge_text}'",
                page,
                "ac13-badge-text",
            )

        # Check side-by-side panel
        conflict_sides = page.locator(CONFLICT_SIDE)
        _safe_assert(
            reporter,
            conflict_sides.count() > 0,
            "Major",
            "No side-by-side comparison panel for hard conflict",
            "Conflict Detection — Hard Match",
            [
                "Check for .conflict-side panel",
            ],
            "Side-by-side panel visible",
            f"Found {conflict_sides.count()} panels",
            page,
            "ac13-no-side-by-side",
        )

        _take_screenshot(page, "ac13-hard-conflict")

        # --- AC #14: Net-new beat — Beat B (music_nightlife, no conflict) ---
        # Beat B should have NO conflict badge
        beat_cards = page.locator(BEAT_CARD)
        beat_b_idx = 1  # Second beat in the card list

        if beat_cards.count() > beat_b_idx:
            beat_b = beat_cards.nth(beat_b_idx)
            b_hard = beat_b.locator(BEAT_CONFLICT_BADGE_HARD)
            b_soft = beat_b.locator(BEAT_CONFLICT_BADGE)
            b_review = beat_b.locator(BEAT_CONFLICT_BADGE_REVIEW)

            # Net-new should have no conflict badges at all
            no_conflict = b_hard.count() == 0 and b_review.count() == 0
            # Note: soft conflict badge uses the same base class, check if any are visible
            if b_soft.count() > 0:
                # Check if any visible soft badges
                visible_soft = False
                for j in range(b_soft.count()):
                    if b_soft.nth(j).is_visible():
                        visible_soft = True
                        break
                if visible_soft:
                    no_conflict = False

            _safe_assert(
                reporter,
                no_conflict,
                "Major",
                "Net-new beat B has unexpected conflict badge",
                "Conflict Detection — Net-New",
                [
                    "Check beat B (music_nightlife) for conflict badges",
                ],
                "No conflict badge on net-new beat",
                f"Hard: {b_hard.count()}, Review: {b_review.count()}, Soft: {b_soft.count()}",
                page,
                "ac14-unexpected-conflict",
            )

        _take_screenshot(page, "ac14-net-new")

        # --- AC #15: Soft conflict ≥70% — Beat C (food_culinary) ---
        # Beat C should show amber conflict badge with similarity percentage
        beat_c_idx = 2
        if beat_cards.count() > beat_c_idx:
            beat_c = beat_cards.nth(beat_c_idx)
            c_badges = beat_c.locator(BEAT_CONFLICT_BADGE)
            has_soft = False
            soft_text = ""

            for j in range(c_badges.count()):
                text = c_badges.nth(j).text_content() or ""
                if "similar" in text.lower() or "conflict" in text.lower():
                    has_soft = True
                    soft_text = text
                    break

            _safe_assert(
                reporter,
                has_soft,
                "Major",
                "Soft conflict beat C missing amber conflict badge",
                "Conflict Detection — Soft ≥70%",
                [
                    "Check beat C (food_culinary, 84% Jaccard vs seed 2)",
                    "Look for amber badge with similarity percentage",
                ],
                "Amber badge with 'Conflict (XX% similar)'",
                f"Badge found: {has_soft}, text: '{soft_text}'",
                page,
                "ac15-no-soft-badge",
            )

            # Check side-by-side panel for soft conflict
            c_sides = beat_c.locator(CONFLICT_SIDE)
            _safe_assert(
                reporter,
                c_sides.count() > 0,
                "Major",
                "No side-by-side panel for soft conflict beat C",
                "Conflict Detection — Soft ≥70%",
                [
                    "Check for .conflict-side in beat C card",
                ],
                "Side-by-side panel visible",
                f"Found {c_sides.count()} panels",
                page,
                "ac15-no-side-by-side",
            )

        _take_screenshot(page, "ac15-soft-conflict")

        # --- AC #16: Review band 30-69% — Beat D (art_street) ---
        beat_d_idx = 3
        if beat_cards.count() > beat_d_idx:
            beat_d = beat_cards.nth(beat_d_idx)
            d_review = beat_d.locator(BEAT_CONFLICT_BADGE_REVIEW)
            has_review = d_review.count() > 0

            _safe_assert(
                reporter,
                has_review,
                "Major",
                "Review-band beat D missing review badge",
                "Conflict Detection — Review 30-69%",
                [
                    "Check beat D (art_street, 56% Jaccard vs seed 3)",
                    "Look for .beat-conflict-badge-review",
                ],
                "Yellow review badge with 'Review (XX% similar)'",
                f"Review badges found: {d_review.count()}",
                page,
                "ac16-no-review-badge",
            )

            if has_review:
                review_text = d_review.first.text_content() or ""
                _safe_assert(
                    reporter,
                    "review" in review_text.lower() or "similar" in review_text.lower(),
                    "Minor",
                    f"Review badge text unexpected: '{review_text}'",
                    "Conflict Detection — Review 30-69%",
                    ["Check badge text"],
                    "Text contains 'Review' and similarity percentage",
                    f"Text: '{review_text}'",
                    page,
                    "ac16-badge-text",
                )

        _take_screenshot(page, "ac16-review-band")

        # --- AC #17: Pass-through <30% — Beat E (nature_green) ---
        beat_e_idx = 4
        if beat_cards.count() > beat_e_idx:
            beat_e = beat_cards.nth(beat_e_idx)
            e_hard = beat_e.locator(BEAT_CONFLICT_BADGE_HARD)
            e_review = beat_e.locator(BEAT_CONFLICT_BADGE_REVIEW)
            e_soft = beat_e.locator(BEAT_CONFLICT_BADGE)

            no_conflict_e = e_hard.count() == 0 and e_review.count() == 0
            if e_soft.count() > 0:
                visible_soft_e = False
                for j in range(e_soft.count()):
                    if e_soft.nth(j).is_visible():
                        visible_soft_e = True
                        break
                if visible_soft_e:
                    no_conflict_e = False

            _safe_assert(
                reporter,
                no_conflict_e,
                "Major",
                "Pass-through beat E has unexpected conflict badge",
                "Conflict Detection — Pass-through <30%",
                [
                    "Check beat E (nature_green, <2% Jaccard)",
                    "Should have no conflict badge",
                ],
                "No conflict badge on pass-through beat",
                f"Hard: {e_hard.count()}, Review: {e_review.count()}, Soft: {e_soft.count()}",
                page,
                "ac17-unexpected-conflict",
            )

        _take_screenshot(page, "ac17-pass-through")

        # --- AC #18: Conflict Resolution Actions ---
        # Test Replace action on hard-conflict beat (beat 0)
        self._test_resolution_action(
            page,
            reporter,
            beat_cards,
            0,
            "replace",
            "Will replace",
            "ac18-replace",
        )

        # Test Skip action on soft-conflict beat (beat 2)
        self._test_resolution_action(
            page,
            reporter,
            beat_cards,
            2,
            "skip",
            "Will skip",
            "ac18-skip",
        )

        # Test Merge action on hard-conflict beat (beat 0) — click resolved label to re-open,
        # then select merge. Beat 0 already has "replace" resolution, so click label to change.
        if beat_cards.count() > 0:
            beat_0 = beat_cards.nth(0)
            resolved_label = beat_0.locator("[data-change-resolution='true']")
            if resolved_label.count() > 0:
                resolved_label.first.click()
                page.wait_for_timeout(500)
        self._test_merge_action(page, reporter, beat_cards, 0, "ac18-merge")

        _take_screenshot(page, "ac18-all-resolutions")

    def _test_resolution_action(
        self,
        page: Page,
        reporter: BugReporter,
        beat_cards,
        beat_idx: int,
        action: str,
        expected_label: str,
        screenshot_name: str,
    ) -> None:
        """Test a specific conflict resolution action on a beat card."""
        if beat_cards.count() <= beat_idx:
            return

        beat = beat_cards.nth(beat_idx)

        # Look for resolution buttons/selects
        action_btns = beat.locator(f"button:has-text('{action.capitalize()}')")
        action_selects = beat.locator(f"select option:has-text('{action.capitalize()}')")
        action_links = beat.locator(f"[data-resolution='{action}']")

        clicked = False
        if action_links.count() > 0:
            action_links.first.click()
            clicked = True
        elif action_btns.count() > 0:
            action_btns.first.click()
            clicked = True
        elif action_selects.count() > 0:
            # Select from dropdown
            select = beat.locator("select").first
            if select.count() > 0:
                select.select_option(label=action.capitalize())
                clicked = True

        if not clicked:
            # Try looking for the action by other means
            all_btns = beat.locator("button")
            for i in range(all_btns.count()):
                text = all_btns.nth(i).text_content() or ""
                if action.lower() in text.lower():
                    all_btns.nth(i).click()
                    clicked = True
                    break

        page.wait_for_timeout(500)

        if clicked:
            # Check for resolution label
            beat_text = beat.text_content() or ""
            has_label = expected_label.lower() in beat_text.lower()
            _safe_assert(
                reporter,
                has_label,
                "Major",
                f"'{action.capitalize()}' resolution missing '{expected_label}' label",
                f"Conflict Resolution — {action.capitalize()}",
                [
                    f"Click '{action}' on beat #{beat_idx + 1}",
                    f"Check for '{expected_label}' label",
                ],
                f"Label '{expected_label}' visible",
                f"Beat text excerpt: '{beat_text[:200]}'",
                page,
                screenshot_name,
            )
        else:
            _safe_assert(
                reporter,
                False,
                "Major",
                f"Could not find '{action}' resolution action on beat #{beat_idx + 1}",
                f"Conflict Resolution — {action.capitalize()}",
                [
                    f"Look for '{action}' button/option on beat card",
                ],
                f"'{action.capitalize()}' action available",
                "Action not found",
                page,
                f"{screenshot_name}-not-found",
            )

        _take_screenshot(page, screenshot_name)

    def _test_merge_action(
        self,
        page: Page,
        reporter: BugReporter,
        beat_cards,
        beat_idx: int,
        screenshot_name: str,
    ) -> None:
        """Test the merge resolution action — should open merge overlay with 3 fields."""
        if beat_cards.count() <= beat_idx:
            return

        beat = beat_cards.nth(beat_idx)

        # Look for merge button
        merge_btns = beat.locator("button:has-text('Merge')")
        merge_links = beat.locator("[data-resolution='merge']")

        clicked = False
        if merge_links.count() > 0:
            merge_links.first.click()
            clicked = True
        elif merge_btns.count() > 0:
            merge_btns.first.click()
            clicked = True
        else:
            all_btns = beat.locator("button")
            for i in range(all_btns.count()):
                text = all_btns.nth(i).text_content() or ""
                if "merge" in text.lower():
                    all_btns.nth(i).click()
                    clicked = True
                    break

        page.wait_for_timeout(500)

        if clicked:
            # Check for merge overlay
            overlay = page.locator(MERGE_OVERLAY)
            has_overlay = overlay.count() > 0

            _safe_assert(
                reporter,
                has_overlay,
                "Major",
                "Merge overlay did not open after clicking Merge",
                "Conflict Resolution — Merge",
                [
                    f"Click 'Merge' on beat #{beat_idx + 1}",
                    "Check for .merge-overlay",
                ],
                "Merge overlay opens",
                f"Overlay found: {has_overlay}",
                page,
                f"{screenshot_name}-no-overlay",
            )

            _take_screenshot(page, screenshot_name)

            # Close merge overlay if open (cleanup). The modal backdrop sits at the button's
            # click point, so a coordinate click (even force) lands on the backdrop. Fire the
            # Cancel button's own handler directly via el.click() (what a human's click on the
            # visible button does); the closure assertion below proves it actually closed.
            if has_overlay:
                close_btns = overlay.locator("button:has-text('Cancel')")
                if close_btns.count() > 0:
                    close_btns.first.evaluate("el => el.click()")
                else:
                    page.keyboard.press("Escape")
                page.wait_for_timeout(300)
                # Confirm the overlay actually closed (so the force-click isn't masking a
                # stuck modal that would break later state).
                _safe_assert(
                    reporter,
                    page.locator(MERGE_OVERLAY).count() == 0
                    or not page.locator(MERGE_OVERLAY).first.is_visible(),
                    "Minor",
                    "Merge overlay did not close after Cancel",
                    "Conflict Resolution — Merge",
                    ["Click Cancel on the merge overlay", "Check the overlay is gone"],
                    "Merge overlay closed",
                    "Overlay still visible",
                    page,
                    f"{screenshot_name}-not-closed",
                )
        else:
            _safe_assert(
                reporter,
                False,
                "Major",
                f"Could not find 'Merge' action on beat #{beat_idx + 1}",
                "Conflict Resolution — Merge",
                [
                    "Look for 'Merge' button on review-band beat",
                ],
                "'Merge' action available",
                "Not found",
                page,
                f"{screenshot_name}-not-found",
            )


# ---------------------------------------------------------------------------
# Test: Proximity Matching Logic (POI Matching Fix)
# ---------------------------------------------------------------------------

PROXIMITY_SAME_BTN = ".proximity-same-btn"
PROXIMITY_DIFF_BTN = ".proximity-diff-btn"
PROXIMITY_PANEL = ".proximity-match-panel"


class TestProximityMatching:
    """Frontend tests for location-first POI deduplication (ACs #1-8)."""

    def test_find_proximity_matches_empty_for_distant_poi(self, browser_page):
        """AC 1: POI >50m from all existing → empty array (auto-new)."""
        page, _seed_data, _reporter = browser_page
        result = page.evaluate("""() => {
            // POI far from any existing (200m+ away)
            const testPoi = { latitude: 48.90, longitude: 2.50 };
            return findProximityMatches(testPoi, cachedPoiList);
        }""")
        assert isinstance(result, list)
        assert len(result) == 0, "Distant POI should have no proximity matches"

    def test_find_proximity_matches_returns_nearby(self, browser_page):
        """AC 2: POI within 50m of one existing → single match returned."""
        page, _seed_data, _reporter = browser_page
        result = page.evaluate("""() => {
            // Find first cached POI with location and create a nearby point
            const existing = cachedPoiList.find(p => p.properties.location && p.properties.location.lat);
            if (!existing) return { error: 'no cached POI with location' };
            // Place incoming POI ~20m away (approx 0.0002 degrees)
            const testPoi = {
                latitude: existing.properties.location.lat + 0.0001,
                longitude: existing.properties.location.lng + 0.0001,
            };
            const matches = findProximityMatches(testPoi, cachedPoiList);
            return { count: matches.length, firstDist: matches.length > 0 ? matches[0].distanceM : null };
        }""")
        if "error" in result:
            pytest.skip(result["error"])
        assert result["count"] >= 1, "Nearby POI should have at least one proximity match"
        assert result["firstDist"] <= 50, "Match should be within 50m"

    def test_find_proximity_matches_sorted_by_distance(self, browser_page):
        """AC 3: Multiple matches sorted ascending by distance."""
        page, _seed_data, _reporter = browser_page
        result = page.evaluate("""() => {
            // Create two fake cached POIs close together, test a point near both
            const fakeCached = [
                { properties: { name: 'A', location: { lat: 48.8530, lng: 2.3499 } } },
                { properties: { name: 'B', location: { lat: 48.8532, lng: 2.3499 } } },
            ];
            const testPoi = { latitude: 48.8531, longitude: 2.3499 };
            const matches = findProximityMatches(testPoi, fakeCached);
            return matches.map(m => ({ name: m.existingPoi.properties.name, dist: m.distanceM }));
        }""")
        assert len(result) == 2, "Should match both nearby POIs"
        assert result[0]["dist"] <= result[1]["dist"], "Matches should be sorted by distance"

    def test_same_name_distant_poi_is_new(self, browser_page):
        """AC 8: Identical names 200m apart → both auto-new (no proximity match)."""
        page, _seed_data, _reporter = browser_page
        result = page.evaluate("""() => {
            const fakeCached = [
                { properties: { name: 'Hôtel de Ville', location: { lat: 48.8530, lng: 2.3499 } } },
            ];
            // Same name, 200m away
            const testPoi = { latitude: 48.8550, longitude: 2.3499 };
            return findProximityMatches(testPoi, fakeCached);
        }""")
        assert len(result) == 0, "Same-name POI 200m away should have no proximity match"

    def test_detect_conflicts_missing_coords(self, browser_page):
        """AC 7: POI without coordinates → missingCoords: true."""
        page, _seed_data, _reporter = browser_page
        result = page.evaluate("""() => {
            const testPoi = { poi_name: 'No Coords POI', beats: [] };
            return detectConflictsForPoi(testPoi);
        }""")
        assert result["missingCoords"] is True
        assert len(result["errors"]) > 0

    def test_detect_conflicts_auto_new_no_match(self, browser_page):
        """AC 1: POI with no nearby existing → isNew: true."""
        page, _seed_data, _reporter = browser_page
        result = page.evaluate("""() => {
            const testPoi = { poi_name: 'Distant POI', latitude: 48.90, longitude: 2.50, beats: [] };
            return detectConflictsForPoi(testPoi);
        }""")
        assert result["isNew"] is True
        assert len(result["proximityMatches"]) == 0

    def test_map_poi_for_api_with_existing_name(self, browser_page):
        """AC 6: useExistingName sends the existing name in payload."""
        page, _seed_data, _reporter = browser_page
        result = page.evaluate("""() => {
            const poi = { poi_name: 'Incoming Name', latitude: 48.85, longitude: 2.35 };
            return mapPoiForApi(poi, { useExistingName: 'Existing Name' });
        }""")
        assert result["name"] == "Existing Name"

    def test_map_poi_for_api_with_force_create(self, browser_page):
        """AC 5: forceCreate sends force_create: true."""
        page, _seed_data, _reporter = browser_page
        result = page.evaluate("""() => {
            const poi = { poi_name: 'Test POI', latitude: 48.85, longitude: 2.35 };
            return mapPoiForApi(poi, { forceCreate: true });
        }""")
        assert result["force_create"] is True

    def test_name_similarity_function(self, browser_page):
        """Name similarity is computed correctly for display."""
        page, _seed_data, _reporter = browser_page
        result = page.evaluate("""() => {
            return {
                identical: nameSimilarity('Hôtel de Ville', 'Hôtel de Ville'),
                similar: nameSimilarity('Hôtel de Ville', 'The Hôtel de Ville'),
                different: nameSimilarity('Hôtel de Ville', 'Jardin du Luxembourg'),
            };
        }""")
        assert result["identical"] == 1.0
        assert result["similar"] > 0.5
        assert result["different"] < 0.5

    def test_boundary_50m_excluded(self, browser_page):
        """Edge: POI at exactly >50m is excluded from proximity matches."""
        page, _seed_data, _reporter = browser_page
        result = page.evaluate("""() => {
            // Place existing POI and incoming ~51m apart (about 0.00046 degrees lat)
            const fakeCached = [
                { properties: { name: 'Boundary POI', location: { lat: 48.8530, lng: 2.3499 } } },
            ];
            const testPoi = { latitude: 48.85346, longitude: 2.3499 };
            return findProximityMatches(testPoi, fakeCached);
        }""")
        assert len(result) == 0, "POI at ~51m should NOT match"


# ---------------------------------------------------------------------------
# Test: Bug Report Generation (Task 8)
# ---------------------------------------------------------------------------


class TestBugReport:
    """Verify bug report is generated at the end of the suite."""

    def test_report_generated(self, browser_page):
        """Final test: save the bug report and verify its structure."""
        page, _seed_data, reporter = browser_page

        report_path = reporter.save_report()

        assert report_path.exists(), f"Bug report not found at {report_path}"

        content = report_path.read_text(encoding="utf-8")
        assert "# Editorial Workbench UI Bug Report" in content
        assert "## Summary" in content
        assert "Tests run:" in content
        assert "Issues found:" in content

        _take_screenshot(page, "final-state")
