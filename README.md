# MyScoutee Big Data lab

A Dockerized, isolated learning lab for analyzing MyScoutee-shaped events. The
generators produce **synthetic data only**. The lab does not connect to the
current MyScoutee backend, Redis, or MongoDB, and it does not affect product
statistics.

## Why these use cases?

MyScoutee has profile lifecycle and event membership telemetry signals
(`profile.registered`, `profile.onboarding`, `event.created`,
`event.member.joined`, `event.member.removed`). Events also have `Casual` and
`Mingle` modes. With many users, events, and long time windows, city/mode
trends and registration -> onboarding -> participation cohorts become useful
data pipeline questions. At the small scale of this local sample, the Big Data
stack is a learning tool; it does not by itself justify a production cluster.

```text
synthetic activity generator -> Kafka (myscoutee.activity.v1)
                                   |-> ClickHouse Kafka Engine -> raw table -> dashboard
                                   +-> Spark batch -> Parquet partitions -> SeaweedFS S3 lake

synthetic affinity task generator -> Kafka (myscoutee.affinity.tasks.v1)
                                   -> Flink, 10-second windows
                                   -> Kafka (myscoutee.affinity.rollups.v1)
                                   -> ClickHouse -> same dashboard

optional schema exercise -> Schema Registry + Avro
                         -> Kafka (myscoutee.activity.avro.v1) -> Avro reader
```

| Component | Role | What to learn |
| --- | --- | --- |
| Kafka, one KRaft broker | Replayable event stream | Topics, partitions, consumer offsets |
| Schema Registry + Avro, optional | Versioned event contract and compact binary records | Compatibility checks, schema IDs, writer/reader schemas |
| ClickHouse | Fast column-oriented queries | Kafka Engine, materialized views, SQL |
| Spark, on demand | Historical batch processing | DataFrames, aggregation, Parquet |
| SeaweedFS mini | Local S3-compatible data lake | Object storage, partitions, readback |
| Flink, on demand | Continuous affinity task stream analysis | Checkpoints, windows, state, Kafka sink |
| Local dashboard | Read the results | Metrics and breakdowns |

The [branded English guide](guides/publication/manuals/MyScoutee_Big_Data_Lab_Guide_EN.pdf)
reviews all 12 technologies from the original learning list, maps them to
MyScoutee use cases, and explains integration and possible replacement
decisions. All Compose projects now live in `stacks/`: the
Kafka/ClickHouse/Spark/Flink core is in `stacks/core/` and is controlled by
`./lab.sh`. Independent projects for Hadoop/HDFS/YARN/MapReduce, Hive, HBase,
Cassandra, Airflow and NiFi are controlled by `./stations.sh`; see the
[station guide](stacks/README.md) for commands, expected results and UIs.
Spark's Hadoop S3A dependency is a client library, not the Hadoop station.
The Elastic search and observability lab lives in a separate repository.

Repository layout: `stacks/core/` owns the shared streaming and batch Compose
project and its Docker build contexts, while each other directory in `stacks/`
owns one isolated technology. The root `producer/` supplies synthetic data to
both kinds of lab; `build/` contains generated outputs and is ignored by Git.
The root launchers keep all commands relative to the repository root.

Start one station at a time on this 15 GiB RAM host. The stations use the same
deterministic synthetic activity and affinity fixture, so their results can be
compared without connecting to the product backend. Stop each station with
`./stations.sh STATION down`; this preserves its data volume. The core lab is
also stopped by default.

## Getting started

Requirements: Docker, Docker Compose, and several GB of free disk space. The
lab runs in its own `myscoutee-bigdata` Compose project. The first run pulls
images and Spark packages. The Hadoop S3 connector has a large AWS SDK
dependency, so the first `batch` run can take several minutes.

```sh
./lab.sh up
./lab.sh seed --users 5000 --days 30 --seed 42
./lab.sh status
./lab.sh topics
./lab.sh groups
```

Dashboard: <http://127.0.0.1:8094>. ClickHouse HTTP: `127.0.0.1:8126`, user
`lab`, password `lab-only`; these credentials are for local development only.
The dashboard refreshes automatically. ClickHouse consumes Kafka
asynchronously, so data may take a few seconds to appear after `seed`.

