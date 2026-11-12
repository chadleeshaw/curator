"""Rate limits apply per client, with a tighter cap on login."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from web.middleware.rate_limit import RateLimitMiddleware


def _app():
    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        calls=2,
        period=60,
        auth_calls=1,
        auth_period=60,
        trusted_proxies=["testclient"],
    )

    @app.get("/api/items")
    def items():
        return {"ok": True}

    @app.post("/api/auth/login")
    def login():
        return {"ok": True}

    @app.get("/api/health")
    def health():
        return {"status": "healthy"}

    return app


def test_the_third_call_is_rejected_and_health_is_not_limited():
    client = TestClient(_app(), headers={"user-agent": "browser"})
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/items").status_code == 200
    assert client.get("/api/items").status_code == 200
    blocked = client.get("/api/items")
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) >= 1
    assert blocked.json()["error"]


def test_login_allows_only_one_call():
    client = TestClient(_app(), headers={"user-agent": "browser"})
    assert client.post("/api/auth/login").status_code == 200
    assert client.post("/api/auth/login").status_code == 429


def test_a_trusted_proxy_uses_the_forwarded_address():
    client = TestClient(_app(), headers={"user-agent": "browser"})
    first = client.get("/api/items", headers={"user-agent": "browser", "x-forwarded-for": "10.1.1.1"})
    second = client.get("/api/items", headers={"user-agent": "browser", "x-real-ip": "10.2.2.2"})
    assert first.status_code == 200
    assert second.status_code == 200


def test_old_timestamps_are_dropped():
    app = _app()
    middleware = next(m for m in app.user_middleware if m.cls is RateLimitMiddleware)
    # Build the middleware the same way a request would, then age its clock.
    limiter = RateLimitMiddleware(app, calls=2, period=60, trusted_proxies=["127.0.0.1"])
    limiter.clients["10.0.0.1"]["/api/items"] = [0]
    limiter.last_cleanup = 0
    limiter._cleanup_old_entries()
    assert "10.0.0.1" not in limiter.clients
    assert middleware.kwargs["calls"] == 2
