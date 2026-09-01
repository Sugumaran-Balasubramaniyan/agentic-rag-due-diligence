"""Extension dispatch for the deterministic document parsers."""

from __future__ import annotations

from .ingestion_contracts import NormalizedBlock, UploadDocument
from .ingestion_errors import PermanentIngestionFailure
from .parsers import CsvDocumentParser, MarkdownDocumentParser


class DeterministicDocumentParser:
    def __init__(self) -> None:
        self._markdown = MarkdownDocumentParser()
        self._csv = CsvDocumentParser()

    def parse(
        self, document: UploadDocument, document_id: str
    ) -> tuple[NormalizedBlock, ...]:
        if document.filename.lower().endswith(".md"):
            return self._markdown.parse(document, document_id)
        if document.filename.lower().endswith(".csv"):
            return self._csv.parse(document, document_id)
        raise PermanentIngestionFailure("unsupported document extension")
