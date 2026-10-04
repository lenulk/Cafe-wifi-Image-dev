"""
ไฟล์สำรองกุญแจ (M7) — common/keybackup.py + หน้า /keys ใน Admin + tools/restore_keys.py
ฐานข้อมูลจำลองในหน่วยความจำ ไม่ต้องมี MariaDB · ไม่แตะ /etc จริง
"""
import contextlib
import json

import pytest

from common import crypto, keybackup

ADMIN_PW = "CafeWifi2026Secure"
PASS = "ร้านเปิดเจ็ดโมงเช้าทุกวัน 2026"
SECRETS = """# test
DB_HOST=127.0.0.1
DB_NAME=cafewifi
DB_USER=cafewifi
DB_PASS=Abc123def456
NATID_PEPPER=aa11
NATID_DEK=bb22bb22
SECRET_KEY=cc33
FAS_KEY=dd44
UPLINK_IP=192.168.1.2
GATEWAY_NAME=Old Shop
SSH_ALT_PORT=40000
"""


# ---------------------------------------------------------------- รูปแบบไฟล์
def test_roundtrip():
    blob = keybackup.pack(SECRETS, PASS, host="cafewifi")
    assert b"NATID_DEK" not in blob and b"bb22bb22" not in blob, "ต้องไม่มีกุญแจเป็นข้อความธรรมดา"
    head = keybackup.read_header(blob)
    assert head["host"] == "cafewifi" and head["dek_fp"] == keybackup.dek_fingerprint(SECRETS)
    assert keybackup.unpack(blob, PASS) == SECRETS


def test_wrong_passphrase_rejected():
    blob = keybackup.pack(SECRETS, PASS)
    with pytest.raises(keybackup.BackupError, match="รหัสผ่าน"):
        keybackup.unpack(blob, PASS + "x")


def test_tampered_header_or_body_rejected():
    blob = keybackup.pack(SECRETS, PASS, host="a")
    doc = json.loads(blob)
    doc["host"] = "evil"                      # หัวไฟล์เป็น AAD -- แก้แล้วถอดไม่ได้
    with pytest.raises(keybackup.BackupError):
        keybackup.unpack(json.dumps(doc).encode(), PASS)
    doc = json.loads(blob)
    doc["ct"] = doc["ct"][:-8] + "AAAAAAA="
    with pytest.raises(keybackup.BackupError):
        keybackup.unpack(json.dumps(doc).encode(), PASS)


def test_not_a_backup_file():
    for junk in (b"", b"hello", json.dumps({"format": "other"}).encode()):
        with pytest.raises(keybackup.BackupError):
            keybackup.read_header(junk)


def test_refuses_incomplete_secrets():
    with pytest.raises(keybackup.BackupError, match="NATID_DEK"):
        keybackup.pack("DB_PASS=x\n", PASS)


def test_passphrase_policy():
    assert keybackup.check_passphrase("short")
    assert keybackup.check_passphrase("aaaaaaaaaaaaaaaa")
    assert keybackup.check_passphrase("abcabcabcabcabc")
    assert not keybackup.check_passphrase(PASS)


# ---------------------------------------------------------------- หน้า Admin
STAFF: list[dict] = []
AUDIT: list[tuple] = []


class FakeCursor:
    def __init__(self):
        self._rows, self.lastrowid, self.rowcount = [], None, 0

    def execute(self, sql, args=()):
        s = " ".join(sql.split()).lower()
        self._rows = []
        if s.startswith("select count(*) as n from staff"):
            self._rows = [{"n": len(STAFF)}]
        elif s.startswith("select role, is_active"):
            self._rows = [r for r in STAFF if r["id"] == args[0]]
        elif s.startswith("select id, username, password_hash"):
            self._rows = [r for r in STAFF if r["username"] == args[0]]
        elif s.startswith("select password_hash from staff"):
            self._rows = [r for r in STAFF if r["id"] == args[0]]
        elif s.startswith("select must_change_password from staff"):
            self._rows = [r for r in STAFF if r["id"] == args[0]]
        elif s.startswith("select ts, staff_id from audit_log"):
            self._rows = [{"ts": "2026-10-04 22:00:00", "staff_id": a[0]} for a in AUDIT if a[1] == args[0]][-1:]
        elif s.startswith("insert into audit_log"):
            AUDIT.append(args)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeConn:
    def cursor(self):
        return FakeCursor()


