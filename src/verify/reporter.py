"""Format and print verification results to stdout."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.verify.traversals import TraversalResult


def _status(passed: bool) -> str:
    return "✓ PASS" if passed else "✗ FAIL"


def print_section(title: str) -> None:
    """Print a section header."""
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def print_counts(node_counts: dict[str, int], rel_counts: dict[str, int]) -> None:
    """Print node and relationship count tables."""
    print_section("NODE COUNTS")
    for label, count in sorted(node_counts.items()):
        print(f"  {label:<20} {count:>5}")

    print_section("RELATIONSHIP COUNTS")
    for rel_type, count in sorted(rel_counts.items()):
        print(f"  {rel_type:<20} {count:>5}")


def print_traversal(result: TraversalResult) -> None:
    """Print a single traversal result with sample rows."""
    status = _status(result.passed)
    print(f"\n  [{status}] {result.name} — {result.row_count} rows (need ≥{result.min_expected})")
    for row in result.sample_rows[:3]:
        formatted = ", ".join(f"{k}={v}" for k, v in row.items())
        print(f"    → {formatted}")


def print_traversals(results: list[TraversalResult]) -> None:
    """Print all traversal results."""
    print_section("TRAVERSAL VERIFICATION")
    for result in results:
        print_traversal(result)


def print_summary(
    totals: dict[str, int],
    traversal_results: list[TraversalResult],
) -> bool:
    """Print final summary. Returns True if all checks passed."""
    all_passed = all(r.passed for r in traversal_results)

    print_section("SUMMARY")
    print(f"  Total nodes:         {totals['total_nodes']}")
    print(f"  Total relationships: {totals['total_relationships']}")
    print(f"  Traversals:          {_status(all_passed)}")
    print()

    if all_passed:
        print("  🎉 All checks passed — schema is ready.")
    else:
        failed = [r.name for r in traversal_results if not r.passed]
        print(f"  ⚠  Failed traversals: {', '.join(failed)}")

    print()
    return all_passed
