SET 'pipeline.name' = 'myscoutee-affinity-recompute-rollups';
SET 'execution.runtime-mode' = 'streaming';
SET 'execution.checkpointing.interval' = '10s';

CREATE TABLE affinity_tasks (
    task_id STRING,
    group_id STRING,
    target_type STRING,
    status STRING,
    queue_wait_ms BIGINT,
    runtime_ms BIGINT,
    processing_time AS PROCTIME()
) WITH (
    'connector' = 'kafka',
    'topic' = 'myscoutee.affinity.tasks.v1',
    'properties.bootstrap.servers' = 'kafka:9092',
    'properties.group.id' = 'myscoutee-flink-affinity-v1',
    'scan.startup.mode' = 'earliest-offset',
    'format' = 'json'
);

CREATE TABLE affinity_rollups (
    window_start STRING,
    group_id STRING,
    target_type STRING,
    `pending` BIGINT,
    `running` BIGINT,
    `done` BIGINT,
    `failed` BIGINT,
    queue_wait_total_ms BIGINT,
    runtime_total_ms BIGINT
) WITH (
    'connector' = 'kafka',
    'topic' = 'myscoutee.affinity.rollups.v1',
    'properties.bootstrap.servers' = 'kafka:9092',
    'format' = 'json',
    'sink.delivery-guarantee' = 'at-least-once'
);

INSERT INTO affinity_rollups
SELECT
    DATE_FORMAT(window_start, 'yyyy-MM-dd HH:mm:ss'),
    group_id,
    target_type,
    CAST(SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS BIGINT),
    CAST(SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) AS BIGINT),
    CAST(SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) AS BIGINT),
    CAST(SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS BIGINT),
    CAST(SUM(CASE WHEN status = 'running' THEN queue_wait_ms ELSE 0 END) AS BIGINT),
    CAST(SUM(CASE WHEN status IN ('done', 'failed') THEN runtime_ms ELSE 0 END) AS BIGINT)
FROM TABLE(TUMBLE(TABLE affinity_tasks, DESCRIPTOR(processing_time), INTERVAL '10' SECOND))
GROUP BY window_start, window_end, group_id, target_type;
