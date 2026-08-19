from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from backend.database import get_db
from backend import schemas
from backend.services.db_service import DatabaseService

router = APIRouter(prefix="/api/services")


@router.get("", response_model=List[schemas.ServiceResponse])
def get_monitored_services(db: Session = Depends(get_db)):
    return DatabaseService.get_services(db)
