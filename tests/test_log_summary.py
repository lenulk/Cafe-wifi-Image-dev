"""
T-LogSummary — หน้าสรุปการใช้งานรายเครื่อง/รายลูกค้า (GET /logs/summary)

ใช้ DB จำลองของ test_logs_search (staff/audit) แล้วครอบ admin.app.query_all/query_one เฉพาะ SQL ของหน้านี้
เก็บ SQL+พารามิเตอร์ที่ประกอบจริงไว้ตรวจ
"""
from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import test_logs_search as base  # noqa: E402

from common import crypto  # noqa: E402

MAC = "AA:BB:CC:DD:EE:01"
RANGE = {"range": "custom", "start": "2026-10-01T00:00", "end": "2026-10-02T00:00"}
FULL = base.NATID_A


class SummaryDB:
    def __init__(self):
        self.calls: list[tuple[str, tuple]] = []
        self.customer = dict(id=7, natid_masked="1-1017-XXXXX-XX-0", first_seen=datetime(2026, 9, 1),
                             last_seen=datetime(2026, 10, 1), visit_count=3)
        self.enc = crypto.natid_encrypt(FULL)
        self.hostname = "Somchai's <b>iPhone</b>"

    def _sess(self):
        return dict(authenticated_at=datetime(2026, 10, 1, 9), ended_at=None, ip="10.10.0.5", mac=MAC,
                    hostname=self.hostname, os_label="iOS", natid_masked=self.customer["natid_masked"])

    def run(self, sql, args=()):
        s = " ".join(sql.split())
        low = s.lower()
        self.calls.append((s, tuple(args)))
        if low.startswith("select id, natid_masked, first_seen"):
            return [self.customer] if args[0] == self.customer["id"] else []
        if low.startswith("select natid_enc from customer"):
            return [dict(natid_enc=self.enc)]
        if low.startswith("select hostname, os_label, authenticated_at from portal_session"):
            return [dict(hostname=self.hostname, os_label="iOS", authenticated_at=datetime(2026, 10, 1, 9))]
        if low.startswith("select c.id, c.natid_masked"):
            row = dict(id=7, natid_masked=self.customer["natid_masked"], last_used=datetime(2026, 10, 1, 9))
            if "c.natid_enc" in low:
                row["natid_enc"] = self.enc
            return [row]
        if low.startswith("select ps.mac, ps.hostname, ps.os_label"):
            return [dict(mac=MAC, hostname=self.hostname, os_label="iOS",
                         authenticated_at=datetime(2026, 10, 1, 9))]
        if low.startswith("select ps.authenticated_at, ps.ended_at, ps.ip"):
            return [self._sess()]
        if "from dns_log x" in low:
            return [dict(qname="example.com", n=5)]
        if low.startswith("select count(*) as n, sum(x.bytes_out)"):
            return [dict(n=2, bytes_out=1000, bytes_in=2000)]
        if "from conn_log x" in low:
            return [dict(dst_ip="93.184.216.34", total=3000, n=2)]
        raise AssertionError(f"SQL ไม่รู้จัก: {s[:100]}")

    def find(self, frag):
        return [c for c in self.calls if frag in c[0].lower()]


@pytest.fixture
def env(monkeypatch):
    client = base.make_client(monkeypatch)
    import admin.app as admin_app
    db = SummaryDB()
    o_all, o_one = admin_app.query_all, admin_app.query_one

    def mine(sql):
        low = " ".join(sql.split()).lower()
        return low.startswith("select") and any(k in low for k in (
            "from customer where id", "from customer where id = %s", "from portal_session",
            "from dns_log x", "from conn_log x"))

    monkeypatch.setattr(admin_app, "query_all",
                        lambda s, a=(): db.run(s, a) if mine(s) else o_all(s, a))
    monkeypatch.setattr(admin_app, "query_one",
                        lambda s, a=(): (db.run(s, a) or [None])[0] if mine(s) else o_one(s, a))
    return client, db


def test_requires_login(env):
    client, _ = env
    r = client.get("/logs/summary", query_string=dict(RANGE, mac=MAC))
    assert r.status_code == 302 and "/login" in r.headers["Location"]


@pytest.mark.parametrize("qs", [{}, {"mac": "zz"}, {"mac": MAC, "cid": "7"}, {"cid": "abc"}, {"cid": "0"}])
def test_bad_params_400(env, qs):
    client, db = env
    base._login_as(client, "staff")
    assert client.get("/logs/summary", query_string=dict(RANGE, **qs)).status_code == 400
    assert not base.AUDIT


def test_bad_range_400(env):
    client, _ = env
    base._login_as(client, "staff")
    r = client.get("/logs/summary", query_string=dict(RANGE, mac=MAC, end="2026-12-01T00:00"))
    assert r.status_code == 400


