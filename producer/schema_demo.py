"""Register, publish, and read two compatible Avro versions in the isolated lab."""

import io
import json
import os
import struct
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastavro import parse_schema, schemaless_reader, schemaless_writer
from kafka import KafkaConsumer, KafkaProducer


SCHEMAS = Path(__file__).parent / "schemas"
REGISTRY = os.environ.get("SCHEMA_REGISTRY_URL", "http://schema-registry:8081")
TOPIC = os.environ.get("KAFKA_TOPIC", "myscoutee.activity.avro.v1")
SUBJECT = f"{TOPIC}-value"


def request(method, path, payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        REGISTRY + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/vnd.schemaregistry.v1+json"},
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.load(response)


def wait_for_registry():
    for _ in range(30):
        try:
            request("GET", "/subjects")
            return
        except (urllib.error.URLError, TimeoutError):
            time.sleep(2)
    raise RuntimeError("Schema Registry did not become available")


def schema(name):
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


def register(value):
    path = "/subjects/" + urllib.parse.quote(SUBJECT, safe="") + "/versions"
    return request("POST", path, {"schemaType": "AVRO", "schema": json.dumps(value)})["id"]


def compatible(value):
    path = "/compatibility/subjects/" + urllib.parse.quote(SUBJECT, safe="") + "/versions/latest"
    return request("POST", path, {"schemaType": "AVRO", "schema": json.dumps(value)})["is_compatible"]


def encode(value, writer_schema, schema_id):
    data = io.BytesIO()
    data.write(b"\x00" + struct.pack(">I", schema_id))
    schemaless_writer(data, parse_schema(writer_schema), value)
    return data.getvalue()


def decode(data, reader_schema):
    if len(data) < 5 or data[0] != 0:
        raise ValueError("Expected Confluent Avro framing")
    schema_id = struct.unpack(">I", data[1:5])[0]
    writer_schema = json.loads(request("GET", f"/schemas/ids/{schema_id}")["schema"])
    record = schemaless_reader(io.BytesIO(data[5:]), parse_schema(writer_schema), parse_schema(reader_schema))
    return schema_id, record


def main():
    wait_for_registry()
    v1, v2, breaking = (schema(name) for name in (
        "activity-v1.avsc", "activity-v2.avsc", "activity-breaking.avsc"))
    subject_path = "/config/" + urllib.parse.quote(SUBJECT, safe="")
    request("PUT", subject_path, {"compatibility": "BACKWARD_TRANSITIVE"})
    id1 = register(v1)
    if not compatible(v2):
        raise RuntimeError("The optional source field should be backward compatible")
    id2 = register(v2)
    if compatible(breaking):
        raise RuntimeError("Changing event_id from string to long should be rejected")

    run_id = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).isoformat()
    base = {
        "occurred_at": now, "event_key": "event.member.joined",
        "group_id": "demo-lab", "city": "Bratislava", "mode": "Casual",
    }
    producer = KafkaProducer(bootstrap_servers=os.environ.get("KAFKA_BOOTSTRAP", "kafka:9092"), acks="all")
    try:
        records = [
            (v1, id1, {**base, "event_id": f"{run_id}-v1"}),
            (v2, id2, {**base, "event_id": f"{run_id}-v2", "source": "schema-demo"}),
        ]
        for writer_schema, schema_id, value in records:
            producer.send(TOPIC, key=run_id.encode(), value=encode(value, writer_schema, schema_id)).get(timeout=30)
    finally:
        producer.flush(timeout=30)
        producer.close()

    consumer = KafkaConsumer(
        TOPIC, bootstrap_servers=os.environ.get("KAFKA_BOOTSTRAP", "kafka:9092"),
        auto_offset_reset="earliest", enable_auto_commit=False, consumer_timeout_ms=30000,
        group_id=f"schema-demo-{run_id}",
    )
    seen = {}
    try:
        for message in consumer:
            if message.key != run_id.encode():
                continue
            schema_id, value = decode(message.value, v2)
            seen[value["event_id"]] = (schema_id, value)
            if len(seen) == 2:
                break
    finally:
        consumer.close()
    if set(seen) != {f"{run_id}-v1", f"{run_id}-v2"}:
        raise RuntimeError(f"Expected two round-tripped records, got {list(seen)}")
    assert seen[f"{run_id}-v1"][1]["source"] is None
    assert seen[f"{run_id}-v2"][1]["source"] == "schema-demo"
    print(f"Subject {SUBJECT}: v1 schema ID {id1}, v2 schema ID {id2}; incompatible change rejected")
    print("Read both Kafka records with the v2 reader schema; the v1 source resolved to null")


if __name__ == "__main__":
    main()
