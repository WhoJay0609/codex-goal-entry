from __future__ import annotations

import json
import unittest

from support import ROOT


class PackageContractTests(unittest.TestCase):
    def test_manifest_lists_goal_family_and_public_entry(self) -> None:
        manifest = json.loads((ROOT / "goal-stack-manifest.json").read_text())
        self.assertEqual(
            [
                "goal-preflight",
                "goal-context",
                "goal-objective",
                "goal-plan",
                "goal-dispatch",
                "goal-team",
                "goal-backend",
                "goal-trace",
                "goal-metadata",
                "goal-close",
            ],
            manifest["skills"],
        )
        self.assertEqual("goal-entry", manifest["public_entry"])
        self.assertIn("name: goal-entry", (ROOT / "SKILL.md").read_text())

    def test_each_manifest_skill_has_matching_frontmatter_name(self) -> None:
        manifest = json.loads((ROOT / "goal-stack-manifest.json").read_text())
        for name in manifest["skills"]:
            text = (ROOT / "skills" / name / "SKILL.md").read_text()
            self.assertIn(f"name: {name}", text)


if __name__ == "__main__":
    unittest.main()
