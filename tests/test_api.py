import unittest
from fastapi.testclient import TestClient
from backend.main import app


class TestAPIEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_health_endpoint(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertEqual(json_data["status"], "OK")
        self.assertEqual(json_data["database"], "UP")

    def test_services_endpoint(self):
        response = self.client.get("/api/services")
        self.assertEqual(response.status_code, 200)
        services = response.json()
        self.assertIsInstance(services, list)
        if len(services) > 0:
            # Check basic service shape
            s = services[0]
            self.assertIn("name", s)
            self.assertIn("type", s)
            self.assertIn("status", s)
            self.assertIn("error_rate", s)

    def test_incidents_list_endpoint(self):
        response = self.client.get("/api/incidents")
        self.assertEqual(response.status_code, 200)
        incidents = response.json()
        self.assertIsInstance(incidents, list)

    def test_analytics_endpoint(self):
        response = self.client.get("/api/analytics")
        self.assertEqual(response.status_code, 200)
        summary = response.json()
        self.assertIn("total_services", summary)
        self.assertIn("active_incidents", summary)
        self.assertIn("total_events", summary)
        self.assertIn("system_health_score", summary)
        self.assertIn("severity_distribution", summary)


if __name__ == "__main__":
    unittest.main()
