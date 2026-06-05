"""Build the pre-computed walking distance matrix for a city.

Queries every POI for the city from Neo4j, then computes a full
ordered-pair walking distance/duration matrix via OSRM's ``/table``
service (foot profile). We use ``/table`` batching rather than per-pair
``/route`` for efficiency: for each source POI ``i`` we issue one
``/table?sources={i}`` call that returns the distances/durations from
``i`` to every POI in one request. Every ordered pair ``i→j`` (i≠j),
both directions, is written.

The result is written to ``data/{city}/distance_matrix.sqlite``:

- ``pairs(from_poi_id, to_poi_id, distance_m, duration_sec)`` — one row
  per ordered pair. Unroutable cells / failed source calls are stored as
  the sentinel ``distance_m=-1, duration_sec=-1``.
- ``poi_coords(poi_id, lat, lng)`` — for PII-safe nearest-POI labelling
  at runtime.
- ``meta(corpus_version_hash, built_at_iso, osm_extract_date, pair_count)``.

Usage:
    python scripts/build_distance_matrix.py <city> [--rebuild]
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sqlite3
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

from src.connection import abort_on_connection_error, create_driver, get_database

OSM_EXTRACT_DATE = "2026-06-03"
_DEFAULT_OSRM_BASE_URL = "http://127.0.0.1:5000"
_SOURCE_RETRIES = 3

POI_QUERY = (
    "MATCH (p:POI) WHERE p.city_name = $city "
    "RETURN p.id AS id, p.location.y AS lat, p.location.x AS lng "
    "ORDER BY p.id"
)


def _base_url() -> str:
    return os.getenv("OSRM_BASE_URL", _DEFAULT_OSRM_BASE_URL)


def _load_pois(city: str) -> list[tuple[str, float, float]]:
    """Return [(poi_id, lat, lng)] for the city, in a stable id order."""
    driver = create_driver()
    try:
        with driver.session(database=get_database()) as session:
            records = session.run(POI_QUERY, city=city)
            return [(r["id"], float(r["lat"]), float(r["lng"])) for r in records]
    finally:
        driver.close()


def _corpus_hash(pois: list[tuple[str, float, float]]) -> str:
    """Stable hash of the sorted (poi_id, lat, lng) list."""
    h = hashlib.sha256()
    for poi_id, lat, lng in sorted(pois):
        h.update(f"{poi_id}|{lat:.6f}|{lng:.6f}\n".encode())
    return h.hexdigest()


def _table_for_source(
    client: httpx.Client,
    coord_str: str,
    source_idx: int,
    n: int,
) -> tuple[list[float | None], list[float | None]]:
    """Call OSRM /table for one source row. Retries up to 3x.

    Returns (distances_row, durations_row), each a length-n list whose
    entries are float metres/seconds or None for unroutable cells. On
    total failure, returns rows of all-None.
    """
    url = (
        f"{_base_url()}/table/v1/foot/{coord_str}"
        f"?sources={source_idx}&annotations=distance,duration"
    )
    last_exc: Exception | None = None
    for attempt in range(_SOURCE_RETRIES):
        try:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != "Ok":
                raise RuntimeError(f"OSRM code={data.get('code')!r}")
            distances = data.get("distances") or [[None] * n]
            durations = data.get("durations") or [[None] * n]
            return (list(distances[0]), list(durations[0]))
        except Exception as exc:  # noqa: BLE001 — retry, then sentinel-fill
            last_exc = exc
            if attempt < _SOURCE_RETRIES - 1:
                time.sleep(0.5 * (2**attempt))
    print(
        f"  ! source {source_idx} failed after {_SOURCE_RETRIES} attempts: {last_exc}",
        file=sys.stderr,
    )
    return ([None] * n, [None] * n)


def _build_pairs(
    pois: list[tuple[str, float, float]],
) -> tuple[list[tuple[str, str, float, int]], int]:
    """Compute every ordered pair via /table batching.

    Returns (rows, sentinel_count) where each row is
    (from_poi_id, to_poi_id, distance_m, duration_sec).
    """
    ids = [p[0] for p in pois]
    n = len(pois)
    # OSRM expects lng,lat;lng,lat;... in the SAME stable index order.
    coord_str = ";".join(f"{lng},{lat}" for _id, lat, lng in pois)

    rows: list[tuple[str, str, float, int]] = []
    sentinel_count = 0

    with httpx.Client(trust_env=False, timeout=60.0) as client:
        for i in range(n):
            distances, durations = _table_for_source(client, coord_str, i, n)
            for j in range(n):
                if i == j:
                    continue
                dist = distances[j] if j < len(distances) else None
                dur = durations[j] if j < len(durations) else None
                if dist is None or dur is None:
                    rows.append((ids[i], ids[j], -1.0, -1))
                    sentinel_count += 1
                else:
                    rows.append((ids[i], ids[j], float(dist), int(round(float(dur)))))
            if (i + 1) % 25 == 0 or i + 1 == n:
                print(f"  ... {i + 1}/{n} sources processed")

    return rows, sentinel_count


def _write_sqlite(
    path: Path,
    pois: list[tuple[str, float, float]],
    rows: list[tuple[str, str, float, int]],
    corpus_hash: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            "CREATE TABLE pairs ("
            "from_poi_id TEXT, to_poi_id TEXT, distance_m REAL, duration_sec INTEGER, "
            "PRIMARY KEY (from_poi_id, to_poi_id))"
        )
        conn.execute("CREATE TABLE poi_coords (poi_id TEXT PRIMARY KEY, lat REAL, lng REAL)")
        conn.execute(
            "CREATE TABLE meta ("
            "corpus_version_hash TEXT, built_at_iso TEXT, "
            "osm_extract_date TEXT, pair_count INTEGER)"
        )
        conn.executemany(
            "INSERT INTO pairs (from_poi_id, to_poi_id, distance_m, duration_sec) "
            "VALUES (?, ?, ?, ?)",
            rows,
        )
        conn.executemany(
            "INSERT INTO poi_coords (poi_id, lat, lng) VALUES (?, ?, ?)",
            pois,
        )
        conn.execute(
            "INSERT INTO meta (corpus_version_hash, built_at_iso, osm_extract_date, pair_count) "
            "VALUES (?, ?, ?, ?)",
            (
                corpus_hash,
                datetime.now(UTC).isoformat(),
                OSM_EXTRACT_DATE,
                len(rows),
            ),
        )
        conn.commit()
    finally:
        conn.close()


@abort_on_connection_error
def main() -> int:
    parser = argparse.ArgumentParser(description="Build the city walking distance matrix.")
    parser.add_argument("city", help="city name as stored on POI.city_name (e.g. 'paris')")
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="rebuild even if a matrix already exists",
    )
    args = parser.parse_args()

    out_path = Path("data") / args.city / "distance_matrix.sqlite"
    if out_path.exists() and not args.rebuild:
        print(f"Matrix already exists at {out_path}. Pass --rebuild to overwrite.")
        return 0

    start = time.time()
    print(f"Loading POIs for city={args.city!r} ...")
    pois = _load_pois(args.city)
    if not pois:
        print(f"No POIs found for city={args.city!r}. Nothing to build.", file=sys.stderr)
        return 1
    print(f"Loaded {len(pois)} POIs. Computing pairs via OSRM /table ...")

    rows, sentinel_count = _build_pairs(pois)
    corpus_hash = _corpus_hash(pois)
    _write_sqlite(out_path, pois, rows, corpus_hash)

    elapsed = time.time() - start
    print(
        f"\nDone. POIs={len(pois)} pairs={len(rows)} "
        f"sentinels={sentinel_count} elapsed={elapsed:.1f}s\n"
        f"Wrote {out_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
