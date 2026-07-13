from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from check_goal_stack import (
    SKILL_NAME_RE,
    check_installed,
    check_source,
    load_manifest,
    tree_digest,
)


class InstallError(RuntimeError):
    pass


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _canonical_no_symlink_path(path: Path) -> Path:
    absolute = Path(os.path.abspath(str(path.expanduser())))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.is_symlink():
            raise InstallError(f"symlinked path component is not allowed: {current}")
    return absolute


def _ensure_plain_owned_directory(
    path: Path, *, create: bool = False, mode: int = 0o700
) -> None:
    _canonical_no_symlink_path(path)
    if create:
        path.mkdir(parents=True, exist_ok=True, mode=mode)
        _canonical_no_symlink_path(path)
    if not path.is_dir():
        raise InstallError(f"directory missing: {path}")
    if hasattr(os, "getuid") and path.stat().st_uid != os.getuid():
        raise InstallError(f"directory is not owned by current user: {path}")


def _reject_symlinks(root: Path) -> None:
    if root.is_symlink():
        raise InstallError(f"symlinked managed entry is not allowed: {root}")
    if not root.exists():
        return
    paths = [root, *root.rglob("*")]
    for path in paths:
        if path.is_symlink():
            raise InstallError(f"symlinked managed path is not allowed: {path}")
        if hasattr(os, "getuid") and path.stat().st_uid != os.getuid():
            raise InstallError(f"managed path is not owned by current user: {path}")


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_names(values: Any, *, label: str) -> List[str]:
    if not isinstance(values, list):
        raise InstallError(f"{label} must be a unique list")
    names: List[str] = []
    for value in values:
        if not isinstance(value, str) or not SKILL_NAME_RE.fullmatch(value):
            raise InstallError(f"invalid {label} entry: {value!r}")
        names.append(value)
    if len(names) != len(set(names)):
        raise InstallError(f"{label} must be a unique list")
    return names


def _snapshot_managed(destination: Path, names: List[str]) -> Dict[str, Any]:
    entries: Dict[str, Optional[str]] = {}
    for name in names:
        current = destination / name
        if current.exists() or current.is_symlink():
            if not current.is_dir() or current.is_symlink():
                raise InstallError(f"managed entry is not a plain directory: {current}")
            _reject_symlinks(current)
            entries[name] = tree_digest(current)
        else:
            entries[name] = None
    manifest = destination / ".goal-stack-manifest.json"
    if manifest.exists() or manifest.is_symlink():
        if not manifest.is_file() or manifest.is_symlink():
            raise InstallError(f"installed manifest is not a plain file: {manifest}")
        if hasattr(os, "getuid") and manifest.stat().st_uid != os.getuid():
            raise InstallError(
                f"installed manifest is not owned by current user: {manifest}"
            )
        manifest_digest: Optional[str] = _file_digest(manifest)
    else:
        manifest_digest = None
    return {"entries": entries, "manifest_digest": manifest_digest}


