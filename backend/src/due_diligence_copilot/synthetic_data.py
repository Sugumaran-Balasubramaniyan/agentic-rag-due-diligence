"""Orchestrate generation of the deterministic Asteria synthetic data room."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

from .domain import DocumentRecord, GroundTruthManifest
from .synthetic_benchmarks import build_benchmark_questions
from .synthetic_templates import SourceDocument, source_documents
from .synthetic_validation import (
    safe_output_path,
    validate_manifest,
)

CANONICAL_DATA_ROOM = Path("data/synthetic/asteria-data-room")
SCHEMA_VERSION = "1.0"
GENERATOR_VERSION = "1.0.0"
GENERATED_AT = "2026-08-31T00:00:00Z"
SYNTHETIC_NOTICE = "All entities and data in this data room are synthetic."


def _document_records(
    sources: Sequence[SourceDocument],
) -> list[DocumentRecord]:
    return [
        DocumentRecord(
            id=source.document_id,
            display_name=source.display_name,
            document_type=source.document_type,
            path=source.path,
            media_type=source.media_type,
            sha256=hashlib.sha256(source.content).hexdigest(),
            byte_length=len(source.content),
        )
        for source in sources
    ]


def build_manifest() -> tuple[GroundTruthManifest, tuple[SourceDocument, ...]]:
    sources = source_documents()
    return (
        GroundTruthManifest(
            schema_version=SCHEMA_VERSION,
            generator_version=GENERATOR_VERSION,
            generated_at=GENERATED_AT,
            synthetic_notice=SYNTHETIC_NOTICE,
            documents=_document_records(sources),
            benchmark_questions=build_benchmark_questions(sources),
        ),
        sources,
    )


def _manifest_bytes(manifest: GroundTruthManifest) -> bytes:
    return (
        json.dumps(
            manifest.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def generate_data_room(
    output_root: Path | str = CANONICAL_DATA_ROOM,
) -> GroundTruthManifest:
    """Write the canonical deterministic source documents and manifest."""
    root = Path(output_root)
    manifest, sources = build_manifest()
    root.mkdir(parents=True, exist_ok=True)
    for source in sources:
        safe_output_path(root, source.path).write_bytes(source.content)
    safe_output_path(root, "manifest.json").write_bytes(_manifest_bytes(manifest))
    return manifest


def load_manifest(output_root: Path | str) -> GroundTruthManifest:
    return GroundTruthManifest.model_validate_json(
        (Path(output_root) / "manifest.json").read_text(encoding="utf-8")
    )


def _default_output() -> Path:
    return Path(__file__).resolve().parents[3] / CANONICAL_DATA_ROOM


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=_default_output())
    args = parser.parse_args(argv)
    manifest = generate_data_room(args.output)
    errors = validate_manifest(manifest, args.output)
    if errors:
        parser.error("generated manifest is invalid: " + "; ".join(errors))
    print(
        f"generated {len(manifest.documents)} documents and "
        f"{len(manifest.benchmark_questions)} benchmark questions at {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
