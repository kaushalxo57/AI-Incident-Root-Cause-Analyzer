from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from backend.database import get_db
from backend import schemas
from backend.services.db_service import DatabaseService

router = APIRouter(prefix="/api/incidents")


@router.get("", response_model=List[schemas.IncidentResponse])
def get_incidents_list(
    status: Optional[str] = Query(None, description="Filter by status (OPEN, INVESTIGATING, RESOLVED, CLOSED)"),
    severity: Optional[str] = Query(None, description="Filter by severity (LOW, MEDIUM, HIGH, CRITICAL)"),
    search: Optional[str] = Query(None, description="Search query in title, summary, or root cause"),
    db: Session = Depends(get_db)
):
    return DatabaseService.get_incidents(
        db=db,
        status=status,
        severity=severity,
        search=search
    )


@router.get("/{incident_id}", response_model=schemas.IncidentResponse)
def get_incident_detail(incident_id: int, db: Session = Depends(get_db)):
    incident = DatabaseService.get_incident_by_id(db, incident_id)
    if not incident:
        raise HTTPException(
            status_code=404,
            detail=f"Incident with ID {incident_id} not found"
        )
    return incident


@router.patch("/{incident_id}/status", response_model=schemas.IncidentResponse)
def update_incident_status(
    incident_id: int,
    payload: schemas.IncidentStatusUpdate,
    db: Session = Depends(get_db)
):
    incident = DatabaseService.update_incident_status(db, incident_id, payload.status)
    if not incident:
        raise HTTPException(
            status_code=404,
            detail=f"Incident with ID {incident_id} not found"
        )
    
    # Recalculate service healths, since resolving an incident might return services to healthy
    DatabaseService.calculate_and_update_services_health(db)
    db.commit()
    db.refresh(incident)
    
    return incident
