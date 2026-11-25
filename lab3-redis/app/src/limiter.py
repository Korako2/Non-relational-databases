from dataclasses import dataclass
from hashlib import sha256
from time import perf_counter
from uuid import uuid4
from pathlib import Path

from prometheus_client import Histogram


REDIS_OPERATION_SECONDS = Histogram(
    "redis_rate_limit_seconds",
    "Time spent on the atomic Redis rate limit operation",
    buckets=(.0005, .001, .0025, .005, .01, .025, .05, .1, .25, .5, 1, 2.5),
)

SLIDING_WINDOW_LUA = (
    Path(__file__).with_name("sliding_window.lua")
    .read_text(encoding="utf-8")
)

@dataclass(frozen=True)
class Decision:
    allowed: bool
    remaining: int
    reset_after_seconds: int


class RedisRateLimiter:
    def __init__(self, redis_client, *, limit: int = 20, window_seconds: int = 10):
        if limit < 1 or window_seconds < 1:
            raise ValueError("limit and window_seconds must be positive")
        self.limit = limit
        self.window_seconds = window_seconds
        self._script = redis_client.register_script(SLIDING_WINDOW_LUA)

    def check(self, client_id: str) -> Decision:
        key = f"rl:items:{sha256(client_id.encode('utf-8')).hexdigest()}"
        start = perf_counter()
        try:
            allowed, remaining, reset = self._script(
                keys=[key],
                args=[self.limit, self.window_seconds * 1000, uuid4().hex],
            )
        finally:
            REDIS_OPERATION_SECONDS.observe(perf_counter() - start)
        return Decision(bool(allowed), int(remaining), int(reset))