Run a historical scan from the beginning of the retained Kafka data to the
latest offsets visible when the job starts. Spark writes partitioned Parquet
to the SeaweedFS `myscoutee-lake` bucket, reads it back, and prints the
aggregate row count:

```sh
./lab.sh batch
./lab.sh query "SELECT event_key, count() FROM activity_events GROUP BY event_key ORDER BY count() DESC"
./lab.sh down
```

The local S3 endpoint is `http://127.0.0.1:8333`. Its lab-only credentials are
`lab` / `lab-only-secret`. For example, with the AWS CLI installed:

```sh
AWS_ACCESS_KEY_ID=lab AWS_SECRET_ACCESS_KEY=lab-only-secret \
  aws --endpoint-url http://127.0.0.1:8333 s3 ls s3://myscoutee-lake/daily_activity/ --recursive
```

## Kafka first look

The core contains one KRaft broker and three synthetic-data topics. Kafka has
no web UI or host-published broker port in this lab; use its CLI inside Docker.
The dashboard at <http://127.0.0.1:8094> shows ClickHouse results after it
consumes Kafka records. For a small, repeatable exercise:

```sh
./lab.sh up
./lab.sh topics
./lab.sh seed --users 120 --days 30 --seed 42
./lab.sh query 'SELECT count() FROM activity_events'
docker compose -f stacks/core/compose.yaml exec -T kafka \
  /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server kafka:9092 \
  --describe --group myscoutee-clickhouse-v1
```

The seed adds 306 synthetic activity events. The table count may already be
nonzero because `down` preserves volumes. In the group output, compare each
partition's `CURRENT-OFFSET` and `LOG-END-OFFSET`; `LAG` becomes zero after
ClickHouse catches up. The producer keys records by `actor_id`, preserving
per-actor order within one partition, not a global order across the topic.
The English guide has the full Kafka terminology, topic inspection and
single-record commands. Kafka is a retained transport for a possible approved
backend event export; the lab does not read product data.

### Optional Avro and Schema Registry exercise

The main activity and affinity streams still carry JSON. Run this separate
exercise with only the broker and Schema Registry; it does not require
ClickHouse, Spark, Flink, or a product backend connection:

```sh
./lab.sh schema-demo
curl -s http://127.0.0.1:8085/subjects/myscoutee.activity.avro.v1-value/versions
./lab.sh down
```

The demo registers `producer/schemas/activity-v1.avsc`, adds a nullable
`source` field with a default in v2, and checks that changing `event_id` from
string to long is incompatible. It publishes one synthetic record per accepted
version to `myscoutee.activity.avro.v1`, then reads both with the v2 reader
schema. Schema Registry stores subject versions and compatibility policy;
Avro encodes the values. The five-byte Confluent framing carries a magic byte
and schema ID, so the reader can fetch the writer schema. The registry is
available on local port 8085 for inspection. Repeating the command reuses the
registered schema versions and appends two new records.

An `.avsc` file is JSON describing a record, not an event payload. In v2,
`type: record` groups named fields under `myscoutee.lab.ActivitySignal`;
`event_id`, `occurred_at`, `event_key`, `group_id`, `city`, and `mode` are
strings. `source` has type `["null", "string"]` and `default: null`: a v2
reader supplies null when decoding an older v1 record without that field.
Avro gives serializers a typed contract and compact binary values, while the
registry checks how that contract changes. The PDF shows the full v2 schema
and explains each part and its limits.

This is an isolated contract lesson. A future backend-owned, post-commit
export of approved `event.member.joined` facts could use this pattern to keep
analytics consumers compatible as optional fields are added. Product state,
authorization, and retention would remain backend-owned. The existing JSON
ClickHouse/Spark/Flink paths do not consume this Avro topic.

The guide also explains that Kafka **uses brokers**. Its ordinary consumer
groups read a retained, partitioned log, while a conventional work queue
distributes jobs and acknowledges individual deliveries. These are processing
models rather than exclusive product categories: RabbitMQ also has replayable
streams. Pages 32-34 cover partition ownership, rebalances, independent group
offsets, replay, duplicate handling and a proposed MyScoutee integration. A
backend-owned outbox could export approved participation or affinity task-state
facts to separate analytics consumers. The existing Mongo task worker, affinity
calculation and Redis admin telemetry remain the product owners; no such export
is connected in this lab.

