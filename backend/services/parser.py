import re
import json
import csv
import io
from datetime import datetime
from typing import List, Dict, Any, Optional
from dateutil import parser as date_parser

# Regex patterns for parsing log lines
BRACKET_PATTERN = re.compile(
    r"^\[([^\]]+)\]\s+\[([^\]]+)\]\s+\[([^\]]+)\]\s*(?:\[([^\]]+)\])?\s*(.*)$"
)
# Matches: [2026-08-19 10:14:00] [payment-api] [ERROR] [req-123] Database timeout occurred
# Group 1: Timestamp, Group 2: Service, Group 3: Level, Group 4: RequestId (optional), Group 5: Message

SYS_LIKE_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:?\d{2}|Z)?)\s+([^\s:]+)\s+([A-Z]+)\s*:\s*(.*)$"
)
# Matches: 2026-08-19 10:14:00 payment-api ERROR: Database timeout occurred
# Group 1: Timestamp, Group 2: Service, Group 3: Level, Group 4: Message

# Regex to detect HTTP status codes (4xx and 5xx)
HTTP_STATUS_PATTERN = re.compile(r"\b(4\d{2}|5\d{2})\b")

# Regex to find UUIDs/Request IDs
UUID_PATTERN = re.compile(r"\b([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\b")
REQ_ID_KV_PATTERN = re.compile(r"\b(?:request_id|req_id|trace_id)=([^\s,]+)")

# Pre-defined common operational phrases for root cause
OPERATIONAL_PATTERNS = {
    "connection_refused": re.compile(r"(connection refused|failed to connect|cannot connect)", re.IGNORECASE),
    "timeout": re.compile(r"(timeout|timed out|latency exceeded)", re.IGNORECASE),
    "database_error": re.compile(r"(database error|postgresql|mysql|sqlstate|db connection)", re.IGNORECASE),
    "auth_failure": re.compile(r"(auth|authentication|unauthorized|forbidden|invalid credentials|401|403)", re.IGNORECASE),
    "service_unavailable": re.compile(r"(unavailable|service unavailable|503|down)", re.IGNORECASE),
    "out_of_memory": re.compile(r"(out of memory|oom|heap space|memory exhaustion)", re.IGNORECASE),
}


