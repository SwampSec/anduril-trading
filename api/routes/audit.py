from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from api.deps import get_audit_logger
from audit.logger import AuditLogger

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/recent")
async def audit_recent(
    audit: Annotated[AuditLogger, Depends(get_audit_logger)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict:
    records = audit.tail(limit)
    return {"count": len(records), "records": records}
