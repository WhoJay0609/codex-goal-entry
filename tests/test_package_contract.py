from __future__ import annotations

import json
import unittest

from support import ROOT, load_top_script


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

    def test_public_entry_is_model_native_and_package_is_v2(self) -> None:
        skill = (ROOT / "SKILL.md").read_text()
        self.assertIn("goal-entry.model-route.v1", skill)
        self.assertIn("direct", skill)
        self.assertIn("compound", skill)
        self.assertIn("goal", skill)
        self.assertNotIn("scripts/resolve_goal_entry.py", skill)
        version = (ROOT / "VERSION").read_text().strip()
        manifest = json.loads((ROOT / "goal-stack-manifest.json").read_text())
        self.assertEqual("2.0.0", version)
        self.assertEqual(version, manifest["version"])

    def test_source_digest_covers_public_entry_and_goal_family(self) -> None:
        checker = load_top_script("check_goal_stack.py")
        result = checker.check_source(ROOT)
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(checker.package_digest(ROOT), result["source_digest"])
        self.assertNotEqual(
            checker.tree_digest(ROOT / "skills"), result["source_digest"]
        )


if __name__ == "__main__":
    unittest.main()
