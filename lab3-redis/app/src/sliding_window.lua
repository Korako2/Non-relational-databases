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