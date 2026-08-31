from due_diligence_copilot.ingestion_contracts import IngestionStatus


def test_task_3_contracts_are_exposed() -> None:
    assert IngestionStatus.SUCCEEDED.value == "succeeded"
