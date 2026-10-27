# MyScoutee Big Data learning stations

These Docker Compose projects are independent. `core/` contains the
Kafka/ClickHouse/Spark/Flink lab controlled by `./lab.sh`; the other directories
are isolated stations controlled by `./stations.sh`. Start **one station at a
time** on a laptop. They use deterministic, synthetic exports from the existing
activity and affinity generators. They do not connect to the backend or its
databases.

From the repository root:

```sh
python3 producer/export.py --users 120 --tasks 40 --seed 42
./stations.sh hadoop up
./stations.sh hadoop run
./stations.sh hadoop down
```

`up` creates the default fixtures if they are missing. `run` executes the
station's MyScoutee exercise. `status` lists its containers. `down` stops the
station and retains its Docker volumes. `reset` also deletes **that station's**
volumes. A fixture regeneration changes the next run's input but does not
automatically clear a database or a previously produced HDFS result.

| Station | MyScoutee case and technology lesson | Interface |
| --- | --- | --- |
| `hadoop` | Event participation by city/mode: upload 71 synthetic joins to HDFS, submit MapReduce WordCount through YARN, inspect a DataNode and NodeManager | [NameNode](http://127.0.0.1:9871), [ResourceManager](http://127.0.0.1:8089) |
| `hive` | Registration/onboarding/join cohort: load the same synthetic activity CSV into Hive and query counts with HiveQL | [HiveServer2 web UI](http://127.0.0.1:10002), Beeline on `127.0.0.1:10000` |
| `hbase` | Latest affinity recompute task state by `target_type#task_id`: create a column family, `put`, `scan`, and count rows | [HBase Master](http://127.0.0.1:16011) |
| `cassandra` | The same 40 latest affinity task states: a CQL table partitioned by target type and day, queried with the partition key | `cqlsh` inside the container |
| `nifi` | Route synthetic valid/invalid activity JSON into accepted/rejected paths and inspect queues and provenance | [NiFi](https://localhost:8444/nifi), `labuser` / `lab-only-password-123` |
| `airflow` | Run extract -> validate -> publish for the registration-to-participation cohort; inspect task dependencies and a generated JSON report | [Airflow](http://127.0.0.1:8096) |

The default fixture contains 306 activity events: 120 registrations, 103
onboarding events, 71 joins, 8 removals and 4 event creations. The Hadoop and
Hive join breakdowns should agree: `Bratislava_Casual = 55` and
`Praha_Casual = 16`. The affinity fixture contains 40 task lifecycles (120
transitions); HBase and Cassandra receive one final state per task. These are
validation values for the default seed, not product statistics.

## Exercise details

### Activity: Hadoop and Hive

`./stations.sh hadoop run` uploads `joins-by-city-mode.txt` to HDFS, removes
only the prior lab result path, submits Hadoop's WordCount example through
YARN, and prints the HDFS output. Compare the input record count, the completed
YARN application and the output sum. HDFS replication is one because the lab
has one DataNode. `./stations.sh hive run` loads the activity CSV into a local
Hive warehouse and prints event-key and city/mode counts. Hive uses the image's
embedded Derby metastore; it is a standalone learning setup, not the same HDFS
installation as the Hadoop station.

### Affinity: HBase and Cassandra

`./stations.sh hbase run` writes one row per synthetic task, prints a count of
40 and scans five sample rows. The [HBase Master](http://127.0.0.1:16011/master.jsp)
shows the `affinity_tasks` schema, its region and server health; it does not
list row values. The RegionServer link uses an internal Docker hostname and
may not open from the host browser. `./stations.sh cassandra run` creates a CQL
keyspace and table, imports
the same final states and runs a partition-key query. Compare the HBase row key
and Cassandra primary key. They model an analytical copy of task state: MongoDB
and the backend worker remain authoritative for real affinity recomputations.

The Cassandra station has **no web UI or login**. Run `./stations.sh cassandra up`
and `./stations.sh cassandra run`, then inspect it from the repository root:

```sh
docker compose -f stacks/cassandra/compose.yaml exec cassandra cqlsh
```

Inside `cqlsh`, use `DESCRIBE KEYSPACE myscoutee_lab;`,
`DESCRIBE TABLE myscoutee_lab.affinity_task_status;`, and:

```sql
SELECT task_id, status, group_id, runtime_ms
FROM myscoutee_lab.affinity_task_status
WHERE target_type = 'USER' AND day = '2026-01-31'
LIMIT 5;
```

The table's primary key is `((target_type, day), task_id)`: the pair in the
inner parentheses is the partition key and `task_id` orders rows inside that
partition. `group_id` is a regular column, so this sample cannot efficiently
serve group-scoped admin queries. `SELECT count(*)` without a partition key
warns about an aggregation scan; the 40-row fixture check is not a production
query pattern. On the host, run:

```sh
docker compose -f stacks/cassandra/compose.yaml exec cassandra nodetool status
```

This shows one `UN` node. The image's
`SimpleSnitch` reports `datacenter1/rack1`; the keyspace uses
`SimpleStrategy` with replication factor 1, so this station cannot demonstrate
replica failure tolerance. `down` preserves the volume; `reset` deletes it.

Cassandra's peer-to-peer coordination, multiple replicas and tunable
consistency are **cluster concepts**, not effects visible in this one-node
fixture. In a three-node cluster with replication factor 3, `ONE` waits for one
replica response and `QUORUM` waits for two; writes are sent to all replicas.
Production topology would use `NetworkTopologyStrategy`, not the lab's
`SimpleStrategy`. The current Flink job writes rollups to Kafka/ClickHouse and
does not feed Cassandra. A future group-scoped status projection would need a
separate, idempotent consumer and a key designed for actual group/day reads;
backend authorization and Mongo task ownership would remain in place.

### Data movement: NiFi

`./stations.sh nifi run` installs a five-processor flow on the canvas:
`GetFile -> EvaluateJsonPath -> RouteOnAttribute -> PutFile (accepted/rejected)`.
It looks for `event_key` in the synthetic JSON while preserving the original
file content. The accepted and rejected files appear in
`build/stations/nifi-output/`. Use NiFi's Data Provenance view to trace each
file. The input fixture directory is writable because `GetFile` consumes the
two sample files. Rerun `python3 producer/export.py` to restore them. After a
`down`/`up` cycle, run the installer again; the NiFi canvas is recreated in
the new container.

For a guided first look, start and install the flow, then open
<https://localhost:8444/nifi> as `labuser` / `lab-only-password-123`. The
local certificate may require a browser exception. On the root canvas, follow
`GetFile -> EvaluateJsonPath -> RouteOnAttribute` to the accepted and rejected
`PutFile` processors. `EvaluateJsonPath` copies `$.event_key` to a FlowFile
attribute. The route accepts a non-empty value; `valid.json` has
`event_key=event.created`, while `invalid.json` has no `event_key`. The
connections may show empty queues because both files finish quickly. Open
**Data Provenance** from the global menu to inspect each file's events and
lineage. Confirm `valid/valid.json` and `rejected/invalid.json` in
`build/stations/nifi-output/`, then rerun the exporter to watch another pass.

### Orchestration: Airflow

`./stations.sh airflow run` tests the DAG locally and prints the report at
`/opt/airflow/output/activity_cohort.json` in its volume. The `standalone`
command generates an admin password in its Docker volume. `./stations.sh airflow up`
copies the current value to the repository's ignored, private
`.local/state/airflow-passwords.json` file. Read it with:

```sh
cat .local/state/airflow-passwords.json
```

The JSON key is the username (`admin`) and its value is the password. The file
is mode `600`; `airflow down` keeps it and the Docker volume, while `airflow
reset` removes both. Running `airflow up` refreshes the local copy. GitLab and
SonarQube keep their own credentials in their respective repositories; see
their READMEs for the owning paths. Do not commit or share any of these files.

The Airflow UI is a development setup. Its DAG orchestrates a Python batch on
the shared fixture; it does not invoke the separate Spark station or replace
GitLab CI.

To inspect the first run, keep Airflow running and open
<http://127.0.0.1:8096>. Sign in as `admin` with the generated password above.
The Home page shows service health. Under **Dags**, find
`myscoutee_activity_cohort`; examples are disabled and this DAG has no
automatic schedule. A previous run may be present because `down` keeps the
volume. Open **Graph** to see `extract -> validate -> publish`, then **Code**
to read the Python tasks. **Runs** and **Grid** show execution states; open a
task's **Logs** or **XCom** to inspect its work and returned value.

Resume the DAG if it is paused, then use **Trigger** for a manual run. Watch all
three tasks reach success in **Grid** or **Graph**. To run the same exercise
from the terminal instead, use `./stations.sh airflow run`; this performs a
local DAG test for logical date `2026-01-31` and prints the report. Either
way, inspect the persistent JSON result with:

```sh
docker compose -f stacks/airflow/compose.yaml exec -T airflow \
  cat /opt/airflow/output/activity_cohort.json
```

With the default fixture, the event counts are 120 registrations, 103
onboarding events and 71 joins; the city/mode join counts are 55 and 16.
Finish with `./stations.sh airflow down`, which keeps the run history.

## Boundaries and sources

Images are pinned; published ports bind to `127.0.0.1`. A single host, one
DataNode and one Cassandra node cannot demonstrate real cluster fault
tolerance. The NiFi password is a local lab credential. Keep real profile
data and backend credentials out of these stations.

Official starting points: [Hadoop single-node setup](https://hadoop.apache.org/docs/r3.4.2/hadoop-project-dist/hadoop-common/SingleCluster.html),
[Hive Docker setup](https://hive.apache.org/docs/latest/admin/setting-up-hive-with-docker/),
[HBase quick start](https://hbase.apache.org/docs/getting-started/),
[Cassandra quick start](https://cassandra.apache.org/doc/latest/cassandra/getting-started/cassandra-quickstart.html),
[NiFi getting started](https://nifi.apache.org/nifi-docs/getting-started.html), and
[Airflow standalone](https://airflow.apache.org/docs/apache-airflow/3.1.7/start.html).
