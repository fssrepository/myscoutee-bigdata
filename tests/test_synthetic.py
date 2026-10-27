import importlib.util
import unittest
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "producer" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SyntheticDataTest(unittest.TestCase):
    def test_activity_funnel_has_valid_transitions(self):
        rows = list(load("generate").make_events(
            300, 30, 42, datetime(2026, 10, 27, tzinfo=timezone.utc), "demo"))
        by_actor = defaultdict(list)
        for row in rows:
            by_actor[row["actor_id"]].append(row["event_key"])
        created_at = {row["activity_id"]: row["occurred_at"] for row in rows if row["event_key"] == "event.created"}
        self.assertEqual(len(rows), len({row["event_id"] for row in rows}))
        self.assertEqual(300, sum(row["event_key"] == "profile.registered" for row in rows))
        for states in by_actor.values():
            if "event.member.joined" in states:
                self.assertLess(states.index("profile.onboarding"), states.index("event.member.joined"))
            if "event.member.removed" in states:
                self.assertLess(states.index("event.member.joined"), states.index("event.member.removed"))
        self.assertTrue(all(created_at[row["activity_id"]] <= row["occurred_at"]
                            for row in rows if row["event_key"] == "event.member.joined"))

    def test_affinity_tasks_have_one_terminal_transition(self):
        rows = list(load("affinity").make_tasks(200, 42, "demo"))
        self.assertEqual(600, len(rows))
        by_task = defaultdict(list)
        for row in rows:
            by_task[row["task_id"]].append(row)
        self.assertEqual(200, len(by_task))
        for states in by_task.values():
            self.assertEqual(["pending", "running"], [x["status"] for x in states[:2]])
            self.assertIn(states[2]["status"], ("done", "failed"))
            self.assertGreater(states[1]["queue_wait_ms"], 0)
            self.assertGreater(states[2]["runtime_ms"], 0)
            self.assertEqual({"task_id", "group_id", "target_type", "status", "queue_wait_ms", "runtime_ms"}, set(states[0]))


if __name__ == "__main__":
    unittest.main()