To see consumer lag, finish the first look above and stop only the downstream
services, then publish a tiny second batch:

```sh
docker compose -f stacks/core/compose.yaml stop dashboard clickhouse lake
./lab.sh seed --users 1 --days 1 --seed 42
docker compose -f stacks/core/compose.yaml exec -T kafka \
  /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server kafka:9092 \
  --describe --group myscoutee-clickhouse-v1
```

This seed adds three records for the default seed value. The stopped
ClickHouse group retains its committed offsets while the topic log ends move
forward; the observed lag was 2 on one partition and 1 on another. Leave
Kafka running to inspect the records with the console consumer. Starting
ClickHouse later lets it resume from its saved group offsets.

## ClickHouse first look

With Kafka still running after the lag exercise, start only the analytical
database and its read-only dashboard; SeaweedFS, Spark, and Flink can remain off:

```sh
docker compose -f stacks/core/compose.yaml up -d clickhouse dashboard
./lab.sh query 'SELECT count(), uniqExact(event_id) FROM activity_events'
./lab.sh query "SELECT name, engine FROM system.tables WHERE database='myscoutee_lab' ORDER BY name"
./lab.sh query "SELECT event_key, count() FROM activity_events GROUP BY event_key ORDER BY count() DESC"
```

Open <http://127.0.0.1:8094>. The `activity_queue` Kafka Engine table reads
the topic, `activity_ingest` is the insert-time materialized view, and the
`activity_events` MergeTree table holds the queryable copy. On the documented
visit, restarting ClickHouse consumed the three pending records: the table
rose from 1006 to 1009 rows and group lag returned to zero. Your counts may
differ with retained volumes. The dashboard shows distinct actor and event
counts, city/mode breakdowns, and a trailing 30-day chart. Its affinity panel
may show retained data from an earlier Flink run even when Flink is stopped.
The English guide covers the data path, storage terms, each panel's meaning,
columnar storage, technology comparisons, and MyScoutee adoption limits on
pages 35-38.

## Spark and SeaweedFS first look

Stop the dashboard and ClickHouse to leave memory for the batch job. Keep Kafka
running; `batch` starts the lake if needed and removes its temporary Spark
container when the run finishes:

```sh
docker compose -f stacks/core/compose.yaml stop dashboard clickhouse
./lab.sh batch
./lab.sh history-up
printf 's3.bucket.list\nfs.ls /buckets/myscoutee-lake/daily_activity\n' | \
  docker compose -f stacks/core/compose.yaml exec -T lake \
  weed shell -filer localhost:8888
```

