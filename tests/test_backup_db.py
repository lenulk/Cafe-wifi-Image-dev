"""
T-Backup — tools/backup_db.py (แก้บั๊ก H4: เดิมไม่มี backup DB เลยในระบบ)

รันจริงด้วย `sh` + `gzip` ตัวจริง (ไม่ mock subprocess) โดยแกล้งเป็น mysqldump ด้วยสคริปต์
ปลอมที่พิมพ์ข้อความคงที่ออก stdout -- ทดสอบ pipe จริง ไม่ใช่แค่ตรรกะล้วน ๆ เพราะบั๊กประเภทนี้
(subprocess.run(stdout=gzip.GzipFile(...)) เขียนข้อมูลดิบทับไฟล์ ไม่ผ่านการบีบอัดจริง)
ตรวจจับไม่ได้ด้วย mock -- ต้องรันจริงถึงจะเห็น
"""
import gzip
import os
import shutil
import stat
from pathlib import Path

import pytest

from tools.backup_db import BackupError, copy_offsite, dump_database, prune_old_backups, run

pytestmark = pytest.mark.skipif(
    shutil.which("sh") is None or shutil.which("gzip") is None,
    reason="ทดสอบนี้ต้องมี sh และ gzip จริงในระบบ (มีอยู่แล้วบนทุก distro เป้าหมาย)",
)

FAKE_DUMP_SCRIPT = """#!/bin/sh
echo "-- fake mysqldump output"
echo "INSERT INTO customer VALUES (1);"
echo "-- Dump completed on 2026-10-14 03:30:00"
"""

FAKE_DUMP_FAIL_SCRIPT = """#!/bin/sh
echo "ERROR 1045: Access denied" >&2
exit 1
"""


def _make_fake_mysqldump(tmp_path, script_text=FAKE_DUMP_SCRIPT, name="fake_mysqldump.sh"):
    p = tmp_path / name
    p.write_text(script_text)
    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return str(p)


def test_dump_database_produces_valid_gzip_via_real_pipe(tmp_path):
    """
    จุดสำคัญที่สุดของเทสต์นี้: เปิดไฟล์ผลลัพธ์ด้วย gzip.open() จริง ๆ แล้วอ่านเนื้อหาออกมา
    เทียบ -- ถ้า pipe ผิด (เช่นข้อมูลดิบไม่ผ่านการบีบอัด) ไฟล์จะเปิดไม่ได้เลยหรือได้ขยะ
    ไม่ใช่แค่เช็คว่าไฟล์มีขนาด > 0
    """
    fake = _make_fake_mysqldump(tmp_path)
    out_path = tmp_path / "out" / "testdb.sql.gz"

    result = dump_database("testdb", "127.0.0.1", 3306, "root", "x",
                           out_path, mysqldump_bin=fake, gzip_bin="gzip")

    assert result == out_path
    assert out_path.exists()
    content = gzip.open(out_path, "rt").read()
    assert "fake mysqldump output" in content
    assert "INSERT INTO customer VALUES (1);" in content
    # เนื้อหามี natid_enc -- ต้องจำกัดสิทธิ์เหมือน secrets.env เสมอ
    assert oct(out_path.stat().st_mode)[-3:] == "600"
    # ไฟล์ .tmp ต้องไม่ค้าง (rename สำเร็จแล้ว)
    assert not out_path.with_suffix(".gz.tmp").exists()


def test_dump_database_raises_and_cleans_up_tmp_on_mysqldump_failure(tmp_path):
    fake = _make_fake_mysqldump(tmp_path, FAKE_DUMP_FAIL_SCRIPT, "fake_dump_fail.sh")
    out_path = tmp_path / "testdb.sql.gz"

    with pytest.raises(BackupError, match="Access denied"):
        dump_database("testdb", "127.0.0.1", 3306, "root", "x",
                      out_path, mysqldump_bin=fake, gzip_bin="gzip")

    assert not out_path.exists()
    assert not out_path.with_suffix(".gz.tmp").exists(), "ไฟล์ .tmp ค้างต้องถูกลบทิ้งเมื่อ mysqldump พัง"


