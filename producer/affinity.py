"""Publish synthetic affinity recompute task transitions."""

import argparse
import json
import os
import random
import uuid


TARGETS = ("USER", "EVENT", "ASSET", "CONFIG")


def make_tasks(count: int, seed: int, run_id: str):
    rng = random.Random(seed)
    for index in range(count):
        task_id = f"{run_id}-task-{index:09d}"
        target = rng.choices(TARGETS, weights=(45, 35, 18, 2))[0]
        group = rng.choice(("demo-base-a", "demo-base-b"))
        wait = rng.randint(20, 15_000)
        runtime = rng.randint(10, 4_000)
        failed = rng.random() < 0.04
        base = {"task_id": task_id, "group_id": group, "target_type": target}
        yield {**base, "status": "pending", "queue_wait_ms": 0, "runtime_ms": 0}
        yield {**base, "status": "running", "queue_wait_ms": wait, "runtime_ms": 0}
        yield {**base, "status": "failed" if failed else "done", "queue_wait_ms": 0, "runtime_ms": runtime}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if not 1 <= args.tasks <= 1_000_000:
        parser.error("--tasks must be 1..1000000")

    from kafka import KafkaProducer

    producer = KafkaProducer(
        bootstrap_servers=os.environ.get("KAFKA_BOOTSTRAP", "kafka:9092"),
        value_serializer=lambda value: json.dumps(value, separators=(",", ":")).encode(),
        acks="all",
        retries=5,
    )
    run_id = uuid.uuid4().hex[:12]
    topic = os.environ.get("KAFKA_TOPIC", "myscoutee.affinity.tasks.v1")
    for value in make_tasks(args.tasks, args.seed, run_id):
        producer.send(topic, key=value["task_id"].encode(), value=value)
    producer.flush(timeout=120)
    producer.close()
    print(f"Published {args.tasks} synthetic affinity tasks ({args.tasks * 3} transitions) to {topic}")


if __name__ == "__main__":
    main()
