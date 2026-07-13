from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from support import ROOT, load_top_script


class InstallerTransactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.installer = load_top_script("install_goal_stack.py")

    def seed_old(self, destination: Path) -> None:
        destination.mkdir(parents=True)
        for name in ("goal-backend", "goal-close", "harness-agent"):
            skill = destination / name
            skill.mkdir()
            (skill / "OLD").write_text(name, encoding="utf-8")

    def test_install_replaces_stack_removes_harness_and_keeps_backup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            destination = root / "skills"
            backup_root = root / "backups"
            self.seed_old(destination)
            result = self.installer.install_goal_stack(ROOT, destination, backup_root)
            self.assertTrue(result["ok"])
            self.assertFalse((destination / "harness-agent").exists())
            manifest = json.loads((ROOT / "goal-stack-manifest.json").read_text())
            for name in manifest["skills"]:
                self.assertTrue((destination / name / "SKILL.md").is_file())
            backup = Path(result["backup_dir"])
            self.assertTrue((backup / "harness-agent" / "OLD").is_file())

    def test_post_install_failure_restores_exact_old_managed_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            destination = root / "skills"
            self.seed_old(destination)
            with self.assertRaises(self.installer.InstallError):
                self.installer.install_goal_stack(
                    ROOT, destination, root / "backups", failpoint="after_install"
                )
            self.assertTrue((destination / "harness-agent" / "OLD").is_file())
            self.assertTrue((destination / "goal-backend" / "OLD").is_file())
            self.assertFalse((destination / "goal-preflight").exists())

    def test_mid_swap_failure_restores_exact_old_managed_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            destination = root / "skills"
            self.seed_old(destination)
            with self.assertRaises(self.installer.InstallError):
                self.installer.install_goal_stack(
                    ROOT, destination, root / "backups", failpoint="after_move_old"
                )
            self.assertTrue((destination / "harness-agent" / "OLD").is_file())
            self.assertTrue((destination / "goal-close" / "OLD").is_file())

    def test_after_backup_failure_preserves_existing_install_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            destination = root / "skills"
            self.seed_old(destination)
            manifest = destination / ".goal-stack-manifest.json"
            manifest.write_text('{"old": true}\n', encoding="utf-8")
            with self.assertRaises(self.installer.InstallError):
                self.installer.install_goal_stack(
                    ROOT,
                    destination,
                    root / "backups",
                    failpoint="after_backup",
                )
            self.assertEqual('{"old": true}\n', manifest.read_text(encoding="utf-8"))

    def test_corrupt_backup_is_rejected_before_restore_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            destination = root / "skills"
            self.seed_old(destination)
            result = self.installer.install_goal_stack(
                ROOT, destination, root / "backups"
            )
            backup = Path(result["backup_dir"])
            (backup / "goal-backend" / "OLD").write_text("corrupt", encoding="utf-8")
            before = (destination / "goal-backend" / "SKILL.md").read_text(
                encoding="utf-8"
            )
            with self.assertRaises(self.installer.InstallError):
                self.installer.restore_goal_stack(destination, backup)
            self.assertEqual(
                before,
                (destination / "goal-backend" / "SKILL.md").read_text(encoding="utf-8"),
            )

    def test_retained_backup_can_restore_old_stack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            destination = root / "skills"
            self.seed_old(destination)
            result = self.installer.install_goal_stack(
                ROOT, destination, root / "backups"
            )
            restored = self.installer.restore_goal_stack(
                destination, Path(result["backup_dir"])
            )
            self.assertTrue(restored["ok"])
            self.assertTrue((destination / "harness-agent" / "OLD").is_file())
            self.assertTrue((destination / "goal-backend" / "OLD").is_file())
            self.assertFalse((destination / "goal-preflight").exists())

    def test_restore_failure_rolls_back_to_new_stack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            destination = root / "skills"
            self.seed_old(destination)
            result = self.installer.install_goal_stack(
                ROOT, destination, root / "backups"
            )
            with self.assertRaises(self.installer.InstallError):
                self.installer.restore_goal_stack(
                    destination,
                    Path(result["backup_dir"]),
                    failpoint="after_restore",
                )
            self.assertFalse((destination / "harness-agent").exists())
            self.assertTrue((destination / "goal-preflight" / "SKILL.md").is_file())
            self.assertFalse((destination / "goal-backend" / "OLD").exists())

    def test_restore_rejects_traversing_backup_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            destination = root / "skills"
            self.seed_old(destination)
            victim = root / "victim"
            victim.mkdir()
            (victim / "KEEP").write_text("safe", encoding="utf-8")
            backup = root / "backup"
            backup.mkdir()
            (backup / "backup-manifest.json").write_text(
                json.dumps(
                    {
                        "schema": "goal-stack-backup/v1",
                        "managed": [str(victim)],
                        "present": [str(victim)],
                        "digests": {},
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(self.installer.InstallError):
                self.installer.restore_goal_stack(destination, backup)
            self.assertTrue((victim / "KEEP").is_file())

    def test_restore_ignores_untrusted_current_manifest_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            destination = root / "skills"
            self.seed_old(destination)
            result = self.installer.install_goal_stack(
                ROOT, destination, root / "backups"
            )
            victim = root / "victim"
            victim.mkdir()
            (victim / "KEEP").write_text("safe", encoding="utf-8")
            (destination / ".goal-stack-manifest.json").write_text(
                json.dumps(
                    {"schema": "goal-stack-package/v1", "skills": [str(victim)]}
                ),
                encoding="utf-8",
            )
            restored = self.installer.restore_goal_stack(
                destination, Path(result["backup_dir"])
            )
            self.assertTrue(restored["ok"])
            self.assertTrue((victim / "KEEP").is_file())

    def test_dry_run_does_not_mutate_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            destination = root / "skills"
            self.seed_old(destination)
            before = sorted(
                str(path.relative_to(destination)) for path in destination.rglob("*")
            )
            result = self.installer.install_goal_stack(
                ROOT, destination, root / "backups", dry_run=True
            )
            after = sorted(
                str(path.relative_to(destination)) for path in destination.rglob("*")
            )
            self.assertTrue(result["ok"])
            self.assertEqual(before, after)
            self.assertFalse((root / "backups").exists())

    def test_symlinked_managed_entry_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            destination = root / "skills"
            destination.mkdir()
            outside = root / "outside"
            outside.mkdir()
            (destination / "goal-backend").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(self.installer.InstallError):
                self.installer.install_goal_stack(ROOT, destination, root / "backups")
            self.assertTrue((destination / "goal-backend").is_symlink())

    def test_symlinked_destination_ancestor_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            actual = root / "actual"
            destination = actual / "skills"
            destination.mkdir(parents=True)
            linked = root / "linked"
            linked.symlink_to(actual, target_is_directory=True)
            with self.assertRaises(self.installer.InstallError):
                self.installer.install_goal_stack(
                    ROOT,
                    linked / "skills",
                    root / "backups",
                )

    def test_existing_lock_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            destination = root / "skills"
            destination.mkdir()
            lock = destination / ".goal-stack-install.lock"
            lock.write_text("busy", encoding="utf-8")
            with self.assertRaises(self.installer.InstallError):
                self.installer.install_goal_stack(ROOT, destination, root / "backups")

    def test_manifest_path_traversal_is_rejected_before_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            (source / "goal-stack-manifest.json").write_text(
                json.dumps(
                    {
                        "schema": "goal-stack-package/v1",
                        "version": "bad",
                        "skills": ["../escape"],
                    }
                ),
                encoding="utf-8",
            )
            destination = root / "skills"
            self.seed_old(destination)
            with self.assertRaises(self.installer.InstallError):
                self.installer.install_goal_stack(source, destination, root / "backups")
            self.assertTrue((destination / "harness-agent" / "OLD").is_file())


if __name__ == "__main__":
    unittest.main()
