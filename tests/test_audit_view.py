"""
T-AuditView — หน้าดู audit_log (GET /audit) เฉพาะ admin

ใช้ DB จำลองชุดเดียวกับ test_logs_search (ผู้ใช้/audit INSERT) แล้วครอบ admin.app.query_all
เฉพาะ SQL ของหน้านี้ (staff / audit_log) · ตรวจ SQL+พารามิเตอร์ที่ประกอบขึ้นจริง
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import test_logs_search as base  # noqa: E402

RANGE = {"range": "custom", "start": "2026-10-01T00:00", "end": "2026-10-02T00:00"}


class AuditDB:
    def __init__(self):
        self.calls: list[tuple[str, tuple]] = []
        self.rows: list[dict] = []

    def add_rows(self, n):
        self.rows = [dict(id=i, ts=datetime(2026, 10, 1, 12, 0), staff_username="admin1", staff_id=1,
                          action="login_ok", target="t", client_ip="10.0.0.1", detail=f"d{i}")
                     for i in range(n)]

    def query_all(self, sql, args=()):
        s = " ".join(sql.split())
        low = s.lower()
        if low.startswith("select username from staff"):
            return [{"username": r["username"]} for r in base.STAFF]
        if low.startswith("select distinct action from audit_log"):
            return [{"action": "custom_action_x"}]
        if "from audit_log a" in low:
            self.calls.append((s, tuple(args)))
            limit, offset = args[-2], args[-1]
            return self.rows[offset:offset + limit]
        raise AssertionError(f"SQL ไม่รู้จัก: {s[:100]}")

    @property
    def main(self):
        return self.calls[-1]


@pytest.fixture
def env(monkeypatch):
    client = base.make_client(monkeypatch)
    import admin.app as admin_app
    db = AuditDB()
    orig = admin_app.query_all

    def routed(sql, args=()):
        low = " ".join(sql.split()).lower()
        if "audit_log" in low and low.startswith("select") or low.startswith("select username from staff"):
            return db.query_all(sql, args)
        return orig(sql, args)

    monkeypatch.setattr(admin_app, "query_all", routed)
    return client, db


def test_requires_login(env):
    client, _ = env
    r = client.get("/audit")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_staff_forbidden_admin_ok(env):
    client, db = env
    base._login_as(client, "staff")
    assert client.get("/audit").status_code == 403
    assert not base.AUDIT, "staff ถูกปฏิเสธ = ไม่ลง view_audit"
    base._login_as(client, "admin")
    r = client.get("/audit")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "custom_action_x" in html and "login_ok" in html and "staff1" in html
    assert "บันทึกการใช้งาน (audit)" in html, "ลิงก์เมนู admin"


def test_nav_link_hidden_from_staff(env):
    client, _ = env
    base._login_as(client, "staff")
    html = client.get("/logs").get_data(as_text=True)
    assert "บันทึกการใช้งาน (audit)" not in html


def test_filters_build_expected_sql_params(env):
    client, db = env
    base._login_as(client, "admin")
    r = client.get("/audit", query_string=dict(RANGE, staff="staff1", action="reveal_natid",
                                               client_ip="10.0.0.9", q="abc"))
    assert r.status_code == 200
    sql, args = db.main
    assert "s.username = %s" in sql and "a.action = %s" in sql and "a.client_ip = %s" in sql
    assert "a.detail LIKE %s" in sql and "ORDER BY a.ts DESC" in sql
    assert args == (datetime(2026, 10, 1), datetime(2026, 10, 2), "staff1", "reveal_natid",
                    "10.0.0.9", "%abc%", 51, 0)


def test_no_filters_only_time_range(env):
    client, db = env
    base._login_as(client, "admin")
    client.get("/audit", query_string=RANGE)
    sql, args = db.main
    assert "s.username = %s" not in sql and "a.action = %s" not in sql and "LIKE" not in sql
    assert args == (datetime(2026, 10, 1), datetime(2026, 10, 2), 51, 0)


def test_like_wildcards_escaped(env):
    client, db = env
    base._login_as(client, "admin")
    client.get("/audit", query_string=dict(RANGE, q="50%_off\\x"))
    assert db.main[1][2] == "%50\\%\\_off\\\\x%"


def test_range_validation(env):
    client, db = env
    base._login_as(client, "admin")
    assert client.get("/audit", query_string={"range": "custom"}).status_code == 400
    assert client.get("/audit", query_string=dict(RANGE, end="2026-12-01T00:00")).status_code == 400
    assert not db.calls and not base.AUDIT
    assert client.get("/audit", query_string={"range": "7d"}).status_code == 200
    assert client.get("/audit", query_string={"range": "bogus"}).status_code == 200  # ถอยเป็น today


def test_view_writes_audit_row(env):
    client, _ = env
    base._login_as(client, "admin")
    client.get("/audit", query_string=dict(RANGE, staff="staff1", q="x" * 80))
    assert len(base.AUDIT) == 1
    a = base.AUDIT[0]
    assert a[0] == 1 and a[1] == "view_audit"
    assert "staff=staff1" in a[4] and "q=" + "x" * 50 + " " in a[4] and "x" * 51 not in a[4]
    assert "start=2026-10-01" in a[4]


def test_audit_no_store(env):
    client, _ = env
    base._login_as(client, "admin")
    r = client.get("/audit", query_string=RANGE)
    assert r.status_code == 200 and r.headers["Cache-Control"] == "no-store"


def test_html_escaped(env):
    client, db = env
    base._login_as(client, "admin")
    db.add_rows(1)
    db.rows[0]["detail"] = "<script>alert(1)</script>"
    html = client.get("/audit", query_string=RANGE).get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html


def test_pagination(env):
    client, db = env
    base._login_as(client, "admin")
    db.add_rows(55)
    h1 = client.get("/audit", query_string=dict(RANGE, staff="staff1")).get_data(as_text=True)
    assert "เก่ากว่า" in h1 and "ใหม่กว่า" not in h1
    assert "page=2" in h1 and "staff=staff1" in h1
    assert h1.count("<td class=\"mono\">login_ok</td>") == 50
    h2 = client.get("/audit", query_string=dict(RANGE, page="2")).get_data(as_text=True)
    assert "ใหม่กว่า" in h2 and "เก่ากว่า" not in h2
    assert db.main[1][-2:] == (51, 50)
    assert h2.count("<td class=\"mono\">login_ok</td>") == 5
