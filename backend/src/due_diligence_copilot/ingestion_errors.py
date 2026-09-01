"""Failure types shared by ingestion stages."""

from __future__ import annotations

from .ingestion_contracts import IngestionFailureClassification


class AuthorizationError(PermissionError):
    pass


class IngestionFailure(Exception):
    classification = IngestionFailureClassification.PERMANENT


class UploadValidationError(IngestionFailure):
    classification = IngestionFailureClassification.VALIDATION


class PermanentIngestionFailure(IngestionFailure):
    classification = IngestionFailureClassification.PERMANENT


class TransientIngestionFailure(IngestionFailure):
    classification = IngestionFailureClassification.TRANSIENT