def _load_backup_manifest(backup: Path) -> Dict[str, Any]:
    try:
        manifest = json.loads(
            (backup / "backup-manifest.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise InstallError(f"invalid backup manifest: {exc}") from exc
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema") != "goal-stack-backup/v1"
    ):
        raise InstallError("invalid backup manifest")
    managed = _validate_names(manifest.get("managed"), label="managed")
    present = _validate_names(manifest.get("present"), label="present")
    expected_managed = _managed_names(Path(__file__).resolve().parents[1])
    if managed != expected_managed:
        raise InstallError(
            "backup managed entries do not match this Goal stack package"
        )
    if not set(present).issubset(managed):
        raise InstallError("backup present entries must be a subset of managed entries")
    digests = manifest.get("digests")
    if not isinstance(digests, dict) or set(digests) != set(present):
        raise InstallError("backup digests must cover every present entry exactly")
    for name, digest in digests.items():
        if not isinstance(digest, str) or len(digest) != 64:
            raise InstallError(f"invalid backup digest for {name}")
    manifest["managed"] = managed
    manifest["present"] = present
    return manifest


def _verify_backup(backup: Path) -> Dict[str, Any]:
    _reject_symlinks(backup)
    manifest = _load_backup_manifest(backup)
    for name in manifest["present"]:
        entry = backup / name
        if not entry.is_dir() or entry.is_symlink():
            raise InstallError(f"backup entry missing or symlinked: {name}")
        _reject_symlinks(entry)
        if tree_digest(entry) != manifest["digests"][name]:
            raise InstallError(f"backup entry digest mismatch: {name}")
    old_manifest = backup / ".goal-stack-manifest.json"
    expected_manifest_digest = manifest.get("manifest_digest")
    if expected_manifest_digest is None:
        if old_manifest.exists() or old_manifest.is_symlink():
            raise InstallError("unexpected installed manifest in backup")
    elif (
        not old_manifest.is_file()
        or old_manifest.is_symlink()
        or _file_digest(old_manifest) != expected_manifest_digest
    ):
        raise InstallError("backup installed manifest digest mismatch")
    return manifest


def _managed_names(source: Path) -> List[str]:
    manifest = load_manifest(source)
    return list(manifest["skills"]) + ["harness-agent"]


def _copy_directory(source: Path, destination: Path) -> None:
    _reject_symlinks(source)
    shutil.copytree(source, destination, symlinks=False)


def _acquire_lock(destination: Path) -> tuple[int, Path]:
    lock = destination / ".goal-stack-install.lock"
    descriptor: Optional[int] = None
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise InstallError(f"Goal stack install lock is already held: {lock}") from exc
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(descriptor)
    except BaseException:
        os.close(descriptor)
        try:
            lock.unlink()
        except FileNotFoundError:
            pass
        raise
    return descriptor, lock


def _release_lock(descriptor: Optional[int], lock: Optional[Path]) -> None:
    identity = os.fstat(descriptor) if descriptor is not None else None
    if descriptor is not None:
        os.close(descriptor)
    if lock is not None:
        try:
            current = os.lstat(lock)
            if identity is not None and (current.st_dev, current.st_ino) == (
                identity.st_dev,
                identity.st_ino,
            ):
                lock.unlink()
        except FileNotFoundError:
            pass


def install_goal_stack(
    source: Path,
    destination: Path,
    backup_root: Path,
    *,
    dry_run: bool = False,
    failpoint: Optional[str] = None,
) -> Dict[str, Any]:
    source = source.resolve()
    source_result = check_source(source)
    if not source_result["ok"]:
        raise InstallError(
            "source package invalid: " + "; ".join(source_result["errors"])
        )
    destination = _canonical_no_symlink_path(destination)
    backup_root = _canonical_no_symlink_path(backup_root)
    _ensure_plain_owned_directory(destination, create=False)
    names = _managed_names(source)
    for name in names:
        _reject_symlinks(destination / name)
    lock_path = destination / ".goal-stack-install.lock"
    if lock_path.exists() or lock_path.is_symlink():
        raise InstallError(f"Goal stack install lock is already held: {lock_path}")
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "destination": str(destination),
            "skills": names[:-1],
            "remove": ["harness-agent"],
            "source_digest": source_result["source_digest"],
        }

    _ensure_plain_owned_directory(backup_root, create=True)
    os.chmod(backup_root, 0o700)
    descriptor: Optional[int] = None
    lock: Optional[Path] = None
    transaction_id = uuid.uuid4().hex
    stage = destination / f".goal-stack-stage-{transaction_id}"
    old = destination / f".goal-stack-old-{transaction_id}"
    backup = backup_root / f"goal-stack-backup-{_timestamp()}-{transaction_id[:8]}"
    moved_old: List[str] = []
    installed_new: List[str] = []
    moved_manifest = False
    installed_manifest = False
    before_snapshot: Optional[Dict[str, Any]] = None
    previous_manifest = destination / ".goal-stack-manifest.json"
    try:
        descriptor, lock = _acquire_lock(destination)
        before_snapshot = _snapshot_managed(destination, names)
        stage.mkdir(mode=0o700)
        old.mkdir(mode=0o700)
        backup.mkdir(mode=0o700)
        for name in names[:-1]:
            _copy_directory(source / "skills" / name, stage / name)
        staged_check = check_installed(source, stage)
        if not staged_check["ok"]:
            raise InstallError(
                "staged install invalid: " + "; ".join(staged_check["errors"])
            )

        present: List[str] = []
        for name in names:
            current = destination / name
            if current.exists():
                present.append(name)
                _copy_directory(current, backup / name)
        if previous_manifest.is_file():
            shutil.copy2(previous_manifest, backup / ".goal-stack-manifest.json")
        backup_manifest = {
            "schema": "goal-stack-backup/v1",
            "managed": names,
            "present": present,
            "digests": {name: before_snapshot["entries"][name] for name in present},
            "manifest_digest": before_snapshot["manifest_digest"],
        }
        (backup / "backup-manifest.json").write_text(
            json.dumps(backup_manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.chmod(backup / "backup-manifest.json", 0o600)
        _verify_backup(backup)
        if failpoint == "after_backup":
            raise InstallError("injected failure after_backup")

        for name in names:
            current = destination / name
            if current.exists():
                os.replace(current, old / name)
                moved_old.append(name)
        if previous_manifest.exists():
            os.replace(previous_manifest, old / ".goal-stack-manifest.json")
            moved_manifest = True
        if failpoint == "after_move_old":
            raise InstallError("injected failure after_move_old")
        for name in names[:-1]:
            os.replace(stage / name, destination / name)
            installed_new.append(name)
        shutil.copy2(source / "goal-stack-manifest.json", previous_manifest)
        installed_manifest = True
        if failpoint == "after_install":
            raise InstallError("injected failure after_install")
        installed_check = check_installed(source, destination)
        if not installed_check["ok"]:
            raise InstallError(
                "installed Goal stack invalid: " + "; ".join(installed_check["errors"])
            )
        shutil.rmtree(old)
        shutil.rmtree(stage)
        return {
            "ok": True,
            "dry_run": False,
            "destination": str(destination),
            "backup_dir": str(backup),
            "skills": names[:-1],
            "removed": ["harness-agent"],
            "source_digest": source_result["source_digest"],
        }
    except BaseException as exc:
        rollback_error: Optional[BaseException] = None
        try:
            for name in installed_new:
                current = destination / name
                if current.exists():
                    shutil.rmtree(current)
            if installed_manifest and previous_manifest.exists():
                previous_manifest.unlink()
            for name in moved_old:
                prior = old / name
                if prior.exists():
                    os.replace(prior, destination / name)
            prior_manifest = old / ".goal-stack-manifest.json"
            if moved_manifest and prior_manifest.exists():
                os.replace(prior_manifest, previous_manifest)
            if (
                before_snapshot is not None
                and _snapshot_managed(destination, names) != before_snapshot
            ):
                raise InstallError(
                    "automatic rollback did not restore the exact pre-install state"
                )
        except BaseException as rollback_exc:
            rollback_error = rollback_exc
        finally:
            for temporary in (stage, old):
                if temporary.exists():
                    shutil.rmtree(temporary)
        if rollback_error is not None:
            raise InstallError(
                f"install failed and rollback verification failed: {rollback_error}"
            ) from exc
        if isinstance(exc, InstallError):
            raise
        raise InstallError(str(exc)) from exc
    finally:
        _release_lock(descriptor, lock)


def restore_goal_stack(
    destination: Path,
    backup: Path,
    *,
    failpoint: Optional[str] = None,
) -> Dict[str, Any]:
    destination = _canonical_no_symlink_path(destination)
    backup = _canonical_no_symlink_path(backup)
    _ensure_plain_owned_directory(destination)
    _ensure_plain_owned_directory(backup)
    manifest = _verify_backup(backup)
    managed = manifest["managed"]
    for name in managed:
        _reject_symlinks(destination / name)
    descriptor: Optional[int] = None
    lock: Optional[Path] = None
    transaction_id = uuid.uuid4().hex
    stage = destination / f".goal-stack-restore-stage-{transaction_id}"
    old = destination / f".goal-stack-restore-old-{transaction_id}"
    moved_current: List[str] = []
    installed_backup: List[str] = []
    moved_manifest = False
    installed_manifest = False
    before_snapshot: Optional[Dict[str, Any]] = None
    try:
        descriptor, lock = _acquire_lock(destination)
        before_snapshot = _snapshot_managed(destination, managed)
        stage.mkdir(mode=0o700)
        old.mkdir(mode=0o700)
        for name in manifest["present"]:
            _copy_directory(backup / name, stage / name)
        old_manifest = backup / ".goal-stack-manifest.json"
        if manifest.get("manifest_digest") is not None:
            shutil.copy2(old_manifest, stage / ".goal-stack-manifest.json")

        current_manifest = destination / ".goal-stack-manifest.json"
        for name in managed:
            current = destination / name
            if current.exists():
                os.replace(current, old / name)
                moved_current.append(name)
        if current_manifest.exists():
            os.replace(current_manifest, old / ".goal-stack-manifest.json")
            moved_manifest = True
        if failpoint == "after_move_current":
            raise InstallError("injected restore failure after_move_current")
        for name in manifest["present"]:
            os.replace(stage / name, destination / name)
            installed_backup.append(name)
        staged_manifest = stage / ".goal-stack-manifest.json"
        if staged_manifest.exists():
            os.replace(staged_manifest, current_manifest)
            installed_manifest = True
        if failpoint == "after_restore":
            raise InstallError("injected restore failure after_restore")
        expected = {
            "entries": {name: manifest["digests"].get(name) for name in managed},
            "manifest_digest": manifest.get("manifest_digest"),
        }
        if _snapshot_managed(destination, managed) != expected:
            raise InstallError("restored state does not match retained backup")
        shutil.rmtree(old)
        shutil.rmtree(stage)
        return {"ok": True, "restored": manifest["present"], "backup_dir": str(backup)}
    except BaseException as exc:
        rollback_error: Optional[BaseException] = None
        try:
            for name in installed_backup:
                current = destination / name
                if current.exists():
                    shutil.rmtree(current)
            if (
                installed_manifest
                and (destination / ".goal-stack-manifest.json").exists()
            ):
                (destination / ".goal-stack-manifest.json").unlink()
            for name in moved_current:
                prior = old / name
                if prior.exists():
                    os.replace(prior, destination / name)
            prior_manifest = old / ".goal-stack-manifest.json"
            if moved_manifest and prior_manifest.exists():
                os.replace(prior_manifest, destination / ".goal-stack-manifest.json")
            if (
                before_snapshot is not None
                and _snapshot_managed(destination, managed) != before_snapshot
            ):
                raise InstallError(
                    "restore rollback did not recover the pre-restore state"
                )
        except BaseException as rollback_exc:
            rollback_error = rollback_exc
        finally:
            for temporary in (stage, old):
                if temporary.exists():
                    shutil.rmtree(temporary)
        if rollback_error is not None:
            raise InstallError(
                f"restore failed and rollback verification failed: {rollback_error}"
            ) from exc
        if isinstance(exc, InstallError):
            raise
        raise InstallError(str(exc)) from exc
    finally:
        _release_lock(descriptor, lock)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Transactionally install or restore the private Goal stack."
    )
    parser.add_argument("--source", type=Path, default=Path.cwd())
    parser.add_argument("--destination-root", type=Path, required=True)
    parser.add_argument("--backup-root", type=Path)
    parser.add_argument("--restore-from", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Required for the real ~/.codex/skills root.",
    )
    args = parser.parse_args()
    live_root = (Path.home() / ".codex" / "skills").resolve()
    if args.destination_root.resolve() == live_root and not args.live:
        raise SystemExit("refusing live installation without --live")
    if args.restore_from:
        result = restore_goal_stack(args.destination_root, args.restore_from)
    else:
        if args.backup_root is None:
            raise SystemExit("--backup-root is required for installation")
        result = install_goal_stack(
            args.source,
            args.destination_root,
            args.backup_root,
            dry_run=args.dry_run,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
