"""Deterministic, provenance-preserving chunk construction."""

from __future__ import annotations

import hashlib

from .ingestion_contracts import Chunk, NormalizedBlock

MAX_CHUNK_CHARACTERS = 1200


def chunk_blocks(
    blocks: tuple[NormalizedBlock, ...] | list[NormalizedBlock],
    *,
    workspace_id: str,
    max_characters: int = MAX_CHUNK_CHARACTERS,
) -> tuple[Chunk, ...]:
    if not workspace_id:
        raise ValueError("workspace_id must not be empty")
    if max_characters < 1:
        raise ValueError("max_characters must be positive")

    chunks: list[Chunk] = []
    for block in blocks:
        for start in range(0, len(block.text), max_characters):
            text = block.text[start : start + max_characters]
            content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            material = (
                f"{workspace_id}\0{block.document_id}\0{len(chunks)}\0{content_hash}"
            )
            chunk_id = f"chunk-{hashlib.sha256(material.encode()).hexdigest()}"
            chunks.append(
                Chunk(
                    id=chunk_id,
                    workspace_id=workspace_id,
                    document_id=block.document_id,
                    ordinal=len(chunks),
                    text=text,
                    content_hash=content_hash,
                    block_id=block.id,
                    source_location=block.source_location,
                )
            )
    return tuple(chunks)
