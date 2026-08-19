from datetime import datetime
from typing import List, Dict, Any, Tuple


class RootCauseAnalyzer:
    INFRA_KEYWORDS = [
        "db", "database", "postgres", "sql", "redis", "cache", 
        "auth", "identity", "broker", "queue", "rabbitmq", "kafka", 
        "network", "dns", "storage", "s3"
    ]

    @classmethod
    def is_infra_service(cls, service_name: str) -> bool:
        name_lower = service_name.lower()
        return any(kw in name_lower for kw in cls.INFRA_KEYWORDS)

    @classmethod
    def analyze_root_cause(cls, anomalies: List[Dict[str, Any]], log_events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Heuristic root cause analyzer that scores services based on chronology, 
        infrastructure flags, and propagation.
        Returns:
            {
                "likely_root_cause": str,
                "confidence": float,
                "summary": str,
                "evidence": List[Dict[str, Any]]
            }
        """
        if not anomalies:
            return {
                "likely_root_cause": "Unknown",
                "confidence": 0.0,
                "summary": "No anomalies detected to evaluate root cause.",
                "evidence": []
            }

        # 1. Sort anomalies chronologically
        sorted_anomalies = sorted(anomalies, key=lambda a: a["timestamp"])
        first_anomaly = sorted_anomalies[0]
        
        # 2. Track service timelines
        service_first_seen: Dict[str, datetime] = {}
        for anomaly in sorted_anomalies:
            svc = anomaly["service_name"]
            ts = anomaly["timestamp"]
            if svc not in service_first_seen:
                service_first_seen[svc] = ts

        # 3. Score services
        scores: Dict[str, float] = {}
        all_services = list(service_first_seen.keys())

        for svc in all_services:
            score = 0.0
            first_ts = service_first_seen[svc]

            # Rule 1: Chronological priority (Earliest anomaly)
            if first_ts == first_anomaly["timestamp"]:
                score += 40.0
            else:
                # Add fractional points if it's very close to the start (within 60 seconds)
                time_diff = (first_ts - first_anomaly["timestamp"]).total_seconds()
                if time_diff <= 60:
                    score += 25.0
                elif time_diff <= 180:
                    score += 10.0

            # Rule 2: Infrastructure vs Application Layer
            if cls.is_infra_service(svc):
                score += 30.0

            # Rule 3: Propagation degree (Number of services failing after this one)
            subsequent_services = 0
            for other_svc in all_services:
                if other_svc == svc:
                    continue
                if service_first_seen[other_svc] > first_ts:
                    subsequent_services += 1
            score += subsequent_services * 15.0

            # Rule 4: Severity boost from original logs
            svc_logs = [l for l in log_events if l["service_name"] == svc]
            has_critical = any(l["level"] == "CRITICAL" for l in svc_logs)
            has_db_error = any("database" in l["message"].lower() or "connection" in l["message"].lower() for l in svc_logs)
            
            if has_critical:
                score += 15.0
            if has_db_error:
                score += 10.0

            scores[svc] = score

        # 4. Identify winner
        likely_root_cause = max(scores, key=scores.get)
        max_score = scores[likely_root_cause]

        # Calculate confidence (normalize score to 0.0 - 1.0 range, capping at 0.98 for humility)
        confidence = min(0.98, max(0.30, max_score / 110.0))

        # 5. Extract chronological evidence chain
        evidence = []
        for anomaly in sorted_anomalies:
            svc = anomaly["service_name"]
            ts = anomaly["timestamp"]
            is_root = (svc == likely_root_cause)
            
            # Determine level
            level = "WARNING"
            reasons_str = "".join(anomaly["reasons"]).lower()
            if "critical" in reasons_str:
                level = "CRITICAL"
            elif "error" in reasons_str or "5xx" in reasons_str:
                level = "ERROR"

            evidence.append({
                "timestamp": ts.isoformat() if isinstance(ts, datetime) else str(ts),
                "service_name": svc,
                "level": level,
                "reasons": anomaly["reasons"],
                "confidence": anomaly["confidence"],
                "is_root_cause_indicator": is_root,
                "message": f"Service [{svc}] flagged anomaly: {', '.join(anomaly['reasons'])}. Sample: \"{anomaly['sample_messages'][0] if anomaly['sample_messages'] else ''}\""
            })

        # 6. Narrative summary
        affected_count = len(all_services)
        affected_list = ", ".join([f"`{s}`" for s in all_services])
        
        if likely_root_cause == first_anomaly["service_name"]:
            summary = (
                f"Incident began directly in the `{likely_root_cause}` service at "
                f"{first_anomaly['timestamp'].strftime('%H:%M:%S')}. "
                f"Errors subsequently propagated to {affected_count - 1} other services: {affected_list}."
            )
        else:
            summary = (
                f"Incident likely originated in the infrastructure layer `{likely_root_cause}`. "
                f"Although `{first_anomaly['service_name']}` experienced the first symptom, "
                f"upstream analysis points to `{likely_root_cause}` as the primary source of failure."
            )

        return {
            "likely_root_cause": likely_root_cause,
            "confidence": round(confidence, 2),
            "summary": summary,
            "evidence": evidence
        }
