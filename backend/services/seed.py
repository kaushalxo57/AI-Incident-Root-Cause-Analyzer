import os
import sys
from datetime import datetime, timedelta

# Adjust path to import backend modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.database import SessionLocal, Base, engine
from backend import models
from backend.services.parser import LogParser
from backend.services.db_service import DatabaseService
from backend.services.root_cause import RootCauseAnalyzer


def seed_database():
    print("Initializing Database Seeder...")
    
    # Establish connection and clean tables
    db = SessionLocal()
    try:
        print("Cleaning existing database records...")
        db.query(models.IncidentEvent).delete()
        db.query(models.Incident).delete()
        db.query(models.LogEvent).delete()
        db.query(models.Service).delete()
        db.query(models.AnalysisRun).delete()
        db.commit()

        print("Seeding services...")
        services_to_create = [
            {"name": "database", "type": "database", "status": "CRITICAL", "error_rate": 20.0, "anomaly_count": 2},
            {"name": "payment-api", "type": "application", "status": "CRITICAL", "error_rate": 25.0, "anomaly_count": 3},
            {"name": "gateway-service", "type": "gateway", "status": "DEGRADED", "error_rate": 5.0, "anomaly_count": 1},
            {"name": "auth-service", "type": "application", "status": "HEALTHY", "error_rate": 0.0, "anomaly_count": 0}
        ]

        for s_data in services_to_create:
            svc = models.Service(**s_data)
            db.add(svc)
        db.commit()

        # Resolve services mapping
        services_map = {s.name: s for s in db.query(models.Service).all()}

        # Seed Incident 1: Historical Resolved Incident
        print("Seeding historical incident...")
        inc1_start = datetime.now() - timedelta(hours=3)
        inc1_end = datetime.now() - timedelta(hours=2, minutes=45)

        incident_hist = models.Incident(
            title="Auth Service Token Validation Latency Spike",
            severity="MEDIUM",
            status="RESOLVED",
            start_time=inc1_start,
            end_time=inc1_end,
            affected_services=["auth-service", "gateway-service"],
            root_cause="auth-service",
            confidence=0.82,
            summary="Auth service token endpoint validation latency spiked above 2500ms causing timeouts in gateway-service. The issue was resolved after scaling auth instances.",
            evidence=[
                {
                    "timestamp": inc1_start.isoformat(),
                    "service_name": "auth-service",
                    "level": "WARNING",
                    "message": "Token verification latency high: 2450ms",
                    "is_root_cause_indicator": True
                },
                {
                    "timestamp": (inc1_start + timedelta(minutes=5)).isoformat(),
                    "service_name": "gateway-service",
                    "level": "ERROR",
                    "message": "Timeout waiting for auth validation token",
                    "is_root_cause_indicator": False
                }
            ]
        )
        db.add(incident_hist)
        db.flush()

        # Seed Incident 1 events
        db.add(models.IncidentEvent(
            incident_id=incident_hist.id,
            timestamp=inc1_start,
            service_name="auth-service",
            level="WARNING",
            message="Token verification latency high: 2450ms",
            event_type="root_cause_indicator",
            importance=4
        ))
        db.add(models.IncidentEvent(
            incident_id=incident_hist.id,
            timestamp=inc1_start + timedelta(minutes=5),
            service_name="gateway-service",
            level="ERROR",
            message="Timeout waiting for auth validation token",
            event_type="anomaly",
            importance=3
        ))
        db.add(models.IncidentEvent(
            incident_id=incident_hist.id,
            timestamp=inc1_end,
            service_name="auth-service",
            level="INFO",
            message="Token verification latency recovered: 12ms",
            event_type="recovery",
            importance=5
        ))
        db.commit()

        # Seed logs from the sample file and register Incident 2
        print("Reading sample logs...")
        sample_log_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../sample_data/demo_logs.log"))
        
        if os.path.exists(sample_log_path):
            with open(sample_log_path, "r") as f:
                log_content = f.read()

            # Shift the log timestamps to match the current date
            shifted_lines = []
            now = datetime.now()
            time_shift = now - datetime(2026, 8, 19, 10, 14, 0)
            
            for line in log_content.splitlines():
                if not line:
                    continue
                # Extract timestamp [2026-08-19 10:00:00]
                match = re.search(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]", line)
                if match:
                    original_ts = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
                    new_ts = original_ts + time_shift
                    new_line = line.replace(match.group(1), new_ts.strftime("%Y-%m-%d %H:%M:%S"))
                    shifted_lines.append(new_line)
                else:
                    shifted_lines.append(line)
            
            log_content_updated = "\n".join(shifted_lines)

            print("Parsing and storing log events...")
            parsed_logs = LogParser.parse_file(log_content_updated, "demo_logs.log")
            
            # Save logs in DB
            db_logs = DatabaseService.save_log_events(db, parsed_logs)
            print(f"Stored {len(db_logs)} log events.")

            # Create Analysis Run
            run_registry = models.AnalysisRun(
                file_name="demo_logs.log",
                file_size=len(log_content_updated.encode("utf-8")),
                status="SUCCESS",
                logs_processed=len(db_logs),
                anomalies_detected=6,
                incidents_created=1
            )
            db.add(run_registry)

            # Create Incident 2 (Current active connection exhaustion)
            print("Creating Active Connection Exhaustion incident...")
            # We can run the analysis pipeline directly on these shifted logs to seed!
            errors_only = [e for e in parsed_logs if e["level"] in ["WARNING", "ERROR", "CRITICAL"]]
            
            # Run detection
            from backend.services.anomaly_detector import AnomalyDetector
            detector = AnomalyDetector(threshold_z=1.5, window_minutes=1)
            anomalies = detector.detect_anomalies(parsed_logs)
            
            if anomalies:
                rc_results = RootCauseAnalyzer.analyze_root_cause(anomalies, errors_only)
                affected_services = list(set(a["service_name"] for a in anomalies))
                start_time = min(a["timestamp"] for a in anomalies)

                active_incident = DatabaseService.create_incident_from_analysis(
                    db=db,
                    analysis_results=rc_results,
                    start_time=start_time,
                    affected_services=affected_services
                )
                print(f"Incident created successfully: {active_incident.title} (ID: {active_incident.id})")
            
            db.commit()

        # Update service healths based on loaded data
        DatabaseService.calculate_and_update_services_health(db)
        db.commit()
        print("Database seeding completed successfully.")

    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {str(e)}")
        raise e
    finally:
        db.close()


import re
if __name__ == "__main__":
    seed_database()