def test_dump_database_raises_if_mysqldump_binary_missing(tmp_path):
    with pytest.raises(BackupError, match="mysqldump-that-does-not-exist"):
        dump_database("testdb", "127.0.0.1", 3306, "root", "x",
                      tmp_path / "out.sql.gz", mysqldump_bin="mysqldump-that-does-not-exist")


def test_prune_old_backups_deletes_only_files_past_retention(tmp_path):
    import time

    old = tmp_path / "cafewifi-old.sql.gz"
    new = tmp_path / "cafewifi-new.sql.gz"
    old.write_bytes(b"x")
    new.write_bytes(b"x")
    old_time = time.time() - 20 * 86400  # 20 วันก่อน
    os.utime(old, (old_time, old_time))

    pruned = prune_old_backups(tmp_path, keep_days=14)
    assert pruned == 1
    assert not old.exists()
    assert new.exists()


def test_run_end_to_end_writes_and_prunes(tmp_path, monkeypatch):
    """
    run() เรียก dump_database(mysqldump_bin="mysqldump") แบบไม่ให้ override ชื่อคำสั่งได้
    (ตั้งใจ -- ผู้ใช้จริงต้องมี mysqldump ตัวจริงบน PATH) เทสต์นี้จึงวางสคริปต์ปลอมชื่อ
    "mysqldump" ไว้ในโฟลเดอร์ที่เพิ่มเข้า PATH ก่อน แทนการ monkeypatch โค้ดภายใน
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _make_fake_mysqldump(bin_dir, name="mysqldump")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    backup_dir = tmp_path / "backups"
    monkeypatch.setenv("DB_NAME", "cafewifi")
    monkeypatch.setenv("DB_HOST", "127.0.0.1")
    monkeypatch.setenv("DB_PORT", "3306")
    monkeypatch.setenv("DB_USER", "root")
    monkeypatch.setenv("DB_PASS", "x")

    result = run(backup_dir=backup_dir, keep_days=14)
    assert result.path.exists()
    assert result.size_bytes > 0
    assert result.pruned == 0
    content = gzip.open(result.path, "rt").read()
    assert "fake mysqldump output" in content
    assert result.offsite_path is None, "ไม่ได้ตั้ง OFFSITE_BACKUP_DIR ในเทสต์นี้ ต้องข้าม"


# ---------------------------------------------------------------- copy_offsite (N4, CODING_BRIEF.md)
def test_copy_offsite_skips_when_env_not_set(tmp_path):
    """กรณีที่ 1: ไม่ตั้ง OFFSITE_BACKUP_DIR -- ต้องข้าม ไม่ throw คืน None"""
    src = tmp_path / "backup.sql.gz"
    src.write_bytes(b"fake backup content")

    result = copy_offsite(src, offsite_dir=None)
    assert result is None


def test_copy_offsite_skips_when_env_is_empty_string(tmp_path):
    src = tmp_path / "backup.sql.gz"
    src.write_bytes(b"fake backup content")
    assert copy_offsite(src, offsite_dir="") is None


def test_copy_offsite_copies_file_when_destination_is_writable(tmp_path):
    """กรณีที่ 2: ตั้งค่าแล้วปลายทางเขียนได้ -- ต้องคัดลอกไฟล์จริง เนื้อหาตรงกับต้นฉบับ"""
    src = tmp_path / "backup.sql.gz"
    src.write_bytes(b"fake backup content for offsite copy")
    offsite_dir = tmp_path / "offsite"  # ยังไม่มีอยู่ก่อน -- ต้องสร้างให้เองด้วย

    result = copy_offsite(src, offsite_dir=str(offsite_dir))

    assert result == offsite_dir / src.name
    assert result.exists()
    assert result.read_bytes() == src.read_bytes()
    if os.name == "posix":
        # เนื้อหามี natid_enc -- ต้องจำกัดสิทธิ์เหมือนต้นฉบับ (Windows ไม่มี POSIX permission
        # bits จริง chmod() แค่สลับ read-only attribute เท่านั้น เช็คได้เฉพาะบน Linux เป้าหมาย)
        assert oct(result.stat().st_mode)[-3:] == "600"


def test_copy_offsite_returns_none_and_does_not_raise_when_destination_unwritable(tmp_path):
    """
    กรณีที่ 3: ปลายทางเขียนไม่ได้ -- จำลองด้วยการวางไฟล์ธรรมดาขวางตำแหน่งที่ควรเป็นโฟลเดอร์ไว้
    ก่อน (mkdir(parents=True, exist_ok=True) จะ raise FileExistsError เพราะ path นั้นมีอยู่แล้ว
    แต่ไม่ใช่โฟลเดอร์) วิธีนี้พกพาข้ามแพลตฟอร์มได้แน่นอน ต่างจากการตั้ง chmod 000 ที่ไม่น่าเชื่อถือ
    บน Windows
    """
    src = tmp_path / "backup.sql.gz"
    src.write_bytes(b"fake backup content")

    blocked_path = tmp_path / "offsite_blocked"
    blocked_path.write_text("ไฟล์ธรรมดาขวางอยู่ตรงนี้ ไม่ใช่โฟลเดอร์", encoding="utf-8")

    result = copy_offsite(src, offsite_dir=str(blocked_path))
    assert result is None, "คัดลอกไม่สำเร็จต้องคืน None ไม่ throw exception ออกมา"


def test_run_copies_offsite_when_env_is_set(tmp_path, monkeypatch):
    """ยืนยันว่า run() ต่อสาย copy_offsite() เข้ากับ OFFSITE_BACKUP_DIR จริง ไม่ใช่แค่ฟังก์ชันลอย ๆ"""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _make_fake_mysqldump(bin_dir, name="mysqldump")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    monkeypatch.setenv("DB_NAME", "cafewifi")
    monkeypatch.setenv("DB_HOST", "127.0.0.1")
    monkeypatch.setenv("DB_PORT", "3306")
    monkeypatch.setenv("DB_USER", "root")
    monkeypatch.setenv("DB_PASS", "x")

    offsite_dir = tmp_path / "offsite"
    result = run(backup_dir=tmp_path / "backups", keep_days=14, offsite_dir=str(offsite_dir))

    assert result.offsite_path is not None
    assert result.offsite_path.exists()
    assert result.offsite_path.read_bytes() == result.path.read_bytes()


# ---------------------------------------------------------------- USB สำรองข้อมูล (2026-10-03)
def test_copy_offsite_refuses_same_device_when_usb_required(tmp_path):
    """ไม่ได้เสียบ USB แต่ปลายทางเป็นโฟลเดอร์บน SD ใบเดิม -- ห้าม 'สำเร็จ' เงียบ ๆ"""
    import tools.backup_db as bdb
    src = tmp_path / "backup.sql.gz"
    src.write_bytes(b"x")
    assert copy_offsite(src, offsite_dir=str(tmp_path / "usb" / "cafe-wifi"),
                        require_separate_device=True) is None
    assert "ไม่ได้เสียบ USB" in bdb._last_offsite_error
    assert not (tmp_path / "usb").exists(), "ต้องไม่สร้างโฟลเดอร์บน SD"


def test_copy_offsite_works_on_fat_usb_where_chmod_fails(tmp_path, monkeypatch):
    """USB ส่วนใหญ่เป็น FAT/exFAT -- chmod/copystat ทำไม่ได้ ต้องยังคัดลอกสำเร็จ"""
    src = tmp_path / "backup.sql.gz"
    src.write_bytes(b"data")
    real_chmod = Path.chmod

    def fat_chmod(self, mode, *a, **k):
        if "offsite" in str(self):
            raise PermissionError(1, "Operation not permitted")
        return real_chmod(self, mode, *a, **k)
    monkeypatch.setattr(Path, "chmod", fat_chmod)
    result = copy_offsite(src, offsite_dir=str(tmp_path / "offsite"))
    assert result is not None and result.read_bytes() == b"data"
    assert not list((tmp_path / "offsite").glob("*.tmp"))


def test_status_file_round_trip(tmp_path):
    import tools.backup_db as bdb
    from tools.backup_db import BackupResult
    st = tmp_path / "backup-status.json"
    bdb._last_offsite_error = "ไม่ได้เสียบ USB สำรองข้อมูล"
    bdb.write_status(st, BackupResult(path=tmp_path / "cafewifi-x.sql.gz", size_bytes=1234, pruned=0))
    d = bdb.read_status(st)
    assert d["ok"] and d["size"] == 1234 and d["offsite_ok"] is False
    assert "ไม่ได้เสียบ USB" in d["offsite_error"]
    bdb.write_status(st, None, "mysqldump exit code 2")
    assert bdb.read_status(st)["ok"] is False
    assert bdb.read_status(tmp_path / "missing.json") is None


# ---------------------------------------------------------------- A8/H2
def test_dump_skips_triggers(tmp_path, monkeypatch):
    """trigger กันแก้หลักฐานลงใหม่จาก sql/018 ตอนกู้ -- ไม่ dump (ไม่งั้น user สำรองต้องมีสิทธิ์ TRIGGER)"""
    import tools.backup_db as b
    seen = {}
    monkeypatch.setattr(b.shutil, "which", lambda name: name)

    def popen(cmd, **kw):
        seen.setdefault("cmds", []).append(cmd)
        raise OSError("stop here")
    monkeypatch.setattr(b.subprocess, "Popen", popen)
    with pytest.raises((OSError, BackupError)):
        dump_database("cafewifi", "127.0.0.1", 3306, "cafe_ops", "x", tmp_path / "d.sql.gz")
    assert "--skip-triggers" in seen["cmds"][0]


def test_run_writes_seal_anchor_to_usb_only_when_copied(tmp_path, monkeypatch):
    import logger.db_seal as ds
    import tools.backup_db as b
    calls = []
    monkeypatch.setattr(ds, "write_anchor", lambda d: calls.append(Path(d)))
    (tmp_path / "local").mkdir()
    monkeypatch.setattr(b, "dump_database", lambda **kw: kw["out_path"].write_bytes(b"x"))
    usb = tmp_path / "usb"
    usb.mkdir()
    monkeypatch.setattr(b, "copy_offsite", lambda src, d, **kw: usb / src.name)
    run(backup_dir=tmp_path / "local", keep_days=14, offsite_dir=str(usb))
    assert calls == [usb]
    calls.clear()
    monkeypatch.setattr(b, "copy_offsite", lambda src, d, **kw: None)
    run(backup_dir=tmp_path / "local", keep_days=14, offsite_dir=str(usb))
    assert calls == [], "คัดลอกลง USB ไม่สำเร็จ = ไม่เขียน anchor"


def test_write_anchor_appends_head_line(tmp_path):
    from datetime import date, datetime
    import logger.db_seal as ds

    class S:
        def __init__(self, h):
            self.h = h

        def last(self):
            return ds.Seal("dns_log", date(2026, 10, 14), 1, 1, 1, "id", "a" * 64, None, self.h)
    ds.write_anchor(tmp_path, S("1" * 64), now=datetime(2026, 10, 16, 3, 31))
    ds.write_anchor(tmp_path, S("2" * 64), now=datetime(2026, 10, 17, 3, 31))
    lines = (tmp_path / ds.ANCHOR_FILE).read_text(encoding="utf-8").splitlines()
    assert lines == [f"2026-10-16T03:31 head=dns_log:2026-10-14 chain={'1' * 64}",
                     f"2026-10-17T03:31 head=dns_log:2026-10-14 chain={'2' * 64}"]
