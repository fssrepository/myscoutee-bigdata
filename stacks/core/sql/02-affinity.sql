CREATE TABLE IF NOT EXISTS myscoutee_lab.affinity_rollups
(
    window_start DateTime('UTC'),
    group_id LowCardinality(String),
    target_type LowCardinality(String),
    pending UInt64,
    running UInt64,
    done UInt64,
    failed UInt64,
    queue_wait_total_ms UInt64,
    runtime_total_ms UInt64,
    ingested_at DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(ingested_at)
ORDER BY (window_start, group_id, target_type);

CREATE TABLE IF NOT EXISTS myscoutee_lab.affinity_rollup_queue
(
    window_start DateTime('UTC'),
    group_id String,
    target_type String,
    pending UInt64,
    running UInt64,
    done UInt64,
    failed UInt64,
    queue_wait_total_ms UInt64,
    runtime_total_ms UInt64
)
ENGINE = Kafka('kafka:9092', 'myscoutee.affinity.rollups.v1', 'myscoutee-clickhouse-affinity-v1', 'JSONEachRow');

CREATE MATERIALIZED VIEW IF NOT EXISTS myscoutee_lab.affinity_rollup_ingest
TO myscoutee_lab.affinity_rollups AS
SELECT * FROM myscoutee_lab.affinity_rollup_queue;
