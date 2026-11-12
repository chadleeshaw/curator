"""Container health check.

Exit 0 only when /api/health returns a 2xx response. A 503 from an
unhealthy database must fail the check.
"""

import sys

import requests


def main(url: str = "http://localhost:8000/api/health") -> int:
    """Return 0 when the health endpoint responds with a 2xx status."""
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
    except requests.RequestException:
        return 1
    return 0


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/api/health"
    sys.exit(main(target))
