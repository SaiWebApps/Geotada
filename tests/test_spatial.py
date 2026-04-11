"""Unit tests for src/utils/spatial.py — no Neo4j required."""

from __future__ import annotations

import math

from src.utils.spatial import coords_to_wkt, point_in_polygon, simplify_polygon


# ---------------------------------------------------------------------------
# coords_to_wkt
# ---------------------------------------------------------------------------

class TestCoordsToWkt:
    def test_format(self):
        coords = [(48.85, 2.34), (48.86, 2.34), (48.86, 2.35), (48.85, 2.34)]
        wkt = coords_to_wkt(coords)
        assert wkt.startswith("POLYGON((")
        assert wkt.endswith("))")

    def test_closes_polygon(self):
        coords = [(48.85, 2.34), (48.86, 2.34), (48.86, 2.35)]  # not closed
        wkt = coords_to_wkt(coords)
        parts = wkt.replace("POLYGON((", "").replace("))", "").split(",")
        assert parts[0].strip() == parts[-1].strip()

    def test_wkt_lng_lat_ordering(self):
        coords = [(48.85, 2.34), (48.86, 2.35), (48.85, 2.34)]
        wkt = coords_to_wkt(coords)
        # WKT uses "lng lat" ordering — first pair should be "2.34 48.85"
        inner = wkt.replace("POLYGON((", "").replace("))", "")
        first_pair = inner.split(",")[0].strip()
        assert first_pair == "2.34 48.85"


# ---------------------------------------------------------------------------
# point_in_polygon
# ---------------------------------------------------------------------------

# Simple square polygon around central Paris
SQUARE_WKT = "POLYGON((2.33 48.84, 2.36 48.84, 2.36 48.87, 2.33 48.87, 2.33 48.84))"


class TestPointInPolygon:
    def test_interior_point(self):
        assert point_in_polygon(48.855, 2.345, SQUARE_WKT) is True

    def test_exterior_point(self):
        assert point_in_polygon(48.90, 2.50, SQUARE_WKT) is False

    def test_boundary_point(self):
        # Point exactly on boundary — covers() should return True
        assert point_in_polygon(48.84, 2.345, SQUARE_WKT) is True

    def test_vertex_point(self):
        # Point exactly on a vertex — covers() should return True
        assert point_in_polygon(48.84, 2.33, SQUARE_WKT) is True

    def test_notre_dame_in_ile_de_la_cite(self):
        # Simplified Ile de la Cite polygon for unit testing
        ile_wkt = (
            "POLYGON(("
            "2.3387 48.8540, 2.3420 48.8555, 2.3475 48.8555, "
            "2.3520 48.8545, 2.3530 48.8530, 2.3510 48.8515, "
            "2.3460 48.8510, 2.3400 48.8520, 2.3387 48.8540"
            "))"
        )
        # Notre-Dame at 48.8530, 2.3499
        assert point_in_polygon(48.8530, 2.3499, ile_wkt) is True
        # Point clearly outside (north bank)
        assert point_in_polygon(48.860, 2.349, ile_wkt) is False


# ---------------------------------------------------------------------------
# simplify_polygon
# ---------------------------------------------------------------------------

class TestSimplifyPolygon:
    def test_simplify_within_range(self):
        # Generate a 50-vertex circle
        coords = [
            (math.cos(i * 2 * math.pi / 50), math.sin(i * 2 * math.pi / 50))
            for i in range(50)
        ]
        coords.append(coords[0])  # close it
        result = simplify_polygon(coords, max_vertices=15)
        vertex_count = len(result) - 1  # exclude closing point
        assert 5 <= vertex_count <= 15

    def test_small_polygon_unchanged(self):
        # A triangle — already below max_vertices, should pass through
        coords = [(0, 0), (1, 0), (0.5, 1), (0, 0)]
        result = simplify_polygon(coords, max_vertices=15)
        vertex_count = len(result) - 1
        assert vertex_count == 3

    def test_result_is_closed(self):
        coords = [
            (math.cos(i * 2 * math.pi / 30), math.sin(i * 2 * math.pi / 30))
            for i in range(30)
        ]
        coords.append(coords[0])
        result = simplify_polygon(coords, max_vertices=10)
        assert result[0] == result[-1]
