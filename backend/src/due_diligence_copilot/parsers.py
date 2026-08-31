"""Deterministic Markdown and CSV parsing with source coordinates."""

from __future__ import annotations

import csv
import hashlib
import io
import re
from pathlib import PurePath

from .domain import SourceLocation
from .ingestion_contracts import NormalizedBlock, UploadDocument
from .ingestion_errors import PermanentIngestionFailure


def _block_id(document_id: str, ordinal: int, text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"block-{document_id}-{ordinal}-{digest[:16]}"


class MarkdownDocumentParser:
    def parse(
        self, document: UploadDocument, document_id: str
    ) -> tuple[NormalizedBlock, ...]:
        try:
            lines = document.content.decode("utf-8").splitlines()
        except UnicodeDecodeError as exc:
            raise PermanentIngestionFailure("document is not valid UTF-8") from exc

        blocks: list[NormalizedBlock] = []
        section: str | None = None
        for line_number, line in enumerate(lines, start=1):
            heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
            if heading is not None and len(heading.group(1)) == 1:
                section = None
            elif heading is not None and len(heading.group(1)) == 2:
                section = heading.group(2)
            if not line.strip():
                continue
            location = {
                "document_id": document_id,
                "path": document.filename,
                "section": section,
                "page": 1,
                "line_start": line_number,
                "line_end": line_number,
            }
            blocks.append(
                NormalizedBlock(
                    id=_block_id(document_id, len(blocks), line),
                    document_id=document_id,
                    ordinal=len(blocks),
                    text=line,
                    block_type="markdown_line",
                    source_location=SourceLocation.model_validate(location),
                )
            )
        if not blocks:
            raise PermanentIngestionFailure("document contains no Markdown blocks")
        return tuple(blocks)


def _column_name(column_number: int) -> str:
    name = ""
    remaining = column_number
    while remaining:
        remaining, remainder = divmod(remaining - 1, 26)
        name = chr(65 + remainder) + name
    return name


class CsvDocumentParser:
    def parse(
        self, document: UploadDocument, document_id: str
    ) -> tuple[NormalizedBlock, ...]:
        try:
            decoded = document.content.decode("utf-8")
            reader = csv.reader(io.StringIO(decoded, newline=""), strict=True)
            rows = list(reader)
        except (UnicodeDecodeError, csv.Error) as exc:
            raise PermanentIngestionFailure("document is not a valid CSV") from exc

        if not rows or not rows[0] or not any(value.strip() for value in rows[0]):
            raise PermanentIngestionFailure("CSV has no header row")
        width = len(rows[0])
        if any(len(row) != width for row in rows):
            raise PermanentIngestionFailure("CSV rows have inconsistent column counts")

        table = PurePath(document.filename).stem
        blocks: list[NormalizedBlock] = []
        spans: list[tuple[int, int]] = []
        physical_line = 0
        span_reader = csv.reader(io.StringIO(decoded, newline=""), strict=True)
        for _row in span_reader:
            spans.append((physical_line + 1, span_reader.line_num))
            physical_line = span_reader.line_num

        for row_number, row in enumerate(rows, start=1):
            line_start, line_end = spans[row_number - 1]
            text_values = (
                row
                if row_number == 1
                else [
                    f"{rows[0][column_number - 1]}: {value}"
                    for column_number, value in enumerate(row, start=1)
                ]
            )
            for column_number, value in enumerate(text_values, start=1):
                if not value.strip():
                    continue
                location = {
                    "document_id": document_id,
                    "path": document.filename,
                    "page": 1,
                    "table": table,
                    "line_start": line_start,
                    "line_end": line_end,
                    "cell": f"{_column_name(column_number)}{row_number}",
                }
                blocks.append(
                    NormalizedBlock(
                        id=_block_id(document_id, len(blocks), value),
                        document_id=document_id,
                        ordinal=len(blocks),
                        text=value,
                        block_type="csv_cell",
                        source_location=SourceLocation.model_validate(location),
                    )
                )
        if not blocks:
            raise PermanentIngestionFailure("CSV contains no cells")
        return tuple(blocks)
