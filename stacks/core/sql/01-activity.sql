CREATE DATABASE IF NOT EXISTS myscoutee_lab;

CREATE TABLE IF NOT EXISTS myscoutee_lab.activity_events
(
    event_id String,
    occurred_at DateTime64(3, 'UTC'),
    event_key LowCardinality(String),
    actor_id String,
    activity_id String,
    city LowCardinality(String),
    mode LowCardinality(String),
    group_id LowCardinality(String),
    amount UInt32
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(occurred_at)
ORDER BY (occurred_at, event_key, event_id);

CREATE TABLE IF NOT EXISTS myscoutee_lab.activity_queue
(
    event_id String,
    occurred_at DateTime64(3, 'UTC'),
    event_key String,
    actor_id String,
    activity_id String,
    city String,
    mode String,
    group_id String,
    amount UInt32
)
ENGINE = Kafka('kafka:9092', 'myscoutee.activity.v1', 'myscoutee-clickhouse-v1', 'JSONEachRow')
SETTINGS kafka_num_consumers = 3, kafka_thread_per_consumer = 1;

CREATE MATERIALIZED VIEW IF NOT EXISTS myscoutee_lab.activity_ingest
TO myscoutee_lab.activity_events AS
SELECT * FROM myscoutee_lab.activity_queue;
