from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_session
from app.queries.incidents import incident_feature_collection


router = APIRouter(prefix="/api/v1/network", tags=["network"])


@router.get("/incidents/{incident_id}")
def incident_geometry(incident_id: UUID, session: Session = Depends(get_session)) -> dict:
    result = incident_feature_collection(session, incident_id)
    if result is None:
        raise HTTPException(status_code=404, detail={"code": "incident_not_found"})
    return result
