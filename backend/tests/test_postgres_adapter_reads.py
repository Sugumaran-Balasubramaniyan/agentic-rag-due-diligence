from __future__ import annotations

from due_diligence_copilot.adapters import PostgresDocumentRepository
from due_diligence_copilot.domain import DocumentType


class RowResult:
    def __init__(self, row: tuple[object, ...] | None) -> None:
        self.row = row

    def fetchone(self) -> tuple[object, ...] | None:
        return self.row


class ReadConnection:
    def execute(self, statement: str, parameters: tuple[object, ...]) -> RowResult:
        del statement, parameters
        return RowResult(
            (
                "doc-1",
                "Notes",
                "financial_summary",
                "notes.md",
                "text/markdown",
                "a" * 64,
                4,
            )
        )


def test_postgres_adapter_decodes_a_scoped_document_row() -> None:
    document = PostgresDocumentRepository(ReadConnection()).get("workspace-a", "doc-1")

    assert document is not None
    assert document.id == "doc-1"
    assert document.document_type == DocumentType.FINANCIAL_SUMMARY
    assert document.sha256 == "a" * 64
