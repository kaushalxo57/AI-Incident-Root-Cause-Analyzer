import unittest
from datetime import datetime, timedelta
from backend.services.anomaly_detector import AnomalyDetector
from backend.services.root_cause import RootCauseAnalyzer


class TestAnalysisServices(unittest.TestCase):
    def test_anomaly_detection_basic(self):
        # Create baseline log events for a service (quiet traffic, then a sudden error burst)
        base_time = datetime.now()
        events = []
        
        # 10 minutes of quiet background logs (1 log per minute)
        for i in range(10):
            events.append({
                "timestamp": base_time + timedelta(minutes=i),
                "service_name": "payment-api",
                "level": "INFO",
                "message": "Transaction query successful",
                "status_code": 200,
                "request_id": f"req-{i}"
            })
            
        # At minute 11, a massive spike of errors
        for j in range(8):
            events.append({
                "timestamp": base_time + timedelta(minutes=11),
                "service_name": "payment-api",
                "level": "ERROR",
                "message": "Stripe timeout connector failed",
                "status_code": 504,
                "request_id": f"req-err-{j}"
            })

        detector = AnomalyDetector(threshold_z=1.5, window_minutes=1)
        anomalies = detector.detect_anomalies(events)
        
        # We should find at least one anomaly corresponding to the spike at minute 11
        self.assertTrue(len(anomalies) > 0)
        
        anomaly = next(a for a in anomalies if a["service_name"] == "payment-api")
        self.assertIn("payment-api", [a["service_name"] for a in anomalies])
        self.assertTrue(any("Error" in r or "5xx" in r or "spike" in r for r in anomaly["reasons"]))

    def test_root_cause_heuristics(self):
        base_time = datetime.now()
        
        # We simulate anomalies in database (earlier) and payment-api/gateway-service (later)
        anomalies = [
            {
                "timestamp": base_time,
                "service_name": "database",
                "reasons": ["Connection pool exhaustion warning"],
                "confidence": 0.85,
                "sample_messages": ["Active connection slots reservation warning"]
            },
            {
                "timestamp": base_time + timedelta(minutes=2),
                "service_name": "payment-api",
                "reasons": ["Error count spike (Z-Score: 3.42)"],
                "confidence": 0.90,
                "sample_messages": ["Database timeout occurred"]
            },
            {
                "timestamp": base_time + timedelta(minutes=3),
                "service_name": "gateway-service",
                "reasons": ["HTTP 5xx responses detected"],
                "confidence": 0.92,
                "sample_messages": ["Checkout API failed due to payment-api unavailable"]
            }
        ]

        log_events = [
            {"service_name": "database", "level": "CRITICAL", "message": "FATAL: remaining connection slots are reserved"},
            {"service_name": "payment-api", "level": "ERROR", "message": "Database timeout occurred"},
            {"service_name": "gateway-service", "level": "ERROR", "message": "HTTP 500: checkout failure"}
        ]

        rc_analysis = RootCauseAnalyzer.analyze_root_cause(anomalies, log_events)
        
        self.assertEqual(rc_analysis["likely_root_cause"], "database")
        self.assertTrue(rc_analysis["confidence"] > 0.8)
        self.assertEqual(len(rc_analysis["evidence"]), 3)
        self.assertTrue(any(ev["is_root_cause_indicator"] for ev in rc_analysis["evidence"] if ev["service_name"] == "database"))


if __name__ == "__main__":
    unittest.main()
