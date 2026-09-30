"""Recoverable, per-file atomic installation writes.

The journal is saved before target writes. Recovery refuses to overwrite edits
made after interruption. Callers must serialize installation into one checkout.
"""

import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import uuid
import sys
from contextlib import contextmanager

JOURNAL = ".specify/engineering-transaction"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def atomic_copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as handle:
            temporary = Path(handle.name)
            with source.open("rb") as original:
                shutil.copyfileobj(original, handle)
            handle.flush()
            os.fsync(handle.fileno())
        shutil.copystat(source, temporary)
        temporary.replace(target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def checked_path(target, relative):
    target = Path(target).resolve()
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise RuntimeError("Invalid installation recovery path")
    path = target / path
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise RuntimeError(f"Refusing installation through symlink: {path}")
    if path.exists() and not path.is_file():
        raise RuntimeError(f"Installation path is not a regular file: {path}")
    return path


def lock_functions(handle, *, windows):
    if windows:
        import msvcrt

        return (
            lambda: msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1),
            lambda: msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1),
        )
    import fcntl

    return (
        lambda: fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB),
        lambda: fcntl.flock(handle.fileno(), fcntl.LOCK_UN),
    )


@contextmanager
def installation_lock(target):
    """Persistent lock inode; the OS releases ownership on process exit."""
    path = checked_path(target, ".specify/engineering-install.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        lock, unlock = lock_functions(handle, windows=os.name == "nt")
        try:
            lock()
        except OSError as error:
            raise RuntimeError("Another installer owns this checkout; retry when it exits.") from error
        try:
            yield
        finally:
            handle.seek(0)
            unlock()


def write_manifest(journal, entries, phase):
    temporary = journal / "manifest.pending"
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump({"schema_version": "2.0", "phase": phase, "entries": entries}, handle)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(journal / "manifest.json")


def cleanup_retired(target):
    for path in (target / ".specify").glob("engineering-retired-*"):
        if path.is_symlink() or not path.is_dir():
            continue
        try:
            shutil.rmtree(path)
        except OSError as error:
            print(f"Installation recovery is complete; cleanup deferred for {path}: {error}", file=sys.stderr)


def retire(target, journal):
    # Once renamed, partial deletion can never look like an active transaction.
    journal.rename(journal.with_name("engineering-retired-" + uuid.uuid4().hex))
    cleanup_retired(target)


def recover(target, apply=False):
    target = Path(target).resolve()
    journal = target / JOURNAL
    if not journal.exists() and not journal.is_symlink():
        return
    if not apply:
        raise RuntimeError("Interrupted installation found; rerun with --apply to recover before planning.")
    with installation_lock(target):
        recover_locked(target)


def recover_locked(target):
    target = Path(target).resolve()
    journal = target / JOURNAL
    cleanup_retired(target)
    if not journal.exists() and not journal.is_symlink():
        return
    if journal.is_symlink() or any(p.is_symlink() for p in journal.parents):
        raise RuntimeError("Refusing symlink installation journal")
    if (journal / "owner").exists():
        raise RuntimeError(
            f"Legacy installation journal at {journal}; stop any old installer and reconcile it manually before removal."
        )
    manifest = checked_path(journal, "manifest.json")
    if not manifest.exists():
        retire(target, journal)  # Snapshot preparation never writes destinations.
        return
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if (
        not isinstance(data, dict)
        or data.get("schema_version") != "2.0"
        or data.get("phase") not in ("prepared", "committed", "rolled_back")
        or not isinstance(data.get("entries"), list)
    ):
        raise RuntimeError(f"Invalid installation journal: {manifest}")
    if data["phase"] in ("committed", "rolled_back"):
        retire(target, journal)
        return
    entries = data["entries"]
    # Validate everything before restoring anything, including snapshot integrity.
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"path", "before", "after", "backup"}:
            raise RuntimeError(f"Invalid installation journal: {manifest}")
        if (
            not isinstance(entry["path"], str)
            or not isinstance(entry["backup"], str)
            or any(
                value is not None
                and (not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value))
                for value in (entry["before"], entry["after"])
            )
        ):
            raise RuntimeError(f"Invalid installation journal: {manifest}")
        path = checked_path(target, entry["path"])
        if digest(path) not in (entry["before"], entry["after"]):
            raise RuntimeError(f"Recovery would overwrite an edited file: {path}; reconcile it with {journal} first.")
        if entry["before"] is not None:
            backup = checked_path(journal, entry["backup"])
            if digest(backup) != entry["before"]:
                raise RuntimeError(f"Damaged installation backup: {backup}")
    for entry in reversed(entries):
        path = checked_path(target, entry["path"])
        if entry["before"] is None:
            path.unlink(missing_ok=True)
        else:
            atomic_copy(journal / entry["backup"], path)
    write_manifest(journal, entries, "rolled_back")
    retire(target, journal)


def apply_writes(target, writes, *, expected=None):
    target = Path(target).resolve()
    with installation_lock(target):
        recover_locked(target)
        if expected is not None:
            for relative, before in expected.items():
                if digest(checked_path(target, relative)) != before:
                    raise RuntimeError(f"File changed after installation planning: {relative}; retry installation.")
        apply_writes_locked(target, writes, expected=expected)


def apply_writes_locked(target, writes, *, expected=None):
    """Map repository-relative paths to staged source files, or None for deletion."""
    target = Path(target).resolve()
    journal = target / JOURNAL
    if any(p.is_symlink() for p in (journal, *journal.parents)):
        raise RuntimeError("Refusing symlink installation journal")
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.mkdir()  # An existing journal must be recovered, never overwritten.
    entries = []
    prepared = False
    try:
        for number, (relative, source) in enumerate(writes.items()):
            path = checked_path(target, relative)
            backup = f"{number}.original"
            before = digest(path)
            if expected is not None and relative in expected and before != expected[relative]:
                raise RuntimeError(f"File changed after installation planning: {relative}")
            if before is not None:
                atomic_copy(path, journal / backup)
            entries.append(
                {
                    "path": relative,
                    "before": before,
                    "after": digest(source) if source is not None else None,
                    "backup": backup,
                }
            )
        write_manifest(journal, entries, "prepared")
        prepared = True
        for entry in entries:
            path = checked_path(target, entry["path"])
            if digest(path) != entry["before"]:
                raise RuntimeError(f"File changed during installation: {path}")
            source = writes[entry["path"]]
            if source is None:
                path.unlink(missing_ok=True)
            else:
                atomic_copy(source, path)
    except Exception:
        if prepared:
            recover_locked(target)
        else:
            retire(target, journal)
        raise
    write_manifest(journal, entries, "committed")
    retire(target, journal)
