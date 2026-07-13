from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from support import ROOT, load_top_script


class InstalledSurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.checker = load_top_script("check_goal_stack.py")
        cls.installer = load_top_script("install_goal_stack.py")

    def test_source_package_is_valid(self) -> None:
        result = self.checker.check_source(ROOT)
        self.assertTrue(result["ok"], result)

    def test_installed_manifest_matches_source_and_has_no_harness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            destination = root / "skills"
            destination.mkdir()
            (destination / "harness-agent").mkdir()
            self.installer.install_goal_stack(ROOT, destination, root / "backups")
            result = self.checker.check_installed(ROOT, destination)
            self.assertTrue(result["ok"], result)
            self.assertFalse((destination / "harness-agent").exists())

    def test_symlinked_installed_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            actual = root / "actual"
            actual.mkdir()
            linked = root / "linked"
            linked.symlink_to(actual, target_is_directory=True)
            result = self.checker.check_installed(ROOT, linked)
            self.assertFalse(result["ok"])
            self.assertIn("destination root is symlinked", result["errors"])


if __name__ == "__main__":
    unittest.main()
