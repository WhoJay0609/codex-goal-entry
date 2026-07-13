from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from support import load_script, write_json


def digest_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


class LegacyTraceCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_script("read_legacy_trace.py")

    def make_trace(self, root: Path, observed: bool = True) -> None:
        write_json(
            root / "manifest.json",
            {
                "schema_version": 2,
                "run_id": "legacy-1",
                "mode": "standard_harness",
                "termination": {"status": "goal_met"},
            },
        )
        rows = [
            {"event_type": "tool_call", "tool_call_id": "call-1", "status": "completed"}
        ]
        if observed:
            rows.append(
                {
                    "event_type": "tool_observation",
                    "tool_call_id": "call-1",
                    "status": "completed",
                }
            )
        (root / "events.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
        )

    def test_supported_legacy_trace_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_trace(root)
            before = digest_tree(root)
            result = self.module.read_legacy_trace(root)
            after = digest_tree(root)
            self.assertEqual("supported", result["status"])
            self.assertEqual(before, after)
            self.assertFalse(result["replay_supported"])
            self.assertNotIn("dispatch_authority", result)

    def test_missing_observation_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_trace(root, observed=False)
            result = self.module.read_legacy_trace(root)
            self.assertEqual("invalid", result["status"])

    def test_missing_optional_events_is_partial(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(
                root / "manifest.json", {"schema_version": 2, "run_id": "legacy-2"}
            )
            result = self.module.read_legacy_trace(root)
            self.assertEqual("partial", result["status"])


if __name__ == "__main__":
    unittest.main()
