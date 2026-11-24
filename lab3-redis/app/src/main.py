import os
from time import perf_counter
from typing import Annotated

import redis
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from .limiter import RedisRateLimiter

HTTP_REQUESTS = Counter(
    "http_requests_total", "HTTP requests by route and outcome", ["method", "route", "status"]
)
HTTP_LATENCY = Histogram(
    "http_request_duration_seconds", "HTTP response time", ["method", "route"],
    buckets=(.001, .0025, .005, .01, .025, .05, .1, .25, .5, 1, 2.5, 5),
)
LIMIT_DECISIONS = Counter("rate_limit_decisions_total", "Rate limit decision count", ["decision"])


def create_app(redis_client=None, *, limit=None, window_seconds=None) -> FastAPI:
    if redis_client is None:
        redis_client = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            password=os.getenv("REDIS_PASSWORD") or None,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
            health_check_interval=30,
        )
    configured_limit = int(limit if limit is not None else os.getenv("RATE_LIMIT", "20"))
    configured_window = int(
        window_seconds if window_seconds is not None else os.getenv("RATE_WINDOW_SECONDS", "10")
    )
    limiter = RedisRateLimiter(redis_client, limit=configured_limit, window_seconds=configured_window)
    app = FastAPI(title="Redis Rate Limiter Lab", version="1.0.0")

    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        start = perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            route = getattr(request.scope.get("route"), "path", "unmatched")
            if route != "/metrics":
                HTTP_REQUESTS.labels(request.method, route, str(status_code)).inc()
                HTTP_LATENCY.labels(request.method, route).observe(perf_counter() - start)

    @app.get("/health/live", tags=["health"])
    def live():
        return {"status": "alive"}

    @app.get("/health/ready", tags=["health"])
    def ready():
        try:
            redis_client.ping()
        except redis.RedisError:
            return JSONResponse(status_code=503, content={"status": "redis_unavailable"})
        return {"status": "ready"}

    @app.get("/api/items", tags=["api"])
    def items(client_id: Annotated[str, Header(
        alias="X-Client-ID", min_length=1, max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$"
    )]):
        try:
            decision = limiter.check(client_id)
        except redis.RedisError:
            raise HTTPException(status_code=503, detail="Rate limiter unavailable") from None
        headers = {
            "X-RateLimit-Limit": str(limiter.limit),
            "X-RateLimit-Remaining": str(decision.remaining),
            "X-RateLimit-Reset": str(decision.reset_after_seconds),
        }
        if not decision.allowed:
            LIMIT_DECISIONS.labels("blocked").inc()
            headers["Retry-After"] = str(decision.reset_after_seconds)
            return JSONResponse(
                status_code=429,
                headers=headers,
                content={"detail": "Too Many Requests"},
            )
        LIMIT_DECISIONS.labels("allowed").inc()
        return JSONResponse(
            status_code=200,
            headers=headers,
            content={"items": [{"id": 1, "name": "book"}, {"id": 2, "name": "keyboard"}]},
        )

    @app.get("/metrics", include_in_schema=False)
    def metrics():
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
