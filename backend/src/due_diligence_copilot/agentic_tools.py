"""Closed, deterministic tools for bounded evidence-first investigations."""

from __future__ import annotations

import re
from collections.abc import Callable
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Annotated, Protocol

from pydantic import Field, model_validator

from .domain import ContractModel, Evidence


class ApprovedToolId(StrEnum):
    CALCULATE_FINANCIAL_METRIC = "calculate_financial_metric"
    INSPECT_CONTRACT_CLAUSE = "inspect_contract_clause"
    DETECT_CONTRADICTIONS = "detect_contradictions"
    ANALYZE_MISSING_DOCUMENTS = "analyze_missing_documents"


APPROVED_TOOL_IDS = tuple(ApprovedToolId)

EvidenceId = Annotated[str, Field(min_length=1, max_length=128)]


class FinancialOperation(StrEnum):
    PERCENTAGE = "percentage"
    SUBTRACT = "subtract"
    REPORTED_VALUE = "reported_value"


class ContractClause(StrEnum):
    CHANGE_OF_CONTROL = "change_of_control"
    PRICE_ESCALATION = "price_escalation"
    TERM = "term"


class FinancialUnit(StrEnum):
    EUR = "EUR"
    USD = "USD"
    PERCENT = "%"
    UNITLESS = "unitless"


class ToolResultStatus(StrEnum):
    SUCCEEDED = "succeeded"
    ABSTAINED = "abstained"


class ToolAbstentionReason(StrEnum):
    MISSING_EVIDENCE = "missing_evidence"
    DIVISION_BY_ZERO = "division_by_zero"
    UNIT_MISMATCH = "unit_mismatch"
    UNSUPPORTED_INPUT = "unsupported_input"


class FinancialMetricArguments(ContractModel):
    operation: FinancialOperation
    left_label: str = Field(min_length=1, max_length=256)
    right_label: str | None = Field(default=None, max_length=256)
    precision: int = Field(default=1, ge=0, le=6)
    evidence_ids: tuple[EvidenceId, ...] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def validate_operands(self) -> FinancialMetricArguments:
        if (
            self.operation
            in {
                FinancialOperation.PERCENTAGE,
                FinancialOperation.SUBTRACT,
            }
            and not self.right_label
        ):
            raise ValueError("binary financial operations require right_label")
        return self


class ContractClauseArguments(ContractModel):
    clause: ContractClause
    evidence_ids: tuple[EvidenceId, ...] = Field(min_length=1, max_length=10)


class ContradictionArguments(ContractModel):
    subject: str = Field(min_length=1, max_length=256)
    evidence_ids: tuple[EvidenceId, ...] = Field(min_length=1, max_length=10)


class MissingDocumentArguments(ContractModel):
    document_name: str = Field(min_length=1, max_length=256)
    evidence_ids: tuple[EvidenceId, ...] = Field(min_length=1, max_length=10)


ToolArguments = (
    FinancialMetricArguments
    | ContractClauseArguments
    | ContradictionArguments
    | MissingDocumentArguments
)


class ToolCall(ContractModel):
    tool_id: ApprovedToolId
    arguments: ToolArguments
    evidence: tuple[Evidence, ...] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def validate_evidence_references(self) -> ToolCall:
        evidence_ids = set(self.arguments.evidence_ids)
        supplied_ids = {evidence.id for evidence in self.evidence}
        if (
            len(evidence_ids) != len(self.arguments.evidence_ids)
            or evidence_ids != supplied_ids
            or len(supplied_ids) != len(self.evidence)
        ):
            raise ValueError("tool evidence must exactly match argument evidence_ids")
        expected_arguments = {
            ApprovedToolId.CALCULATE_FINANCIAL_METRIC: FinancialMetricArguments,
            ApprovedToolId.INSPECT_CONTRACT_CLAUSE: ContractClauseArguments,
            ApprovedToolId.DETECT_CONTRADICTIONS: ContradictionArguments,
            ApprovedToolId.ANALYZE_MISSING_DOCUMENTS: MissingDocumentArguments,
        }
        if type(self.arguments) is not expected_arguments[self.tool_id]:
            raise ValueError("tool arguments do not match the approved tool ID")
        return self


