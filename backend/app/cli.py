"""Backup and restore of everything the console cannot rebuild (scripts/backup.sh, scripts/restore.sh).

    python -m app.cli backup  <file|->   database + OpenTofu state + approved roles + SSH host keys
    python -m app.cli verify  <file|->   check an archive without changing anything
    python -m app.cli restore <file|->   replace the current data with an archive (backend stopped)

Not included, because they are rebuilt or are not the console's: provider caches and plan files (re-created by the
next plan), Ansible run directories, and secrets (keep secrets/ in your password manager or vault).
"""

from __future__ import annotations

import io
import json
import os
import shutil
import sqlite3
import sys
import tarfile
import tempfile
from contextlib import closing
from datetime import datetime, timezone

from . import __version__
from .config import get_settings

WORKSPACE_PARTS = ("state", "profiles", "known_hosts")  # under WORKSPACE_DIR
FORMAT = 1


def _db_path() -> str:
    url = get_settings().database_url
    if not url.startswith("sqlite:///"):
        raise SystemExit("Backup supports the built-in SQLite database. For PostgreSQL use pg_dump.")
    return url.replace("sqlite:///", "", 1)


def _running_jobs(db: str) -> int:
    if not os.path.exists(db):
        return 0
    with closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as con:
        try:
            return con.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]
        except sqlite3.OperationalError:
            return 0


def backup(target: str, force: bool = False) -> None:
    s, db = get_settings(), _db_path()
    busy = _running_jobs(db)
    if busy and not force:
        raise SystemExit(f"{busy} job(s) are running; OpenTofu state may change underneath. Wait, or pass --force.")
    out = sys.stdout.buffer if target == "-" else open(target, "wb")
    with tempfile.TemporaryDirectory() as tmp, tarfile.open(fileobj=out, mode="w:gz") as tar:
        snap = os.path.join(tmp, "app.db")
        if os.path.exists(db):  # online backup: consistent even while the backend writes
            src, dst = sqlite3.connect(db), sqlite3.connect(snap)
            try:
                src.backup(dst)
                # sign-in sessions are not restored: everyone signs in again after a restore
                if dst.execute("SELECT 1 FROM sqlite_master WHERE name = 'auth_sessions'").fetchone():
                    dst.execute("DELETE FROM auth_sessions")
                    dst.commit()
                dst.execute("PRAGMA journal_mode=DELETE")  # the copy inherits WAL; fold everything into one file
            finally:
                src.close()
                dst.close()
            tar.add(snap, "data/app.db")
        for part in WORKSPACE_PARTS:
            path = os.path.join(s.workspace_dir, part)
            if os.path.isdir(path):
                tar.add(path, f"workspace/{part}")
        meta = json.dumps({"format": FORMAT, "version": __version__, "created": datetime.now(timezone.utc).isoformat(),
                           "parts": ["data/app.db", *[f"workspace/{p}" for p in WORKSPACE_PARTS]]}, indent=1).encode()
        info = tarfile.TarInfo("backup.json")
        info.size, info.mtime = len(meta), int(datetime.now().timestamp())
        tar.addfile(info, io.BytesIO(meta))
    if out is not sys.stdout.buffer:
        out.close()
        print(f"Backup written to {target}", file=sys.stderr)


def _members(tar: tarfile.TarFile) -> list[tarfile.TarInfo]:
    """Only regular files and directories under data/ and workspace/<part>/; no links, no '..', no absolute paths."""
    allowed = ("backup.json", "data/app.db", *[f"workspace/{p}" for p in WORKSPACE_PARTS])
    members = []
    for m in tar.getmembers():
        name = m.name
        if name.startswith("/") or ".." in name.split("/") or not (m.isfile() or m.isdir()):
            raise SystemExit(f"Refusing archive: unsafe entry {name!r}")
        if not any(name == a or name.startswith(a + "/") for a in allowed):
            raise SystemExit(f"Refusing archive: unexpected entry {name!r}")
        members.append(m)
    return members


def _open(source: str) -> tarfile.TarFile:
    if source == "-":
        return tarfile.open(fileobj=io.BytesIO(sys.stdin.buffer.read()), mode="r:gz")
    return tarfile.open(source, mode="r:gz")


def verify(source: str) -> dict:
    with _open(source) as tar:
        members = _members(tar)
        meta = json.load(tar.extractfile("backup.json"))
        if meta.get("format") != FORMAT:
            raise SystemExit(f"Unknown backup format {meta.get('format')}")
        with tempfile.TemporaryDirectory() as tmp:
            tar.extract("data/app.db", tmp, filter="data")
            with closing(sqlite3.connect(os.path.join(tmp, "data/app.db"))) as con:
                ok = con.execute("PRAGMA integrity_check").fetchone()[0]
                counts = {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]  # noqa: S608 (fixed names)
                          for t in ("virtual_machines", "stacks", "history")}
        states = sorted(m.name for m in members if m.name.endswith(".tfstate"))
    if ok != "ok":
        raise SystemExit(f"Database in the archive is damaged: {ok}")
    result = {**meta, "database": counts, "state_files": states}
    print(json.dumps(result, indent=1))
    return result


def restore(source: str) -> None:
    s, db = get_settings(), _db_path()
    data = sys.stdin.buffer.read() if source == "-" else None
    src = (lambda: tarfile.open(fileobj=io.BytesIO(data), mode="r:gz")) if data is not None else \
        (lambda: tarfile.open(source, mode="r:gz"))
    with src() as tar:
        members = _members(tar)
        with tempfile.TemporaryDirectory(dir=os.path.dirname(db) or None) as tmp:
            tar.extractall(tmp, members=members, filter="data")
            restored_db = os.path.join(tmp, "data", "app.db")
            with closing(sqlite3.connect(restored_db)) as con:
                if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise SystemExit("Database in the archive is damaged; nothing was changed.")
            for suffix in ("", "-wal", "-shm"):
                if os.path.exists(db + suffix):
                    os.remove(db + suffix)
            shutil.move(restored_db, db)
            for part in WORKSPACE_PARTS:
                dest = os.path.join(s.workspace_dir, part)
                shutil.rmtree(dest, ignore_errors=True)
                if os.path.isdir(os.path.join(tmp, "workspace", part)):
                    shutil.copytree(os.path.join(tmp, "workspace", part), dest)
    # plans made before the restore no longer match the restored state
    for env in ("test", "prod", "platform"):
        shutil.rmtree(os.path.join(s.workspace_dir, env, "plans"), ignore_errors=True)
    print("Restore complete. Start the console again; then plan once per environment to check state against Proxmox.",
          file=sys.stderr)


def main(argv: list[str]) -> None:
    if len(argv) < 2 or argv[0] not in ("backup", "verify", "restore"):
        raise SystemExit(__doc__)
    cmd, target = argv[0], argv[1]
    if cmd == "backup":
        backup(target, force="--force" in argv[2:])
    elif cmd == "verify":
        verify(target)
    else:
        restore(target)


if __name__ == "__main__":
    main(sys.argv[1:])