def test_unknown_and_purged_cid_404(env):
    client, db = env
    base._login_as(client, "staff")
    assert client.get("/logs/summary", query_string=dict(RANGE, cid="99")).status_code == 404
    db.customer["natid_masked"] = "PURGED"
    assert client.get("/logs/summary", query_string=dict(RANGE, cid="7")).status_code == 404
    assert not base.AUDIT


def test_mac_summary_sql_uses_mac_and_range(env):
    client, db = env
    base._login_as(client, "staff")
    r = client.get("/logs/summary", query_string=dict(RANGE, mac="aa-bb-cc-dd-ee-01"))
    assert r.status_code == 200
    start, end = datetime(2026, 10, 1), datetime(2026, 10, 2)
    sql, args = db.find("from dns_log x")[0]
    assert "x.mac = %s" in sql and "event_kind = 'query'" in sql and "LIMIT" in sql
    assert args == (start, end, MAC, 20)
    sql, args = db.find("sum(x.bytes_out)")[0]
    assert args == (start, end, MAC)
    assert "ทุกการใช้งานของเครื่องนี้ (อาจหลายลูกค้า)" in r.get_data(as_text=True)


def test_cid_summary_restricts_by_customer_windows(env):
    client, db = env
    base._login_as(client, "staff")
    r = client.get("/logs/summary", query_string=dict(RANGE, cid="7"))
    assert r.status_code == 200
    start, end = datetime(2026, 10, 1), datetime(2026, 10, 2)
    sql, args = db.find("from dns_log x")[0]
    assert "= %s" in sql and "s.authenticated_at <= x.ts" in sql
    from common.log_mapping import session_match   # ต้องเป็นกฎชุดเดียวกับ /logs + export เป๊ะ
    assert session_match("x", "client_ip", "x.ts") in sql
    # กฎเดียวกับ MAPPING_JOIN: ตรงหลาย session = ไม่ระบุตัว ห้ามใช้ EXISTS (แถวกำกวมจะไปโผล่ในสรุปทุกคน)
    assert "CASE WHEN COUNT(*)=1 THEN MAX(s.id) END" in sql and "EXISTS" not in sql
    assert args == (start, end, MAC, 7, 20)
    sql, args = db.find("sum(x.bytes_out)")[0]
    assert "CASE WHEN COUNT(*)=1" in sql and "COALESCE(x.started_at, x.ts)" in sql
    assert args == (start, end, MAC, 7)
    html = r.get_data(as_text=True)
    assert "example.com" in html and "93.184.216.34" in html and "1.9 KB" in html or "KB" in html


def test_staff_sees_masked_only(env):
    client, db = env
    base._login_as(client, "staff")
    for qs in (dict(mac=MAC), dict(cid="7")):
        html = client.get("/logs/summary", query_string=dict(RANGE, **qs)).get_data(as_text=True)
        assert "1-1017-XXXXX-XX-0" in html
        assert not re.search(r"\d{13}", html) and FULL not in html
    assert not any("natid_enc" in c[0].lower() for c in db.calls)


def test_admin_sees_full_id_and_view_natid_audit(env):
    client, db = env
    base._login_as(client, "admin")
    html = client.get("/logs/summary", query_string=dict(RANGE, cid="7")).get_data(as_text=True)
    assert FULL in html
    actions = [a[1] for a in base.AUDIT]
    assert "search_log" in actions and "view_natid_log" in actions
    vn = next(a for a in base.AUDIT if a[1] == "view_natid_log")
    assert "count=1" in vn[4] and not re.search(r"\d{13}", vn[4])
    base.AUDIT.clear()
    html = client.get("/logs/summary", query_string=dict(RANGE, mac=MAC)).get_data(as_text=True)
    assert FULL in html and any(a[1] == "view_natid_log" for a in base.AUDIT)


def test_search_log_audit_written_without_digits(env):
    client, _ = env
    base._login_as(client, "staff")
    client.get("/logs/summary", query_string=dict(RANGE, cid="7"))
    assert len(base.AUDIT) == 1
    a = base.AUDIT[0]
    assert a[1] == "search_log" and a[4].startswith("summary cid=7 start=2026-10-01")
    assert "end=2026-10-02" in a[4] and not re.search(r"\d{13}", a[4])
    base.AUDIT.clear()
    client.get("/logs/summary", query_string=dict(RANGE, mac=MAC))
    assert base.AUDIT[0][4].startswith(f"summary mac={MAC} start=")


def test_hostname_html_escaped(env):
    client, _ = env
    base._login_as(client, "staff")
    html = client.get("/logs/summary", query_string=dict(RANGE, mac=MAC)).get_data(as_text=True)
    assert "<b>iPhone</b>" not in html and "&lt;b&gt;iPhone&lt;/b&gt;" in html


def test_summary_no_store(env):
    """หน้าที่โชว์เลขบัตรเต็มต้องไม่ถูกแคช"""
    client, _ = env
    base._login_as(client, "admin")
    r = client.get("/logs/summary", query_string=dict(RANGE, mac=MAC))
    assert r.status_code == 200 and r.headers["Cache-Control"] == "no-store"
