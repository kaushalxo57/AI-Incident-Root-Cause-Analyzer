from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, desc
from backend import models, schemas


class DatabaseService:
    @staticmethod
    def get_or_create_services_from_logs(db: Session, service_names: List[str]) -> Dict[str, models.Service]:
        """
        Takes unique service names, finds them in the database, or creates them if missing.
        Returns a mapping of service_name -> Service model.
        """
        service_map = {}
        if not service_names:
            return service_map

        # Query existing
        existing_services = db.query(models.Service).filter(models.Service.name.in_(service_names)).all()
        for s in existing_services:
            service_map[s.name] = s

        # Create new ones
        for name in service_names:
            if name not in service_map:
                # Deduce type
                name_lower = name.lower()
                svc_type = "application"
                if any(kw in name_lower for kw in ["db", "database", "postgres", "sql"]):
                    svc_type = "database"
                elif "gateway" in name_lower or "nginx" in name_lower:
                    svc_type = "gateway"
                elif any(kw in name_lower for kw in ["external", "stripe", "twilio", "aws"]):
                    svc_type = "external"

                new_svc = models.Service(
                    name=name,
                    type=svc_type,
                    status="HEALTHY",
                    error_rate=0.0,
                    anomaly_count=0
                )
                db.add(new_svc)
                db.flush()  # Populates ID
                service_map[name] = new_svc

        return service_map

    @classmethod
    def save_log_events(cls, db: Session, parsed_logs: List[Dict[str, Any]]) -> List[models.LogEvent]:
        if not parsed_logs:
            return []

        # Find unique services and resolve them
        service_names = list(set(log["service_name"] for log in parsed_logs))
        service_map = cls.get_or_create_services_from_logs(db, service_names)

        db_events = []
        for log in parsed_logs:
            svc_name = log["service_name"]
            svc = service_map.get(svc_name)
            
            db_event = models.LogEvent(
                timestamp=log["timestamp"],
                service_id=svc.id if svc else None,
                service_name=svc_name,
                level=log["level"],
                message=log["message"],
                status_code=log["status_code"],
                request_id=log["request_id"],
                details=log["details"]
            )
            db.add(db_event)
            db_events.append(db_event)

        db.flush()
        return db_events

    @staticmethod
    def calculate_and_update_services_health(db: Session):
        """
        Updates service error rates and anomaly counts based on log events 
        from the last 15 minutes, and sets their statuses.
        """
        services = db.query(models.Service).all()
        now = datetime.now()
        fifteen_mins_ago = now - timedelta(minutes=15)

        for svc in services:
            # Get error logs count vs total logs count
            total_logs = db.query(func.count(models.LogEvent.id)).filter(
                and_(
                    models.LogEvent.service_id == svc.id,
                    models.LogEvent.timestamp >= fifteen_mins_ago
                )
            ).scalar() or 0

            error_logs = db.query(func.count(models.LogEvent.id)).filter(
                and_(
                    models.LogEvent.service_id == svc.id,
                    models.LogEvent.level.in_(["WARNING", "ERROR", "CRITICAL"]),
                    models.LogEvent.timestamp >= fifteen_mins_ago
                )
            ).scalar() or 0

            # Calculate error rate
            error_rate = 0.0
            if total_logs > 0:
                error_rate = round((error_logs / total_logs) * 100.0, 2)

            # Get recent active incidents affecting this service
            # (where status is not RESOLVED or CLOSED)
            active_incidents = db.query(models.Incident).filter(
                and_(
                    models.Incident.status.in_(["OPEN", "INVESTIGATING"]),
                    models.Incident.affected_services.cast(models.String).like(f'%"{svc.name}"%')
                )
            ).all()

            # Determine severity of active incidents
            highest_severity = None
            if active_incidents:
                severities = [inc.severity for inc in active_incidents]
                if "CRITICAL" in severities:
                    highest_severity = "CRITICAL"
                elif "HIGH" in severities:
                    highest_severity = "HIGH"
                elif "MEDIUM" in severities:
                    highest_severity = "MEDIUM"
                elif "LOW" in severities:
                    highest_severity = "LOW"

            # Determine status
            status = "HEALTHY"
            if error_rate >= 10.0 or highest_severity in ["CRITICAL", "HIGH"]:
                status = "CRITICAL"
            elif error_rate >= 2.0 or highest_severity in ["MEDIUM", "LOW"]:
                status = "DEGRADED"

            # Update service model
            svc.error_rate = error_rate
            svc.status = status
            
            # Anomaly count: total anomalies generated in the last 1 hour
            # (approximate using the incident events logged)
            anomalies = db.query(func.count(models.IncidentEvent.id)).filter(
                and_(
                    models.IncidentEvent.service_name == svc.name,
                    models.IncidentEvent.event_type == "anomaly",
                    models.IncidentEvent.timestamp >= now - timedelta(hours=1)
                )
            ).scalar() or 0
            svc.anomaly_count = anomalies

        db.flush()

    @staticmethod
    def create_incident_from_analysis(db: Session, analysis_results: Dict[str, Any], start_time: datetime, affected_services: List[str]) -> models.Incident:
        """
        Creates a new incident with its supporting timeline events.
        """
        # Determine incident severity based on root cause level, confidence and service impact
        # Count number of affected services
        svc_count = len(affected_services)
        
        # Look at the evidence levels
        levels = [ev["level"] for ev in analysis_results["evidence"]]
        
        severity = "LOW"
        if "CRITICAL" in levels or svc_count >= 3:
            severity = "CRITICAL"
        elif "ERROR" in levels or svc_count >= 2:
            severity = "HIGH"
        elif "WARNING" in levels:
            severity = "MEDIUM"

        title = f"Multiple anomalies detected in {analysis_results['likely_root_cause']}"
        if severity == "CRITICAL":
            title = f"Critical service degradation starting at {start_time.strftime('%H:%M')} due to {analysis_results['likely_root_cause']} failure"
        elif severity == "HIGH":
            title = f"High-error spike in {analysis_results['likely_root_cause']} affecting downstream services"

        incident = models.Incident(
            title=title,
            severity=severity,
            status="OPEN",
            start_time=start_time,
            affected_services=affected_services,
            root_cause=analysis_results["likely_root_cause"],
            confidence=analysis_results["confidence"],
            summary=analysis_results["summary"],
            evidence=analysis_results["evidence"]
        )
        db.add(incident)
        db.flush()  # Populate incident.id

        # Create supporting events in the timeline
        for ev in analysis_results["evidence"]:
            event_type = "anomaly"
            importance = 3
            if ev["is_root_cause_indicator"]:
                event_type = "root_cause_indicator"
                importance = 5
            elif ev["level"] in ["ERROR", "CRITICAL"]:
                event_type = "critical_error"
                importance = 4
            
            db_event = models.IncidentEvent(
                incident_id=incident.id,
                timestamp=datetime.fromisoformat(ev["timestamp"]) if isinstance(ev["timestamp"], str) else ev["timestamp"],
                service_name=ev["service_name"],
                level=ev["level"],
                message=ev["message"],
                event_type=event_type,
                importance=importance
            )
            db.add(db_event)

        db.flush()
        return incident

    @staticmethod
    def get_incidents(db: Session, status: Optional[str] = None, severity: Optional[str] = None, search: Optional[str] = None) -> List[models.Incident]:
        query = db.query(models.Incident)
        
        if status:
            query = query.filter(models.Incident.status == status)
        if severity:
            query = query.filter(models.Incident.severity == severity)
        if search:
            query = query.filter(
                or_(
                    models.Incident.title.ilike(f"%{search}%"),
                    models.Incident.summary.ilike(f"%{search}%"),
                    models.Incident.root_cause.ilike(f"%{search}%")
                )
            )

        # Order by severity (CRITICAL, HIGH, MEDIUM, LOW) and then start_time descending
        # PostgreSQL support for custom sorting can be done in Python or using SQL CASE statements
        incidents = query.order_by(desc(models.Incident.start_time)).all()
        
        # Sort in python for strict severity ordering
        severity_weights = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
        
        # If open first, then sorted by severity weight, then start time
        incidents.sort(
            key=lambda x: (
                0 if x.status in ["OPEN", "INVESTIGATING"] else 1,
                -severity_weights.get(x.severity, 0),
                -x.start_time.timestamp()
            )
        )
        
        return incidents

    @staticmethod
    def get_incident_by_id(db: Session, incident_id: int) -> Optional[models.Incident]:
        return db.query(models.Incident).filter(models.Incident.id == incident_id).first()

    @staticmethod
    def update_incident_status(db: Session, incident_id: int, status: str) -> Optional[models.Incident]:
        incident = db.query(models.Incident).filter(models.Incident.id == incident_id).first()
        if incident:
            incident.status = status
            if status in ["RESOLVED", "CLOSED"]:
                incident.end_time = datetime.now()
            else:
                incident.end_time = None
            db.flush()
        return incident

    @staticmethod
    def get_services(db: Session) -> List[models.Service]:
        return db.query(models.Service).order_by(models.Service.name).all()

    @classmethod
    def get_analytics_summary(cls, db: Session) -> Dict[str, Any]:
        """
        Computes aggregates for the dashboard view.
        """
        total_services = db.query(func.count(models.Service.id)).scalar() or 0
        
        active_incidents = db.query(func.count(models.Incident.id)).filter(
            models.Incident.status.in_(["OPEN", "INVESTIGATING"])
        ).scalar() or 0
        
        total_events = db.query(func.count(models.LogEvent.id)).scalar() or 0

        # Calculate system health score
        # Base is 100.
        # Deduct 25 points for each active CRITICAL incident.
        # Deduct 15 points for each active HIGH incident.
        # Deduct 5 points for each active MEDIUM/LOW incident.
        # Deduct 5 points for each CRITICAL service status.
        # Deduct 2 points for each DEGRADED service status.
        # Minimum health score is 10.0.
        health_score = 100.0
        
        active_inc_list = db.query(models.Incident.severity).filter(
            models.Incident.status.in_(["OPEN", "INVESTIGATING"])
        ).all()
        
        for (sev,) in active_inc_list:
            if sev == "CRITICAL":
                health_score -= 25
            elif sev == "HIGH":
                health_score -= 15
            else:
                health_score -= 5

        services = db.query(models.Service.status).all()
        for (status,) in services:
            if status == "CRITICAL":
                health_score -= 5
            elif status == "DEGRADED":
                health_score -= 2

        health_score = max(10.0, min(100.0, health_score))

        # Severity distribution of all incidents
        severity_counts = db.query(
            models.Incident.severity,
            func.count(models.Incident.id)
        ).group_by(models.Incident.severity).all()
        
        severity_distribution = [{"severity": s, "count": c} for s, c in severity_counts]

        # Service Health Summary
        service_list = db.query(models.Service).all()
        service_health = [
            {
                "name": s.name,
                "status": s.status,
                "error_rate": s.error_rate,
                "anomaly_count": s.anomaly_count
            } for s in service_list
        ]

        # Error rate timeline over the last 1 hour in 5-minute buckets
        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)
        
        # SQL query to bucket logs in 5-minute intervals
        # To keep it generic across database configurations, we can fetch the last 1 hour log events and bucket in python.
        logs = db.query(
            models.LogEvent.timestamp,
            models.LogEvent.level
        ).filter(models.LogEvent.timestamp >= one_hour_ago).all()

        # Group in python
        # Pre-populate buckets
        buckets = {}
        start_time = one_hour_ago - timedelta(minutes=one_hour_ago.minute % 5, seconds=one_hour_ago.second, microseconds=one_hour_ago.microsecond)
        t = start_time
        while t <= now:
            buckets[t] = {"error": 0, "total": 0}
            t += timedelta(minutes=5)

        for ts, lvl in logs:
            # Round ts to nearest 5 mins
            rounded_ts = ts - timedelta(minutes=ts.minute % 5, seconds=ts.second, microseconds=ts.microsecond)
            rounded_ts = rounded_ts.replace(tzinfo=None) # remove tz for dict lookup
            
            # Find the closest bucket
            closest_bucket = None
            min_diff = timedelta(days=1)
            for b in buckets.keys():
                diff = abs(b - rounded_ts)
                if diff < min_diff:
                    min_diff = diff
                    closest_bucket = b
            
            if closest_bucket and min_diff < timedelta(minutes=5):
                buckets[closest_bucket]["total"] += 1
                if lvl in ["WARNING", "ERROR", "CRITICAL"]:
                    buckets[closest_bucket]["error"] += 1

        timeline = []
        for b_ts, counts in sorted(buckets.items()):
            tot = counts["total"]
            err = counts["error"]
            rate = round((err / tot) * 100.0, 2) if tot > 0 else 0.0
            
            timeline.append({
                "timestamp": b_ts,
                "error_count": err,
                "total_count": tot,
                "rate": rate
            })

        return {
            "total_services": total_services,
            "active_incidents": active_incidents,
            "total_events": total_events,
            "system_health_score": health_score,
            "severity_distribution": severity_distribution,
            "service_health": service_health,
            "error_rate_timeline": timeline
        }
