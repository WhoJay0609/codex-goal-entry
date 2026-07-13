from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from support import load_metadata_script


class MetadataInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_metadata_script("update_skill_inventory.py")

    def test_quoted_frontmatter_names_are_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skills = root / "skills"
            skill = skills / "analyze-results"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                '---\nname: "analyze-results"\ndescription: test\n---\n',
                encoding="utf-8",
            )
            registry = root / "families.json"
            registry.write_text(
                json.dumps(
                    {
                        "global_deny": {"skills": [], "goal_tools": [], "prefixes": []},
                        "families": {"research": {"skills": ["analyze-results"]}},
                    }
                ),
                encoding="utf-8",
            )
            result = self.module.build_inventory(skills, registry)
            self.assertEqual(["analyze-results"], result["installed"])
            self.assertEqual(["analyze-results"], result["registered"])
            self.assertEqual([], result["unregistered"])


if __name__ == "__main__":
    unittest.main()