class FinancialMetricResult(ContractModel):
    id: str = Field(default="unassigned-tool-result", min_length=1, max_length=128)
    tool_id: ApprovedToolId = ApprovedToolId.CALCULATE_FINANCIAL_METRIC
    status: ToolResultStatus
    value: Decimal | None = None
    unit: FinancialUnit
    claim: str | None = Field(default=None, max_length=2000)
    evidence: tuple[Evidence, ...] = Field(default=(), max_length=10)
    primary_evidence: tuple[Evidence, ...] = Field(default=(), max_length=10)
    reason: ToolAbstentionReason | None = None


class ContractClauseResult(ContractModel):
    id: str = Field(default="unassigned-tool-result", min_length=1, max_length=128)
    tool_id: ApprovedToolId = ApprovedToolId.INSPECT_CONTRACT_CLAUSE
    status: ToolResultStatus
    clause: ContractClause
    claim: str | None = Field(default=None, max_length=2000)
    evidence: tuple[Evidence, ...] = Field(default=(), max_length=10)
    primary_evidence: tuple[Evidence, ...] = Field(default=(), max_length=10)
    reason: ToolAbstentionReason | None = None


class ContradictionResult(ContractModel):
    id: str = Field(default="unassigned-tool-result", min_length=1, max_length=128)
    tool_id: ApprovedToolId = ApprovedToolId.DETECT_CONTRADICTIONS
    status: ToolResultStatus
    subject: str = Field(min_length=1, max_length=256)
    claim: str | None = Field(default=None, max_length=2000)
    evidence: tuple[Evidence, ...] = Field(default=(), max_length=10)
    primary_evidence: tuple[Evidence, ...] = Field(default=(), max_length=10)
    reason: ToolAbstentionReason | None = None


class MissingDocumentResult(ContractModel):
    id: str = Field(default="unassigned-tool-result", min_length=1, max_length=128)
    tool_id: ApprovedToolId = ApprovedToolId.ANALYZE_MISSING_DOCUMENTS
    status: ToolResultStatus
    document_name: str = Field(min_length=1, max_length=256)
    claim: str | None = Field(default=None, max_length=2000)
    evidence: tuple[Evidence, ...] = Field(default=(), max_length=10)
    primary_evidence: tuple[Evidence, ...] = Field(default=(), max_length=10)
    reason: ToolAbstentionReason | None = None


ToolResult = (
    FinancialMetricResult
    | ContractClauseResult
    | ContradictionResult
    | MissingDocumentResult
)


class ToolRegistry(Protocol):
    def execute(self, call: ToolCall) -> ToolResult: ...


_LABEL_NUMBER = re.compile(
    r"(?<![A-Za-z0-9])(?:(?P<currency>EUR|USD)\s*)?"
    r"(?P<number>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)(?P<percent>%)?",
    re.IGNORECASE,
)


def _quantize(value: Decimal, precision: int) -> Decimal:
    quantum = Decimal("1").scaleb(-precision)
    return value.quantize(quantum, rounding=ROUND_HALF_UP)


