#!/usr/bin/env python3
"""Strip pdftotext map-label artifacts from a chunk file.

Detects runs of sparse-whitespace lines (map text labels that pdftotext renders
as long lines with massive whitespace padding around 1-3 tiny fragments) and
removes them. Preserves prose verbatim. Writes <chunk>.cleaned.txt alongside
the original; never overwrites.

Usage:
    python3 scripts/strip_pdf_artifacts.py <chunk_file_or_dir> [<chunk_file_or_dir> ...]

If a directory is passed, every *.txt under it (excluding existing *.cleaned.txt)
is processed.

Heuristic:
    - "Sparse line" = length >= 30 AND has >0 non-ws chars AND non-ws/total < 0.15
    - Removable run = >=5 consecutive sparse lines (up to 2 blank lines tolerated
      within a run; blank streaks >2 close the run)
    - Lines outside such runs are kept verbatim
    - Box-drawing-character-dense lines (>50% of non-ws is | + - = ─ ┐ ┘ etc.)
      are also marked sparse to catch any future ASCII-art borders

Validated 2026-04-25 on:
    - rough-guide-paris/chunk-01-islands.txt (known good): 0 prose lines lost,
      10% normalized-char reduction (all map labels)
    - rough-guide-paris/chunk-06-marais.txt (stalled extraction): 17% reduction
    - rough-guide-paris/chunk-08-quartier-latin.txt (stalled extraction): 15% reduction
    - frommers-24-great-walks/chunk-01-birthplace-of-the-city.txt (known good):
      0% reduction (no map artifacts in source)
"""
from __future__ import annotations

import sys
from pathlib import Path

BOX_CHARS = set("|+-=─┐┘└┌│╔╗╚╝═║▌█░▒▓")

MIN_RUN_LINES = 5
SPARSE_DENSITY_MAX = 0.15
SPARSE_MIN_LINE_LEN = 30
BOX_DENSITY_MIN = 0.50
BOX_MIN_NON_WS = 3
BLANK_TOLERANCE = 2


def line_is_sparse(line: str) -> bool:
    ll = len(line)
    if ll < SPARSE_MIN_LINE_LEN:
        return False
    nws = ll - sum(1 for c in line if c.isspace())
    if nws == 0:
        return False
    return nws / ll < SPARSE_DENSITY_MAX


def line_is_box_dense(line: str) -> bool:
    stripped = "".join(c for c in line if not c.isspace())
    n = len(stripped)
    if n < BOX_MIN_NON_WS:
        return False
    box = sum(1 for c in stripped if c in BOX_CHARS)
    return box / n > BOX_DENSITY_MIN


def find_removal_ranges(lines: list[str]) -> list[tuple[int, int]]:
    """Return half-open [start, end) line ranges to remove."""
    ranges: list[tuple[int, int]] = []
    current_start: int | None = None
    blank_streak = 0
    for i, l in enumerate(lines):
        nws = len(l) - sum(1 for c in l if c.isspace())
        is_removable = line_is_sparse(l) or line_is_box_dense(l)
        is_blank = nws == 0
        if is_removable:
            if current_start is None:
                current_start = i
            blank_streak = 0
        elif is_blank:
            blank_streak += 1
            if blank_streak > BLANK_TOLERANCE and current_start is not None:
                end = i - blank_streak
                if end - current_start >= MIN_RUN_LINES:
                    ranges.append((current_start, end))
                current_start = None
                blank_streak = 0
        else:
            if current_start is not None:
                end = i
                if end - current_start >= MIN_RUN_LINES:
                    ranges.append((current_start, end))
            current_start = None
            blank_streak = 0
    if current_start is not None and len(lines) - current_start >= MIN_RUN_LINES:
        ranges.append((current_start, len(lines)))
    return ranges


def clean_chunk(src_path: Path) -> tuple[Path, dict]:
    raw = src_path.read_text()
    lines = raw.splitlines()
    ranges = find_removal_ranges(lines)
    removed = set()
    for start, end in ranges:
        for k in range(start, end):
            removed.add(k)
    cleaned_lines = [l for i, l in enumerate(lines) if i not in removed]
    cleaned = "\n".join(cleaned_lines) + ("\n" if raw.endswith("\n") else "")

    out_path = src_path.with_suffix(".cleaned.txt")
    if src_path.suffix == ".txt":
        out_path = src_path.with_name(src_path.stem + ".cleaned.txt")
    out_path.write_text(cleaned)

    raw_chars = len(raw)
    cleaned_chars = len(cleaned)
    raw_nonws = sum(1 for c in raw if not c.isspace())
    cleaned_nonws = sum(1 for c in cleaned if not c.isspace())
    stats = {
        "src": str(src_path),
        "out": str(out_path),
        "lines_before": len(lines),
        "lines_after": len(cleaned_lines),
        "lines_removed": len(removed),
        "line_reduction_pct": round(100 * len(removed) / len(lines), 1) if lines else 0,
        "raw_chars": raw_chars,
        "cleaned_chars": cleaned_chars,
        "char_reduction_pct": round(100 * (raw_chars - cleaned_chars) / raw_chars, 1) if raw_chars else 0,
        "raw_nonws": raw_nonws,
        "cleaned_nonws": cleaned_nonws,
        "nonws_reduction_pct": round(100 * (raw_nonws - cleaned_nonws) / raw_nonws, 1) if raw_nonws else 0,
        "ranges": [[s, e] for s, e in ranges],
    }
    return out_path, stats


def gather_inputs(args: list[str]) -> list[Path]:
    paths: list[Path] = []
    for a in args:
        p = Path(a)
        if p.is_dir():
            for f in sorted(p.glob("*.txt")):
                if f.name.endswith(".cleaned.txt"):
                    continue
                paths.append(f)
        elif p.is_file():
            paths.append(p)
        else:
            print(f"WARN: not found: {a}", file=sys.stderr)
    return paths


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    inputs = gather_inputs(sys.argv[1:])
    if not inputs:
        print("no input files", file=sys.stderr)
        return 1

    suspicious = []
    print(f"{'file':<70} {'lines_b':>8} {'lines_a':>8} {'line%':>6} {'nonws%':>7}")
    for p in inputs:
        out_path, stats = clean_chunk(p)
        suspicious_flag = ""
        if stats["nonws_reduction_pct"] > 40:
            suspicious_flag = "  *SUSPICIOUS (>40% non-ws removed)"
            suspicious.append((p, stats))
        rel = str(p).replace("/Users/adamserblowski/Ondoway/", "")
        print(f"{rel:<70} {stats['lines_before']:>8} {stats['lines_after']:>8} {stats['line_reduction_pct']:>6} {stats['nonws_reduction_pct']:>7}{suspicious_flag}")

    if suspicious:
        print(f"\n{len(suspicious)} suspicious files (>40% non-ws removed) — manual review recommended:")
        for p, s in suspicious:
            print(f"  {p}: {s['nonws_reduction_pct']}% non-ws reduction")
    return 0


if __name__ == "__main__":
    sys.exit(main())
