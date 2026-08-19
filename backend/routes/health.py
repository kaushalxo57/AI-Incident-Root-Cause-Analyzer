from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from backend.database import get_db

router = APIRouter()


@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    db_status = "UP"
    try:
        # Perform quick select to verify connection
        db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"DOWN: {str(e)}"

    if db_status != "UP":
        raise HTTPException(
            status_code=503,
            detail={"status": "DEGRADED", "database": db_status}
        )

    return {
        "status": "OK",
        "database": "UP",
        "service": "AI Incident & Root-Cause Analyzer"
    }
