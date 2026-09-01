from __future__ import annotations

from decimal import Decimal

from due_diligence_copilot.domain import Evidence, SourceLocation


def test_financial_percentage_uses_decimal_and_explicit_percent_unit() -> None:
    from due_diligence_copilot.agentic_tools import (
        ApprovedToolId,
        DeterministicToolRegistry,
        FinancialMetricArguments,
        FinancialOperation,
        FinancialUnit,
        ToolCall,
    )

    revenue_evidence = Evidence(
        id="evidence-revenue",
        document_id="revenue-by-customer",
        display_name="Asteria FY2025 Revenue by Customer",
        source_location=SourceLocation(
            document_id="revenue-by-customer",
            path="revenue-by-customer.csv",
            line_start=2,
            line_end=2,
            cell="A2",
        ),
        excerpt="Northstar Health GmbH,5400000,54.0%",
        chunk_id="chunk-revenue",
    )

    result = DeterministicToolRegistry().execute(
        ToolCall(
            tool_id=ApprovedToolId.CALCULATE_FINANCIAL_METRIC,
            arguments=FinancialMetricArguments(
                operation=FinancialOperation.PERCENTAGE,
                left_label="Northstar Health GmbH",
                right_label="Total",
                precision=1,
                evidence_ids=("evidence-revenue",),
            ),
            evidence=(revenue_evidence,),
        )
    )

    assert result.value == Decimal("54.0")
    assert result.unit == FinancialUnit.PERCENT
    assert result.evidence[0].id == "evidence-revenue"


def test_financial_subtraction_preserves_currency_and_rounds_half_up() -> None:
    from due_diligence_copilot.agentic_tools import (
        ApprovedToolId,
        DeterministicToolRegistry,
        FinancialMetricArguments,
        FinancialOperation,
        FinancialUnit,
        ToolCall,
    )

    financial_evidence = Evidence(
        id="evidence-financial",
        document_id="financial-summary",
        display_name="Asteria Systems SAS Financial Summary",
        source_location=SourceLocation(
            document_id="financial-summary",
            path="financial-summary.md",
            line_start=8,
            line_end=9,
        ),
        excerpt=("FY2025 revenue: EUR 10,000,000.\nOperating expenses: EUR 7,600,000."),
        chunk_id="chunk-financial",
    )

    result = DeterministicToolRegistry().execute(
        ToolCall(
            tool_id=ApprovedToolId.CALCULATE_FINANCIAL_METRIC,
            arguments=FinancialMetricArguments(
                operation=FinancialOperation.SUBTRACT,
                left_label="FY2025 revenue",
                right_label="Operating expenses",
                precision=0,
                evidence_ids=("evidence-financial",),
            ),
            evidence=(financial_evidence,),
        )
    )

    assert result.value == Decimal("2400000")
    assert result.unit == FinancialUnit.EUR


def test_financial_reported_value_returns_exact_evidence_line() -> None:
    from due_diligence_copilot.agentic_tools import (
        ApprovedToolId,
        DeterministicToolRegistry,
        FinancialMetricArguments,
        FinancialOperation,
        FinancialUnit,
        ToolCall,
    )

    evidence = Evidence(
        id="evidence-ebitda",
        document_id="financial-summary",
        display_name="Asteria Systems SAS Financial Summary",
        source_location=SourceLocation(
            document_id="financial-summary",
            path="financial-summary.md",
            section="Key figures",
            line_start=10,
            line_end=10,
        ),
        excerpt="EBITDA: EUR 2,400,000 (revenue less operating expenses).",
        chunk_id="chunk-ebitda",
    )

    result = DeterministicToolRegistry().execute(
        ToolCall(
            tool_id=ApprovedToolId.CALCULATE_FINANCIAL_METRIC,
            arguments=FinancialMetricArguments(
                operation=FinancialOperation.REPORTED_VALUE,
                left_label="EBITDA",
                precision=0,
                evidence_ids=("evidence-ebitda",),
            ),
            evidence=(evidence,),
        )
    )

    assert result.value == Decimal("2400000")
    assert result.unit == FinancialUnit.EUR
    assert result.claim == evidence.excerpt


def test_financial_percentage_abstains_on_division_by_zero() -> None:
    from due_diligence_copilot.agentic_tools import (
        ApprovedToolId,
        DeterministicToolRegistry,
        FinancialMetricArguments,
        FinancialOperation,
        FinancialUnit,
        ToolAbstentionReason,
        ToolCall,
        ToolResultStatus,
    )

    evidence = Evidence(
        id="evidence-zero",
        document_id="financial-summary",
        display_name="Financial Summary",
        source_location=SourceLocation(
            document_id="financial-summary",
            path="financial-summary.md",
            line_start=1,
        ),
        excerpt="Revenue: 4000\nTotal: 0",
        chunk_id="chunk-zero",
    )

    result = DeterministicToolRegistry().execute(
        ToolCall(
            tool_id=ApprovedToolId.CALCULATE_FINANCIAL_METRIC,
            arguments=FinancialMetricArguments(
                operation=FinancialOperation.PERCENTAGE,
                left_label="Revenue",
                right_label="Total",
                precision=1,
                evidence_ids=("evidence-zero",),
            ),
            evidence=(evidence,),
        )
    )

    assert result.status == ToolResultStatus.ABSTAINED
    assert result.value is None
    assert result.unit == FinancialUnit.PERCENT
    assert result.reason == ToolAbstentionReason.DIVISION_BY_ZERO


