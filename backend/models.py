from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from backend.database import Base


class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True, nullable=False)
    type = Column(String(50), default="application", nullable=False)  # database, application, gateway, external
    status = Column(String(20), default="HEALTHY", nullable=False)  # HEALTHY, DEGRADED, CRITICAL
    error_rate = Column(Float, default=0.0, nullable=False)
    anomaly_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    logs = relationship("LogEvent", back_populates="service")


class LogEvent(Base):
    __tablename__ = "log_events"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), index=True, nullable=False)
    service_id = Column(Integer, ForeignKey("services.id", ondelete="SET NULL"), nullable=True)
    service_name = Column(String(100), index=True, nullable=False)
    level = Column(String(20), index=True, nullable=False)  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    message = Column(Text, nullable=False)
    status_code = Column(Integer, nullable=True)
    request_id = Column(String(100), index=True, nullable=True)
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    service = relationship("Service", back_populates="logs")


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    severity = Column(String(20), index=True, nullable=False)  # LOW, MEDIUM, HIGH, CRITICAL
    status = Column(String(20), index=True, default="OPEN", nullable=False)  # OPEN, INVESTIGATING, RESOLVED, CLOSED
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=True)
    affected_services = Column(JSON, nullable=False)  # List of service names (strings)
    root_cause = Column(String(255), nullable=True)  # Name of service or specific system component
    confidence = Column(Float, default=0.0, nullable=False)  # 0.0 to 1.0 confidence score
    summary = Column(Text, nullable=False)
    evidence = Column(JSON, nullable=True)  # Detailed list of key evidence logs/metrics
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    events = relationship("IncidentEvent", back_populates="incident", cascade="all, delete-orphan")


class IncidentEvent(Base):
    __tablename__ = "incident_events"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(Integer, ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    service_name = Column(String(100), nullable=False)
    level = Column(String(20), nullable=False)
    message = Column(Text, nullable=False)
    event_type = Column(String(50), nullable=False)  # anomaly, critical_error, root_cause_indicator, recovery
    importance = Column(Integer, default=3, nullable=False)  # 1 to 5
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    incident = relationship("Incident", back_populates="events")


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_size = Column(Integer, nullable=False)  # In bytes
    status = Column(String(20), nullable=False)  # SUCCESS, FAILED, RUNNING
    logs_processed = Column(Integer, default=0, nullable=False)
    anomalies_detected = Column(Integer, default=0, nullable=False)
    incidents_created = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
