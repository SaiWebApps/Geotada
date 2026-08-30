"""W5.12 — set up the two persona days for the kill-criterion measurement ON the
iOS Simulator (plan W5.12): a disposable user + profile on the dev graph, a bearer
token minted with the running API's own secret (this script runs under the same
`dev_env.py exec --profile local --render` wrapper `make api` uses), and the two
W5.1 persona days GENERATED and COMPOSED over the real wire (:8000) so each has a
living session (v1) the phone can hold. Prints the dart-defines the integration
test needs; writes the trip ids to w512-trips.json (no token in the repo — it goes
to stdout only, for the shell that launches the test).

Teardown: `python w512_setup.py --teardown` deletes the user, profile and trips.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))

from neo4j import GraphDatabase  # noqa: E402

from src.api.auth.tokens import create_access_token  # noqa: E402

API = "http://127.0.0.1:8000/api/v1"
HERE = pathlib.Path(__file__).resolve().parent
USER_ID = "w512-sim-user"
USER_EMAIL = "w512-sim@example.invalid"
PROFILE_ID = "w512-sim-profile"

# The two W5.1 persona requests, as /trips/generate wants them (both clock halves).
FD = {
    "profile_id": PROFILE_ID, "center_lat": 48.856407, "center_lng": 2.342655,
    "duration_min": 180, "round_trip": False, "start_date": "2026-08-23", "end_date": "2026-08-23",
    "start_time": "15:00", "party": "couple", "weather": "dry",
}
RO = {
    "profile_id": PROFILE_ID, "center_lat": 48.859962, "center_lng": 2.326561,
    "duration_min": 180, "round_trip": True, "start_date": "2026-08-19", "end_date": "2026-08-19",
    "start_time": "14:00", "party": "take_it_easy", "lenses": ["visual_art"],
}
# W5.13: Rosemary's day at her own doc's leg length. Under her preset's 12-minute cap
# the street-certified day (S5.4) is ONE stop with no rest — the bench day's Orangerie
# leg is 13 min by the street (11 by estimate). At 13 the bench day comes back; the demo
# replays her trace on both, and the regression is the closing panel's.
RO13 = {**RO, "max_leg_minutes": 13}


def _driver():
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    return GraphDatabase.driver(
        uri, auth=(os.environ.get("NEO4J_USER", "neo4j"), os.environ.get("NEO4J_PASSWORD", ""))
    )


def _call(method: str, path: str, token: str, body: dict | None = None):
    req = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=900) as resp:
            return resp.status, json.load(resp), time.perf_counter() - t0
    except urllib.error.HTTPError as e:
        try:
            d = json.load(e)
        except Exception:  # noqa: BLE001
            d = {"detail": "<unparseable>"}
        return e.code, d, time.perf_counter() - t0


def teardown() -> None:
    with _driver() as d, d.session() as s:
        s.run(
            "MATCH (p:Profile {id: $pid})-[:IS_CAPTAIN_OF]->(t:Trip) "
            "OPTIONAL MATCH (t)-[:HAS_ITEM]->(i) DETACH DELETE i, t",
            pid=PROFILE_ID,
        )
        s.run("MATCH (p:Profile {id: $pid}) DETACH DELETE p", pid=PROFILE_ID)
        s.run("MATCH (u:User {id: $uid}) DETACH DELETE u", uid=USER_ID)
    print("torn down")


def main() -> None:
    if "--teardown" in sys.argv:
        teardown()
        return
    with _driver() as d, d.session() as s:
        s.run("MERGE (u:User {id: $uid}) SET u.email = $email", uid=USER_ID, email=USER_EMAIL)
        s.run(
            "MERGE (p:Profile {id: $pid}) SET p.display_name = 'W5.12 Simulator' "
            "WITH p MATCH (u:User {id: $uid}) MERGE (u)-[:HAS_PROFILE]->(p)",
            pid=PROFILE_ID,
            uid=USER_ID,
        )
    token = create_access_token(USER_ID, USER_EMAIL)
    trips: dict[str, dict] = {}
    wanted = [a for a in sys.argv[1:] if not a.startswith("--")] or ["FD", "RO"]
    for name, body in (("FD", FD), ("RO", RO), ("RO13", RO13)):
        if name not in wanted:
            continue
        code, gen, secs = _call("POST", "/trips/generate", token, body)
        print(f"{name} generate: HTTP {code} in {secs:.1f} s", file=sys.stderr)
        if code != 201:
            print(json.dumps(gen)[:400], file=sys.stderr)
            continue
        trip_id = gen["trip_id"]
        # Compose authors with a provider and verifies faithfulness; a 422 (the
        # verifier refused twice) is the LLM path's own weather — try three times.
        for attempt in range(1, 4):
            code, comp, secs = _call(
                "POST", f"/trips/{trip_id}/compose", token, {"route_id": f"{trip_id}-opt1"}
            )
            print(
                f"{name} compose attempt {attempt}: HTTP {code} in {secs:.1f} s "
                f"(v{comp.get('plan_version')})",
                file=sys.stderr,
            )
            if code == 200:
                break
        code, sess, secs = _call("GET", f"/trips/{trip_id}/session", token)
        print(
            f"{name} session: HTTP {code} in {secs:.2f} s — {len(sess.get('stops', []))} stops, "
            f"{len(sess.get('contingencies', []))} contingencies, day start {sess.get('day_start_hhmm')}",
            file=sys.stderr,
        )
        trips[name] = {"trip_id": trip_id, "stops": len(sess.get("stops", [])),
                       "contingencies": len(sess.get("contingencies", []))}
        (HERE / f"w512-session-{name}.json").write_text(json.dumps(sess, indent=1))
    existing = json.loads((HERE / "w512-trips.json").read_text()) if (HERE / "w512-trips.json").exists() else {}
    existing.update(trips)
    trips = existing
    (HERE / "w512-trips.json").write_text(json.dumps(trips, indent=1))
    # The dart-defines for the launcher (the token is NOT written to the repo).
    print(
        " ".join(
            [
                f"--dart-define=W512_TOKEN={token}",
                f"--dart-define=W512_PROFILE={PROFILE_ID}",
                f"--dart-define=W512_TRIP_FD={trips.get('FD', {}).get('trip_id', '')}",
                f"--dart-define=W512_TRIP_RO={trips.get('RO', {}).get('trip_id', '')}",
                f"--dart-define=W512_TRIP_RO13={trips.get('RO13', {}).get('trip_id', '')}",
                "--dart-define=API_BASE_URL=http://127.0.0.1:8000/api/v1",
            ]
        )
    )


if __name__ == "__main__":
    main()