@pytest.fixture
def admin(tmp_path, monkeypatch):
    STAFF.clear()
    AUDIT.clear()
    for i, (u, role) in enumerate((("owner", "admin"), ("barista", "staff")), 1):
        STAFF.append(dict(id=i, username=u, password_hash=crypto.hash_password(ADMIN_PW), display_name=u,
                          role=role, is_active=1, must_change_password=0, password_changed_at=None,
                          last_login_at=None))
    (tmp_path / "secrets.env").write_text(SECRETS, encoding="utf-8")
    monkeypatch.setenv("ETC_DIR", str(tmp_path))
    import common.db as db
    monkeypatch.setattr(db, "get_conn", lambda: contextlib.nullcontext(FakeConn()))

    def _run(sql, args=()):
        c = FakeCursor()
        c.execute(sql, args)
        return c
    monkeypatch.setattr(db, "query_one", lambda s, a=(): _run(s, a).fetchone())
    monkeypatch.setattr(db, "query_all", lambda s, a=(): _run(s, a).fetchall())
    monkeypatch.setattr(db, "execute", lambda s, a=(): _run(s, a).rowcount)
    import importlib
    mod = importlib.reload(importlib.import_module("admin.app"))
    mod.SETUP_TOKEN_FILE = tmp_path / "setup.token"
    mod.app.config.update(SESSION_COOKIE_SECURE=False, TESTING=True, CSRF_ENABLED=False)
    mod._attempts.clear()
    return mod


def _login(mod, user="owner"):
    c = mod.app.test_client()
    assert c.post("/login", data=dict(username=user, password=ADMIN_PW)).status_code == 302
    return c


def _post(c, **over):
    d = dict(current_password=ADMIN_PW, passphrase=PASS, passphrase_confirm=PASS)
    d.update(over)
    return c.post("/keys/backup", data=d)


def test_page_shows_never_backed_up(admin):
    html = _login(admin).get("/keys").get_data(as_text=True)
    assert "ยังไม่เคยสำรอง" in html and keybackup.dek_fingerprint(SECRETS) in html


def test_staff_cannot_backup(admin):
    c = _login(admin, "barista")
    assert c.get("/keys").status_code == 403
    assert _post(c).status_code == 403


def test_download_decrypts_to_secrets_and_is_audited(admin):
    r = _post(_login(admin))
    assert r.status_code == 200
    assert r.headers["Cache-Control"] == "no-store"
    assert "attachment" in r.headers["Content-Disposition"] and ".cwkey" in r.headers["Content-Disposition"]
    assert keybackup.unpack(r.data, PASS) == SECRETS
    assert [a[1] for a in AUDIT].count("key_backup") == 1


def test_wrong_account_password_refused(admin):
    r = _post(_login(admin), current_password="nope")
    assert r.status_code == 400 and "ไม่ถูกต้อง" in r.get_data(as_text=True)
    assert "key_backup" not in [a[1] for a in AUDIT]


def test_passphrase_must_differ_from_account_and_match(admin):
    c = _login(admin)
    assert _post(c, passphrase=ADMIN_PW, passphrase_confirm=ADMIN_PW).status_code == 400
    assert _post(c, passphrase_confirm=PASS + "x").status_code == 400
    assert _post(c, passphrase="short", passphrase_confirm="short").status_code == 400


def test_bruteforce_locks(admin):
    c = _login(admin)
    for _ in range(5):
        _post(c, current_password="wrong")
    assert _post(c).status_code == 429


# ---------------------------------------------------------------- กู้คืน
def test_restore_keeps_local_network_values(tmp_path, monkeypatch):
    from tools import restore_keys
    monkeypatch.setenv("ETC_DIR", str(tmp_path))
    monkeypatch.setattr(restore_keys, "ETC_DIR", tmp_path)
    new_machine = SECRETS.replace("NATID_DEK=bb22bb22", "NATID_DEK=ffff").replace(
        "UPLINK_IP=192.168.1.2", "UPLINK_IP=10.0.0.5").replace("GATEWAY_NAME=Old Shop", "GATEWAY_NAME=New Shop")
    (tmp_path / "secrets.env").write_text(new_machine, encoding="utf-8")
    f = tmp_path / "b.cwkey"
    f.write_bytes(keybackup.pack(SECRETS, PASS))
    monkeypatch.setenv("CAFEWIFI_RESTORE_PASSPHRASE", PASS)
    assert restore_keys.main([str(f), "--no-db"]) == 0
    got = keybackup.parse_env((tmp_path / "secrets.env").read_text(encoding="utf-8"))
    assert got["NATID_DEK"] == "bb22bb22", "กุญแจถอดเลขบัตรต้องเป็นของเดิม"
    assert got["UPLINK_IP"] == "10.0.0.5" and got["GATEWAY_NAME"] == "New Shop", "ค่าเครือข่ายต้องเป็นของเครื่องใหม่"
    assert list(tmp_path.glob("secrets.env.before-restore-*")), "ต้องเก็บกุญแจชุดเดิมของเครื่องไว้"


def test_restore_wrong_passphrase_writes_nothing(tmp_path, monkeypatch):
    from tools import restore_keys
    monkeypatch.setenv("ETC_DIR", str(tmp_path))
    monkeypatch.setattr(restore_keys, "ETC_DIR", tmp_path)
    (tmp_path / "secrets.env").write_text("NATID_DEK=keep\n", encoding="utf-8")
    f = tmp_path / "b.cwkey"
    f.write_bytes(keybackup.pack(SECRETS, PASS))
    monkeypatch.setenv("CAFEWIFI_RESTORE_PASSPHRASE", "wrong passphrase!!")
    assert restore_keys.main([str(f)]) == 3
    assert (tmp_path / "secrets.env").read_text(encoding="utf-8") == "NATID_DEK=keep\n"