def _label_values(
    evidence: tuple[Evidence, ...], label: str
) -> tuple[tuple[Decimal, FinancialUnit, str], ...]:
    wanted = label.casefold()
    lines = _evidence_lines(evidence)
    if wanted == "largest customer":
        candidates: list[tuple[Decimal, Decimal, str]] = []
        for line in lines:
            fields = [field.strip() for field in line.split(",")]
            if not fields or fields[0].casefold() == "total":
                continue
            matches = list(_LABEL_NUMBER.finditer(line))
            amounts = [
                Decimal(match.group("number").replace(",", ""))
                for match in matches
                if match.group("percent") is None
            ]
            percentages = [
                Decimal(match.group("number").replace(",", ""))
                for match in matches
                if match.group("percent") is not None
            ]
            if amounts and percentages:
                candidates.append((amounts[0], percentages[0], line.strip()))
        if candidates:
            _, percentage, line = max(candidates, key=lambda item: item[0])
            return ((percentage, FinancialUnit.PERCENT, line),)
    values: list[tuple[Decimal, FinancialUnit, str]] = []
    for line in lines:
        normalised_line = line.casefold()
        label_start = normalised_line.find(wanted)
        if label_start == -1:
            continue
        value_text = line[label_start + len(label) :]
        for match in _LABEL_NUMBER.finditer(value_text):
            number = Decimal(match.group("number").replace(",", ""))
            unit = (
                FinancialUnit.PERCENT
                if match.group("percent")
                else FinancialUnit.EUR
                if "(eur)" in value_text[: match.start()].casefold()
                else FinancialUnit.USD
                if "(usd)" in value_text[: match.start()].casefold()
                else FinancialUnit((match.group("currency") or "unitless").upper())
                if match.group("currency")
                else FinancialUnit.UNITLESS
            )
            values.append((number, unit, line.strip()))
    return tuple(values)


def _evidence_lines(evidence: tuple[Evidence, ...]) -> tuple[str, ...]:
    grouped: dict[tuple[str, str, int | None], list[Evidence]] = {}
    for item in evidence:
        location = item.source_location
        key = (location.document_id, location.path, location.line_start)
        grouped.setdefault(key, []).append(item)
    lines: list[str] = []
    for items in grouped.values():
        if all(item.source_location.cell is not None for item in items):
            ordered = sorted(
                items,
                key=lambda item: item.source_location.cell or "",
            )
            if len(ordered) == 1 and "\n" in ordered[0].excerpt:
                lines.extend(ordered[0].excerpt.splitlines())
            else:
                lines.append(",".join(item.excerpt for item in ordered))
        else:
            for item in items:
                lines.extend(item.excerpt.splitlines())
    return tuple(lines)


def _evidence_containing(
    evidence: tuple[Evidence, ...], marker: str
) -> tuple[Evidence, ...]:
    wanted = marker.casefold()
    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", marker):
        numeric_marker = re.compile(rf"(?<![0-9.]){re.escape(marker)}(?![0-9.])")
        matching = tuple(
            item for item in evidence if numeric_marker.search(item.excerpt) is not None
        )
    else:
        matching = tuple(item for item in evidence if wanted in item.excerpt.casefold())
    return matching or evidence


def _evidence_row_for_marker(
    evidence: tuple[Evidence, ...], marker: str
) -> tuple[Evidence, ...]:
    matching = _evidence_containing(evidence, marker)
    first = matching[0]
    location = first.source_location
    row = tuple(
        item
        for item in evidence
        if (
            item.source_location.document_id == location.document_id
            and item.source_location.path == location.path
            and item.source_location.line_start == location.line_start
        )
    )
    return row or matching


def _unique_evidence(items: tuple[Evidence, ...]) -> tuple[Evidence, ...]:
    seen: set[str] = set()
    unique: list[Evidence] = []
    for item in items:
        if item.id not in seen:
            seen.add(item.id)
            unique.append(item)
    return tuple(unique)


