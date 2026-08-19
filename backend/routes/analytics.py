from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.database import get_db
from backend import schemas
from backend.services.db_service import DatabaseService

router = APIRouter(prefix="/api/analytics")


@router.get("", response_model=schemas.AnalyticsSummary)
def get_analytics_metrics(db: Session = Depends(get_db)):
    return DatabaseService.get_analytics_summary(db)
