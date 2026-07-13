"""Hermetic proof for scripts/prune_orphan_pois — no live graph.

A destructive tool must be adversarially tested before it touches prod: this
proves it deletes EXACTLY the repo-orphan nodes, aborts a mass-orphan wipe, and
mutates nothing on a dry-run. A fake session records every query so we can assert
which DELETEs ran (and, crucially, which did not).
"""

from __future__ import annotations

import pytest

from scripts.prune_orphan_pois import compute_orphans, orphan_cap, run_prune


def _silent(*_a):
    pass


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def data(self):
        return self._rows

    def single(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    """Returns canned detection rows; records DELETE queries instead of running
    them. ``other_counts`` feeds the cross-city tripwire query (before, after)."""

    def __init__(self, poi_rows, beat_rows, other_counts=(7, 7)):
        self._poi_rows = poi_rows
        self._beat_rows = beat_rows
        self._other = list(other_counts)
        self.deletes: list[tuple[str, dict]] = []

    def run(self, query, **params):
        if "p.city_name <> $slug" in query:  # cross-city tripwire
            return _Result([{"n": self._other.pop(0)}])
        if "RETURN p.name AS name" in query:
            return _Result(self._poi_rows)
        if "HAS_BEAT" in query and "b.beat_id AS id" in query:
            return _Result(self._beat_rows)
        if "DETACH DELETE b" in query:
            self.deletes.append(("beats", params))
            return _Result([{"n": len(params.get("ids", []))}])
        if "DETACH DELETE p" in query:
            self.deletes.append(("pois", params))
            return _Result([{"n": len(params.get("keys", []))}])
        raise AssertionError(f"unexpected query: {query}")

    def execute_write(self, fn):
        # Neo4j runs fn in a transaction that rolls back if fn raises. The fake
        # just propagates the exception (the test asserts on it).
        return fn(self)


# Graph has 3 POIs (2 canonical + 1 stale) and 2 beats (1 canonical + 1 stale).
_POIS = [
    {"name": "Asia Society", "name_key": "asia society"},
    {"name": "Nicholas Roerich Museum", "name_key": "nicholas roerich museum"},
    {"name": "Asia Society and Museum", "name_key": "asia society and museum"},  # stale
]
_BEATS = [{"id": "keep_beat_1"}, {"id": "stale_beat_1"}]
_REPO_POI_KEYS = {"asia society", "nicholas roerich museum"}
_REPO_BEAT_IDS = {"keep_beat_1"}


def test_computes_exactly_the_orphans():
    total, orphan_pois, orphan_beats = compute_orphans(
        _POIS, _BEATS, _REPO_POI_KEYS, _REPO_BEAT_IDS
    )
    assert total == 3
    assert orphan_pois == [("Asia Society and Museum", "asia society and museum")]
    assert orphan_beats == ["stale_beat_1"]


def test_dry_run_mutates_nothing():
    sess = _FakeSession(_POIS, _BEATS)
    code = run_prune(sess, "new_york", _REPO_POI_KEYS, _REPO_BEAT_IDS, apply=False, echo=_silent)
    assert code == 0
    assert sess.deletes == []  # the whole point: no delete without --apply


def test_apply_deletes_beats_then_pois_exactly():
    sess = _FakeSession(_POIS, _BEATS)
    code = run_prune(sess, "new_york", _REPO_POI_KEYS, _REPO_BEAT_IDS, apply=True, echo=_silent)
    assert code == 0
    assert [kind for kind, _ in sess.deletes] == ["beats", "pois"]  # beats before POIs
    assert sess.deletes[0][1]["ids"] == ["stale_beat_1"]
    assert sess.deletes[1][1]["keys"] == ["asia society and museum"]


def test_clean_graph_deletes_nothing():
    sess = _FakeSession(_POIS[:2], _BEATS[:1])  # only canonical nodes
    code = run_prune(sess, "new_york", _REPO_POI_KEYS, _REPO_BEAT_IDS, apply=True, echo=_silent)
    assert code == 0
    assert sess.deletes == []


def test_cap_aborts_a_mass_orphan_wipe():
    # A name_key normalization bug: EVERY POI reads as an orphan. The cap must
    # abort before deleting anything, even with --apply.
    stale = [{"name": f"p{i}", "name_key": f"k{i}"} for i in range(50)]
    sess = _FakeSession(stale, [])
    code = run_prune(sess, "new_york", {"nothing"}, set(), apply=True, echo=_silent)
    assert code == 2
    assert sess.deletes == []  # nothing deleted on abort


def test_force_bypasses_the_cap():
    stale = [{"name": f"p{i}", "name_key": f"k{i}"} for i in range(50)]
    sess = _FakeSession(stale, [])
    code = run_prune(sess, "new_york", {"nothing"}, set(), apply=True, force=True, echo=_silent)
    assert code == 0
    assert [kind for kind, _ in sess.deletes] == ["pois"]  # only POIs (no orphan beats here)


def test_cross_city_tripwire_rolls_back():
    # Another city's POI count changes during the delete (7 -> 6): the tripwire
    # must raise so the transaction rolls back — a prod safety net.
    sess = _FakeSession(_POIS, _BEATS, other_counts=(7, 6))
    with pytest.raises(RuntimeError, match="TRIPWIRE"):
        run_prune(sess, "new_york", _REPO_POI_KEYS, _REPO_BEAT_IDS, apply=True, echo=_silent)


def test_cap_scales_with_graph_size():
    assert orphan_cap(0) == 20  # absolute floor
    assert orphan_cap(1000) == 150  # 15%
