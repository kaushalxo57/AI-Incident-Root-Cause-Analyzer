import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Dict, Any

from backend.database import get_db
from backend import models, schemas
from backend.services.parser import LogParser
from backend.services.anomaly_detector import AnomalyDetector
from backend.services.similarity import LogClustering
from backend.services.root_cause import RootCauseAnalyzer
from backend.services.db_service import DatabaseService

# Setup logger
logger = logging.getLogger("backend.routes.logs")

router = APIRouter(prefix="/api/logs")

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_EXTENSIONS = {".log", ".txt", ".csv", ".json"}


@router.post("/upload", response_model=schemas.AnalysisRunResponse)
async def upload_and_analyze_logs(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    # 1. Validate file extension
    file_name = file.filename or "unknown.log"
    extension = "." + file_name.split(".")[-1].lower() if "." in file_name else ""
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format '{extension}'. Only .log, .txt, .csv, and .json are supported."
        )

    # 2. Read content and validate size
    try:
        content_bytes = await file.read()
        file_size = len(content_bytes)
        if file_size > MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail="File exceeds maximum size of 10MB.")
        
        file_content = content_bytes.decode("utf-8", errors="replace")
    except Exception as e:
        logger.exception("Failed to read uploaded log file")
        raise HTTPException(status_code=400, detail=f"Failed to read file content: {str(e)}")

    # 3. Create analysis run registry
    run_registry = models.AnalysisRun(
        file_name=file_name,
        file_size=file_size,
        status="RUNNING"
    )
    db.add(run_registry)
    db.commit()
    db.refresh(run_registry)

    try:
        # 4. Parse file
        parsed_events = LogParser.parse_file(file_content, file_name)
        if not parsed_events:
            run_registry.status = "SUCCESS"
            run_registry.logs_processed = 0
            run_registry.anomalies_detected = 0
            run_registry.incidents_created = 0
            db.commit()
            return run_registry

        # 5. Save logs to database
        db_events = DatabaseService.save_log_events(db, parsed_events)

        # 6. Run anomaly detection
        # Create detector (1-minute buckets, Z-score threshold = 2.0)
        detector = AnomalyDetector(threshold_z=2.0, window_minutes=1)
        # Pass parsed_events with actual datetime objects
        anomalies = detector.detect_anomalies(parsed_events)

        incidents_count = 0
        if anomalies:
            # 7. Correlate and analyze root cause
            # Group errors for similarity analysis where helpful
            errors_only = [e for e in parsed_events if e["level"] in ["WARNING", "ERROR", "CRITICAL"]]
            
            # Run root cause analysis
            rc_results = RootCauseAnalyzer.analyze_root_cause(anomalies, errors_only)

            # Determine affected services
            affected_services = list(set(a["service_name"] for a in anomalies))
            
            # Find earliest start time of the anomalies
            start_time = min(a["timestamp"] for a in anomalies)

            # Create incident in PostgreSQL
            DatabaseService.create_incident_from_analysis(
                db=db,
                analysis_results=rc_results,
                start_time=start_time,
                affected_services=affected_services
            )
            incidents_count = 1

        # 8. Update microservice error rates and overall statuses
        DatabaseService.calculate_and_update_services_health(db)

        # 9. Update analysis run metadata
        run_registry.status = "SUCCESS"
        run_registry.logs_processed = len(db_events)
        run_registry.anomalies_detected = len(anomalies)
        run_registry.incidents_created = incidents_count
        db.commit()
        db.refresh(run_registry)

        return run_registry

    except Exception as e:
        logger.exception(f"Log analysis execution failed for run {run_registry.id}")
        run_registry.status = "FAILED"
        db.commit()
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred during log analysis. Details have been logged."
        )