class DeterministicToolRegistry:
    """Dispatch only through the literal approved tool-ID dictionary."""

    def __init__(self) -> None:
        self._executors: dict[ApprovedToolId, Callable[[ToolCall], ToolResult]] = {
            ApprovedToolId.CALCULATE_FINANCIAL_METRIC: self._calculate_financial_metric,
            ApprovedToolId.INSPECT_CONTRACT_CLAUSE: self._inspect_contract_clause,
            ApprovedToolId.DETECT_CONTRADICTIONS: self._detect_contradictions,
            ApprovedToolId.ANALYZE_MISSING_DOCUMENTS: self._analyze_missing_documents,
        }

    def execute(self, call: ToolCall) -> ToolResult:
        executor = self._executors.get(call.tool_id)
        if executor is None:
            raise ValueError("tool ID is not approved")
        return executor(call)

    def _calculate_financial_metric(self, call: ToolCall) -> FinancialMetricResult:
        arguments = call.arguments
        assert isinstance(arguments, FinancialMetricArguments)
        left_values = _label_values(call.evidence, arguments.left_label)
        if arguments.operation is FinancialOperation.REPORTED_VALUE:
            if not left_values:
                return FinancialMetricResult(
                    status=ToolResultStatus.ABSTAINED,
                    unit=FinancialUnit.UNITLESS,
                    evidence=call.evidence,
                    reason=ToolAbstentionReason.MISSING_EVIDENCE,
                )
            value, unit, line = left_values[0]
            primary = _evidence_containing(call.evidence, arguments.left_label)
            return FinancialMetricResult(
                status=ToolResultStatus.SUCCEEDED,
                value=_quantize(value, arguments.precision),
                unit=unit,
                claim=primary[0].excerpt,
                evidence=primary,
                primary_evidence=primary,
            )

        if arguments.operation is FinancialOperation.PERCENTAGE:
            explicit_percentage = next(
                (
                    (value, line)
                    for value, unit, line in left_values
                    if unit is FinancialUnit.PERCENT
                ),
                None,
            )
            if explicit_percentage is not None:
                right_values = _label_values(call.evidence, arguments.right_label or "")
                if (
                    right_values
                    and right_values[0][1] is not FinancialUnit.PERCENT
                    and arguments.left_label.casefold() != "largest customer"
                ):
                    return FinancialMetricResult(
                        status=ToolResultStatus.ABSTAINED,
                        unit=FinancialUnit.UNITLESS,
                        evidence=call.evidence,
                        reason=ToolAbstentionReason.UNIT_MISMATCH,
                    )
                value, line = explicit_percentage
                primary_candidates = tuple(
                    item
                    for item in call.evidence
                    if f"{value}%" in item.excerpt
                    and "revenue share" in item.excerpt.casefold()
                )
                primary = (
                    (min(primary_candidates, key=lambda item: len(item.excerpt)),)
                    if primary_candidates
                    else _evidence_containing(call.evidence, str(value))
                )
                return FinancialMetricResult(
                    status=ToolResultStatus.SUCCEEDED,
                    value=_quantize(value, arguments.precision),
                    unit=FinancialUnit.PERCENT,
                    claim=primary[0].excerpt,
                    evidence=_evidence_row_for_marker(call.evidence, str(value)),
                    primary_evidence=primary,
                )

        right_values = _label_values(call.evidence, arguments.right_label or "")
        if not left_values or not right_values:
            return FinancialMetricResult(
                status=ToolResultStatus.ABSTAINED,
                unit=FinancialUnit.UNITLESS,
                evidence=call.evidence,
                reason=ToolAbstentionReason.MISSING_EVIDENCE,
            )
        left, left_unit, left_line = left_values[0]
        right, right_unit, right_line = right_values[0]
        if left_unit is not right_unit:
            return FinancialMetricResult(
                status=ToolResultStatus.ABSTAINED,
                unit=FinancialUnit.UNITLESS,
                evidence=call.evidence,
                reason=ToolAbstentionReason.UNIT_MISMATCH,
            )
        if arguments.operation is FinancialOperation.PERCENTAGE:
            if right == 0:
                return FinancialMetricResult(
                    status=ToolResultStatus.ABSTAINED,
                    unit=FinancialUnit.PERCENT,
                    evidence=call.evidence,
                    reason=ToolAbstentionReason.DIVISION_BY_ZERO,
                )
            value = _quantize(left / right * Decimal("100"), arguments.precision)
            primary = _evidence_containing(call.evidence, str(value))
            if primary == call.evidence:
                primary = _evidence_containing(call.evidence, arguments.left_label)
            return FinancialMetricResult(
                status=ToolResultStatus.SUCCEEDED,
                value=value,
                unit=FinancialUnit.PERCENT,
                claim=primary[0].excerpt,
                evidence=_unique_evidence(
                    (
                        *_evidence_row_for_marker(call.evidence, arguments.left_label),
                        *_evidence_row_for_marker(
                            call.evidence, arguments.right_label or ""
                        ),
                    )
                ),
                primary_evidence=primary,
            )
        value = _quantize(left - right, arguments.precision)
        return FinancialMetricResult(
            status=ToolResultStatus.SUCCEEDED,
            value=value,
            unit=left_unit,
            claim=_evidence_containing(call.evidence, str(value))[0].excerpt,
            evidence=call.evidence,
            primary_evidence=_evidence_containing(call.evidence, str(value)),
        )

    def _inspect_contract_clause(self, call: ToolCall) -> ContractClauseResult:
        if not isinstance(call.arguments, ContractClauseArguments):
            raise ValueError("contract tool received incompatible arguments")
        clause = call.arguments.clause.replace("_", " ").casefold()
        for item in call.evidence:
            for line in item.excerpt.splitlines():
                normalised = line.casefold()
                matches = (
                    (
                        clause in {"change of control", "change_of_control"}
                        and "change of control" in normalised
                        and "consent" in normalised
                    )
                    or (
                        clause in {"price escalation", "price_escalation"}
                        and "increase price" in normalised
                    )
                    or (
                        clause in {"term", "contract term"}
                        and "initial term" in normalised
                    )
                )
                if matches:
                    relevant = (item,)
                    return ContractClauseResult(
                        status=ToolResultStatus.SUCCEEDED,
                        clause=call.arguments.clause,
                        claim=line.strip(),
                        evidence=relevant,
                        primary_evidence=relevant,
                    )
        return ContractClauseResult(
            status=ToolResultStatus.ABSTAINED,
            clause=call.arguments.clause,
            evidence=call.evidence,
            reason=ToolAbstentionReason.MISSING_EVIDENCE,
        )

    def _detect_contradictions(self, call: ToolCall) -> ContradictionResult:
        if not isinstance(call.arguments, ContradictionArguments):
            raise ValueError("contradiction tool received incompatible arguments")
        subject = call.arguments.subject.casefold()
        for item in call.evidence:
            for line in item.excerpt.splitlines():
                normalised = line.casefold()
                if "conflict" in normalised and subject in normalised:
                    relevant = tuple(
                        candidate
                        for candidate in call.evidence
                        if subject in candidate.excerpt.casefold()
                        or "mandatory" in candidate.excerpt.casefold()
                        or "password-only" in candidate.excerpt.casefold()
                    )
                    relevant = relevant or (item,)
                    return ContradictionResult(
                        status=ToolResultStatus.SUCCEEDED,
                        subject=call.arguments.subject,
                        claim=line.strip(),
                        evidence=relevant,
                        primary_evidence=(item,),
                    )
        return ContradictionResult(
            status=ToolResultStatus.ABSTAINED,
            subject=call.arguments.subject,
            evidence=call.evidence,
            reason=ToolAbstentionReason.UNSUPPORTED_INPUT,
        )

    def _analyze_missing_documents(self, call: ToolCall) -> MissingDocumentResult:
        if not isinstance(call.arguments, MissingDocumentArguments):
            raise ValueError("missing-document tool received incompatible arguments")
        document_name = call.arguments.document_name.casefold()
        for item in call.evidence:
            for line in item.excerpt.splitlines():
                normalised = line.casefold()
                missing = document_name in normalised and (
                    "outstanding" in normalised
                    or "not provided" in normalised
                    or "not included" in normalised
                )
                if missing:
                    relevant = (item,)
                    return MissingDocumentResult(
                        status=ToolResultStatus.SUCCEEDED,
                        document_name=call.arguments.document_name,
                        claim=line.strip(),
                        evidence=relevant,
                        primary_evidence=relevant,
                    )
        return MissingDocumentResult(
            status=ToolResultStatus.ABSTAINED,
            document_name=call.arguments.document_name,
            evidence=call.evidence,
            reason=ToolAbstentionReason.MISSING_EVIDENCE,
        )
