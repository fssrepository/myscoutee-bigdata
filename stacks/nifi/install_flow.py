"""Install and start the synthetic MyScoutee activity validation flow."""

import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


BASE = "https://localhost:8444/nifi-api"
CONTEXT = ssl._create_unverified_context()
USERNAME = os.environ.get("NIFI_LAB_USER", "labuser")
PASSWORD = os.environ.get("NIFI_LAB_PASSWORD", "lab-only-password-123")
FIXTURES = Path(__file__).resolve().parents[2] / "build/stations/nifi-inbox"
# Keep the three processing stages readable while stacking the outputs above
# and below RouteOnAttribute so the complete flow fits a laptop viewport.
LAYOUT = ((0, 0), (600, 0), (1200, 0), (1200, -450), (1200, 500))


def request(method: str, path: str, token: str | None = None, payload=None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if isinstance(payload, dict):
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    else:
        data = payload
        if data is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, context=CONTEXT, timeout=25) as response:
            body = response.read().decode()
            return json.loads(body) if body.startswith("{") else body
    except urllib.error.HTTPError as error:
        raise RuntimeError(
            f"NiFi {method} {path} returned HTTP {error.code}: "
            f"{error.read().decode()[:500]}"
        ) from error


def authenticate() -> str:
    form = urllib.parse.urlencode({"username": USERNAME, "password": PASSWORD}).encode()
    for _ in range(90):
        try:
            return request("POST", "/access/token", payload=form)
        except (urllib.error.URLError, TimeoutError, RuntimeError):
            time.sleep(2)
    raise RuntimeError("NiFi did not become ready within three minutes")


def create_processor(token: str, group: str, name: str, kind: str, x: int, y: int):
    return request("POST", f"/process-groups/{group}/processors", token, {
        "revision": {"version": 0},
        "component": {
            "type": f"org.apache.nifi.processors.standard.{kind}",
            "name": name,
            "position": {"x": x, "y": y},
        },
    })


def configure(token: str, processor: dict, properties: dict, terminate: list[str] | None = None):
    component = {"id": processor["id"], "config": {"properties": properties}}
    if terminate is not None:
        component["config"]["autoTerminatedRelationships"] = terminate
    return request("PUT", f"/processors/{processor['id']}", token, {
        "revision": processor["revision"], "component": component,
    })


def place(token: str, processor: dict, x: int, y: int):
    current = request("GET", f"/processors/{processor['id']}", token)
    if current["component"]["position"] == {"x": x, "y": y}:
        return
    request("PUT", f"/processors/{processor['id']}", token, {
        "revision": current["revision"],
        "component": {"id": processor["id"], "position": {"x": x, "y": y}},
    })


def connect(token: str, group: str, source: dict, target: dict, relationships: list[str]):
    return request("POST", f"/process-groups/{group}/connections", token, {
        "revision": {"version": 0},
        "component": {
            "source": {"id": source["id"], "type": "PROCESSOR", "groupId": group},
            "destination": {"id": target["id"], "type": "PROCESSOR", "groupId": group},
            "selectedRelationships": relationships,
        },
    })


def start(token: str, processor: dict):
    current = request("GET", f"/processors/{processor['id']}", token)
    if current["component"]["state"] != "RUNNING":
        request("PUT", f"/processors/{processor['id']}/run-status", token, {
            "revision": current["revision"], "state": "RUNNING"
        })


def main():
    token = authenticate()
    root = request("GET", "/flow/process-groups/root", token)
    group = root["processGroupFlow"]["id"]
    existing = {
        item["component"]["name"]: item
        for item in root["processGroupFlow"]["flow"]["processors"]
    }
    names = ("MyScoutee - Get synthetic events", "MyScoutee - Extract event key",
             "MyScoutee - Route valid events", "MyScoutee - Accepted", "MyScoutee - Rejected")
    if all(name in existing for name in names):
        processors = [existing[name] for name in names]
        route = request("GET", f"/processors/{processors[2]['id']}", token)
        desired = "${event_key:isEmpty():not()}"
        if route["component"]["config"]["properties"].get("valid") != desired:
            if route["component"]["state"] != "STOPPED":
                raise RuntimeError("Stop the existing NiFi route processor before changing it")
            processors[2] = configure(token, route, {"valid": desired})
    elif any(name in existing for name in names):
        raise RuntimeError("Partial NiFi flow exists; inspect it in the UI before retrying")
    else:
        source = create_processor(token, group, names[0], "GetFile", *LAYOUT[0])
        check = create_processor(token, group, names[1], "EvaluateJsonPath", *LAYOUT[1])
        route = create_processor(token, group, names[2], "RouteOnAttribute", *LAYOUT[2])
        accepted = create_processor(token, group, names[3], "PutFile", *LAYOUT[3])
        rejected = create_processor(token, group, names[4], "PutFile", *LAYOUT[4])
        source = configure(token, source, {
            "Input Directory": "/opt/lab/inbox",
            "Keep Source File": "false",
            "File Filter": ".*\\.json",
        })
        check = configure(token, check, {
            "Destination": "flowfile-attribute",
            "Path Not Found Behavior": "skip",
            "event_key": "$.event_key",
        }, ["unmatched"])
        route = configure(token, route, {"valid": "${event_key:isEmpty():not()}"})
        accepted = configure(token, accepted, {
            "Directory": "/opt/lab/output/valid",
            "Conflict Resolution Strategy": "replace",
        }, ["success", "failure"])
        rejected = configure(token, rejected, {
            "Directory": "/opt/lab/output/rejected",
            "Conflict Resolution Strategy": "replace",
        }, ["success", "failure"])
        connect(token, group, source, check, ["success"])
        connect(token, group, check, route, ["matched"])
        connect(token, group, check, rejected, ["failure"])
        connect(token, group, route, accepted, ["valid"])
        connect(token, group, route, rejected, ["unmatched"])
        processors = [source, check, route, accepted, rejected]

    for processor, (x, y) in zip(processors, LAYOUT):
        place(token, processor, x, y)
    for processor in reversed(processors):
        start(token, processor)
    if not FIXTURES.exists():
        raise RuntimeError("Run python3 producer/export.py before installing the NiFi flow")
    print("NiFi flow running. Inspect accepted/rejected files and Data Provenance at https://localhost:8444/nifi")


if __name__ == "__main__":
    main()