def test_financial_subtraction_abstains_on_currency_unit_mismatch() -> None:
    from due_diligence_copilot.agentic_tools import (
        ApprovedToolId,
        DeterministicToolRegistry,
        FinancialMetricArguments,
        FinancialOperation,
        FinancialUnit,
        ToolAbstentionReason,
        ToolCall,
        ToolResultStatus,
    )

    evidence = Evidence(
        id="evidence-mismatch",
        document_id="financial-summary",
        display_name="Financial Summary",
        source_location=SourceLocation(
            document_id="financial-summary",
            path="financial-summary.md",
            line_start=1,
        ),
        excerpt="Revenue: EUR 4000\nExpenses: USD 1000",
        chunk_id="chunk-mismatch",
    )

    result = DeterministicToolRegistry().execute(
        ToolCall(
            tool_id=ApprovedToolId.CALCULATE_FINANCIAL_METRIC,
            arguments=FinancialMetricArguments(
                operation=FinancialOperation.SUBTRACT,
                left_label="Revenue",
                right_label="Expenses",
                precision=0,
                evidence_ids=("evidence-mismatch",),
            ),
            evidence=(evidence,),
        )
    )

    assert result.status == ToolResultStatus.ABSTAINED
    assert result.value is None
    assert result.unit == FinancialUnit.UNITLESS
    assert result.reason == ToolAbstentionReason.UNIT_MISMATCH


def test_contract_tool_returns_clause_claim_linked_to_supplied_evidence() -> None:
    from due_diligence_copilot.agentic_tools import (
        ApprovedToolId,
        ContractClauseArguments,
        DeterministicToolRegistry,
        ToolCall,
    )

    evidence = Evidence(
        id="evidence-change-control",
        document_id="major-customer-contract",
        display_name="Northstar Health GmbH Customer Contract",
        source_location=SourceLocation(
            document_id="major-customer-contract",
            path="major-customer-contract.md",
            section="Change of control",
            line_start=9,
            line_end=9,
        ),
        excerpt="A change of control requires Northstar's prior written consent.",
        chunk_id="chunk-change-control",
    )

    result = DeterministicToolRegistry().execute(
        ToolCall(
            tool_id=ApprovedToolId.INSPECT_CONTRACT_CLAUSE,
            arguments=ContractClauseArguments(
                clause="change_of_control",
                evidence_ids=("evidence-change-control",),
            ),
            evidence=(evidence,),
        )
    )

    assert result.claim == evidence.excerpt
    assert [item.id for item in result.evidence] == ["evidence-change-control"]


def test_contradiction_tool_returns_evidence_linked_conflict() -> None:
    from due_diligence_copilot.agentic_tools import (
        ApprovedToolId,
        ContradictionArguments,
        DeterministicToolRegistry,
        ToolCall,
    )

    policy = Evidence(
        id="evidence-policy",
        document_id="security-policy",
        display_name="Asteria Information Security Policy",
        source_location=SourceLocation(
            document_id="security-policy",
            path="security-policy.md",
            section="Access control",
            line_start=9,
            line_end=9,
        ),
        excerpt=(
            "Multi-factor authentication (MFA) is mandatory for all production access."
        ),
        chunk_id="chunk-policy",
    )
    board = Evidence(
        id="evidence-board",
        document_id="board-minutes",
        display_name="Asteria Board Minutes",
        source_location=SourceLocation(
            document_id="board-minutes",
            path="board-minutes.md",
            section="Security remediation discussion",
            line_start=10,
            line_end=11,
        ),
        excerpt=(
            "The board noted that legacy support accounts may remain password-only.\n"
            "This exception conflicts with the security policy requirement that MFA "
            "is mandatory for all production access."
        ),
        chunk_id="chunk-board",
    )

    result = DeterministicToolRegistry().execute(
        ToolCall(
            tool_id=ApprovedToolId.DETECT_CONTRADICTIONS,
            arguments=ContradictionArguments(
                subject="MFA",
                evidence_ids=("evidence-policy", "evidence-board"),
            ),
            evidence=(policy, board),
        )
    )

    assert result.claim == (
        "This exception conflicts with the security policy requirement that MFA is "
        "mandatory for all production access."
    )
    assert {item.id for item in result.evidence} == {
        "evidence-policy",
        "evidence-board",
    }


def test_missing_document_tool_returns_outstanding_evidence() -> None:
    from due_diligence_copilot.agentic_tools import (
        ApprovedToolId,
        DeterministicToolRegistry,
        MissingDocumentArguments,
        ToolCall,
    )

    evidence = Evidence(
        id="evidence-soc2",
        document_id="document-request-list",
        display_name="Asteria Document Request List",
        source_location=SourceLocation(
            document_id="document-request-list",
            path="document-request-list.md",
            section="Requests",
            line_start=14,
            line_end=14,
            cell="C4",
        ),
        excerpt=(
            "SOC 2 Type II report: outstanding; management has not provided this "
            "document."
        ),
        chunk_id="chunk-soc2",
    )

    result = DeterministicToolRegistry().execute(
        ToolCall(
            tool_id=ApprovedToolId.ANALYZE_MISSING_DOCUMENTS,
            arguments=MissingDocumentArguments(
                document_name="SOC 2 Type II report",
                evidence_ids=("evidence-soc2",),
            ),
            evidence=(evidence,),
        )
    )

    assert result.claim == evidence.excerpt
    assert result.document_name == "SOC 2 Type II report"
    assert [item.id for item in result.evidence] == ["evidence-soc2"]
