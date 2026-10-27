"""Export deterministic synthetic events for the isolated learning stations."""

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from affinity import make_tasks
from generate import make_events


def export(destination: Path, users: int, tasks: int, seed: int) -> dict[str, int]:
    destination.mkdir(parents=True, exist_ok=True)
    events = list(make_events(
        users, 30, seed, datetime(2026, 1, 31, tzinfo=timezone.utc), "station"
    ))
    transitions = list(make_tasks(tasks, seed, "station"))
    joins = [event for event in events if event["event_key"] == "event.member.joined"]

    with (destination / "activity.jsonl").open("w", encoding="utf-8") as stream:
        for event in events:
            stream.write(json.dumps(event, separators=(",", ":")) + "\n")

    with (destination / "activity.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        for event in events:
            writer.writerow((event["event_id"], event["occurred_at"],
                             event["event_key"], event["actor_id"],
                             event["city"], event["mode"]))

    with (destination / "joins-by-city-mode.txt").open("w", encoding="utf-8") as stream:
        for event in joins:
            stream.write(f'{event["city"]}_{event["mode"]}\n')

    with (destination / "affinity.jsonl").open("w", encoding="utf-8") as stream:
        for task in transitions:
            stream.write(json.dumps(task, separators=(",", ":")) + "\n")

    latest = transitions[2::3]
    with (destination / "affinity.cql").open("w", encoding="utf-8") as stream:
        stream.write(
            "CREATE KEYSPACE IF NOT EXISTS myscoutee_lab WITH REPLICATION = "
            "{'class': 'SimpleStrategy', 'replication_factor': 1};\n"
            "CREATE TABLE IF NOT EXISTS myscoutee_lab.affinity_task_status "
            "(target_type text, day date, task_id text, status text, group_id text, "
            "runtime_ms int, PRIMARY KEY ((target_type, day), task_id));\n"
        )
        for task in latest:
            stream.write(
                "INSERT INTO myscoutee_lab.affinity_task_status "
                "(target_type, day, task_id, status, group_id, runtime_ms) "
                f"VALUES ('{task['target_type']}', '2026-01-31', "
                f"'{task['task_id']}', '{task['status']}', "
                f"'{task['group_id']}', {task['runtime_ms']});\n"
            )

    with (destination / "affinity.hbase").open("w", encoding="utf-8") as stream:
        stream.write("create 'affinity_tasks', 'state' unless exists 'affinity_tasks'\n")
        for task in latest:
            row = f"{task['target_type']}#{task['task_id']}"
            stream.write(f"put 'affinity_tasks', '{row}', 'state:status', '{task['status']}'\n")
            stream.write(f"put 'affinity_tasks', '{row}', 'state:group', '{task['group_id']}'\n")
        stream.write("count 'affinity_tasks'\n")
        stream.write("scan 'affinity_tasks', {LIMIT => 5}\n")

    (destination / "nifi-inbox").mkdir(exist_ok=True)
    (destination / "nifi-output").mkdir(exist_ok=True)
    (destination / "nifi-output" / "valid").mkdir(exist_ok=True)
    (destination / "nifi-output" / "rejected").mkdir(exist_ok=True)
    (destination / "nifi-inbox" / "valid.json").write_text(
        json.dumps(events[0], separators=(",", ":")), encoding="utf-8"
    )
    (destination / "nifi-inbox" / "invalid.json").write_text(
        '{"event_id":"invalid","actor_id":"station-user"}', encoding="utf-8"
    )
    return {"events": len(events), "joins": len(joins), "tasks": len(latest)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("build/stations"))
    parser.add_argument("--users", type=int, default=120)
    parser.add_argument("--tasks", type=int, default=40)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if not 1 <= args.users <= 100_000 or not 1 <= args.tasks <= 100_000:
        parser.error("--users and --tasks must be 1..100000")
    print(export(args.output, args.users, args.tasks, args.seed))


if __name__ == "__main__":
    main()
