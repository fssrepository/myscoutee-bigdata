"""Orchestrate a synthetic MyScoutee registration-to-participation report."""

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from airflow.sdk import dag, task


@dag(
    dag_id="myscoutee_activity_cohort",
    description="Synthetic registration, onboarding and event participation cohort",
    schedule=None,
    start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    catchup=False,
    tags=["myscoutee", "activity", "learning"],
)
def activity_cohort():
    @task
    def extract() -> dict:
        events = [json.loads(line) for line in Path("/opt/lab/activity.jsonl").read_text().splitlines()]
        counts = Counter(event["event_key"] for event in events)
        joins = Counter(
            f"{event['city']}|{event['mode']}"
            for event in events if event["event_key"] == "event.member.joined"
        )
        return {"events": dict(counts), "joins_by_city_mode": dict(joins)}

    @task
    def validate(report: dict) -> dict:
        counts = report["events"]
        registrations = counts.get("profile.registered", 0)
        onboarded = counts.get("profile.onboarding", 0)
        joined = counts.get("event.member.joined", 0)
        if not (registrations >= onboarded >= joined > 0):
            raise ValueError(f"Unexpected synthetic cohort: {counts}")
        if sum(report["joins_by_city_mode"].values()) != joined:
            raise ValueError("Join breakdown does not match the event total")
        return report

    @task
    def publish(report: dict) -> str:
        path = Path("/opt/airflow/output/activity_cohort.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        return str(path)

    publish(validate(extract()))


activity_cohort()
