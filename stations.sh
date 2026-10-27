#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export COMPOSE_PROGRESS=quiet

station="${1:-}"
action="${2:-}"
case "$station" in
  hadoop|hive|hbase|cassandra|airflow|nifi) ;;
  *) echo 'Usage: ./stations.sh {hadoop|hive|hbase|cassandra|airflow|nifi} {up|run|status|down|reset}' >&2; exit 2 ;;
esac
compose=(docker compose -f "stacks/$station/compose.yaml")

case "$action" in
  up)
    if [[ ! -f build/stations/activity.jsonl ]]; then
      python3 producer/export.py
    fi
    if [[ "$station" == nifi ]]; then
      mkdir -p build/stations/nifi-inbox build/stations/nifi-output/valid build/stations/nifi-output/rejected
    fi
    "${compose[@]}" up -d --build
    if [[ "$station" == airflow ]]; then
      ready=false
      for _ in {1..90}; do
        if curl --fail --silent --output /dev/null http://127.0.0.1:8096/ \
          && "${compose[@]}" exec -T airflow test -s /opt/airflow/simple_auth_manager_passwords.json.generated 2>/dev/null; then
          ready=true
          break
        fi
        sleep 2
      done
      if [[ "$ready" != true ]]; then echo 'Airflow did not become ready.' >&2; exit 1; fi
      umask 077
      mkdir -p .local/state
      password_file=$(mktemp .local/state/airflow-passwords.json.XXXXXX)
      if "${compose[@]}" exec -T airflow cat /opt/airflow/simple_auth_manager_passwords.json.generated > "$password_file" \
        && python3 -c 'import json, sys; assert json.load(open(sys.argv[1])).get("admin")' "$password_file"; then
        mv -f "$password_file" .local/state/airflow-passwords.json
        echo 'Airflow login: admin; password file: .local/state/airflow-passwords.json'
      else
        rm -f "$password_file"
        echo 'Could not save the Airflow password locally.' >&2
        exit 1
      fi
    fi
    ;;
  run)
    if [[ ! -f build/stations/activity.jsonl ]]; then
      echo 'Run ./stations.sh STATION up first to create fixtures.' >&2
      exit 2
    fi
    case "$station" in
      hadoop)
        ready=false
        for _ in {1..45}; do
          if "${compose[@]}" exec -T namenode hdfs dfsadmin -report 2>/dev/null | grep -F 'Live datanodes (1)' >/dev/null; then
            ready=true
            break
          fi
          sleep 2
        done
        if [[ "$ready" != true ]]; then echo 'HDFS did not become ready.' >&2; exit 1; fi
        "${compose[@]}" exec -T namenode bash -lc '
          set -e
          hdfs dfs -mkdir -p /myscoutee/joins
          hdfs dfs -put -f /opt/lab/joins-by-city-mode.txt /myscoutee/joins/input.txt
          hdfs dfs -rm -r -f /myscoutee/joins/result >/dev/null 2>&1 || :
          hadoop jar /opt/hadoop/share/hadoop/mapreduce/hadoop-mapreduce-examples-3.4.2.jar \
            wordcount /myscoutee/joins/input.txt /myscoutee/joins/result
          hdfs dfs -cat /myscoutee/joins/result/part-r-00000'
        ;;
      hive)
        ready=false
        for _ in {1..45}; do
          if "${compose[@]}" exec -T hive bash -lc 'echo > /dev/tcp/127.0.0.1/10000' >/dev/null 2>&1; then
            ready=true
            break
          fi
          sleep 2
        done
        if [[ "$ready" != true ]]; then echo 'HiveServer2 did not become ready.' >&2; exit 1; fi
        "${compose[@]}" exec -T hive beeline -u 'jdbc:hive2://hive:10000/default' -f /opt/lab-sql/activity.hql
        ;;
      hbase)
        ready=false
        for _ in {1..45}; do
          if curl --fail --silent --output /dev/null http://127.0.0.1:16011/; then
            ready=true
            break
          fi
          sleep 2
        done
        if [[ "$ready" != true ]]; then echo 'HBase Master did not become ready.' >&2; exit 1; fi
        "${compose[@]}" exec -T hbase hbase shell -n /opt/lab/affinity.hbase
        ;;
      cassandra)
        ready=false
        for _ in {1..45}; do
          if "${compose[@]}" exec -T cassandra cqlsh -e 'DESCRIBE KEYSPACES' >/dev/null 2>&1; then
            ready=true
            break
          fi
          sleep 2
        done
        if [[ "$ready" != true ]]; then echo 'Cassandra did not become ready.' >&2; exit 1; fi
        "${compose[@]}" exec -T cassandra cqlsh -f /opt/lab/affinity.cql
        "${compose[@]}" exec -T cassandra cqlsh -e \
          "SELECT task_id, status FROM myscoutee_lab.affinity_task_status WHERE target_type='USER' AND day='2026-01-31' LIMIT 5;"
        ;;
      airflow)
        "${compose[@]}" exec -T airflow airflow dags test myscoutee_activity_cohort 2026-01-31
        "${compose[@]}" exec -T airflow cat /opt/airflow/output/activity_cohort.json
        ;;
      nifi)
        python3 stacks/nifi/install_flow.py
        ;;
    esac
    ;;
  status)
    "${compose[@]}" ps
    ;;
  down)
    "${compose[@]}" down
    ;;
  reset)
    "${compose[@]}" down --volumes
    if [[ "$station" == airflow ]]; then rm -f .local/state/airflow-passwords.json; fi
    ;;
  *) echo 'Usage: ./stations.sh {hadoop|hive|hbase|cassandra|airflow|nifi} {up|run|status|down|reset}' >&2; exit 2 ;;
esac
