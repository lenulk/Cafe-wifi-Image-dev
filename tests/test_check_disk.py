"""
T-CheckDisk — tools/check_disk.py (N1, CODING_BRIEF.md)

รันได้ทั้งหมดบน Windows ด้วย fake disk_usage_fn -- ไม่ต้องมีดิสก์เต็มจริง ไม่ต้องมี MariaDB จริง
"""
from collections import namedtuple

import pytest

from tools import check_disk

_Usage = namedtuple("usage", ["total", "used", "free"])

TOTAL = 100_000_000_000  # 100 GB สมมติ


def _fake_usage(percent_used: float):
    used = int(TOTAL * percent_used / 100)
    free = TOTAL - used
    return _Usage(total=TOTAL, used=used, free=free)


# ---------------------------------------------------------------- check_path (ตรรกะล้วน ๆ)
def test_check_path_ok_below_warn_threshold():
    status = check_disk.check_path("/", warn_pct=80, crit_pct=90,
                                   disk_usage_fn=lambda p: _fake_usage(50))
    assert status.level == "ok"
    assert status.percent_used == pytest.approx(50.0)


def test_check_path_warn_at_exactly_warn_threshold():
    status = check_disk.check_path("/", warn_pct=80, crit_pct=90,
                                   disk_usage_fn=lambda p: _fake_usage(80))
    assert status.level == "warn"


def test_check_path_warn_between_thresholds():
    status = check_disk.check_path("/", warn_pct=80, crit_pct=90,
                                   disk_usage_fn=lambda p: _fake_usage(85))
    assert status.level == "warn"


def test_check_path_crit_at_or_above_crit_threshold():
    status = check_disk.check_path("/", warn_pct=80, crit_pct=90,
                                   disk_usage_fn=lambda p: _fake_usage(95))
    assert status.level == "crit"


def test_check_path_handles_zero_total_without_dividing_by_zero():
    status = check_disk.check_path("/", warn_pct=80, crit_pct=90,
                                   disk_usage_fn=lambda p: _Usage(total=0, used=0, free=0))
    assert status.percent_used == 0.0
    assert status.level == "ok"


# ---------------------------------------------------------------- format_alert_line
def test_format_alert_line_labels_crit_as_critical():
    status = check_disk.check_path("/tmp", 80, 90, disk_usage_fn=lambda p: _fake_usage(95))
    line = check_disk.format_alert_line(status)
    assert "CRITICAL" in line
    assert "/tmp" in line
    assert "95.0%" in line


def test_format_alert_line_labels_warn_as_warning():
    status = check_disk.check_path("/tmp", 80, 90, disk_usage_fn=lambda p: _fake_usage(85))
    line = check_disk.format_alert_line(status)
    assert "WARNING" in line


# ---------------------------------------------------------------- run() end-to-end
@pytest.fixture
def audit_calls(monkeypatch):
    calls = []
    import common.audit as audit_mod
    monkeypatch.setattr(audit_mod, "log", lambda action, **kw: calls.append((action, kw)))
    monkeypatch.setattr(check_disk, "recently_alerted", lambda path, level: False)
    return calls


def test_run_normal_disk_writes_no_alert_and_no_audit_row(tmp_path, audit_calls):
    """กรณีที่ 1: ปกติ -- ไม่มี WARNING/CRITICAL, ไม่มีแถว audit_log"""
    statuses = check_disk.run(log_dir=str(tmp_path), warn_pct=80, crit_pct=90,
                              disk_usage_fn=lambda p: _fake_usage(40))
    assert all(s.level == "ok" for s in statuses)
    assert audit_calls == []
    assert not (tmp_path / "alert.log").exists(), "ไม่ควรสร้าง alert.log ถ้าไม่มีอะไรต้องเตือน"


def test_run_over_warn_writes_alert_and_one_audit_row_per_path(tmp_path, audit_calls):
    """กรณีที่ 2: เกิน warn (แต่ไม่ถึง crit) -- ต้องมี WARNING ใน alert.log และแถว audit_log"""
    statuses = check_disk.run(log_dir=str(tmp_path), warn_pct=80, crit_pct=90,
                              disk_usage_fn=lambda p: _fake_usage(85))
    assert all(s.level == "warn" for s in statuses)

    alert_text = (tmp_path / "alert.log").read_text(encoding="utf-8")
    assert alert_text.count("WARNING") == 2  # ตรวจ 2 path (LOG_DIR และ /) เจอ warn ทั้งคู่
    assert "CRITICAL" not in alert_text

    assert len(audit_calls) == 2
    for action, kw in audit_calls:
        assert action == "disk_alert"
        assert kw["detail"].startswith("warn 85.0% used")
        assert "MB free" in kw["detail"]


def test_run_over_crit_writes_critical_alert_and_audit_row(tmp_path, audit_calls):
    """กรณีที่ 3: เกิน crit -- ต้องมี CRITICAL ใน alert.log และแถว audit_log ระบุ crit"""
    statuses = check_disk.run(log_dir=str(tmp_path), warn_pct=80, crit_pct=90,
                              disk_usage_fn=lambda p: _fake_usage(97))
    assert all(s.level == "crit" for s in statuses)

    alert_text = (tmp_path / "alert.log").read_text(encoding="utf-8")
    assert alert_text.count("CRITICAL") == 2

    assert len(audit_calls) == 2
    assert all(kw["detail"].startswith("crit 97.0% used") for _, kw in audit_calls)


