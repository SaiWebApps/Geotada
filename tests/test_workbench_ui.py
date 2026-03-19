"""Playwright UI test suite for the Editorial Review Workbench (review.html).

Systematically exercises the workbench through its complete workflow and
produces a markdown bug report with screenshots. Runs against a live
FastAPI + Neo4j stack on localhost:8000.

Usage:
    pytest tests/test_workbench_ui.py -v --tb=short

Requires: playwright, pytest
Stack must be running: docker compose up -d && make api-up
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import urllib.error
import urllib.parse
import urllib.request

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
WORKBENCH_URL = (Path(__file__).parent.parent / "frontend" / "review.html").resolve().as_uri()
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "ui_test_fixture.json"
REPORT_DIR = Path(__file__).parent / "reports"
SCREENSHOT_DIR = REPORT_DIR / "screenshots"

# Seed data constants
SEED_POI_NAME = "UI Test Seed \u2014 Old North Church"
SEED_BEATS = [
    {
        "lens_slug": "hidden_history",
        "gravity": 4,
        "script_body": (
            "The Old North Church steeple held two lanterns on that fateful "
            "April night in 1775. Robert Newman climbed the dark narrow stairs "
            "while Paul Revere waited across the harbor. The signal one if by "
            "land two if by sea changed the course of American history. Those "
            "lanterns became the most famous signal lights in the revolution "
            "sparking the midnight ride that warned every Middlesex village "
            "and farm."
        ),
    },
    {
        "lens_slug": "revolutionary_moments",
        "gravity": 3,
        "script_body": (
            "Paul Revere galloped through the Massachusetts countryside warning "
            "colonial militia that British regulars were marching toward Lexington "
            "and Concord. His midnight ride covered roughly twelve miles of dark "
            "roads and sleeping villages. At every farmhouse he pounded on doors "
            "shouting the regulars are coming. Samuel Prescott and William Dawes "
            "joined the ride but only Prescott made it all the way to Concord."
        ),
    },
    {
        "lens_slug": "dark_history",
        "gravity": 2,
        "script_body": (
            "British soldiers occupied Boston for years before the Revolution "
            "turning churches into stables and homes into barracks. The redcoats "
            "patrolled cobblestone streets enforcing harsh laws on colonial citizens. "
            "Tensions boiled over at the Boston Massacre when soldiers fired into "
            "a crowd killing five men."
        ),
    },
]

# Taggable lenses — derived from definitions.py (single source of truth)
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
        return {"_error": True, "_status": exc.code, "_body": exc.read().decode("utf-8", errors="replace")}
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
    """Assert without stopping the suite. Logs a bug if condition is False."""
    reporter.increment_tests()
    if not condition:
        ss_path = None
        if page and screenshot_name:
            ss_path = _take_screenshot(page, screenshot_name)
        reporter.log_issue(severity, title, flow, steps, expected, actual, ss_path)
        return False
    return True


def _load_fixture() -> list[dict]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Fixtures — Seed Data Setup / Teardown (Task 3)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def reporter():
    """Module-scoped bug reporter shared across all tests."""
    return BugReporter()


@pytest.fixture(scope="module")
def seed_data():
    """Seed test data into Neo4j and clean up after all tests.

    Setup:
      1. Verify API is reachable
      2. Check/seed 12 lenses
      3. Create seed POI + 3 beats + edges

    Teardown:
      1. Delete all test-created POIs (prefix "UI Test")
    """
    # --- Verify API ---
    try:
        resp = _api_get("/nodes/Lens?limit=1")
        if resp is None:
            pytest.skip(f"API not reachable at {API_BASE}")
        if isinstance(resp, dict) and resp.get("_error"):
            pytest.skip(f"API error: {resp.get('_status')}")
    except Exception as exc:
        pytest.skip(f"API not reachable at {API_BASE}: {exc}")

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
        if isinstance(resp, dict) and resp.get("_error"):
            return False
        return True

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

    # --- Create Seed POI ---
    poi_data = _api_post(
        "/nodes/POI",
        {
            "name": SEED_POI_NAME,
            "latitude": 42.3663,
            "longitude": -71.0544,
            "short_description": "Seed POI for UI conflict detection tests",
            "importance_tier": 1,
            "trigger_radius": 10,
            "typical_duration_min": 30,
            "kid_friendly": "yes",
        },
    )
    if not _is_ok(poi_data) or not isinstance(poi_data, dict):
        pytest.skip(f"Failed to create seed POI: {poi_data}")

    poi_id = _get_id(poi_data)
    created_ids["poi"].append(poi_id)

    # --- Create Seed Beats + Edges ---
    for beat_def in SEED_BEATS:
        beat_data = _api_post(
            "/nodes/NarrativeBeat",
            {
                "script_body": beat_def["script_body"],
                "gravity": beat_def["gravity"],
                "lens": beat_def["lens_slug"],
            },
        )
        if not _is_ok(beat_data) or not isinstance(beat_data, dict):
            continue
        beat_id = _get_id(beat_data)
        created_ids["beat"].append(beat_id)

        # Link beat to POI
        edge_data = _api_post(
            "/edges/HAS_BEAT",
            {
                "source": {"label": "POI", "id": poi_id},
                "target": {"label": "NarrativeBeat", "id": beat_id},
            },
        )
        if _is_ok(edge_data) and isinstance(edge_data, dict):
            created_ids["edge_has_beat"].append(_get_id(edge_data))

        # Tag beat with lens
        lens_slug = beat_def["lens_slug"]
        if lens_slug in lens_id_map:
            tag_data = _api_post(
                "/edges/TAGGED_WITH",
                {
                    "source": {"label": "NarrativeBeat", "id": beat_id},
                    "target": {"label": "Lens", "id": lens_id_map[lens_slug]},
                },
            )
            if _is_ok(tag_data) and isinstance(tag_data, dict):
                created_ids["edge_tagged_with"].append(_get_id(tag_data))

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
            try:
                _api_delete(f"/nodes/Lens/{lid}")
            except Exception:
                pass


@pytest.fixture(scope="module")
def browser_page(seed_data, reporter):
    """Launch a visible Chromium browser for the test suite."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=300)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        yield page, seed_data, reporter
        # Save bug report before closing
        report_path = reporter.save_report()
        print(f"\n\nBug report saved to: {report_path}")
        browser.close()


