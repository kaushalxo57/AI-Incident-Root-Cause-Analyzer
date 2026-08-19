import unittest
from datetime import datetime
from backend.services.parser import LogParser


class TestLogParser(unittest.TestCase):
    def test_parse_bracket_line(self):
        line = "[2026-08-19 10:14:00] [payment-api] [ERROR] [req-abc123] Database timeout occurred."
        parsed = LogParser.parse_line(line)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["service_name"], "payment-api")
        self.assertEqual(parsed["level"], "ERROR")
        self.assertEqual(parsed["message"], "Database timeout occurred.")
        self.assertEqual(parsed["request_id"], "req-abc123")
        self.assertIsInstance(parsed["timestamp"], datetime)
        self.assertEqual(parsed["timestamp"].hour, 10)
        self.assertEqual(parsed["timestamp"].minute, 14)

    def test_parse_json_line(self):
        line = '{"timestamp": "2026-08-19T10:14:00Z", "service": "auth-service", "level": "warn", "message": "Failed login attempt", "status_code": 401}'
        parsed = LogParser.parse_line(line)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["service_name"], "auth-service")
        self.assertEqual(parsed["level"], "WARNING")
        self.assertEqual(parsed["message"], "Failed login attempt")
        self.assertEqual(parsed["status_code"], 401)

    def test_extract_status_code(self):
        self.assertEqual(LogParser.extract_status_code("Checkout request failed with status code 500"), 500)
        self.assertEqual(LogParser.extract_status_code("User received 404 Not Found response"), 404)
        self.assertIsNone(LogParser.extract_status_code("Regular connection timeout alert"))

    def test_extract_request_id(self):
        # UUID detection
        self.assertEqual(LogParser.extract_request_id("Error trace req_id=e36a445d-7521-4f3e-8c3b-2877a9442a8b in component"), "e36a445d-7521-4f3e-8c3b-2877a9442a8b")
        # key value detection
        self.assertEqual(LogParser.extract_request_id("Error trace request_id=req-9901 in component"), "req-9901")


if __name__ == "__main__":
    unittest.main()