def test_run_reads_thresholds_from_env_when_not_passed_explicitly(tmp_path, audit_calls, monkeypatch):
    monkeypatch.setenv("DISK_WARN_PCT", "50")
    monkeypatch.setenv("DISK_CRIT_PCT", "60")
    statuses = check_disk.run(log_dir=str(tmp_path), disk_usage_fn=lambda p: _fake_usage(55))
    assert all(s.level == "warn" for s in statuses), "55% ต้องเกิน DISK_WARN_PCT=50 จาก env"


def test_run_defaults_to_80_90_when_no_env_and_no_explicit_args(tmp_path, audit_calls, monkeypatch):
    monkeypatch.delenv("DISK_WARN_PCT", raising=False)
    monkeypatch.delenv("DISK_CRIT_PCT", raising=False)
    statuses = check_disk.run(log_dir=str(tmp_path), disk_usage_fn=lambda p: _fake_usage(75))
    assert all(s.level == "ok" for s in statuses), "75% ต้องยังไม่เกิน default warn=80"

# หมายเหตุ: ไม่มีเทสต์แยกสำหรับ main() -- ตรงกับธรรมเนียมของ tools/*.py ทุกไฟล์ในโปรเจกต์
# (purge_old_data.py, backup_db.py, enforce_voucher_expiry.py ต่างก็มาร์ก main() เป็น
# `# pragma: no cover` ไม่มีเทสต์ตรง ๆ) เพราะ main() เรียก run()/shutil.disk_usage โดยไม่รับ
# พารามิเตอร์ ให้ inject fake ได้เลย -- ค่า default ของพารามิเตอร์ถูก bind ตอน import ครั้งเดียว
# (ข้อจำกัดของ Python เอง) การ monkeypatch check_disk.shutil.disk_usage ทีหลังจึงไม่มีผลกับ
# ฟังก์ชันที่อ้างค่า default นั้นไปแล้ว -- ลองเขียนเทสต์แบบนี้ไว้ก่อนแล้วพบว่า "ผ่านโดยบังเอิญ"
# เพราะดิสก์จริงของเครื่องที่ทดสอบ (C:\) ตอนนั้นเต็มเกิน 90% พอดี ไม่ได้ผ่านเพราะ mock ทำงาน
# จริง -- ตรรกะที่สำคัญ (run(), check_path(), check_all()) มีเทสต์ inject fake ครบแล้วด้านบน


# ---------------------------------------------------------------- T9
def test_percent_is_used_over_used_plus_free_like_df():
    """df: used/(used+free) · มี reserved blocks (total > used+free) ต้องไม่ถูกนับเป็นที่ว่าง"""
    u = _Usage(total=100, used=80, free=10)   # 90% ตาม df (ไม่ใช่ 80%)
    st = check_disk.check_path("/", 80, 90, disk_usage_fn=lambda p: u)
    assert st.percent_used == pytest.approx(80 / 90 * 100)
    assert st.level == "warn"


def test_missing_log_dir_does_not_stop_root_check(tmp_path, audit_calls):
    def usage(p):
        if p == str(tmp_path / "nope"):
            raise FileNotFoundError(p)
        return _fake_usage(95)
    statuses = check_disk.run(log_dir=str(tmp_path / "nope"), warn_pct=80, crit_pct=90, disk_usage_fn=usage)
    by_path = {s.path: s for s in statuses}
    assert by_path[str(tmp_path / "nope")].level == "error"
    assert by_path["/"].level == "crit", "/ ต้องยังถูกตรวจ"
    assert {kw["target"] for _, kw in audit_calls} == {str(tmp_path / "nope"), "/"}


def test_audit_written_even_when_alert_file_write_fails(tmp_path, audit_calls, monkeypatch):
    order = []
    import common.audit as audit_mod
    monkeypatch.setattr(audit_mod, "log", lambda action, **kw: order.append("audit"))

    def boom(path, line):
        order.append("file")
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(check_disk, "write_alert", boom)
    statuses = check_disk.run(log_dir=str(tmp_path), warn_pct=80, crit_pct=90,
                              disk_usage_fn=lambda p: _fake_usage(95))
    assert len(statuses) == 2
    assert order == ["audit", "file", "audit", "file"], "audit ก่อนไฟล์ และทำต่อแม้ไฟล์ล้ม"


def test_same_level_alert_is_not_repeated_within_window(tmp_path, audit_calls, monkeypatch):
    """timer ทุก 15 นาที: ระดับเดิมที่บันทึกไปแล้วใน REPEAT_HOURS ไม่ลง audit ซ้ำ แต่ alert.log ยังเขียน"""
    monkeypatch.setattr(check_disk, "recently_alerted", lambda path, level: True)
    check_disk.run(log_dir=str(tmp_path), warn_pct=80, crit_pct=90,
                   disk_usage_fn=lambda p: _fake_usage(95))
    assert audit_calls == []
    assert "CRITICAL" in (tmp_path / "alert.log").read_text(encoding="utf-8")


def test_recently_alerted_queries_by_level_and_fails_open(monkeypatch):
    import common.db as db_mod
    seen = {}

    def fake_query_one(sql, args):
        seen["args"] = args
        return {"hit": 1}
    monkeypatch.setattr(db_mod, "query_one", fake_query_one)
    assert check_disk.recently_alerted("/", "crit") is True
    assert seen["args"][1:] == ("/", "crit %")

    def broken(sql, args):
        raise RuntimeError("db down")
    monkeypatch.setattr(db_mod, "query_one", broken)
    assert check_disk.recently_alerted("/", "crit") is False, "อ่าน DB ไม่ได้ = บันทึกซ้ำดีกว่าเงียบ"
