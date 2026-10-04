"""
กู้คืนจากเครื่องเดิมผ่าน setup wizard -- /restore (ผู้ใช้ cafewifi) + setup/restore.py (root)
ไม่มี MariaDB/root จริง: ฝั่ง wizard ใช้ fixture ของ test_setup_wizard · ฝั่ง root แทน mysql ด้วยตัวจำลอง
"""
import json
import os
import stat

import pytest

from common import keybackup
from test_setup_wizard import STAFF, csrf, login, make_admin, wiz  # noqa: F401 -- wiz = fixture

PASS = "ร้านเปิดเจ็ดโมงเช้าทุกวัน 2026"
DEK, PEPPER = "a" * 64, "b" * 64
SECRETS = (f"DB_NAME=cafewifi\nDB_PASS=OldPass1\nNATID_PEPPER={PEPPER}\nNATID_DEK={DEK}\n"
           "SECRET_KEY=old-flask\nFAS_KEY=old-fas\n")


def _post(c, blob, pw=PASS, page="/restore"):
    from io import BytesIO
    return c.post("/restore", data={"csrf": csrf(c, page), "passphrase": pw,
                                    "cwkey": (BytesIO(blob), "shop.cwkey")},
                  content_type="multipart/form-data")


# ------------------------------------------------------------------ wizard
def test_restore_requires_setup_code(wiz):
    assert wiz.get("/restore").headers["Location"].endswith("/code")


def test_admin_page_offers_restore(wiz):
    login(wiz)
    assert "/restore" in wiz.get("/admin").get_data(as_text=True)


def test_wrong_passphrase_writes_nothing(wiz):
    login(wiz)
    r = _post(wiz, keybackup.pack(SECRETS, PASS), pw="wrong passphrase!!")
    assert r.status_code == 400
    assert not (wiz.run / "restore.json").exists()


def test_good_backup_sends_only_data_keys(wiz):
    login(wiz)
    r = _post(wiz, keybackup.pack(SECRETS, PASS))
    assert r.status_code == 302 and r.headers["Location"].endswith("/restore")
    req = wiz.run / "restore.json"
    assert json.loads(req.read_text(encoding="utf-8")) == {"NATID_DEK": DEK, "NATID_PEPPER": PEPPER}
    if os.name == "posix":
        assert stat.S_IMODE(req.stat().st_mode) == 0o600
    html = wiz.get("/restore").get_data(as_text=True)
    assert 'http-equiv="refresh"' in html, "ระหว่างกู้หน้าต้องอัปเดตเอง"
    assert wiz.get("/").headers["Location"].endswith("/restore")


def test_restore_refused_once_admin_exists(wiz):
    login(wiz); make_admin(wiz)
    assert wiz.get("/restore").headers["Location"].endswith("/network")
    _post(wiz, keybackup.pack(SECRETS, PASS), page="/network")   # ยิงตรงก็ไม่ได้
    assert not (wiz.run / "restore.json").exists()


def test_restore_bruteforce_locks(wiz):
    login(wiz)
    blob = keybackup.pack(SECRETS, PASS)
    for _ in range(10):
        _post(wiz, blob, pw="wrong passphrase!!")
    assert _post(wiz, blob).status_code == 429
    assert not (wiz.run / "restore.json").exists()


def test_done_status_shown(wiz):
    login(wiz)
    (wiz.state / "restore.json").write_text(json.dumps(
        {"state": "done", "message": "กู้คืนสำเร็จจาก cafewifi-20261004-033000.sql.gz", "staff": 2,
         "customers_checked": 5}), encoding="utf-8")
    STAFF.append({"id": 1, "username": "owner", "password_hash": "x"})   # บัญชีเดิมกลับมาแล้ว
    html = wiz.get("/restore").get_data(as_text=True)
    assert "กู้คืนสำเร็จ" in html and "ตั้งค่าเครือข่าย" in html


