"""Manifest and source-byte validation for the synthetic data room."""

from __future__ import annotations

import csv
import hashlib
import io
from pathlib import Path, PurePosixPath

from .domain import GroundTruthManifest, SourceLocation


def safe_output_path(root: Path, relative_path: str) -> Path:
    """Return a path below root, rejecting absolute and traversal paths."""
    relative = PurePosixPath(relative_path)
    if (
        not relative.parts
        or relative.is_absolute()
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ValueError(f"unsafe output path: {relative_path}")

    root_resolved = root.resolve()
    candidate = (root_resolved / Path(*relative.parts)).resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(f"unsafe output path: {relative_path}") from exc
    return candidate


def _resolve_literal(root: Path, literal: str, location: SourceLocation) -> bool:
    source_path = safe_output_path(root, location.path)
    if location.cell is not None:
        rows = list(csv.reader(io.StringIO(source_path.read_text(encoding="utf-8"))))
        letters = ""
        digits = ""
        for character in location.cell:
            if character.isalpha():
                letters += character.upper()
            else:
                digits += character
        if not letters or not digits:
            return False
        column = 0
        for character in letters:
            column = column * 26 + ord(character) - 64
        row_number = int(digits)
        return (
            0 < row_number <= len(rows)
            and 0 < column <= len(rows[row_number - 1])
            and rows[row_number - 1][column - 1] == literal
        )

    if location.line_start is None:
        return False
    lines = source_path.read_text(encoding="utf-8").splitlines()
    end = location.line_end or location.line_start
    return 0 < location.line_start <= end <= len(lines) and literal in "\n".join(
        lines[location.line_start - 1 : end]
    )


def _markdown_sections(root: Path, location: SourceLocation) -> set[str]:
    if not location.path.endswith(".md"):
        return set()
    lines = (
        safe_output_path(root, location.path).read_text(encoding="utf-8").splitlines()
    )
    return {line[3:] for line in lines if line.startswith("## ") and len(line) > 3}


def _validate_location(
    root: Path,
    manifest: GroundTruthManifest,
    literal: str,
    location: SourceLocation,
    question_id: str,
) -> list[str]:
    documents = manifest.documents_by_id()
    if location.document_id not in documents:
        return [f"{question_id}: unknown document {location.document_id}"]
    if documents[location.document_id].path != location.path:
        return [f"{question_id}: location path does not match document"]
    errors: list[str] = []
    try:
        if location.section is not None and location.path.endswith(".md"):
            if location.section not in _markdown_sections(root, location):
                errors.append(
                    f"{question_id}: section does not exist: {location.section}"
                )
        if not _resolve_literal(root, literal, location):
            errors.append(f"{question_id}: literal does not resolve: {literal}")
    except (OSError, UnicodeError, ValueError) as exc:
        errors.append(f"{question_id}: location cannot be resolved: {exc}")
    return errors


def validate_manifest(
    manifest: GroundTruthManifest,
    output_root: Path | str,
) -> list[str]:
    """Return concrete validation errors for hashes and every cited literal."""
    root = Path(output_root)
    errors: list[str] = []
    for document in manifest.documents:
        try:
            source_path = safe_output_path(root, document.path)
            source = source_path.read_bytes()
        except (OSError, ValueError) as exc:
            errors.append(f"{document.id}: cannot read source: {exc}")
            continue
        if len(source) != document.byte_length:
            errors.append(f"{document.id}: byte length mismatch")
        if hashlib.sha256(source).hexdigest() != document.sha256:
            errors.append(f"{document.id}: SHA-256 mismatch")

    for question in manifest.benchmark_questions:
        references = [
            (
                question.expected_answer.source_location,
                question.expected_answer.literal,
            )
        ]
        references.extend(
            (item.source_location, item.literal) for item in question.expected_evidence
        )
        for location, literal in references:
            errors.extend(
                _validate_location(root, manifest, literal, location, question.id)
            )
    return errors
