#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
compose=(docker compose -f stacks/core/compose.yaml)

case "${1:-}" in
  up)
    "${compose[@]}" up -d --build kafka topic clickhouse lake dashboard
    "${compose[@]}" exec -T clickhouse clickhouse-client --user lab --password lab-only --multiquery < stacks/core/sql/02-affinity.sql
    ;;
  seed)
    shift
    "${compose[@]}" --profile tools run --no-deps --build --rm producer "$@"
    ;;
  schema-demo)
    "${compose[@]}" --profile schema up -d kafka schema-registry
    "${compose[@]}" exec -T kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:9092 --create --if-not-exists --topic myscoutee.activity.avro.v1 --partitions 3 --replication-factor 1
    "${compose[@]}" --profile schema run --no-deps --build --rm schema-demo
    ;;
  batch)
    mkdir -p build/ivy build/spark-events
    LAB_UID="$(id -u)" LAB_GID="$(id -g)" "${compose[@]}" --profile batch run --build --rm spark
    ;;
  history-up)
    mkdir -p build/spark-events
    LAB_UID="$(id -u)" LAB_GID="$(id -g)" "${compose[@]}" --profile history up -d --build spark-history
    ;;
  history-down)
    "${compose[@]}" --profile history stop spark-history
    ;;
  stream-up)
    "${compose[@]}" up -d --build kafka topic clickhouse dashboard
    "${compose[@]}" exec -T clickhouse clickhouse-client --user lab --password lab-only --multiquery < stacks/core/sql/02-affinity.sql
    "${compose[@]}" --profile stream up -d --build flink-jobmanager flink-taskmanager
    if "${compose[@]}" exec -T flink-jobmanager bin/flink list --running 2>/dev/null | grep -Fq 'myscoutee-affinity-recompute-rollups'; then
      echo 'Affinity Flink job already running.'
    else
      "${compose[@]}" --profile stream run --no-deps --build --rm flink-submit
      if ! "${compose[@]}" exec -T flink-jobmanager bin/flink list --running 2>/dev/null | grep -Fq 'myscoutee-affinity-recompute-rollups'; then
        echo 'Affinity Flink job was not submitted; inspect the SQL Client output.' >&2
        exit 1
      fi
    fi
    ;;
  affinity-seed)
    shift
    "${compose[@]}" --profile stream run --no-deps --build --rm affinity-producer "$@"
    ;;
  status)
    "${compose[@]}" ps
    ;;
  topics)
    "${compose[@]}" exec -T kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:9092 --list | grep '^myscoutee\.'
    ;;
  groups)
    "${compose[@]}" exec -T kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server kafka:9092 --list
    ;;
  query)
    shift
    if [[ $# -ne 1 ]]; then echo 'Usage: ./lab.sh query "SQL"' >&2; exit 2; fi
    "${compose[@]}" exec -T clickhouse clickhouse-client --user lab --password lab-only --database myscoutee_lab --query "$1"
    ;;
  down)
    "${compose[@]}" --profile stream --profile history --profile schema down
    ;;
  reset)
    "${compose[@]}" --profile stream --profile history --profile schema down --volumes
    ;;
  *)
    echo 'Usage: ./lab.sh {up|seed [--users N --days N --seed N]|schema-demo|batch|history-up|history-down|stream-up|affinity-seed [--tasks N --seed N]|status|topics|groups|query "SQL"|down|reset}' >&2
    exit 2
    ;;
esac
