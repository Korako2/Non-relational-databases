CREATE DATABASE IF NOT EXISTS lab4;

CREATE TABLE IF NOT EXISTS lab4.requests
(
    timestamp DateTime('UTC'),
    service LowCardinality(String),
    endpoint LowCardinality(String),
    method LowCardinality(String),
    status_code UInt16,
    duration_ms UInt32
)
ENGINE = MergeTree()
PARTITION BY toDate(timestamp)
ORDER BY (timestamp, service)
TTL timestamp + INTERVAL 14 DAY DELETE;
