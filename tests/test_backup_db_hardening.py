"""
tests/test_backup_db_hardening.py — U1-U4 (รีวิว tools 14 ต.ค. 2026)
ไม่พึ่ง pipe/mysqldump จริง จึงรันผ่านบน Windows ได้ (ใช้ Popen ปลอม)
"""
from __future__ import annotations

import gzip
import json
import os
import subprocess
import time

import pytest

from tools import backup_db
from tools.backup_db import BackupError


def _gz(path, text: str) -> None:
    with gzip.open(path, "wb") as f:
        f.write(text.encode())


# ---- U4: ตรวจว่า dump ครบ ----
def test_verify_dump_complete_accepts_marker_with_trailing_blank_lines(tmp_path):
    p = tmp_path / "a.sql.gz"
    _gz(p, "INSERT 1;\n-- Dump completed on 2026-10-14 03:30:00\n\n\n")
    backup_db.verify_dump_complete(p)


def test_verify_dump_complete_rejects_missing_marker(tmp_path):
    p = tmp_path / "a.sql.gz"
    _gz(p, "-- Dump completed on x\nINSERT INTO t VALUES (1);\n")  # marker ไม่ใช่บรรทัดสุดท้าย
    with pytest.raises(BackupError, match="ไม่ครบ"):
        backup_db.verify_dump_complete(p)


