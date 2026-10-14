"""
T-AuditScrub (T8) -- POST /audit/scrub: admin ล้าง MAC/เลขบัตรในแถว audit เก่า โดยไม่ลบแถว
"""
from __future__ import annotations

import contextlib
import re
from datetime import datetime, timedelta

import pytest

from common import crypto

PW = "CafeWifi2026Secure"
NOW = datetime.now()
OLD = NOW - timedelta(days=400)
NEW = NOW - timedelta(days=10)
CUTOFF = (NOW - timedelta(days=200)).strftime("%Y-%m-%d")
REASON = "ล้างตามนโยบายเก็บข้อมูล"

STAFF: list[dict] = []
AUDIT_ROWS: list[dict] = []   # ตาราง audit_log จำลอง (รวมแถวที่ log_required เขียนเพิ่ม)
UPDATES: list[tuple] = []


class FakeCursor:
    def __init__(self):
        self._rows, self.lastrowid, self.rowcount = [], None, 0

    def execute(self, sql, args=()):
        s = " ".join(sql.split()).lower()
        self._rows = []
        if s.startswith("select password_hash from staff"):
            self._rows = [r for r in STAFF if r["id"] == args[0]]
        elif s.startswith("select id, username, password_hash"):
            self._rows = [r for r in STAFF if r["username"] == args[0]]
        elif s.startswith("select must_change_password from staff"):
            self._rows = [r for r in STAFF if r["id"] == args[0]]
        elif s.startswith("select count(*) as n from staff"):
            self._rows = [{"n": len(STAFF)}]
        elif s.startswith("select role, is_active"):
            self._rows = [r for r in STAFF if r["id"] == args[0]]
        elif s.startswith("select id, target, detail from audit_log"):
            cutoff, last_id, limit = args
            self._rows = sorted((dict(id=r["id"], target=r["target"], detail=r["detail"])
                                 for r in AUDIT_ROWS if r["ts"] < cutoff and r["id"] > last_id),
                                key=lambda r: r["id"])[:limit]
        elif s.startswith("update audit_log set target"):
            t, d, i = args
            UPDATES.append(args)
            for r in AUDIT_ROWS:
                if r["id"] == i:
                    r["target"], r["detail"] = t, d
            self.rowcount = 1
        elif s.startswith("insert into audit_log"):
            staff_id, action, target, ip, detail = args
            AUDIT_ROWS.append(dict(id=len(AUDIT_ROWS) + 1000, ts=datetime.now(), staff_id=staff_id,
                                   action=action, target=target, client_ip=ip, detail=detail))
            self.rowcount = 1
        elif s.startswith("select count(*) as n from rate_attempt"):
            self._rows = [{"n": 0}]
        elif s.startswith("insert into rate_attempt"):
            pass
        elif s.startswith("select count(*) as n from access_request"):
            self._rows = [{"n": 0}]
        elif s.startswith("update staff"):
            pass
        elif s.startswith("select distinct action") or s.startswith("select username from staff"):
            self._rows = []
        elif "from audit_log a" in s:
            self._rows = []
        else:
            raise AssertionError(f"SQL ไม่รู้จัก: {s[:100]}")

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
def admin(monkeypatch):
    STAFF.clear(); AUDIT_ROWS.clear(); UPDATES.clear()
    for i, (u, role) in enumerate((("owner", "admin"), ("barista", "staff")), 1):
        STAFF.append(dict(id=i, username=u, password_hash=crypto.hash_password(PW), display_name=u,
                          role=role, is_active=1, must_change_password=0, password_changed_at=None,
                          last_login_at=None))
    AUDIT_ROWS.extend([
        dict(id=1, ts=OLD, staff_id=1, action="request_approve", target="customer:5", client_ip="10.0.0.9",
             detail="mac=AA:BB:CC:DD:EE:01 customer=1-2345-XXXXX-XX-3 ok"),
        dict(id=2, ts=OLD, staff_id=2, action="enforce", target="aa-bb-cc-dd-ee-02", client_ip="10.0.0.8",
             detail="พิมพ์เลขเต็ม 1101700000010 ในเหตุผล"),
        dict(id=3, ts=OLD, staff_id=1, action="login_ok", target="owner", client_ip="10.0.0.7",
             detail="ไม่มีข้อมูลลูกค้า"),
        dict(id=4, ts=NEW, staff_id=1, action="request_approve", target="customer:6", client_ip="10.0.0.9",
             detail="mac=AA:BB:CC:DD:EE:09 customer=1-2345-XXXXX-XX-3"),
    ])
    import common.db as db
    monkeypatch.setattr(db, "get_conn", lambda: contextlib.nullcontext(FakeConn()))

    def _run(sql, args=()):
        c = FakeCursor(); c.execute(sql, args); return c

    monkeypatch.setattr(db, "query_one", lambda s, a=(): _run(s, a).fetchone())
    monkeypatch.setattr(db, "query_all", lambda s, a=(): _run(s, a).fetchall())
    monkeypatch.setattr(db, "execute", lambda s, a=(): _run(s, a).rowcount)
    import importlib
    mod = importlib.reload(importlib.import_module("admin.app"))
    mod.app.config.update(SESSION_COOKIE_SECURE=False, TESTING=True, CSRF_ENABLED=False)
    mod._attempts.clear()
    return mod


