"""
T-LogsNatid — admin เห็นเลขบัตรเต็มในหน้าค้นหา log/CSV (staff เห็นแต่ masked) + UX ของหน้า /logs

ใช้ DB จำลองชุดเดียวกับ test_logs_search (import เป็น base)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import test_logs_search as base  # noqa: E402

from common import crypto  # noqa: E402

NAT = base.NATID_A                 # 1101700000010
FMT = "1-1017-00000-01-0"


@pytest.fixture
def client(monkeypatch):
    return base.make_client(monkeypatch)


def _enable_full_natid():
    base.CUSTOMERS[0]["natid_enc"] = crypto.natid_encrypt(NAT)


def _digits13(text: str) -> bool:
    return re.search(r"\d{13}", text.replace("-", "")) is not None


# ---------------------------------------------------------------- staff
def test_staff_html_has_no_full_id_and_never_selects_natid_enc(client):
    _enable_full_natid()           # แม้ DB มีกุญแจถอด staff ก็ต้องไม่ได้
    base._login_as(client, "staff")
    base._conn(0)
    html = client.get("/logs", query_string=base.AUG1).get_data(as_text=True)
    assert "1-2345-XXXXX-XX-3" in html
    assert not _digits13(html)
    assert not any("natid_enc" in s for s in base.SQL_SEEN)
    assert not [a for a in base.AUDIT if a[1] == "view_natid_log"]


def test_staff_cannot_get_csv_so_no_full_id(client):
    _enable_full_natid()
    base._login_as(client, "staff")
    base._conn(0)
    assert client.get("/logs", query_string=base._q(format="csv")).status_code == 403
    assert not any("natid_enc" in s for s in base.SQL_SEEN)


# ---------------------------------------------------------------- admin HTML
def test_admin_html_shows_formatted_full_id_and_audits_once(client):
    _enable_full_natid()
    base._login_as(client, "admin")
    base._conn(0)
    base._conn(5)
    html = client.get("/logs", query_string=base.AUG1).get_data(as_text=True)
    assert html.count(f">{FMT}</a>") == 2
    assert NAT not in html
    rows = [a for a in base.AUDIT if a[1] == "view_natid_log"]
    assert len(rows) == 1, "หนึ่งหน้า = หนึ่งแถว ไม่ว่ามีกี่แถวผลลัพธ์"
    detail = rows[0][4]
    assert "natid_full=1" in detail and "log_type=conn" in detail and "page=1" in detail
    assert not _digits13(detail) and "1101" not in detail
    # search_log มาก่อน view_natid_log (ลงก่อนส่งหน้า)
    assert [a[1] for a in base.AUDIT][:2] == ["search_log", "view_natid_log"]


def test_admin_link_uses_masked_q_and_cid_not_full_id(client):
    _enable_full_natid()
    base._login_as(client, "admin")
    base._conn(0)
    html = client.get("/logs", query_string=base.AUG1).get_data(as_text=True)
    assert "q=1-2345-XXXXX-XX-3" in html and "cid=1" in html
    assert "q=1-1017" not in html and NAT not in html


def test_admin_no_audit_row_when_no_full_id_shown(client):
    base._login_as(client, "admin")
    base._conn(0)                  # ไม่มี natid_enc -> ถอดไม่ได้ -> แสดง masked
    html = client.get("/logs", query_string=base.AUG1).get_data(as_text=True)
    assert "1-2345-XXXXX-XX-3" in html
    assert not [a for a in base.AUDIT if a[1] == "view_natid_log"]


def test_purged_customer_is_not_decrypted(client):
    _enable_full_natid()
    base.CUSTOMERS[0]["natid_masked"] = "PURGED"
    try:
        base._login_as(client, "admin")
        base._conn(0)
        html = client.get("/logs", query_string=base.AUG1).get_data(as_text=True)
        assert FMT not in html
        assert not [a for a in base.AUDIT if a[1] == "view_natid_log"]
        sel = [s for s in base.SQL_SEEN if "natid_enc" in s]
        assert sel and "natid_masked <> %s" in sel[0], "คิวรี่ต้องกรอง PURGED"
    finally:
        base.CUSTOMERS[0]["natid_masked"] = "1-2345-XXXXX-XX-3"


def test_undecryptable_blob_falls_back_to_masked(client):
    base.CUSTOMERS[0]["natid_enc"] = b"garbage-garbage-garbage-garbage-garbage"
    base._login_as(client, "admin")
    base._conn(0)
    r = client.get("/logs", query_string=base.AUG1)
    assert r.status_code == 200 and "1-2345-XXXXX-XX-3" in r.get_data(as_text=True)


def test_audit_failure_blocks_page(client, monkeypatch):
    """log_required ล้มเหลว = ไม่ส่งหน้าที่มีเลขเต็ม"""
    _enable_full_natid()
    from common import audit
    orig = audit.log_required

    def boom(action, *a, **k):
        if action == audit.VIEW_NATID_LOG:
            raise RuntimeError("db down")
        return orig(action, *a, **k)
    monkeypatch.setattr(audit, "log_required", boom)
    base._login_as(client, "admin")
    base._conn(0)
    client.application.config["PROPAGATE_EXCEPTIONS"] = False
    r = client.get("/logs", query_string=base.AUG1)
    assert r.status_code == 500 and FMT not in r.get_data(as_text=True)


def test_hint_shows_full_id_for_admin_and_counts(client):
    _enable_full_natid()
    base._login_as(client, "admin")
    from datetime import datetime
    base.SESSIONS[0]["ended_at"] = datetime(2026, 8, 1, 9, 0)
    try:
        base._conn(30, dst="10.10.0.1", dst_port=53, proto="udp")
        html = client.get("/logs", query_string=base.AUG1).get_data(as_text=True)
        assert f"เคยใช้สิทธิ์ของ {FMT}" in html
        rows = [a for a in base.AUDIT if a[1] == "view_natid_log"]
        assert len(rows) == 1 and "natid_full=1" in rows[0][4]
    finally:
        base.SESSIONS[0]["ended_at"] = datetime(2026, 8, 3, 0, 0)


# ---------------------------------------------------------------- CSV
def test_admin_csv_has_customer_natid_column_and_audit_count(client):
    _enable_full_natid()
    base._login_as(client, "admin")
    base._conn(0)
    body = client.get("/logs", query_string=base._q(format="csv")).get_data(as_text=True)
    lines = body.lstrip("﻿").splitlines()
    header = lines[0].split(",")
    assert "customer_natid" in header and "customer_masked" in header
    cells = lines[1].split(",")
    assert cells[header.index("customer_natid")] == FMT
    assert cells[header.index("customer_masked")] == "1-2345-XXXXX-XX-3"
    last = base.AUDIT[-1]
    assert last[1] == "export_log" and "natid_full=1" in last[4] and "rows=1" in last[4]
    assert not _digits13(last[4])
    assert not [a for a in base.AUDIT if a[1] == "view_natid_log"], "CSV ใช้แถว export_log แถวเดียว"


def test_admin_dns_csv_has_customer_natid_column(client):
    _enable_full_natid()
    base._login_as(client, "admin")
    base._dns(0, "www.example.com", None)
    body = client.get("/logs", query_string=base._q(format="csv", log_type="dns")).get_data(as_text=True)
    header = body.lstrip("﻿").splitlines()[0].split(",")
    assert "customer_natid" in header
    assert FMT in body
    assert "natid_full=1" in base.AUDIT[-1][4]


# ---------------------------------------------------------------- A1 LIKE wildcard
def test_underscore_in_hostname_search_is_literal(client):
    base._login_as(client, "admin")
    base.SESSIONS[0]["hostname"] = "my-pc"
    base._conn(0)
    html = client.get("/logs", query_string=base._q(q="my_pc")).get_data(as_text=True)
    assert "93.184.216.34" not in html, "my_pc ต้องไม่ตรงกับ my-pc"
    base.SESSIONS[0]["hostname"] = "my_pc"
    html = client.get("/logs", query_string=base._q(q="my_pc")).get_data(as_text=True)
    assert "93.184.216.34" in html
    base.SESSIONS[0]["hostname"] = "Somchais-iPhone"


def test_like_params_are_escaped():
    from common.sqlutil import like_escape, format_natid
    assert like_escape(r"a%b_c\d") == r"a\%b\_c\\d"
    assert format_natid(NAT) == FMT and format_natid("123") == "123"


# ---------------------------------------------------------------- A2 interpreted kind
@pytest.mark.parametrize("q,expect", [
    ("aa-bb-cc-dd-ee-01", "ค้นเป็น: <strong>MAC AA:BB:CC:DD:EE:01"),
    (NAT, "ค้นเป็น: <strong>เลขบัตร 1-1017-XXXXX-XX-0"),
    ("cafe-8f3k2", "เลขอ้างอิง CAFE-8F3K2"),
    ("1.1.1.1", "IP 1.1.1.1"),
    ("example.com", "ชื่อเว็บ example.com"),
    ("tracker", "ชื่อเครื่องหรือชื่อเว็บ tracker"),
])
def test_kind_label_shown(client, q, expect):
    base._login_as(client, "staff")
    html = client.get("/logs", query_string=base._q(q=q)).get_data(as_text=True)
    assert expect in html
    if q != NAT:       # ช่องค้นสะท้อนสิ่งที่พนักงานพิมพ์เองกลับมา (เดิมเป็นอยู่แล้ว) ส่วนป้ายตีความต้องเป็น masked
        assert not _digits13(html)


def test_kind_label_customer_selected(client):
    base._login_as(client, "admin")
    import admin.app as admin_app
    orig = admin_app.query_one
    admin_app.query_one = lambda sql, args=(): (
        dict(id=1, natid_masked="1-2345-XXXXX-XX-3") if sql.lower().lstrip().startswith("select id, natid_masked")
        else orig(sql, args))
    try:
        html = client.get("/logs", query_string=base._q(q="1-2345-XXXXX-XX-3", cid="1")).get_data(as_text=True)
    finally:
        admin_app.query_one = orig
    assert "ลูกค้าที่เลือก" in html


# ---------------------------------------------------------------- A3 pivot links
def test_customer_cell_pivots_by_cid_with_masked_q(client):
    base._login_as(client, "staff")
    base._conn(0)
    html = client.get("/logs", query_string=base.AUG1).get_data(as_text=True)
    m = re.search(r'href="([^"]*q=1-2345-XXXXX-XX-3[^"]*)"', html)
    assert m and "cid=1" in m.group(1) and "page=1" in m.group(1)


def test_other_pivots_clear_cid(client):
    base._login_as(client, "admin")
    base._conn(0)
    html = client.get("/logs", query_string=base._q(cid="1")).get_data(as_text=True)
    m = re.search(r'href="([^"]*q=AA:BB:CC:DD:EE:01[^"]*)"', html)
    assert m and "cid=1" not in m.group(1)


def test_summary_link_only_when_view_exists(client):
    base._login_as(client, "admin")
    base._conn(0)
    has = "log_summary" in client.application.view_functions
    html = client.get("/logs", query_string=base.AUG1).get_data(as_text=True)
    assert ("/logs/summary" in html) == has
    saved = client.application.view_functions.pop("log_summary", None)
    try:
        html = client.get("/logs", query_string=base.AUG1).get_data(as_text=True)
        assert "sumlink\" href" not in html and r"/logs/summary" not in html
    finally:
        if saved:
            client.application.view_functions["log_summary"] = saved
