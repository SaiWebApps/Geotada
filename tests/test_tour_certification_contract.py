"""Pins the finish line and the approved investigation reference set."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from itertools import pairwise
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SPEC = REPO / "specs" / "2026-07-21-tour-certification"


def _json(name: str) -> dict:
    return json.loads((SPEC / name).read_text(encoding="utf-8"))


def _git_bytes(commit: str, path: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=REPO,
        check=False,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    return result.stdout


def _git_blob_oid(content: bytes) -> str:
    result = subprocess.run(
        ["git", "hash-object", "--stdin"],
        cwd=REPO,
        input=content,
        check=True,
        capture_output=True,
    )
    return result.stdout.decode().strip()


def _anchor_slice(content: bytes, *, start_marker: str, end_marker: str | None) -> bytes:
    newline = b"\n"
    start_token = start_marker.encode() + newline
    assert content.count(start_token) == 1
    start = content.index(start_token) + len(start_token)
    if end_marker is None:
        return content[start:]
    end_token = newline + end_marker.encode() + newline
    end = content.index(end_token, start)
    return content[start:end]


def test_contract_has_four_independent_hard_gates_and_a_finish_rule() -> None:
    contract = _json("contract.json")

    assert contract["schema_version"] == 2
    assert contract["contract_id"] == "tour-certification-v2"
    assert contract["status"] == "FROZEN_BEFORE_CANDIDATE_GENERATION"
    assert set(contract["gates"]) == {"FACT", "GEO", "TIME", "ENJOY"}
    assert all(gate["hard"] for gate in contract["gates"].values())
    assert "passes FACT, GEO, TIME, and ENJOY" in contract["definitions"]["certified_tour"]


def test_time_and_enjoyment_finish_line_cannot_regress_to_old_false_gates() -> None:
    contract = _json("contract.json")
    time_gate = contract["gates"]["TIME"]
    enjoy_gate = contract["gates"]["ENJOY"]


    assert time_gate["maximum_requested_fraction"] == 1.1
    assert time_gate["requires_final_baked_audio"] is True
    assert time_gate["word_count_can_certify"] is False
    assert enjoy_gate["legacy_ten_point_checklist_is_release_gate"] is False
    assert enjoy_gate["requires_two_independent_reviews"] is True
    assert enjoy_gate["provider_supplies_total_or_release_decision"] is False
    assert set(enjoy_gate["axes"]) == {
        "site_presence",
        "narrative_motion",
        "human_specificity",
        "spoken_voice",
        "editorial_control",
    }
    assert enjoy_gate["axis_score_range"] == [0, 2]
    assert enjoy_gate["two_reviewer_aggregate_threshold"] == 7.0
    assert enjoy_gate["unanimous_zero_axis_rejects"] is True
    assert enjoy_gate["same_axis_below_weakest_positive_gold_consensus_rejects"] is True


def test_fact_materiality_has_one_precedence_rule_for_gloss_vs_changed_fact() -> None:
    fact_gate = _json("contract.json")["gates"]["FACT"]
    claim_types = set(fact_gate["material_claim_types"])
    controls = set(fact_gate["allowed_controls"])

    assert "causal_relation_changing_who_what_or_why" not in claim_types
    assert "superlative" not in claim_types
    assert "checkable_historical_causation_or_agency_changing_who_did_or_caused_what" in claim_types
    assert "objective_or_source_attributed_superlative_ranking" in claim_types
    assert (
        "licensed_editorial_prominence_magnetism_motive_or_personification_gloss_that_changes_no_checkable_fact"
        in controls
    )
    assert "exact frozen fact-policy calibration cases" in fact_gate["precedence_rule"]


def test_contract_forbids_best_of_n_and_unbounded_quality_retries() -> None:
    budget = _json("contract.json")["provider_budget"]

    assert budget["physical_attempts_per_authorized_unit"] == 1
    assert budget["automatic_quality_retries"] == 0
    assert budget["total_provider_calls_per_candidate_max"] <= 12
    assert budget["owner_imposed_static_dollar_cap"] is None
    assert "trusted code computes" in budget["cost_authorization_rule"]


def test_reference_manifest_has_replayable_per_document_provenance() -> None:
    manifest = _json("investigation-reference-manifest.json")

    assert manifest["schema_version"] == 2
    assert "source_commit" not in manifest
    assert "source_branch" not in manifest
    assert manifest["apple_proxy_material_allowed"] is False
    assert len(manifest["documents"]) == 28

    ids = [entry["id"] for entry in manifest["documents"]]
    paths = [entry["path"] for entry in manifest["documents"]]
    assert len(ids) == len(set(ids))
    assert len(paths) == len(set(paths))

    for entry in manifest["documents"]:
        assert entry["source_ref"] in {
            "investigation",
            "main",
            "origin/scope6-acceptance-finding",
        }
        assert re.fullmatch(r"[0-9a-f]{40}", entry["source_commit"])
        assert re.fullmatch(r"[0-9a-f]{40}", entry["source_blob_oid"])
        path = REPO / entry["path"]
        content = path.read_bytes()
        assert hashlib.sha256(content).hexdigest() == entry["sha256"], entry["path"]
        source_content = _git_bytes(entry["source_commit"], entry["path"])
        assert hashlib.sha256(source_content).hexdigest() == entry["sha256"], entry["path"]
        assert _git_blob_oid(source_content) == entry["source_blob_oid"]
        assert source_content == content, entry["path"]
        lowered = content.lower()
        assert b"pypi.apple.com" not in lowered, entry["path"]
        assert b"apple proxy" not in lowered, entry["path"]
        assert b"apple-proxy" not in lowered, entry["path"]


def test_every_investigation_added_document_is_included_or_explicitly_excluded() -> None:
    manifest = _json("investigation-reference-manifest.json")
    investigation_paths = {
        entry["path"]
        for entry in manifest["documents"]
        if entry["source_ref"] == "investigation"
    }
    source_range = manifest["investigation_range"]
    result = subprocess.run(
        [
            "git",
            "diff",
            "--name-status",
            source_range["base_commit"],
            source_range["head_commit"],
            "--",
            "*.md",
        ],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    )
    added_markdown = {
        line.split("\t", maxsplit=1)[1]
        for line in result.stdout.splitlines()
        if line.startswith("A\t")
    }
    assert len(added_markdown) == 19
    assert investigation_paths == added_markdown

    excluded = manifest["excluded_investigation_artifacts"]
    assert {entry["path"] for entry in excluded} == {
        "specs/2026-07-13-compose-correct-dont-reject/state.json",
        "tests/goldens/compose_per_chapter.json",
        "tests/goldens/compose_whole_tour.json",
    }
    for entry in excluded:
        assert re.fullmatch(r"[0-9a-f]{40}", entry["source_commit"])
        assert re.fullmatch(r"[0-9a-f]{40}", entry["source_blob_oid"])
        source_content = _git_bytes(entry["source_commit"], entry["path"])
        assert hashlib.sha256(source_content).hexdigest() == entry["sha256"]
        assert _git_blob_oid(source_content) == entry["source_blob_oid"]
        assert entry["reason"]


def test_latest_acceptance_failure_supersedes_historical_plans_without_a_cycle() -> None:
    documents = _json("investigation-reference-manifest.json")["documents"]
    by_id = {entry["id"]: entry for entry in documents}

    chain = [
        "correct_dont_reject_red_team",
        "correct_dont_reject_red_team_reopen",
        "correct_dont_reject_plan",
        "correct_dont_reject_plan_05b",
        "scope6_acceptance_run",
    ]
    for current, successor in pairwise(chain):
        assert by_id[current]["superseded_by"] == successor
    assert "superseded_by" not in by_id["scope6_acceptance_run"]
    assert by_id["scope6_acceptance_run"]["classification"] == "algorithm_acceptance_failure"

    for start in by_id:
        seen: set[str] = set()
        current = start
        while successor := by_id[current].get("superseded_by"):
            assert successor in by_id
            assert successor not in seen
            seen.add(successor)
            current = successor


def test_calibration_anchors_are_frozen_locatable_and_axis_independent() -> None:
    references = _json("investigation-reference-manifest.json")
    calibration = _json("calibration-manifest.json")
    by_id = {entry["id"]: entry for entry in references["documents"]}

    assert calibration["status"] == "FROZEN_BEFORE_CANDIDATE_GENERATION"
    assert calibration["schema_version"] == 2
    assert calibration["decision_method"] == "blind_five_axis_score_and_gold_consensus"
    assert calibration["rules"]["legacy_ten_point_score_is_release_gate"] is False
    assert calibration["rules"]["five_axis_score_is_release_gate"] is True
    assert calibration["rules"]["five_axis_aggregate_threshold"] == 7.0
    assert calibration["rules"]["provider_supplies_total_or_release_decision"] is False
    assert calibration["rules"]["axis_labels_are_independent"] is True
    fact_policy = calibration["fact_policy_calibration"]
    assert fact_policy["reference_document_id"] == "fact_gate_calibration_02b"
    fact_cases = {
        case["candidate_text"]: case["expected_fact"]
        for case in fact_policy["cases"][:5]
    }
    assert fact_cases == {
        "the street bent itself to make them feel at home": "PASS",
        "Those same ladies wanted more than newspapers": "PASS",
        "The Meurice drew the writers too": "PASS",
        "the most famous story attached to this place": "PASS",
        "the ladies of the Napoleonic nobility drew an English clientele": "PASS",
    }

    anchors = {entry["id"]: entry for entry in calibration["anchors"]}
    assert set(anchors) == {
        "le_meurice_01f",
        "le_meurice_01e",
        "le_meurice_01g",
    }
    for anchor in anchors.values():
        document = by_id[anchor["reference_document_id"]]
        content = (REPO / document["path"]).read_bytes()
        slice_spec = anchor["slice"]
        extracted = _anchor_slice(
            content,
            start_marker=slice_spec["start_marker"],
            end_marker=slice_spec["end_marker"],
        )
        assert len(extracted) == slice_spec["size_bytes"]
        assert hashlib.sha256(extracted).hexdigest() == slice_spec["sha256"]
        assert set(anchor["expected"]) == {"FACT", "GEO", "TIME", "ENJOY"}

    assert anchors["le_meurice_01f"]["expected"] == {
        "FACT": "PASS",
        "GEO": "NOT_RUN",
        "TIME": "NOT_RUN",
        "ENJOY": "PASS",
    }
    assert anchors["le_meurice_01g"]["expected"]["ENJOY"] == "PASS"
    assert anchors["le_meurice_01g"]["expected"]["FACT"] == "FAIL"
    assert (
        anchors["le_meurice_01g"]["label_origin"]
        == "human_approved_positive_preserved_under_five_axis_v2"
    )
    assert "le_meurice_01c_version_a" not in anchors
    assert "le_meurice_01c_version_b" not in anchors

    summary = calibration["summary_only_positive_labels"]
    assert {entry["id"] for entry in summary} == {"paris_a", "paris_b", "nyc_a", "nyc_b"}
    assert all(entry["expected_enjoyment"] == "PASS" for entry in summary)
    assert calibration["summary_only_policy"]["eligible_for_model_calibration"] is False


def test_evidence_bundle_binds_contract_references_and_calibration() -> None:
    required = set(_json("contract.json")["required_evidence_bundle"])

    assert {
        "artifact_sha256",
        "contract_sha256",
        "reference_manifest_sha256",
        "calibration_manifest_sha256",
    } <= required


def test_moving_the_finish_line_requires_a_new_version_and_full_recalibration() -> None:
    protocol = _json("contract.json")["change_protocol"]

    assert protocol == {
        "change_during_candidate_evaluation": False,
        "requires_new_contract_version": True,
        "requires_owner_approval": True,
        "requires_full_anchor_recalibration": True,
        "requires_full_candidate_rerun": True,
    }
