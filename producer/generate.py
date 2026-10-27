"""Generate synthetic MyScoutee-shaped lifecycle events for the Kafka lab."""

import argparse
import json
import os
import random
import uuid
from datetime import datetime, timedelta, timezone


CITIES = ("Bratislava", "Praha", "Brno", "Košice")
MODES = ("Casual", "Mingle")


def make_events(users: int, days: int, seed: int, now: datetime, run_id: str):
    rng = random.Random(seed)
    origin = now - timedelta(days=days)
    sequence = 0

    def event(key, actor, activity, city, mode, when):
        nonlocal sequence
        sequence += 1
        return {
            "event_id": f"{run_id}-{sequence:09d}",
            "occurred_at": when.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            "event_key": key,
            "actor_id": actor,
            "activity_id": activity,
            "city": city,
            "mode": mode,
            "group_id": "demo-lab",
            "amount": 1,
        }

    activities = []
    for index in range(max(1, users // 30)):
        city = rng.choice(CITIES)
        mode = rng.choice(MODES)
        activity = f"{run_id}-activity-{index:06d}"
        activities.append((activity, city, mode))
        when = origin + timedelta(seconds=rng.random() * days * 86400 * 0.1)
        yield event("event.created", f"{run_id}-host-{index:06d}", activity, city, mode, when)

    for index in range(users):
        actor = f"{run_id}-user-{index:09d}"
        activity, city, mode = rng.choice(activities)
        start = origin + timedelta(seconds=(0.1 + rng.random() * 0.65) * days * 86400)
        yield event("profile.registered", actor, "", city, mode, start)
        if rng.random() < 0.81:
            onboarded = min(now, start + timedelta(hours=rng.uniform(1, 24)))
            yield event("profile.onboarding", actor, "", city, mode, onboarded)
            if rng.random() < 0.59:
                joined = min(now, onboarded + timedelta(hours=rng.uniform(1, 48)))
                yield event("event.member.joined", actor, activity, city, mode, joined)
                if rng.random() < 0.12:
                    removed = min(now, joined + timedelta(hours=rng.uniform(1, 24)))
                    yield event("event.member.removed", actor, activity, city, mode, removed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--users", type=int, default=5000)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if not 1 <= args.users <= 1_000_000 or not 1 <= args.days <= 365:
        parser.error("--users must be 1..1000000 and --days 1..365")

    from kafka import KafkaProducer

    producer = KafkaProducer(
        bootstrap_servers=os.environ.get("KAFKA_BOOTSTRAP", "kafka:9092"),
        value_serializer=lambda value: json.dumps(value, separators=(",", ":")).encode(),
        acks="all",
        retries=5,
    )
    run_id = uuid.uuid4().hex[:12]
    topic = os.environ.get("KAFKA_TOPIC", "myscoutee.activity.v1")
    count = 0
    for value in make_events(args.users, args.days, args.seed, datetime.now(timezone.utc), run_id):
        producer.send(topic, key=value["actor_id"].encode(), value=value)
        count += 1
    producer.flush(timeout=120)
    producer.close()
    print(f"Published {count} synthetic events to {topic}; run_id={run_id}")


if __name__ == "__main__":
    main()
