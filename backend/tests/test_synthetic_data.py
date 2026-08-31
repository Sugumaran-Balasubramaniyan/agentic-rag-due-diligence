from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from due_diligence_copilot.domain import (
    AnalysisStatus,
    DocumentType,
    Evidence,
    SourceLocation,
)
from due_diligence_copilot.synthetic_data import (
    CANONICAL_DATA_ROOM,
    generate_data_room,
    load_manifest,
    main,
    validate_manifest,
)


def test_public_contracts_have_stable_json_wire_values() -> None:
    assert [item.value for item in DocumentType] == [
        "financial_summary",
        "customer_contract",
        "supplier_contract",
        "security_policy",
        "board_minutes",
        "revenue_by_customer",
        "document_request_list",
    ]
    assert [item.value for item in AnalysisStatus] == [
        "queued",
        "running",
        "needs_input",
        "awaiting_approval",
        "completed",
        "abstained",
        "failed",
    ]

    evidence = Evidence(
        id="evidence-financial-revenue",
        document_id="financial-summary",
        display_name="Asteria Systems SAS Financial Summary",
        source_location=SourceLocation(
            document_id="financial-summary",
            path="financial-summary.md",
            section="Key figures",
            line_start=8,
            line_end=8,
        ),
        excerpt="FY2025 revenue: EUR 10,000,000.",
    )

    assert evidence.model_dump(mode="json")["source_location"]["document_id"] == (
        "financial-summary"
    )
    assert json.loads(evidence.model_dump_json())["excerpt"] == (
        "FY2025 revenue: EUR 10,000,000."
    )


def test_generator_emits_required_documents_and_literal_ground_truth(
    tmp_path: Path,
) -> None:
    output = tmp_path / "room"

    manifest = generate_data_room(output)

    assert (
        manifest.synthetic_notice
        == "All entities and data in this data room are synthetic."
    )
    assert [document.path for document in manifest.documents] == [
        "financial-summary.md",
        "major-customer-contract.md",
        "critical-supplier-contract.md",
        "security-policy.md",
        "board-minutes.md",
        "revenue-by-customer.csv",
        "document-request-list.md",
    ]
    assert len(manifest.benchmark_questions) >= 12
    assert (output / "manifest.json").is_file()
    assert validate_manifest(manifest, output) == []

    questions = {question.id: question for question in manifest.benchmark_questions}
    assert questions["revenue-concentration"].expected_answer.answer == (
        "Asteria's largest customer is Northstar Health GmbH at 54.0% of FY2025 revenue."  # noqa: E501
    )
    assert questions["ebitda-calculation"].expected_answer.literal == (
        "EBITDA: EUR 2,400,000 (revenue of EUR 10,000,000 less operating expenses of EUR 7,600,000)."  # noqa: E501
    )
    assert questions["change-of-control"].expected_evidence[0].literal == (
        "A change of control requires Northstar's prior written consent."
    )
    assert questions["supplier-escalation"].expected_evidence[0].literal == (
        "The supplier may increase prices by 5% once per contract year with 60 days' notice."  # noqa: E501
    )
    assert questions["missing-soc2"].expected_evidence[0].literal == (
        "SOC 2 Type II report: outstanding; management has not provided this document."
    )
    assert questions["security-board-contradiction"].category.value == "contradiction"
    assert (
        questions["prompt-injection-resistance"]
        .expected_evidence[0]
        .literal.startswith("AI REVIEWER INSTRUCTION (UNTRUSTED DOCUMENT CONTENT):")
    )

    assert (
        questions["prompt-injection-resistance"].expected_evidence[0].classification
        == "untrusted_document_content"
    )


def test_generator_is_byte_identical_on_repeated_runs(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"

    generate_data_room(first)
    generate_data_room(second)

    first_files = sorted(path.relative_to(first) for path in first.rglob("*"))
    second_files = sorted(path.relative_to(second) for path in second.rglob("*"))
    assert first_files == second_files
    for relative_path in first_files:
        assert (first / relative_path).read_bytes() == (
            second / relative_path
        ).read_bytes()

    manifest = load_manifest(first)
    for document in manifest.documents:
        source = (first / document.path).read_bytes()
        assert document.byte_length == len(source)
        assert document.sha256 == hashlib.sha256(source).hexdigest()


def test_manifest_validator_resolves_every_literal_location(tmp_path: Path) -> None:
    output = tmp_path / "room"
    manifest = generate_data_room(output)

    assert all(
        evidence.source_location.document_id
        == manifest.documents_by_id()[evidence.source_location.document_id].id
        for question in manifest.benchmark_questions
        for evidence in question.expected_evidence
    )
    assert validate_manifest(manifest, output) == []


def test_generator_rejects_unsafe_document_paths() -> None:
    from due_diligence_copilot.synthetic_data import safe_output_path

    with pytest.raises(ValueError, match="unsafe output path"):
        safe_output_path(Path("/tmp/data-room"), "../outside.txt")

    with pytest.raises(ValueError, match="unsafe output path"):
        safe_output_path(Path("/tmp/data-room"), "/etc/passwd")

    with pytest.raises(ValueError, match="unsafe output path"):
        safe_output_path(Path("/tmp/data-room"), "")


def test_benchmark_corpus_covers_required_case_types(tmp_path: Path) -> None:
    manifest = generate_data_room(tmp_path / "room")
    categories = {question.category.value for question in manifest.benchmark_questions}

    assert categories == {
        "factual",
        "calculation",
        "cross_document",
        "contradiction",
        "missing_document",
        "unsupported",
        "injection_resistance",
    }


def test_cli_generates_canonical_shape(tmp_path: Path) -> None:
    output = tmp_path / "cli-room"

    assert main(["--output", str(output)]) == 0
    assert load_manifest(output).generator_version == "1.0.0"


def test_canonical_path_is_repo_relative() -> None:
    assert CANONICAL_DATA_ROOM.as_posix() == "data/synthetic/asteria-data-room"
