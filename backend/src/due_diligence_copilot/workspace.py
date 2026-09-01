"""Workspace identifier validation and authorization checks."""

from __future__ import annotations

import re

from .ingestion_contracts import AccessContext
from .ingestion_errors import AuthorizationError

WORKSPACE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"
_WORKSPACE_ID = re.compile(WORKSPACE_ID_PATTERN)


def validate_workspace_id(workspace_id: str) -> str:
    if not _WORKSPACE_ID.fullmatch(workspace_id):
        raise ValueError("invalid workspace_id")
    return workspace_id


def require_workspace_access(context: AccessContext, workspace_id: str) -> None:
    validate_workspace_id(workspace_id)
    if workspace_id not in context.allowed_workspace_ids:
        raise AuthorizationError("principal is not authorized for workspace")


def require_read_workspace(context: AccessContext) -> str:
    """Resolve a read scope from authenticated context, never caller input."""
    if context.workspace_id is None:
        if len(context.allowed_workspace_ids) != 1:
            raise AuthorizationError("read context requires one workspace scope")
        workspace_id = next(iter(context.allowed_workspace_ids))
    else:
        workspace_id = context.workspace_id
    require_workspace_access(context, workspace_id)
    return workspace_id
