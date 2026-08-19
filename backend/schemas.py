from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional, Any, Dict


# --- SERVICE SCHEMAS ---
class ServiceBase(BaseModel):
    name: str
    type: str
    status: str
    error_rate: float
    anomaly_count: int


class ServiceResponse(ServiceBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# --- LOG EVENT SCHEMAS ---
class LogEventBase(BaseModel):
    timestamp: datetime
    service_name: str
    level: str
    message: str
    status_code: Optional[int] = None
    request_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class LogEventResponse(LogEventBase):
    id: int
    service_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


# --- INCIDENT EVENT SCHEMAS ---
class IncidentEventBase(BaseModel):
    timestamp: datetime
    service_name: str
    level: str
    message: str
    event_type: str
    importance: int


class IncidentEventResponse(IncidentEventBase):
    id: int
    incident_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# --- INCIDENT SCHEMAS ---
class IncidentBase(BaseModel):
    title: str
    severity: str
    status: str
    start_time: datetime
    end_time: Optional[datetime] = None
    affected_services: List[str]
    root_cause: Optional[str] = None
    confidence: float
    summary: str
    evidence: Optional[List[Dict[str, Any]]] = None


class IncidentResponse(IncidentBase):
    id: int
    created_at: datetime
    updated_at: datetime
    events: List[IncidentEventResponse] = []

    class Config:
        from_attributes = True


class IncidentStatusUpdate(BaseModel):
    status: str = Field(pattern="^(OPEN|INVESTIGATING|RESOLVED|CLOSED)$")


# --- ANALYSIS RUN SCHEMAS ---
class AnalysisRunResponse(BaseModel):
    id: int
    timestamp: datetime
    file_name: str
    file_size: int
    status: str
    logs_processed: int
    anomalies_detected: int
    incidents_created: int
    created_at: datetime

    class Config:
        from_attributes = True


# --- ANALYTICS SCHEMAS ---
class SeverityCount(BaseModel):
    severity: str
    count: int


class ServiceHealthSummary(BaseModel):
    name: str
    status: str
    error_rate: float
    anomaly_count: int


class ErrorRateTimelinePoint(BaseModel):
    timestamp: datetime
    error_count: int
    total_count: int
    rate: float


class AnalyticsSummary(BaseModel):
    total_services: int
    active_incidents: int
    total_events: int
    system_health_score: float
    severity_distribution: List[SeverityCount]
    service_health: List[ServiceHealthSummary]
    error_rate_timeline: List[ErrorRateTimelinePoint]