On the documented visit Spark wrote and read back 259 grouped rows from 1009
retained Kafka activity records. The object listing shows `day=...` prefixes,
Snappy-compressed Parquet parts, and `_SUCCESS`. This is a fresh bounded Kafka
read every time; the job deduplicates by `event_id` and **overwrites** the
`daily_activity` output, so it does not keep earlier snapshots. The SeaweedFS
shell reads internal filer metadata; the published `127.0.0.1:8333` endpoint
is S3-compatible API access. Open the [Spark History Server](http://127.0.0.1:18080/)
after `history-up`, select **MyScoutee activity history**, then inspect **Jobs**
(actions and duration), **Stages** (parallel tasks, shuffle and skew), **SQL**
(query plans), and **Executors** (task, memory and I/O metrics). The batch logs
Spark events in ignored `build/spark-events/`; existing runs from before this
change have no history. The active Spark UI at port 4040 exists only while the
temporary batch container runs. Stop the history server with `./lab.sh history-down`
to free its memory; the event logs remain.

Open the [SeaweedFS Filer UI](http://127.0.0.1:8888/buckets/myscoutee-lake/daily_activity/)
to browse the `day=...` prefixes and Parquet objects. This UI is a filer/object
browser, not a Parquet row viewer. Both UIs bind only to `127.0.0.1` and have
no login in this local lab. Pages 39-44 of the English guide explain the data
path, execution model, monitoring, object layout, and MyScoutee use cases.

## Flink and affinity

In the current backend, `AffinityRecomputeTaskService` creates durable MongoDB
tasks (`USER`, `EVENT`, `ASSET`, `CONFIG`; `pending`, `running`, `done`,
`failed`). `AffinityRecomputeChangeStreamService` wakes the worker, while
`AffinityRecomputeMetricsService` measures queue wait and runtime.
`AffinityCalculationService` calculates the scores from profile, distance,
rating, configuration, and other inputs. Kafka task signals alone do not give
Flink enough information to replace these responsibilities.

Here, Flink reads **synthetic recompute task states**, aggregates them into
10-second processing-time windows, and writes the results to another Kafka
topic. This reveals queue load, distribution by target type, failure rate,
and wait time. It helps estimate the operational load of a future affinity
feature without taking over the backend's decisions.

```sh
./lab.sh stream-up
./lab.sh affinity-seed --tasks 1000 --seed 42
./lab.sh query "SELECT target_type, sum(pending), sum(done), sum(failed) FROM affinity_rollups FINAL GROUP BY target_type"
```

Flink UI: <http://127.0.0.1:8081>. The dashboard's affinity panel receives
data after the first 10-second window closes. Running `stream-up` again does
not submit another job with the same name. The lab's Kafka sink uses
at-least-once delivery; a ClickHouse `ReplacingMergeTree` table merges
duplicate window records by key. This is not a production exactly-once
guarantee. A newly submitted Flink job starts from the earliest retained
topic offset and may reprocess earlier synthetic signals. Use this to observe
how Kafka replay interacts with processing-time windows.
The English guide's pages 45-47 explain the job graph, task slots, windows,
checkpoints, UI panels, SQL job submission, time semantics, and the MyScoutee
telemetry boundary in this visit.

The `batch` command reads all available Kafka activity data, deduplicates it
by event ID, and writes daily/city/mode/event-key aggregates as Parquet. The
Parquet objects remain in the `lake-data` Docker volume. `up` does not start
Spark; run it explicitly to keep the everyday lab smaller. `down` preserves
Docker volumes; `./lab.sh reset` deletes them (destructive).

## Metrics and data handling

- Funnel stages count **distinct synthetic actor IDs**. The simulator emits
  joins only after onboarding, but the all-history stage counts are not a
  verified same-person conversion cohort.
- `city` and `mode` are dimensions assigned to simulated events. The current
  telemetry may not contain all these dimensions.
- The raw table uses `event_id` to identify retries. The dashboard counts
  with `uniqExact` queries, and the Spark batch deduplicates by the same field.
- Generator IDs and cities are artificial. Connecting real data requires a
  separate authenticated export contract, field minimization, consent, and
  deletion/retention rules. Do not attach a second consumer directly to the
  existing Redis admin telemetry stream: the backend owns its processing and
  retention.
- Affinity `task_id` values are synthetic. A real task export should contain
  only status, target type, group, and timing fields as needed, without
  profile data or target identifiers.

This is a single-machine development lab, not production infrastructure. It
has no cluster replicas, TLS, multi-user access controls, or guaranteed
exactly-once delivery. Local Kafka retention is seven days; the ClickHouse
volume keeps rows that have already been ingested.

## Exercises

1. Run `seed` with two different `--seed` values and observe how the
   ClickHouse query and Spark Parquet results change.
2. Stop only ClickHouse, produce more messages, restart it, and inspect the
   effect of Kafka consumer lag.
3. Compare the `city` and `mode` breakdowns. Explore why
   `uniqExact(actor_id)` differs from `count()`.
4. After `batch`, inspect the S3 bucket's `day=` partitions. Run the batch
   again after producing more events and compare the ClickHouse live view
   with the historical Parquet snapshot.
5. Inspect checkpoints in the Flink UI, send another `affinity-seed` sample,
   and compare the `pending`, `done`, and `failed` counters.

## Technical references

The lab follows the [official Apache Kafka Docker image guide](https://kafka.apache.org/41/getting-started/docker/),
the [ClickHouse Kafka Engine and materialized view pattern](https://clickhouse.com/docs/integrations/connectors/data-ingestion/kafka/kafka-table-engine),
the [Spark Kafka integration guide](https://spark.apache.org/docs/4.0.4/streaming/structured-streaming-kafka-integration.html),
the [Flink Docker/SQL Client guide](https://nightlies.apache.org/flink/flink-docs-release-2.2/docs/deployment/resource-providers/standalone/docker/),
and the [SeaweedFS mini quick start](https://github.com/seaweedfs/seaweedfs#quick-start).
Image and connector versions are pinned in `stacks/core/compose.yaml`.