def test_verify_dump_complete_rejects_truncated_gzip(tmp_path):
    p = tmp_path / "a.sql.gz"
    _gz(p, "x" * 100000 + "\n-- Dump completed\n")
    data = p.read_bytes()
    p.write_bytes(data[: len(data) // 2])
    with pytest.raises(BackupError):
        backup_db.verify_dump_complete(p)


def test_verify_dump_complete_large_stream_reads_only_tail(tmp_path):
    p = tmp_path / "big.sql.gz"
    _gz(p, ("INSERT INTO t VALUES (1);\n" * 200000) + "-- Dump completed on y\n")
    backup_db.verify_dump_complete(p)


# ---- U3/U4: Popen ปลอม ----
class _FakeStdout:
    def close(self):
        pass


class _HangingProc:
    killed = False

    def __init__(self, *a, **kw):
        self.stdout = _FakeStdout()
        self.returncode = None
        self._first = True

    def communicate(self, timeout=None):
        if self._first and not type(self).killed:
            self._first = False
            raise subprocess.TimeoutExpired("fake", timeout)
        return b"", b""

    def kill(self):
        type(self).killed = True
        self.returncode = -9


def test_dump_timeout_kills_processes_and_cleans_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(backup_db.shutil, "which", lambda b: b)
    monkeypatch.setattr(backup_db.subprocess, "Popen", _HangingProc)
    _HangingProc.killed = False
    flags = []
    real_open = os.open

    def spy(path, fl, mode=0o777, *a, **kw):
        flags.append((fl, mode))
        return real_open(path, fl, mode)

    monkeypatch.setattr(backup_db.os, "open", spy)
    out = tmp_path / "x.sql.gz"
    with pytest.raises(BackupError, match="เกินเวลา"):
        backup_db.dump_database("db", "h", 1, "u", "p", out, timeout=1)
    assert _HangingProc.killed
    assert not out.exists() and not (tmp_path / "x.sql.gz.tmp").exists()
    # U4: สร้าง tmp ด้วย O_EXCL + 0600
    assert flags and flags[0][0] & os.O_EXCL and flags[0][1] == 0o600


def test_timeout_from_env(monkeypatch):
    monkeypatch.setenv("BACKUP_TIMEOUT_SEC", "42")
    assert backup_db._timeout_from_env() == 42
    monkeypatch.setenv("BACKUP_TIMEOUT_SEC", "abc")
    assert backup_db._timeout_from_env() == backup_db.DEFAULT_BACKUP_TIMEOUT_SEC


class _OkProc:
    def __init__(self, *a, **kw):
        self.stdout = _FakeStdout()
        self.returncode = 0

    def communicate(self, timeout=None):
        return b"", b""


def test_dump_without_completion_marker_is_rejected_and_not_renamed(tmp_path, monkeypatch):
    monkeypatch.setattr(backup_db.shutil, "which", lambda b: b)
    monkeypatch.setattr(backup_db.subprocess, "Popen", _OkProc)
    out = tmp_path / "x.sql.gz"
    # Popen ปลอมไม่เขียนอะไร -> tmp ว่าง (ไม่ใช่ gzip) = ไม่ครบ
    with pytest.raises(BackupError):
        backup_db.dump_database("db", "h", 1, "u", "p", out)
    assert not out.exists() and not (tmp_path / "x.sql.gz.tmp").exists()


# ---- U1: prune offsite แม้ copy ล้ม + ลบ .tmp ค้าง ----
def _age(path, days):
    t = time.time() - days * 86400
    os.utime(path, (t, t))


def test_run_prunes_offsite_even_when_offsite_copy_fails(tmp_path, monkeypatch):
    local, off = tmp_path / "local", tmp_path / "usb"
    local.mkdir(); off.mkdir()
    old_off = off / "cafewifi-old.sql.gz"; old_off.write_bytes(b"x"); _age(old_off, 30)
    stale_tmp = off / "cafewifi-z.sql.gz.tmp"; stale_tmp.write_bytes(b"x"); _age(stale_tmp, 3)
    fresh_tmp = off / "cafewifi-y.sql.gz.tmp"; fresh_tmp.write_bytes(b"x")
    stale_local = local / "cafewifi-q.sql.gz.tmp"; stale_local.write_bytes(b"x"); _age(stale_local, 3)

    def fake_dump(out_path, **kw):
        _gz(out_path, "-- Dump completed\n")
        return out_path

    monkeypatch.setattr(backup_db, "dump_database", fake_dump)
    monkeypatch.setattr(backup_db, "copy_offsite", lambda *a, **kw: None)  # USB เต็ม
    res = backup_db.run(backup_dir=local, keep_days=14, offsite_dir=str(off))
    assert res.offsite_path is None
    assert not old_off.exists() and not stale_tmp.exists() and not stale_local.exists()
    assert fresh_tmp.exists(), ".tmp ใหม่อาจเป็นงานที่กำลังเขียนอยู่ ห้ามลบ"


def test_run_does_not_raise_when_offsite_dir_missing(tmp_path, monkeypatch):
    def fake_dump(out_path, **kw):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        _gz(out_path, "-- Dump completed\n")
        return out_path

    monkeypatch.setattr(backup_db, "dump_database", fake_dump)
    monkeypatch.setattr(backup_db, "copy_offsite", lambda *a, **kw: None)
    res = backup_db.run(backup_dir=tmp_path / "local", keep_days=14,
                        offsite_dir=str(tmp_path / "not-mounted" / "x"))
    assert res.path.exists()


def test_prune_dir_safely_swallows_oserror(tmp_path, monkeypatch):
    def boom(*a, **kw):
        raise OSError(19, "No such device")

    monkeypatch.setattr(backup_db, "prune_old_backups", boom)
    assert backup_db._prune_dir_safely(tmp_path, 14) == 0


# ---- U2: main() จับ ValueError/OSError + เขียน status ----
@pytest.mark.parametrize("exc", [ValueError("bad int"), OSError(28, "No space"), BackupError("x")])
def test_main_writes_failure_status_and_exits_nonzero(tmp_path, monkeypatch, exc):
    monkeypatch.setenv("LOG_DIR", str(tmp_path))

    def boom():
        raise exc

    monkeypatch.setattr(backup_db, "run", boom)
    assert backup_db.main() == 1
    data = json.loads((tmp_path / "backup-status.json").read_text(encoding="utf-8"))
    assert data["ok"] is False and data["error"]