def _login(mod, user="owner"):
    c = mod.app.test_client()
    assert c.post("/login", data=dict(username=user, password=PW)).status_code == 302
    return c


def _post(c, **over):
    d = dict(cutoff=CUTOFF, reason=REASON, current_password=PW)
    d.update(over)
    return c.post("/audit/scrub", data=d, follow_redirects=False)


def _row(i):
    return next(r for r in AUDIT_ROWS if r["id"] == i)


def test_staff_forbidden(admin):
    assert _post(_login(admin, "barista")).status_code == 403
    assert not UPDATES


def test_requires_login(admin):
    r = admin.app.test_client().post("/audit/scrub", data=dict(cutoff=CUTOFF))
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_wrong_password_rejected(admin):
    r = _post(_login(admin), current_password="wrong")
    assert r.status_code == 302
    assert not UPDATES and not any(r["action"] == "audit_scrub" for r in AUDIT_ROWS)
    assert "MAC" not in _row(1)["detail"] and "AA:BB" in _row(1)["detail"]


@pytest.mark.parametrize("bad", [
    (NOW - timedelta(days=30)).strftime("%Y-%m-%d"),
    (NOW - timedelta(days=179)).strftime("%Y-%m-%d"),
    (NOW + timedelta(days=5)).strftime("%Y-%m-%d"),
    "not-a-date", "",
])
def test_cutoff_within_retention_or_invalid_rejected(admin, bad):
    c = _login(admin)
    _post(c, cutoff=bad)
    assert not UPDATES
    assert not any(r["action"] == "audit_scrub" for r in AUDIT_ROWS)


def test_short_reason_rejected(admin):
    _post(_login(admin), reason="สั้น")
    assert not UPDATES


def test_scrubs_pii_keeps_everything_else(admin):
    before = {i: dict(_row(i)) for i in (1, 2, 3, 4)}
    c = _login(admin)
    r = _post(c)
    assert r.status_code == 302
    assert len(AUDIT_ROWS) >= 4
    assert _row(1)["detail"] == "mac=[ลบแล้ว] customer=[ลบแล้ว] ok"
    assert _row(2)["target"] == "[ลบแล้ว]"
    assert _row(2)["detail"] == "พิมพ์เลขเต็ม [ลบแล้ว] ในเหตุผล"
    # ไม่ลบแถว และ staff_id/action/ts/client_ip ไม่เปลี่ยน
    for i in (1, 2, 3):
        for k in ("staff_id", "action", "ts", "client_ip"):
            assert _row(i)[k] == before[i][k]
    assert _row(1)["target"] == "customer:5"
    # แถวที่ไม่มีข้อมูลลูกค้า -> ไม่ถูก UPDATE; แถวใหม่กว่า cutoff -> ไม่ถูกแตะ
    assert [u[2] for u in UPDATES] == [1, 2]
    assert _row(3) == before[3] and _row(4) == before[4]
    flashed = c.get("/audit").get_data(as_text=True)
    assert "ล้างข้อมูลลูกค้าใน audit แล้ว 2 แถว" in flashed


def test_audit_scrub_rows_written_and_not_scrubbed(admin):
    _post(_login(admin))
    rows = [r for r in AUDIT_ROWS if r["action"] == "audit_scrub"]
    assert len(rows) == 2 and all(r["staff_id"] == 1 for r in rows)
    assert CUTOFF in rows[0]["detail"] and REASON in rows[0]["detail"]
    assert "แก้=2" in rows[1]["detail"] and REASON in rows[1]["detail"]


def test_batches_iterate_without_loop(admin, monkeypatch):
    import admin.views.audit_view as av
    monkeypatch.setattr(av, "SCRUB_BATCH", 2)
    _post(_login(admin))
    assert _row(1)["detail"].count("[ลบแล้ว]") == 2 and _row(2)["target"] == "[ลบแล้ว]"


def test_scrub_text_patterns():
    from admin.views.audit_view import scrub_text
    assert scrub_text("a aa:BB:cc:dd:ee:ff b") == "a [ลบแล้ว] b"
    assert scrub_text("aa-bb-cc-dd-ee-ff") == "[ลบแล้ว]"
    assert scrub_text("1-2345-XXXXX-XX-3") == "[ลบแล้ว]"
    assert scrub_text("1-1017-00000-01-0") == "[ลบแล้ว]"
    assert scrub_text("id 1101700000010.") == "id [ลบแล้ว]."
    assert scrub_text("12345678901234") == "12345678901234"   # 14 หลัก ไม่ใช่เลขบัตร
    assert scrub_text("10.0.0.5 CAFE-8F3K2") == "10.0.0.5 CAFE-8F3K2"
    assert scrub_text(None) is None and scrub_text("") == ""


def test_form_present_with_csrf_for_admin(admin):
    html = _login(admin).get("/audit").get_data(as_text=True)
    m = re.search(r'<form[^>]*action="/audit/scrub"[^>]*>(.*?)</form>', html, re.S)
    assert m and 'name="csrf_token"' in m.group(1) and "ย้อนกลับไม่ได้" in html
