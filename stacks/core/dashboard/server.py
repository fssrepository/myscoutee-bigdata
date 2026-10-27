"""Small read-only ClickHouse dashboard for the local Big Data lab."""

import json
import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


BASE = os.environ.get("CLICKHOUSE_URL", "http://clickhouse:8123")
USER = os.environ.get("CLICKHOUSE_USER", "lab")
PASSWORD = os.environ.get("CLICKHOUSE_PASSWORD", "lab-only")
HTML = Path(__file__).with_name("index.html").read_bytes()


def query(sql):
    request = urllib.request.Request(
        BASE + "/?database=myscoutee_lab",
        data=(sql + " FORMAT JSONEachRow").encode(),
        headers={"X-ClickHouse-User": USER, "X-ClickHouse-Key": PASSWORD},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        return [json.loads(line) for line in response if line.strip()]


QUERIES = {
    "summary": """SELECT
        uniqExact(event_id) AS events,
        uniqExactIf(actor_id, event_key = 'profile.registered') AS registered,
        uniqExactIf(actor_id, event_key = 'profile.onboarding') AS onboarded,
        uniqExactIf(actor_id, event_key = 'event.member.joined') AS joined,
        uniqExactIf(activity_id, event_key = 'event.created') AS activities
        FROM activity_events""",
    "daily": """SELECT toString(toDate(occurred_at)) AS day,
        event_key, uniqExact(event_id) AS events
        FROM activity_events WHERE occurred_at >= now() - INTERVAL 30 DAY
        GROUP BY day, event_key ORDER BY day, event_key""",
    "cities": """SELECT city,
        uniqExactIf(actor_id, event_key = 'profile.registered') AS registered,
        uniqExactIf(actor_id, event_key = 'event.member.joined') AS joined
        FROM activity_events GROUP BY city ORDER BY registered DESC""",
    "modes": """SELECT mode, uniqExactIf(event_id, event_key = 'event.created') AS created,
        uniqExactIf(event_id, event_key = 'event.member.joined') AS joined
        FROM activity_events GROUP BY mode ORDER BY joined DESC""",
    "affinity": """SELECT target_type,
        sum(pending) AS pending_tasks, sum(running) AS running_tasks,
        sum(done) AS done_tasks, sum(failed) AS failed_tasks,
        round(sum(queue_wait_total_ms) / nullIf(sum(running), 0), 0) AS avg_queue_wait_ms,
        round(sum(runtime_total_ms) / nullIf(sum(done) + sum(failed), 0), 0) AS avg_runtime_ms
        FROM affinity_rollups FINAL GROUP BY target_type ORDER BY pending_tasks DESC""",
}


class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            return self.send(200, HTML, "text/html; charset=utf-8")
        if self.path in ("/api/health", "/api/metrics"):
            try:
                if self.path == "/api/health":
                    query("SELECT 1 AS ok")
                    result = {"status": "ok"}
                else:
                    result = {name: query(sql) for name, sql in QUERIES.items()}
                return self.send(200, json.dumps(result).encode(), "application/json")
            except (urllib.error.URLError, TimeoutError, ValueError) as exc:
                body = json.dumps({"error": type(exc).__name__}).encode()
                return self.send(503, body, "application/json")
        self.send(404, b"Not found", "text/plain; charset=utf-8")


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