# ---------------------------------------------------------------------------
# Test: City Prompt + JSON Load + Duplicate Resolver (ACs #1-2) — Task 4
# ---------------------------------------------------------------------------

class TestWorkbenchLoadFlow:
    """Tests for initial load: city prompt, JSON load, duplicate resolver, worklist."""

    def test_city_prompt_and_json_load(self, browser_page):
        page, seed_data, reporter = browser_page
        fixture = _load_fixture()

        # --- City Prompt Flow ---
        page.goto(WORKBENCH_URL)
        page.wait_for_load_state("networkidle")

        # Assert city overlay is visible
        overlay = page.locator(CITY_OVERLAY)
        overlay_visible = overlay.is_visible()
        _safe_assert(
            reporter, overlay_visible,
            "Critical", "City overlay not visible on load",
            "City Prompt", ["Navigate to workbench URL"],
            "City overlay (#cityOverlay) is visible",
            f"Overlay visible: {overlay_visible}",
            page, "ac1-city-overlay-missing",
        )

        # Type "Boston" and submit
        page.locator(CITY_INPUT).fill("Boston")
        page.locator(CITY_SUBMIT).click()

        # Wait for overlay to close (10s timeout for Nominatim — Risk R2)
        try:
            overlay.wait_for(state="hidden", timeout=15000)
            city_accepted = True
        except Exception:
            city_accepted = False
            _safe_assert(
                reporter, False,
                "Critical", "City overlay did not close after submitting 'Boston'",
                "City Prompt", [
                    "Navigate to workbench URL",
                    "Type 'Boston' into #cityInput",
                    "Click #citySubmitBtn",
                ],
                "Overlay closes within 10s",
                "Overlay still visible after 15s (Nominatim may be slow/down)",
                page, "ac1-city-timeout",
            )

        if city_accepted:
            # Verify city label
            label_text = page.locator(CITY_LABEL).text_content() or ""
            _safe_assert(
                reporter, "Boston" in label_text,
                "Major", "City label does not contain 'Boston'",
                "City Prompt", ["Submit 'Boston' city"],
                "'Boston' appears in #cityLabel",
                f"Label text: '{label_text}'",
                page, "ac1-city-label",
            )

        # --- JSON Load Flow ---
        # Capture console errors for debugging
        console_errors: list[str] = []
        page.on("console", lambda msg: console_errors.append(f"[{msg.type}] {msg.text}") if msg.type == "error" else None)

        # Wait for Load JSON button to be enabled (city geocoding must complete first)
        load_btn = page.locator(LOAD_JSON_BTN)
        try:
            load_btn.wait_for(state="visible", timeout=5000)
        except Exception:
            pass

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
                reporter, False,
                "Critical", f"Console errors during JSON load: {'; '.join(console_errors[:3])}",
                "JSON Load", ["Load fixture via file chooser"],
                "No console errors",
                f"{len(console_errors)} error(s): {'; '.join(console_errors[:3])}",
                page, "ac1-console-errors",
            )

        # Check if error toast appeared (JSON validation failure)
        error_toast = page.locator(ERROR_TOAST)
        if error_toast.count() > 0 and error_toast.first.is_visible():
            toast_text = error_toast.first.text_content() or ""
            _safe_assert(
                reporter, False,
                "Critical", f"Error toast appeared during JSON load: {toast_text[:200]}",
                "JSON Load", ["Load fixture via file chooser"],
                "No error toast",
                f"Toast: {toast_text[:200]}",
                page, "ac1-json-error-toast",
            )

        # --- Duplicate Resolver (AC #2) ---
        dup_overlay = page.locator(DUP_OVERLAY)
        try:
            dup_overlay.wait_for(state="visible", timeout=5000)
            dup_visible = True
        except Exception:
            dup_visible = False

        _safe_assert(
            reporter, dup_visible,
            "Major", "Duplicate resolver overlay did not appear",
            "Duplicate Resolver", [
                "Load fixture with entries #6/#7 sharing name 'UI Test — Duplicate Harbor Walk'",
            ],
            "#dupOverlay becomes visible",
            f"Overlay visible: {dup_visible}",
            page, "ac2-dup-overlay-missing",
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
                second_input.fill("UI Test \u2014 Duplicate Harbor Walk (2)")

            # Click resolve
            page.locator(DUP_RESOLVE_BTN).click()

            # Wait for overlay to close
            try:
                dup_overlay.wait_for(state="hidden", timeout=5000)
                dup_resolved = True
            except Exception:
                dup_resolved = False

            _safe_assert(
                reporter, dup_resolved,
                "Critical", "Duplicate resolver overlay did not close after resolve",
                "Duplicate Resolver", [
                    "Rename duplicate entry",
                    "Click #dupResolveBtn",
                ],
                "Overlay closes after resolution",
                "Overlay still visible",
                page, "ac2-dup-not-resolved",
            )

        # --- Worklist Rendering (AC #1) ---
        # Wait for worklist rows to appear
        page.wait_for_timeout(2000)
        rows = page.locator(WORKLIST_ROW)

        try:
            rows.first.wait_for(state="visible", timeout=5000)
        except Exception:
            pass

        row_count = rows.count()
        _safe_assert(
            reporter, row_count == 12,
            "Critical", f"Worklist shows {row_count} POIs instead of 12",
            "Worklist Rendering", [
                "Load 12-entry fixture",
                "Resolve duplicate names",
                "Check worklist row count",
            ],
            "12 .worklist-row elements visible",
            f"Found {row_count} rows",
            page, "ac1-worklist-count",
        )

        _take_screenshot(page, "ac1-worklist-loaded")


# ---------------------------------------------------------------------------
# Test: Detail View, Editing, Badges, Beats (ACs #3-7, #9-12) — Task 5
# ---------------------------------------------------------------------------

class TestDetailViewAndEditing:
    """Tests for POI detail rendering, editing, badges, and beat cards."""

    def test_detail_view_rendering(self, browser_page):
        """AC #3: Click each POI and verify detail view renders correct field values."""
        page, seed_data, reporter = browser_page
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
                    reporter, actual_name == expected_name,
                    "Major", f"POI name mismatch for entry #{idx + 1}",
                    "Detail View", [
                        f"Click worklist row #{i + 1} (poi_idx={idx})",
                        "Check [data-field='poi_name'] value",
                    ],
                    f"Name: '{expected_name}'",
                    f"Name: '{actual_name}'",
                    page, f"ac3-name-mismatch-{idx}",
                )

            # Check latitude
            lat_field = page.locator(DATA_FIELD.format("latitude"))
            if lat_field.count() > 0:
                actual_lat = lat_field.first.input_value()
                expected_lat = str(expected_poi["latitude"])
                _safe_assert(
                    reporter, actual_lat == expected_lat,
                    "Major", f"Latitude mismatch for entry #{idx + 1}",
                    "Detail View", [f"Check latitude for '{expected_poi['poi_name']}'"],
                    f"Lat: {expected_lat}",
                    f"Lat: {actual_lat}",
                    page, f"ac3-lat-mismatch-{idx}",
                )

            # Check longitude
            lng_field = page.locator(DATA_FIELD.format("longitude"))
            if lng_field.count() > 0:
                actual_lng = lng_field.first.input_value()
                expected_lng = str(expected_poi["longitude"])
                _safe_assert(
                    reporter, actual_lng == expected_lng,
                    "Major", f"Longitude mismatch for entry #{idx + 1}",
                    "Detail View", [f"Check longitude for '{expected_poi['poi_name']}'"],
                    f"Lng: {expected_lng}",
                    f"Lng: {actual_lng}",
                    page, f"ac3-lng-mismatch-{idx}",
                )

        reporter.increment_tests()

    def test_geofence_flag(self, browser_page):
        """AC #4: Outside-geofence POI shows flagged badge and yellow warning."""
        page, seed_data, reporter = browser_page

        # Find entry #4 (Times Square — outside geofence)
        # It has poi_name "UI Test — Times Square Billboard"
        rows = page.locator(WORKLIST_ROW)
        found = False

        for i in range(rows.count()):
            row = rows.nth(i)
            row_text = row.text_content() or ""
            if "Times Square" in row_text:
                # Check for flagged badge in worklist
                flagged_badge = row.locator(BADGE_FLAGGED)
                has_flagged = flagged_badge.count() > 0 and flagged_badge.first.is_visible()
                _safe_assert(
                    reporter, has_flagged,
                    "Major", "Outside-geofence POI missing flagged badge",
                    "Geofence Detection", [
                        "Load fixture with entry #4 (New York coords)",
                        "Check worklist row for .badge-flagged",
                    ],
                    ".badge-flagged visible on worklist row",
                    f"Badge visible: {has_flagged}",
                    page, "ac4-no-flagged-badge",
                )

                # Click to open detail
                row.click()
                page.wait_for_timeout(500)

                # Check for geofence warning in map area
                geofence_warn = page.locator(MAP_WARN_GEOFENCE)
                warn_visible = geofence_warn.count() > 0 and geofence_warn.first.is_visible()
                _safe_assert(
                    reporter, warn_visible,
                    "Minor", "No geofence warning in detail view for outside-geofence POI",
                    "Geofence Detection", [
                        "Click outside-geofence POI",
                        "Check for .map-warn-geofence element",
                    ],
                    "Yellow geofence warning visible in map area",
                    f"Warning visible: {warn_visible}",
                    page, "ac4-no-geofence-warning",
                )

                _take_screenshot(page, "ac4-geofence")
                found = True
                break

        if not found:
            _safe_assert(
                reporter, False,
                "Critical", "Could not find Times Square POI in worklist",
                "Geofence Detection", ["Search worklist for 'Times Square'"],
                "Entry #4 found in worklist",
                "Not found",
                page, "ac4-poi-not-found",
            )

    def test_invalid_coords(self, browser_page):
        """AC #5: Invalid-coords POI shows field warnings and blocks upload."""
        page, seed_data, reporter = browser_page

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
                    reporter, warn_count >= 1,
                    "Major", "No field warnings for invalid coordinates (lat 999, lng -999)",
                    "Coord Validation", [
                        "Click invalid-coords POI (entry #5)",
                        "Check for .field-warning elements",
                    ],
                    ".field-warning visible near coordinate fields",
                    f"Found {warn_count} warnings",
                    page, "ac5-no-coord-warnings",
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
                    reporter, map_warn_visible,
                    "Minor", "Map does not show 'Invalid coordinates' message",
                    "Coord Validation", ["Check map area for invalid coords message"],
                    "'Invalid coordinates — pin removed' message visible",
                    f"Map warning visible: {map_warn_visible}",
                    page, "ac5-no-map-warning",
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
                        reporter, was_blocked,
                        "Critical",
                        "Invalid-coords POI was uploaded despite invalid coordinates",
                        "Coord Validation", [
                            "Click Mark as Complete on invalid-coords POI",
                        ],
                        "Upload blocked — POI stays in non-uploaded state",
                        "POI appears to have been uploaded",
                        page, "ac5-invalid-uploaded",
                    )

                _take_screenshot(page, "ac5-invalid-coords")
                found = True
                break

        if not found:
            _safe_assert(
                reporter, False,
                "Critical", "Could not find Invalid Location POI in worklist",
                "Coord Validation", ["Search worklist for 'Invalid Location'"],
                "Entry #5 found in worklist",
                "Not found",
                page, "ac5-poi-not-found",
            )

    def test_edit_persistence(self, browser_page):
        """AC #6: Edits persist when navigating away and back."""
        page, seed_data, reporter = browser_page

        rows = page.locator(WORKLIST_ROW)
        if rows.count() < 2:
            _safe_assert(
                reporter, False,
                "Critical", "Not enough worklist rows for edit persistence test",
                "Edit Persistence", ["Need at least 2 POIs in worklist"],
                "2+ POIs available", f"Found {rows.count()}",
            )
            return

        # Click first valid POI (entry #1 — "Boston Harbor Lighthouse")
        first_row = None
        second_row = None
        for i in range(rows.count()):
            row_text = rows.nth(i).text_content() or ""
            if "Harbor Lighthouse" in row_text and first_row is None:
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
                reporter, current_name == edited_name,
                "Major", "POI name edit did not persist after navigation",
                "Edit Persistence", [
                    "Edit POI name",
                    "Navigate to different POI",
                    "Navigate back",
                    "Check POI name",
                ],
                f"Name: '{edited_name}'",
                f"Name: '{current_name}'",
                page, "ac6-name-not-persisted",
            )

        beat_script = page.locator(DATA_BEAT_FIELD.format("script_body"))
        if beat_script.count() > 0 and edited_script:
            current_script = beat_script.first.input_value()
            _safe_assert(
                reporter, "EDIT_MARKER" in current_script,
                "Major", "Beat script_body edit did not persist after navigation",
                "Edit Persistence", [
                    "Edit beat script_body",
                    "Navigate away and back",
                    "Check script_body",
                ],
                "Script contains 'EDIT_MARKER'",
                f"Script: '{current_script[:80]}...'",
                page, "ac6-script-not-persisted",
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
        page, seed_data, reporter = browser_page

        # Wait for worklist rows to be available
        rows = page.locator(WORKLIST_ROW)
        try:
            rows.first.wait_for(state="visible", timeout=5000)
        except Exception:
            _safe_assert(
                reporter, False,
                "Critical", "No worklist rows available for defer test",
                "Defer Flow", ["Wait for .worklist-row elements"],
                "Worklist rows visible", f"Count: {rows.count()}",
                page, "ac7-no-rows",
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
                reporter, has_deferred,
                "Major", "POI badge did not change to 'deferred' after clicking Defer",
                "Defer Flow", [
                    "Click entry #3 (Quiet Garden)",
                    "Click #deferBtn",
                    "Check for .badge-deferred",
                ],
                ".badge-deferred visible on worklist row",
                f"Badge found: {has_deferred}",
                page, "ac7-no-deferred-badge",
            )

            _take_screenshot(page, "ac7-deferred")

            # Re-select the deferred POI
            rows.nth(target_row).click()
            page.wait_for_timeout(500)

            _take_screenshot(page, "ac7-reselected")
        else:
            _safe_assert(
                reporter, False,
                "Critical", "Defer button not visible",
                "Defer Flow", ["Navigate to POI", "Look for #deferBtn"],
                "Defer button visible",
                "Button not found or not visible",
                page, "ac7-no-defer-btn",
            )

    def test_beat_rendering(self, browser_page):
        """ACs #9, #10, #12: Beat cards render all fields, multi-lens POI renders all beats."""
        page, seed_data, reporter = browser_page
        fixture = _load_fixture()

        # Find multi-lens POI (entry #8 — Quincy Market, 4 beats)
        rows = page.locator(WORKLIST_ROW)
        for i in range(rows.count()):
            row_text = rows.nth(i).text_content() or ""
            if "Quincy Market" in row_text:
                rows.nth(i).click()
                page.wait_for_timeout(500)

                # AC #10: Check beat card count
                beats = page.locator(BEAT_CARD)
                beat_count = beats.count()
                _safe_assert(
                    reporter, beat_count == 4,
                    "Major", f"Multi-lens POI shows {beat_count} beat cards instead of 4",
                    "Beat Rendering", [
                        "Click Quincy Market POI (entry #8, 4 beats)",
                        "Count .beat-card elements",
                    ],
                    "4 beat cards rendered",
                    f"{beat_count} beat cards found",
                    page, "ac10-beat-count",
                )

                # AC #9: Check each beat card has all 5 fields
                for bi in range(beat_count):
                    beat = beats.nth(bi)
                    for field in ["script_body", "physical_cue", "lens", "gravity", "source_passage"]:
                        field_el = beat.locator(DATA_BEAT_FIELD.format(field))
                        has_field = field_el.count() > 0
                        _safe_assert(
                            reporter, has_field,
                            "Major",
                            f"Beat #{bi + 1} missing field: {field}",
                            "Beat Rendering", [
                                f"Check beat card #{bi + 1} for [data-beat-field='{field}']",
                            ],
                            f"Field '{field}' present in beat card",
                            f"Field not found",
                            page, f"ac9-missing-field-{field}-beat{bi}",
                        )

                # Check lens dropdown has 16 taggable options
                lens_selects = page.locator(DATA_BEAT_FIELD.format("lens"))
                if lens_selects.count() > 0:
                    options = lens_selects.first.locator("option")
                    option_count = options.count()
                    # Expect 16 taggable lens options + 1 "Select lens..." placeholder = 17
                    _safe_assert(
                        reporter, option_count >= 16,
                        "Major", f"Lens dropdown has {option_count} options instead of 16+",
                        "Beat Rendering", ["Check lens select option count"],
                        "16+ options in lens dropdown",
                        f"{option_count} options found",
                        page, "ac9-lens-count",
                    )

                # AC #12: Check beat count header
                beats_header = page.locator("h3:has-text('Narrative Beats')")
                if beats_header.count() > 0:
                    header_text = beats_header.first.text_content() or ""
                    _safe_assert(
                        reporter, "(4)" in header_text,
                        "Minor", f"Beat count header says '{header_text}' instead of containing '(4)'",
                        "Beat Rendering", ["Check h3 text for beat count"],
                        "'Narrative Beats (4)' in header",
                        f"Header: '{header_text}'",
                        page, "ac12-beat-header",
                    )

                _take_screenshot(page, "ac9-10-12-beats")
                break

    def test_beat_editing(self, browser_page):
        """AC #11: Beat lens and gravity edits persist after navigation."""
        page, seed_data, reporter = browser_page

        rows = page.locator(WORKLIST_ROW)

        # Navigate to multi-lens POI (Quincy Market)
        target = None
        other = None
        for i in range(rows.count()):
            row_text = rows.nth(i).text_content() or ""
            if "Quincy Market" in row_text:
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
                    reporter, current_gravity == new_gravity,
                    "Major", "Beat gravity edit did not persist after navigation",
                    "Beat Editing", [
                        f"Change gravity from {original_gravity} to {new_gravity}",
                        "Navigate away and back",
                        "Check gravity value",
                    ],
                    f"Gravity: {new_gravity}",
                    f"Gravity: {current_gravity}",
                    page, "ac11-gravity-not-persisted",
                )

                # Restore
                gravity_fields.first.clear()
                gravity_fields.first.fill(original_gravity)
                gravity_fields.first.dispatch_event("input")

        _take_screenshot(page, "ac11-beat-edit")

    def test_empty_beat_stripped_on_load(self, browser_page):
        """Edge case: Empty script_body beats are stripped during JSON load."""
        page, seed_data, reporter = browser_page

        rows = page.locator(WORKLIST_ROW)
        for i in range(rows.count()):
            row_text = rows.nth(i).text_content() or ""
            if "Empty Script" in row_text:
                rows.nth(i).click()
                page.wait_for_timeout(500)

                # Empty beats should have been stripped during processJson
                beat_cards = page.locator(BEAT_CARD)
                _safe_assert(
                    reporter, beat_cards.count() == 0,
                    "Major", f"Empty-beat POI still has {beat_cards.count()} beat cards after load",
                    "Edge Cases", [
                        "Click entry #9 (originally had empty script_body)",
                        "Check beat card count — empty beats should be stripped",
                    ],
                    "0 beat cards (empty beat stripped during load)",
                    f"{beat_cards.count()} beat cards found",
                    page, "ec1-empty-not-stripped",
                )

                _take_screenshot(page, "ec1-empty-beat-stripped")
                break

    def test_long_text_no_overflow(self, browser_page):
        """Edge case: Long POI name and description don't overflow containers."""
        page, seed_data, reporter = browser_page

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
                        reporter, not overflow,
                        "Minor", "Long POI name overflows worklist row container",
                        "Edge Cases", [
                            "Check bounding box of long-name POI row vs parent",
                        ],
                        "Row fits within .left-panel width",
                        f"Row extends {box['x'] + box['width'] - parent_box['x'] - parent_box['width']:.0f}px beyond parent",
                        page, "ec3-overflow",
                    )

                rows.nth(i).click()
                page.wait_for_timeout(500)
                _take_screenshot(page, "ec3-long-text")
                break

    def test_audit_notes_rendering(self, browser_page):
        """Edge case: Audit notes render in correct containers (object + array)."""
        page, seed_data, reporter = browser_page

        rows = page.locator(WORKLIST_ROW)
        for i in range(rows.count()):
            row_text = rows.nth(i).text_content() or ""
            if "Audited Beacon" in row_text:
                rows.nth(i).click()
                page.wait_for_timeout(500)

                # Check POI-level audit notes
                poi_notes = page.locator(POI_AUDIT_NOTES_BOX)
                _safe_assert(
                    reporter, poi_notes.count() > 0,
                    "Major", "POI-level audit notes not rendered",
                    "Audit Notes", [
                        "Click entry #12 (Audited Beacon Hill)",
                        "Check for .poi-audit-notes-box",
                    ],
                    ".poi-audit-notes-box present",
                    f"Found {poi_notes.count()} elements",
                    page, "ec4-no-poi-audit",
                )

                # Check beat-level audit notes
                beat_notes = page.locator(AUDIT_NOTES_BOX)
                _safe_assert(
                    reporter, beat_notes.count() > 0,
                    "Major", "Beat-level audit notes not rendered",
                    "Audit Notes", [
                        "Check for .audit-notes-box in beat cards",
                    ],
                    ".audit-notes-box present in beat cards",
                    f"Found {beat_notes.count()} elements",
                    page, "ec4-no-beat-audit",
                )

                _take_screenshot(page, "ec4-audit-notes")
                break

    def test_gravity_boundaries(self, browser_page):
        """Edge case: Gravity 1 and 5 render without validation warnings."""
        page, seed_data, reporter = browser_page

        rows = page.locator(WORKLIST_ROW)

        # Check high-gravity POI (entry #2 — Faneuil Hall Anchor, gravity 5)
        for i in range(rows.count()):
            row_text = rows.nth(i).text_content() or ""
            if "Faneuil Hall Anchor" in row_text:
                rows.nth(i).click()
                page.wait_for_timeout(500)

                gravity_warnings = page.locator(f"{BEAT_CARD} {BEAT_WARNING}")
                gravity_warn_texts = []
                for j in range(gravity_warnings.count()):
                    text = gravity_warnings.nth(j).text_content() or ""
                    if "gravity" in text.lower() or "Gravity" in text:
                        gravity_warn_texts.append(text)

                _safe_assert(
                    reporter, len(gravity_warn_texts) == 0,
                    "Minor", "Gravity 5 shows validation warning when it shouldn't",
                    "Edge Cases", [
                        "Click high-gravity POI (gravity 5)",
                        "Check for gravity-related .beat-warning",
                    ],
                    "No gravity warnings for valid gravity 5",
                    f"Found warnings: {gravity_warn_texts}",
                    page, "ec2-gravity5-warning",
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
                    reporter, len(gravity_warn_texts) == 0,
                    "Minor", "Gravity 1 shows validation warning when it shouldn't",
                    "Edge Cases", [
                        "Click low-gravity POI (gravity 1)",
                        "Check for gravity-related .beat-warning",
                    ],
                    "No gravity warnings for valid gravity 1",
                    f"Found warnings: {gravity_warn_texts}",
                    page, "ec2-gravity1-warning",
                )
                break


