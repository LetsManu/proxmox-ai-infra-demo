"""Backup, verify and restore round trip; archives with unsafe entries are refused."""

import io
import os
import sqlite3
import tarfile

import pytest

from app import cli
from app.config import get_settings


def test_backup_restore_round_trip(tmp_path, capsys):
    s = get_settings()
    db = cli._db_path()
    state = os.path.join(s.workspace_dir, "state", "test")
    os.makedirs(state, exist_ok=True)
    with open(os.path.join(state, "terraform.tfstate"), "w") as fh:
        fh.write('{"version": 4, "serial": 7}')
    with sqlite3.connect(db) as con:
        con.execute("INSERT INTO history (timestamp, vm_name, environment, action, status, user, plan_summary) "
                    "VALUES ('2026-10-19', 'backup-marker', 'test', 'plan', 'success', 'anna', '')")
        con.execute("INSERT INTO auth_sessions (token_hash, username, display_name, roles, csrf, provider, created_at, "
                    "expires_at) VALUES ('h', 'anna', '', '[]', 'c', 'ldap', '2026-10-19', '2099-01-01')")
    archive = str(tmp_path / "b.tar.gz")
    cli.backup(archive)
    meta = cli.verify(archive)
    assert "workspace/state/test/terraform.tfstate" in meta["state_files"] and meta["database"]["history"] >= 1

    # lose state and the marker row, then restore
    os.remove(os.path.join(state, "terraform.tfstate"))
    with sqlite3.connect(db) as con:
        con.execute("DELETE FROM history WHERE vm_name = 'backup-marker'")
    from app.database import engine

    engine.dispose()  # the restore replaces the database file
    cli.restore(archive)
    engine.dispose()
    with open(os.path.join(state, "terraform.tfstate")) as fh:
        assert '"serial": 7' in fh.read()
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT count(*) FROM history WHERE vm_name = 'backup-marker'").fetchone()[0] == 1
        assert con.execute("SELECT count(*) FROM auth_sessions").fetchone()[0] == 0  # sessions are never restored


@pytest.mark.parametrize("name", ["../evil", "/etc/passwd", "workspace/../../x", "other/file"])
def test_unsafe_archives_are_refused(tmp_path, name):
    archive = tmp_path / "bad.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        data = b"x"
        info = tarfile.TarInfo(name)
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    with pytest.raises(SystemExit, match="Refusing archive"):
        cli.restore(str(archive))


def test_symlinks_are_refused(tmp_path):
    archive = tmp_path / "link.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        info = tarfile.TarInfo("workspace/state/link")
        info.type, info.linkname = tarfile.SYMTYPE, "/etc/shadow"
        tar.addfile(info)
    with pytest.raises(SystemExit, match="unsafe entry"):
        cli.restore(str(archive))