# ------------------------------------------------------------------ root (setup/restore.py)
@pytest.fixture
def root(tmp_path, monkeypatch):
    from setup import restore
    etc, run, state, usb = tmp_path / "etc", tmp_path / "run", tmp_path / "state", tmp_path / "usb"
    for d in (etc, run, state, usb):
        d.mkdir()
    (etc / "secrets.env").write_text(f"DB_NAME=cafewifi\nDB_PASS=NewPass9\nNATID_DEK={'f' * 64}\n"
                                     f"NATID_PEPPER={'e' * 64}\nFAS_KEY=new-fas\nOFFSITE_BACKUP_DIR={usb}\n",
                                     encoding="utf-8")
    for name in ("cafewifi-20261003-033000.sql.gz", "cafewifi-20261004-033000.sql.gz", "other-20261005-033000.sql.gz"):
        (usb / name).write_bytes(b"")
    monkeypatch.setattr(restore, "ETC_DIR", etc)
    monkeypatch.setattr(restore, "RUN_DIR", run)
    monkeypatch.setattr(restore, "STATE_DIR", state)
    monkeypatch.setattr(restore, "REQUEST_FILE", run / "restore.json")
    monkeypatch.setattr(restore, "STATUS_FILE", state / "restore.json")
    monkeypatch.setattr(restore, "OPT_DIR", tmp_path)
    calls = {"staff": 0, "verify": (3, 3), "imported": None, "sql": []}
    monkeypatch.setattr(restore, "staff_count", lambda db: calls["staff"])
    monkeypatch.setattr(restore, "import_dump", lambda db, p: calls.__setitem__("imported", p.name))
    monkeypatch.setattr(restore, "apply_migrations", lambda db: None)
    monkeypatch.setattr(restore, "verify_keys", lambda db, d, p: calls["verify"])
    monkeypatch.setattr(restore, "mysql", lambda db, sql=None, stdin=None: calls["sql"].append(sql))
    if not hasattr(os, "chown"):
        monkeypatch.setattr(os, "chown", lambda *a: None, raising=False)
    (run / "restore.json").write_text(json.dumps({"NATID_DEK": DEK, "NATID_PEPPER": PEPPER}), encoding="utf-8")
    restore.calls, restore.etc = calls, etc
    return restore


def _status(r):
    return json.loads(r.STATUS_FILE.read_text(encoding="utf-8"))


def test_root_restores_newest_backup_and_only_data_keys(root):
    assert root.main() == 0
    assert root.calls["imported"] == "cafewifi-20261004-033000.sql.gz", "ใช้ไฟล์ล่าสุดของฐานนี้เท่านั้น"
    env = keybackup.parse_env((root.etc / "secrets.env").read_text(encoding="utf-8"))
    assert env["NATID_DEK"] == DEK and env["NATID_PEPPER"] == PEPPER
    assert env["FAS_KEY"] == "new-fas" and env["DB_PASS"] == "NewPass9", "ค่าอื่นต้องเป็นของเครื่องนี้"
    assert list(root.etc.glob("secrets.env.before-restore-*"))
    assert not (root.RUN_DIR / "restore.json").exists() and not list(root.RUN_DIR.glob("*.json")), "ไม่ทิ้งกุญแจค้าง"
    assert _status(root)["state"] == "done"
    assert any("setup_restore" in (s or "") for s in root.calls["sql"]), "ต้องลง audit หลังคืนฐานข้อมูล"


def test_root_wrong_keys_rolls_back_and_keeps_secrets(root):
    before = (root.etc / "secrets.env").read_text(encoding="utf-8")
    root.calls["verify"] = (0, 3)
    assert root.main() == 1
    assert (root.etc / "secrets.env").read_text(encoding="utf-8") == before
    assert any("DROP DATABASE" in (s or "") for s in root.calls["sql"]), "ข้อมูลที่ถอดไม่ได้ต้องถูกล้างทิ้ง"
    assert "ไม่ตรง" in _status(root)["message"]


def test_root_refuses_machine_in_use(root):
    root.calls["staff"] = 2
    assert root.main() == 1
    assert root.calls["imported"] is None and "มีข้อมูลอยู่แล้ว" in _status(root)["message"]


def test_root_no_usb_backup(root):
    for p in root.etc.parent.joinpath("usb").iterdir():
        p.unlink()
    assert root.main() == 1
    assert "ไม่พบไฟล์สำรอง" in _status(root)["message"]


def test_root_rejects_malformed_keys(root):
    (root.RUN_DIR / "restore.json").write_text(json.dumps({"NATID_DEK": "x'; DROP", "NATID_PEPPER": PEPPER}),
                                               encoding="utf-8")
    assert root.main() == 1
    assert root.calls["imported"] is None