class LogParser:
    @staticmethod
    def parse_timestamp(ts_str: str) -> datetime:
        try:
            return date_parser.parse(ts_str)
        except Exception:
            return datetime.now()

    @staticmethod
    def normalize_level(level_str: str) -> str:
        lvl = level_str.strip().upper()
        if lvl in ["INFO", "DEBUG", "WARN", "WARNING", "ERROR", "CRITICAL", "FATAL"]:
            if lvl == "WARN":
                return "WARNING"
            if lvl == "FATAL":
                return "CRITICAL"
            return lvl
        return "INFO"

    @classmethod
    def extract_status_code(cls, message: str) -> Optional[int]:
        # Search for HTTP status codes
        match = HTTP_STATUS_PATTERN.search(message)
        if match:
            return int(match.group(1))
        return None

    @classmethod
    def extract_request_id(cls, line: str) -> Optional[str]:
        # Try KV pair first
        kv_match = REQ_ID_KV_PATTERN.search(line)
        if kv_match:
            return kv_match.group(1).strip("[]{}()\"'")
        
        # Try generic UUID pattern
        uuid_match = UUID_PATTERN.search(line)
        if uuid_match:
            return uuid_match.group(1)
        return None

    @classmethod
    def parse_line(cls, line: str) -> Optional[Dict[str, Any]]:
        line = line.strip()
        if not line:
            return None

        # 1. Try JSON parsing
        try:
            data = json.loads(line)
            if isinstance(data, dict):
                # Extract text fields
                msg = data.get("message") or data.get("msg") or data.get("log") or str(data)
                lvl = data.get("level") or data.get("severity") or "INFO"
                svc = data.get("service") or data.get("service_name") or data.get("logger") or "unknown-service"
                ts_str = data.get("timestamp") or data.get("time") or data.get("date") or datetime.now().isoformat()
                status_code = data.get("status_code") or data.get("status") or cls.extract_status_code(msg)
                req_id = data.get("request_id") or data.get("req_id") or data.get("trace_id") or cls.extract_request_id(line)

                return {
                    "timestamp": cls.parse_timestamp(str(ts_str)),
                    "service_name": str(svc),
                    "level": cls.normalize_level(str(lvl)),
                    "message": str(msg),
                    "status_code": int(status_code) if status_code and str(status_code).isdigit() else None,
                    "request_id": str(req_id) if req_id else None,
                    "details": data
                }
        except json.JSONDecodeError:
            pass

        # 2. Try bracket parsing: [timestamp] [service] [level] [req_id] message
        bracket_match = BRACKET_PATTERN.match(line)
        if bracket_match:
            ts_str, svc, lvl, req_id, msg = bracket_match.groups()
            if not msg:  # If req_id group was not present, req_id will contain the message
                msg = req_id
                req_id = None
            
            if not req_id:
                req_id = cls.extract_request_id(line)

            return {
                "timestamp": cls.parse_timestamp(ts_str),
                "service_name": svc,
                "level": cls.normalize_level(lvl),
                "message": msg.strip(),
                "status_code": cls.extract_status_code(msg),
                "request_id": req_id,
                "details": None
            }

        # 3. Try syslog-like parsing: timestamp service LEVEL: message
        sys_match = SYS_LIKE_PATTERN.match(line)
        if sys_match:
            ts_str, svc, lvl, msg = sys_match.groups()
            return {
                "timestamp": cls.parse_timestamp(ts_str),
                "service_name": svc,
                "level": cls.normalize_level(lvl),
                "message": msg.strip(),
                "status_code": cls.extract_status_code(msg),
                "request_id": cls.extract_request_id(line),
                "details": None
            }

        # 4. Fallback: search for words in raw text
        # Try to find a timestamp
        # Match standard YYYY-MM-DD HH:MM:SS timestamps
        ts_match = re.search(r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?)", line)
        ts = cls.parse_timestamp(ts_match.group(1)) if ts_match else datetime.now()

        # Try to find level
        lvl_match = re.search(r"\b(DEBUG|INFO|WARN|WARNING|ERROR|CRITICAL|FATAL)\b", line, re.IGNORECASE)
        lvl = cls.normalize_level(lvl_match.group(1)) if lvl_match else "INFO"

        # Guess service name: if there is a word followed by [some_number] or bracket, e.g. "service-name[2381]"
        svc_match = re.search(r"\b([a-zA-Z0-9_\-]+-service|[a-zA-Z0-9_\-]+-api|gateway|database|auth|payment)\b", line, re.IGNORECASE)
        svc = svc_match.group(1).lower() if svc_match else "system"

        # Cleanup line to form message
        msg = line
        if ts_match:
            msg = msg.replace(ts_match.group(1), "")
        if lvl_match:
            msg = re.sub(r"\b" + re.escape(lvl_match.group(1)) + r"\b", "", msg, flags=re.IGNORECASE)
        
        msg = msg.strip(": \t[]-")

        return {
            "timestamp": ts,
            "service_name": svc,
            "level": lvl,
            "message": msg,
            "status_code": cls.extract_status_code(line),
            "request_id": cls.extract_request_id(line),
            "details": None
        }

    @classmethod
    def parse_csv(cls, file_content: str) -> List[Dict[str, Any]]:
        parsed_events = []
        f = io.StringIO(file_content.strip())
        reader = csv.DictReader(f)
        
        # Check if we have typical columns
        headers = reader.fieldnames or []
        ts_col = next((h for h in headers if h.lower() in ["timestamp", "time", "date", "created_at"]), None)
        svc_col = next((h for h in headers if h.lower() in ["service", "service_name", "app", "component"]), None)
        lvl_col = next((h for h in headers if h.lower() in ["level", "severity", "type"]), None)
        msg_col = next((h for h in headers if h.lower() in ["message", "msg", "log", "text"]), None)
        status_col = next((h for h in headers if h.lower() in ["status", "status_code", "code"]), None)
        req_col = next((h for h in headers if h.lower() in ["request_id", "req_id", "trace_id"]), None)

        for row in reader:
            ts = cls.parse_timestamp(row[ts_col]) if ts_col and row.get(ts_col) else datetime.now()
            svc = row[svc_col] if svc_col and row.get(svc_col) else "unknown-service"
            lvl = cls.normalize_level(row[lvl_col]) if lvl_col and row.get(lvl_col) else "INFO"
            msg = row[msg_col] if msg_col and row.get(msg_col) else str(row)
            status_code = row[status_col] if status_col and row.get(status_col) else None
            req_id = row[req_col] if req_col and row.get(req_col) else None

            if status_code is None:
                status_code = cls.extract_status_code(msg)
            if req_id is None:
                req_id = cls.extract_request_id(msg)

            parsed_events.append({
                "timestamp": ts,
                "service_name": str(svc),
                "level": lvl,
                "message": str(msg),
                "status_code": int(status_code) if status_code and str(status_code).isdigit() else None,
                "request_id": str(req_id) if req_id else None,
                "details": row
            })
        return parsed_events

    @classmethod
    def parse_file(cls, file_content: str, file_name: str) -> List[Dict[str, Any]]:
        name_lower = file_name.lower()
        if name_lower.endswith(".json"):
            # Check if JSON array or JSON-Lines
            content_stripped = file_content.strip()
            if content_stripped.startswith("[") and content_stripped.endswith("]"):
                try:
                    data_list = json.loads(content_stripped)
                    events = []
                    for item in data_list:
                        if isinstance(item, dict):
                            msg = item.get("message") or item.get("msg") or item.get("log") or str(item)
                            lvl = item.get("level") or item.get("severity") or "INFO"
                            svc = item.get("service") or item.get("service_name") or item.get("logger") or "unknown-service"
                            ts_str = item.get("timestamp") or item.get("time") or item.get("date") or datetime.now().isoformat()
                            status_code = item.get("status_code") or item.get("status") or cls.extract_status_code(msg)
                            req_id = item.get("request_id") or item.get("req_id") or item.get("trace_id") or cls.extract_request_id(msg)
                            
                            events.append({
                                "timestamp": cls.parse_timestamp(str(ts_str)),
                                "service_name": str(svc),
                                "level": cls.normalize_level(str(lvl)),
                                "message": str(msg),
                                "status_code": int(status_code) if status_code and str(status_code).isdigit() else None,
                                "request_id": str(req_id) if req_id else None,
                                "details": item
                            })
                    return events
                except json.JSONDecodeError:
                    pass
            
            # Treat as JSON lines
            events = []
            for line in file_content.splitlines():
                parsed = cls.parse_line(line)
                if parsed:
                    events.append(parsed)
            return events

        elif name_lower.endswith(".csv"):
            return cls.parse_csv(file_content)
        
        else: # .log, .txt or fallback
            events = []
            for line in file_content.splitlines():
                parsed = cls.parse_line(line)
                if parsed:
                    events.append(parsed)
            return events
