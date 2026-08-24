from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...diagnostics.service import diagnostics_snapshot
from ...schemas.diagnostics import DiagnosticsRead, RuntimeIdentityRead
from ...identity import get_runtime_identity
from ...storage.database import get_db

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])


@router.get("/identity", response_model=RuntimeIdentityRead)
def identity() -> RuntimeIdentityRead:
    value = get_runtime_identity()
    return RuntimeIdentityRead(product=value.product, version=value.version, revision=value.revision, environment=value.environment)


@router.get("", response_model=DiagnosticsRead)
def diagnostics(session: Session = Depends(get_db)) -> DiagnosticsRead:
    return diagnostics_snapshot(session)