# ---------------------------------------------------------------------------
# Test: Upload Flow + Error Handling (ACs #8, #12a) — Task 6
# ---------------------------------------------------------------------------

class TestUploadFlow:
    """Tests for single-POI upload via Mark as Complete and error handling."""

    def test_single_poi_upload(self, browser_page):
        """AC #8: Mark a valid POI as complete, verify progressive upload."""
        page, seed_data, reporter = browser_page

        rows = page.locator(WORKLIST_ROW)

        # Find entry #1 (Boston Harbor Lighthouse — valid, standard)
        target = None
        for i in range(rows.count()):
            row_text = rows.nth(i).text_content() or ""
            if "Harbor Lighthouse" in row_text:
                target = i
                break

        if target is None:
            _safe_assert(
                reporter, False,
                "Critical", "Could not find Harbor Lighthouse POI for upload test",
                "Upload Flow", ["Search worklist"],
                "Entry #1 in worklist", "Not found",
                page, "ac8-poi-not-found",
            )
            return

        rows.nth(target).click()
        page.wait_for_timeout(2000)

        # Click Mark as Complete
        mc_btn = page.locator(MARK_COMPLETE_BTN)
        if mc_btn.count() == 0 or not mc_btn.first.is_visible():
            _safe_assert(
                reporter, False,
                "Critical", "Mark as Complete button not visible",
                "Upload Flow", ["Navigate to valid POI", "Check #markCompleteBtn"],
                "Button visible", "Not visible",
                page, "ac8-no-mc-btn",
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
            if "Harbor Lighthouse" in row_text:
                uploaded_badge = rows.nth(i).locator(BADGE_UPLOADED)
                if uploaded_badge.count() > 0:
                    uploaded_found = True
                break

        # Also check if success toast appeared
        success = page.locator(SUCCESS_TOAST)
        toast_appeared = success.count() > 0 and success.first.is_visible()

        _safe_assert(
            reporter, uploaded_found or toast_appeared,
            "Critical", "POI upload did not complete — no uploaded badge or success toast",
            "Upload Flow", [
                "Navigate to valid POI (Harbor Lighthouse)",
                "Click Mark as Complete",
                "Wait 3s for upload",
                "Check for .badge-uploaded or #successToast",
            ],
            "POI shows uploaded badge or success toast appears",
            f"Uploaded badge: {uploaded_found}, Toast: {toast_appeared}",
            page, "ac8-upload-failed",
        )

        # Verify via API
        if uploaded_found or toast_appeared:
            try:
                poi_name = "UI Test \u2014 Boston Harbor Lighthouse"
                encoded = urllib.parse.quote(poi_name, safe="")
                api_resp = _api_get(f"/graph/poi/{encoded}/beats")
                # API returns {"poi_name": "...", "beats": [...]} — extract beats list
                if isinstance(api_resp, dict) and "beats" in api_resp:
                    beat_count = len(api_resp["beats"])
                    _safe_assert(
                        reporter, beat_count >= 1,
                        "Major", "Uploaded POI has no beats in database",
                        "Upload Flow", [
                            "GET /api/v1/graph/poi/{name}/beats",
                            "Check response",
                        ],
                        "At least 1 beat returned",
                        f"{beat_count} beats returned",
                        page, "ac8-no-api-beats",
                    )
                elif isinstance(api_resp, list):
                    beat_count = len(api_resp)
                    _safe_assert(
                        reporter, beat_count >= 1,
                        "Major", "Uploaded POI has no beats in database",
                        "Upload Flow", [
                            "GET /api/v1/graph/poi/{name}/beats",
                            "Check response",
                        ],
                        "At least 1 beat returned",
                        f"{beat_count} beats returned",
                        page, "ac8-no-api-beats",
                    )
                else:
                    status = api_resp.get("_status", "unknown") if isinstance(api_resp, dict) else "null"
                    _safe_assert(
                        reporter, False,
                        "Major", f"API verification returned error: {status}",
                        "Upload Flow", ["GET /api/v1/graph/poi/{name}/beats"],
                        "200 OK with beat data",
                        f"Response: {api_resp}",
                        page, "ac8-api-error",
                    )
            except Exception as exc:
                _safe_assert(
                    reporter, False,
                    "Minor", f"API verification failed: {exc}",
                    "Upload Flow", ["API call to verify upload"],
                    "Successful API response", str(exc),
                )

        _take_screenshot(page, "ac8-uploaded")

    def test_error_toast_structure(self, browser_page):
        """AC #12a: Error toast exists in DOM with correct structure."""
        page, seed_data, reporter = browser_page

        error_toast = page.locator(ERROR_TOAST)
        _safe_assert(
            reporter, error_toast.count() > 0,
            "Major", "Error toast element (#errorToast) not found in DOM",
            "Error Handling", [
                "Check DOM for #errorToast element",
            ],
            "#errorToast exists in DOM",
            f"Count: {error_toast.count()}",
            page, "ac12a-no-toast",
        )

        _take_screenshot(page, "ac12a-error-toast")


# ---------------------------------------------------------------------------
# Test: Conflict Detection and Resolution (ACs #13-18) — Task 7
# ---------------------------------------------------------------------------

class TestConflictDetection:
    """Tests for conflict detection across all Jaccard bands and resolution actions."""

    def test_conflict_detection_and_resolution(self, browser_page):
        """ACs #13-18: Trigger conflict detection on entry #11, verify all bands and actions."""
        page, seed_data, reporter = browser_page

        rows = page.locator(WORKLIST_ROW)

        # Find entry #11 (UI Test Seed — Old North Church)
        target = None
        for i in range(rows.count()):
            row_text = rows.nth(i).text_content() or ""
            if "Old North Church" in row_text:
                target = i
                break

        if target is None:
            _safe_assert(
                reporter, False,
                "Critical", "Could not find conflict-target POI (Old North Church)",
                "Conflict Detection", ["Search worklist for 'Old North Church'"],
                "Entry #11 in worklist", "Not found",
                page, "ac13-poi-not-found",
            )
            return

        rows.nth(target).click()
        page.wait_for_timeout(2000)

        # Trigger conflict detection via Mark as Complete
        mc_btn = page.locator(MARK_COMPLETE_BTN)
        if mc_btn.count() == 0 or not mc_btn.first.is_visible():
            _safe_assert(
                reporter, False,
                "Critical", "Mark as Complete button not visible for conflict POI",
                "Conflict Detection", ["Navigate to conflict-target POI"],
                "Button visible", "Not visible",
                page, "ac13-no-mc-btn",
            )
            return

        mc_btn.first.click()
        page.wait_for_timeout(3000)  # Wait for conflict detection API calls

        _take_screenshot(page, "ac13-conflict-triggered")

        # --- AC #13: Hard conflict — Beat A (hidden_history, same lens as seed) ---
        hard_badges = page.locator(BEAT_CONFLICT_BADGE_HARD)
        has_hard = hard_badges.count() > 0
        _safe_assert(
            reporter, has_hard,
            "Critical", "No hard conflict badge found after triggering Mark as Complete",
            "Conflict Detection — Hard Match", [
                "Click Mark as Complete on conflict-target POI",
                "Beat A shares lens 'hidden_history' with seeded beat",
                "Check for .beat-conflict-badge-hard",
            ],
            "Red hard conflict badge visible on beat A",
            f"Hard badges found: {hard_badges.count()}",
            page, "ac13-no-hard-badge",
        )

        if has_hard:
            badge_text = hard_badges.first.text_content() or ""
            _safe_assert(
                reporter, "same lens" in badge_text.lower() or "conflict" in badge_text.lower(),
                "Minor", f"Hard conflict badge text unexpected: '{badge_text}'",
                "Conflict Detection — Hard Match", [
                    "Check badge text content",
                ],
                "Text contains 'Conflict (same lens)' or similar",
                f"Text: '{badge_text}'",
                page, "ac13-badge-text",
            )

        # Check side-by-side panel
        conflict_sides = page.locator(CONFLICT_SIDE)
        _safe_assert(
            reporter, conflict_sides.count() > 0,
            "Major", "No side-by-side comparison panel for hard conflict",
            "Conflict Detection — Hard Match", [
                "Check for .conflict-side panel",
            ],
            "Side-by-side panel visible",
            f"Found {conflict_sides.count()} panels",
            page, "ac13-no-side-by-side",
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
            no_conflict = (b_hard.count() == 0 and b_review.count() == 0)
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
                reporter, no_conflict,
                "Major", "Net-new beat B has unexpected conflict badge",
                "Conflict Detection — Net-New", [
                    "Check beat B (music_nightlife) for conflict badges",
                ],
                "No conflict badge on net-new beat",
                f"Hard: {b_hard.count()}, Review: {b_review.count()}, Soft: {b_soft.count()}",
                page, "ac14-unexpected-conflict",
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
                reporter, has_soft,
                "Major", "Soft conflict beat C missing amber conflict badge",
                "Conflict Detection — Soft ≥70%", [
                    "Check beat C (food_culinary, 84% Jaccard vs seed 2)",
                    "Look for amber badge with similarity percentage",
                ],
                "Amber badge with 'Conflict (XX% similar)'",
                f"Badge found: {has_soft}, text: '{soft_text}'",
                page, "ac15-no-soft-badge",
            )

            # Check side-by-side panel for soft conflict
            c_sides = beat_c.locator(CONFLICT_SIDE)
            _safe_assert(
                reporter, c_sides.count() > 0,
                "Major", "No side-by-side panel for soft conflict beat C",
                "Conflict Detection — Soft ≥70%", [
                    "Check for .conflict-side in beat C card",
                ],
                "Side-by-side panel visible",
                f"Found {c_sides.count()} panels",
                page, "ac15-no-side-by-side",
            )

        _take_screenshot(page, "ac15-soft-conflict")

        # --- AC #16: Review band 30-69% — Beat D (art_street) ---
        beat_d_idx = 3
        if beat_cards.count() > beat_d_idx:
            beat_d = beat_cards.nth(beat_d_idx)
            d_review = beat_d.locator(BEAT_CONFLICT_BADGE_REVIEW)
            has_review = d_review.count() > 0

            _safe_assert(
                reporter, has_review,
                "Major", "Review-band beat D missing review badge",
                "Conflict Detection — Review 30-69%", [
                    "Check beat D (art_street, 56% Jaccard vs seed 3)",
                    "Look for .beat-conflict-badge-review",
                ],
                "Yellow review badge with 'Review (XX% similar)'",
                f"Review badges found: {d_review.count()}",
                page, "ac16-no-review-badge",
            )

            if has_review:
                review_text = d_review.first.text_content() or ""
                _safe_assert(
                    reporter, "review" in review_text.lower() or "similar" in review_text.lower(),
                    "Minor", f"Review badge text unexpected: '{review_text}'",
                    "Conflict Detection — Review 30-69%", ["Check badge text"],
                    "Text contains 'Review' and similarity percentage",
                    f"Text: '{review_text}'",
                    page, "ac16-badge-text",
                )

        _take_screenshot(page, "ac16-review-band")

        # --- AC #17: Pass-through <30% — Beat E (nature_green) ---
        beat_e_idx = 4
        if beat_cards.count() > beat_e_idx:
            beat_e = beat_cards.nth(beat_e_idx)
            e_hard = beat_e.locator(BEAT_CONFLICT_BADGE_HARD)
            e_review = beat_e.locator(BEAT_CONFLICT_BADGE_REVIEW)
            e_soft = beat_e.locator(BEAT_CONFLICT_BADGE)

            no_conflict_e = (e_hard.count() == 0 and e_review.count() == 0)
            if e_soft.count() > 0:
                visible_soft_e = False
                for j in range(e_soft.count()):
                    if e_soft.nth(j).is_visible():
                        visible_soft_e = True
                        break
                if visible_soft_e:
                    no_conflict_e = False

            _safe_assert(
                reporter, no_conflict_e,
                "Major", "Pass-through beat E has unexpected conflict badge",
                "Conflict Detection — Pass-through <30%", [
                    "Check beat E (nature_green, <2% Jaccard)",
                    "Should have no conflict badge",
                ],
                "No conflict badge on pass-through beat",
                f"Hard: {e_hard.count()}, Review: {e_review.count()}, Soft: {e_soft.count()}",
                page, "ac17-unexpected-conflict",
            )

        _take_screenshot(page, "ac17-pass-through")

        # --- AC #18: Conflict Resolution Actions ---
        # Test Replace action on hard-conflict beat (beat 0)
        self._test_resolution_action(
            page, reporter, beat_cards, 0,
            "replace", "Will replace", "ac18-replace",
        )

        # Test Skip action on soft-conflict beat (beat 2)
        self._test_resolution_action(
            page, reporter, beat_cards, 2,
            "skip", "Will skip", "ac18-skip",
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
                reporter, has_label,
                "Major",
                f"'{action.capitalize()}' resolution missing '{expected_label}' label",
                f"Conflict Resolution — {action.capitalize()}", [
                    f"Click '{action}' on beat #{beat_idx + 1}",
                    f"Check for '{expected_label}' label",
                ],
                f"Label '{expected_label}' visible",
                f"Beat text excerpt: '{beat_text[:200]}'",
                page, screenshot_name,
            )
        else:
            _safe_assert(
                reporter, False,
                "Major", f"Could not find '{action}' resolution action on beat #{beat_idx + 1}",
                f"Conflict Resolution — {action.capitalize()}", [
                    f"Look for '{action}' button/option on beat card",
                ],
                f"'{action.capitalize()}' action available",
                "Action not found",
                page, f"{screenshot_name}-not-found",
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
                reporter, has_overlay,
                "Major", "Merge overlay did not open after clicking Merge",
                "Conflict Resolution — Merge", [
                    f"Click 'Merge' on beat #{beat_idx + 1}",
                    "Check for .merge-overlay",
                ],
                "Merge overlay opens",
                f"Overlay found: {has_overlay}",
                page, f"{screenshot_name}-no-overlay",
            )

            _take_screenshot(page, screenshot_name)

            # Close merge overlay if open (click cancel/close or press Escape)
            if has_overlay:
                close_btns = overlay.locator("button:has-text('Cancel')")
                if close_btns.count() > 0:
                    close_btns.first.click()
                else:
                    page.keyboard.press("Escape")
                page.wait_for_timeout(300)
        else:
            _safe_assert(
                reporter, False,
                "Major", f"Could not find 'Merge' action on beat #{beat_idx + 1}",
                "Conflict Resolution — Merge", [
                    "Look for 'Merge' button on review-band beat",
                ],
                "'Merge' action available",
                "Not found",
                page, f"{screenshot_name}-not-found",
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
        page, seed_data, reporter = browser_page
        result = page.evaluate("""() => {
            // POI far from any existing (200m+ away)
            const testPoi = { latitude: 42.40, longitude: -71.20 };
            return findProximityMatches(testPoi, cachedPoiList);
        }""")
        assert isinstance(result, list)
        assert len(result) == 0, "Distant POI should have no proximity matches"

    def test_find_proximity_matches_returns_nearby(self, browser_page):
        """AC 2: POI within 50m of one existing → single match returned."""
        page, seed_data, reporter = browser_page
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
        page, seed_data, reporter = browser_page
        result = page.evaluate("""() => {
            // Create two fake cached POIs close together, test a point near both
            const fakeCached = [
                { properties: { name: 'A', location: { lat: 42.3601, lng: -71.0589 } } },
                { properties: { name: 'B', location: { lat: 42.3603, lng: -71.0589 } } },
            ];
            const testPoi = { latitude: 42.3602, longitude: -71.0589 };
            const matches = findProximityMatches(testPoi, fakeCached);
            return matches.map(m => ({ name: m.existingPoi.properties.name, dist: m.distanceM }));
        }""")
        assert len(result) == 2, "Should match both nearby POIs"
        assert result[0]["dist"] <= result[1]["dist"], "Matches should be sorted by distance"

    def test_same_name_distant_poi_is_new(self, browser_page):
        """AC 8: Identical names 200m apart → both auto-new (no proximity match)."""
        page, seed_data, reporter = browser_page
        result = page.evaluate("""() => {
            const fakeCached = [
                { properties: { name: 'Old City Hall', location: { lat: 42.3580, lng: -71.0589 } } },
            ];
            // Same name, 200m away
            const testPoi = { latitude: 42.3600, longitude: -71.0589 };
            return findProximityMatches(testPoi, fakeCached);
        }""")
        assert len(result) == 0, "Same-name POI 200m away should have no proximity match"

    def test_detect_conflicts_missing_coords(self, browser_page):
        """AC 7: POI without coordinates → missingCoords: true."""
        page, seed_data, reporter = browser_page
        result = page.evaluate("""() => {
            const testPoi = { poi_name: 'No Coords POI', beats: [] };
            return detectConflictsForPoi(testPoi);
        }""")
        assert result["missingCoords"] is True
        assert len(result["errors"]) > 0

    def test_detect_conflicts_auto_new_no_match(self, browser_page):
        """AC 1: POI with no nearby existing → isNew: true."""
        page, seed_data, reporter = browser_page
        result = page.evaluate("""() => {
            const testPoi = { poi_name: 'Distant POI', latitude: 42.40, longitude: -71.20, beats: [] };
            return detectConflictsForPoi(testPoi);
        }""")
        assert result["isNew"] is True
        assert len(result["proximityMatches"]) == 0

    def test_map_poi_for_api_with_existing_name(self, browser_page):
        """AC 6: useExistingName sends the existing name in payload."""
        page, seed_data, reporter = browser_page
        result = page.evaluate("""() => {
            const poi = { poi_name: 'Incoming Name', latitude: 42.36, longitude: -71.06 };
            return mapPoiForApi(poi, { useExistingName: 'Existing Name' });
        }""")
        assert result["name"] == "Existing Name"

    def test_map_poi_for_api_with_force_create(self, browser_page):
        """AC 5: forceCreate sends force_create: true."""
        page, seed_data, reporter = browser_page
        result = page.evaluate("""() => {
            const poi = { poi_name: 'Test POI', latitude: 42.36, longitude: -71.06 };
            return mapPoiForApi(poi, { forceCreate: true });
        }""")
        assert result["force_create"] is True

    def test_name_similarity_function(self, browser_page):
        """Name similarity is computed correctly for display."""
        page, seed_data, reporter = browser_page
        result = page.evaluate("""() => {
            return {
                identical: nameSimilarity('Old City Hall', 'Old City Hall'),
                similar: nameSimilarity('Old City Hall', 'The Old City Hall'),
                different: nameSimilarity('Old City Hall', 'Boston Common'),
            };
        }""")
        assert result["identical"] == 1.0
        assert result["similar"] > 0.5
        assert result["different"] < 0.5

    def test_boundary_50m_excluded(self, browser_page):
        """Edge: POI at exactly >50m is excluded from proximity matches."""
        page, seed_data, reporter = browser_page
        result = page.evaluate("""() => {
            // Place existing POI and incoming ~51m apart (about 0.00046 degrees lat)
            const fakeCached = [
                { properties: { name: 'Boundary POI', location: { lat: 42.3600, lng: -71.0589 } } },
            ];
            const testPoi = { latitude: 42.36046, longitude: -71.0589 };
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
        page, seed_data, reporter = browser_page

        report_path = reporter.save_report()

        assert report_path.exists(), f"Bug report not found at {report_path}"

        content = report_path.read_text(encoding="utf-8")
        assert "# Editorial Workbench UI Bug Report" in content
        assert "## Summary" in content
        assert "Tests run:" in content
        assert "Issues found:" in content

        _take_screenshot(page, "final-state")
