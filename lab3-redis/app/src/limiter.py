from dataclasses import dataclass
from hashlib import sha256
from time import perf_counter
from uuid import uuid4

from prometheus_client import Histogram


REDIS_OPERATION_SECONDS = Histogram(
    "redis_rate_limit_seconds",
    "Time spent on the atomic Redis rate limit operation",
    buckets=(.0005, .001, .0025, .005, .01, .025, .05, .1, .25, .5, 1, 2.5),
)

SLIDING_WINDOW_LUA = r"""
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local member = ARGV[3]

local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
local cutoff = now - window
redis.call('ZREMRANGEBYSCORE', key, '-inf', cutoff)
local count = redis.call('ZCARD', key)

if count < limit then
    redis.call('ZADD', key, now, member)
    redis.call('PEXPIRE', key, window)
    count = count + 1
    local first = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local reset = math.max(0, math.ceil((tonumber(first[2]) + window - now) / 1000))
    return {1, limit - count, reset}
end

local first = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
local retry = math.max(1, math.ceil((tonumber(first[2]) + window - now) / 1000))
return {0, 0, retry}
"""


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
