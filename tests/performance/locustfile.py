"""
Locust Load Testing Configuration

Tests how the Curator application handles concurrent users.

Run with:
  # CLI mode (headless) - 20 users, 2 per second spawn rate, 60 second test
  locust -f tests/performance/locustfile.py --headless -u 20 -r 2 -t 60s --host http://localhost:8000

  # Web UI mode (interactive dashboard)
  locust -f tests/performance/locustfile.py --host http://localhost:8000
  # Then open http://localhost:8089 in your browser

  # Distributed mode for heavy load testing
  locust -f tests/performance/locustfile.py --master --host http://localhost:8000
  locust -f tests/performance/locustfile.py --worker --master-host=localhost

Performance targets:
  - 95th percentile response time < 500ms for reads
  - 95th percentile response time < 1000ms for writes
  - Support 50 concurrent users with <5% failure rate
  - Throughput > 100 req/sec under normal load
"""

import logging
from typing import Dict, Optional

from locust import HttpUser, between, events, task

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CuratorUser(HttpUser):
    """
    Simulates a user interacting with the Curator application.

    Task weights determine how often each task is executed:
    - Higher weight = more frequent execution
    - Weights are relative (task with weight 3 runs 3x more than weight 1)
    """

    # Wait between 1-3 seconds between tasks (simulates user reading/thinking)
    wait_time = between(1, 3)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.token: Optional[str] = None
        self.headers: Dict[str, str] = {}

    def on_start(self):
        """
        Called when a simulated user starts.
        Attempts to login and get an auth token.
        """
        try:
            response = self.client.post("/api/login", json={"username": "admin", "password": "admin"}, name="Login")

            if response.status_code == 200:
                data = response.json()
                self.token = data.get("access_token")
                self.headers = {"Authorization": f"Bearer {self.token}"}
                logger.info("Successfully authenticated user")
            else:
                logger.warning(f"Login failed with status {response.status_code}")
                self.headers = {}
                self.token = None
        except Exception as e:
            logger.error(f"Login error: {e}")
            self.headers = {}
            self.token = None

    @task(5)
    def view_library(self):
        """
        Most common operation - viewing the library of periodicals.
        Weight: 5 (very frequent)
        """
        self.client.get("/api/periodicals", headers=self.headers, name="View Library")

    @task(3)
    def view_library_paginated(self):
        """
        View library with pagination (realistic usage pattern).
        Weight: 3 (frequent)
        """
        self.client.get("/api/periodicals?skip=0&limit=20", headers=self.headers, name="View Library (Paginated)")

    @task(2)
    def view_tracking(self):
        """
        View tracked periodicals.
        Weight: 2 (common)
        """
        self.client.get("/api/periodicals/tracking", headers=self.headers, name="View Tracking")

    @task(2)
    def check_ocr_queue(self):
        """
        Check OCR processing queue status.
        Weight: 2 (common)
        """
        self.client.get("/api/queue/stats", headers=self.headers, name="OCR Queue Stats")

    @task(1)
    def check_tasks_status(self):
        """
        Check background tasks status.
        Weight: 1 (occasional)
        """
        self.client.get("/api/tasks/status", headers=self.headers, name="Tasks Status")

    @task(1)
    def search_periodicals(self):
        """
        Search for periodicals (heavier operation).
        Weight: 1 (occasional)
        """
        self.client.get(
            "/api/search/periodicals?q=national+geographic", headers=self.headers, name="Search Periodicals"
        )

    @task(1)
    def view_version(self):
        """
        View API version (lightweight public endpoint).
        Weight: 1 (occasional)
        """
        self.client.get("/api/version", name="Get Version")


class AdminUser(HttpUser):
    """
    Simulates an admin user performing administrative tasks.
    These operations are typically heavier and less frequent.
    """

    wait_time = between(3, 8)  # Admins wait longer between actions

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.token: Optional[str] = None
        self.headers: Dict[str, str] = {}

    def on_start(self):
        """Login as admin"""
        try:
            response = self.client.post("/api/login", json={"username": "admin", "password": "admin"})
            if response.status_code == 200:
                self.token = response.json().get("access_token")
                self.headers = {"Authorization": f"Bearer {self.token}"}
            else:
                self.headers = {}
        except Exception:
            self.headers = {}

    @task(3)
    def view_all_tracking(self):
        """View all tracking entries"""
        self.client.get("/api/periodicals/tracking", headers=self.headers, name="Admin: View All Tracking")

    @task(2)
    def view_ocr_queue(self):
        """View full OCR queue"""
        self.client.get("/api/queue", headers=self.headers, name="Admin: View OCR Queue")

    @task(1)
    def check_all_tasks(self):
        """Check all background tasks"""
        self.client.get("/api/tasks/status", headers=self.headers, name="Admin: Check Tasks")


# Event handlers for custom metrics and logging
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when the test starts"""
    logger.info("🚀 Starting Curator load test...")
    logger.info(f"Target host: {environment.host}")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when the test stops"""
    logger.info("✅ Load test completed")

    # Log summary statistics
    stats = environment.stats
    logger.info(f"Total requests: {stats.total.num_requests}")
    logger.info(f"Total failures: {stats.total.num_failures}")
    logger.info(f"Average response time: {stats.total.avg_response_time:.2f}ms")
    logger.info(f"Max response time: {stats.total.max_response_time:.2f}ms")
    logger.info(f"RPS: {stats.total.total_rps:.2f}")


@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, **kwargs):
    """
    Log slow requests for investigation.
    Customize the threshold as needed.
    """
    if response_time > 1000:  # Log requests slower than 1 second
        logger.warning(f"⚠️  Slow request: {name} took {response_time:.2f}ms")


if __name__ == "__main__":
    print(
        """
    Locust Load Testing for Curator
    ================================

    Quick start commands:

    1. CLI mode (automated test):
       locust -f tests/performance/locustfile.py --headless -u 20 -r 2 -t 60s --host http://localhost:8000

    2. Web UI mode (interactive):
       locust -f tests/performance/locustfile.py --host http://localhost:8000
       Then open: http://localhost:8089

    3. High load test:
       locust -f tests/performance/locustfile.py --headless -u 100 -r 10 -t 120s --host http://localhost:8000

    Make sure the Curator app is running on http://localhost:8000 before starting!
    """
    )
