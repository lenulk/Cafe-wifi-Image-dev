"""
T-LogsSuggest — รายการแนะนำใต้ช่องค้น log (GET /logs/suggest) + การเลือกลูกค้าด้วย cid ที่ /logs

ใช้ DB จำลองชุดเดียวกับ test_logs_search (ผู้ใช้/audit/เมนู) แล้วครอบ admin.app.query_all
เฉพาะ SQL ของตัวแนะนำ (customer / voucher / portal_session) ด้วยตัวจำลองแบบ Python ล้วนในไฟล์นี้
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import test_logs_search as base  # noqa: E402

from common import crypto  # noqa: E402

# เลขบัตรทดสอบ (checksum ถูกทั้งคู่) -- 1101700000010 → masked 1-1017-XXXXX-XX-0
NAT1 = "1101700000010"
NAT2 = "3100600000003"
T = datetime(2026, 10, 12, 14, 3)


def _cust(cid, nat, last_seen=T, visits=5):
    return dict(id=cid, natid_enc=crypto.natid_encrypt(nat), natid_masked=crypto.mask_natid(nat),
                last_seen=last_seen, visit_count=visits)


class SuggestDB:
    def __init__(self):
        self.customers = [_cust(1, NAT1), _cust(2, NAT2, last_seen=datetime(2026, 10, 1))]
        self.vouchers = [dict(customer_id=1, username="CAFE-AB12C", status="active",
                              natid_masked=crypto.mask_natid(NAT1))]
        self.sessions = [
            dict(customer_id=1, mac="AA:BB:CC:DD:EE:01", ip="10.10.0.105", hostname="Somchais-iPhone",
                 os_label="iPhone", started_at=T),
            dict(customer_id=1, mac="AA:BB:CC:DD:EE:01", ip="10.10.0.105", hostname="Somchais-iPhone",
                 os_label="iPhone", started_at=datetime(2026, 10, 10)),
            dict(customer_id=2, mac="11:22:33:44:55:66", ip="192.168.1.20", hostname="DESKTOP_7KQ2L",
                 os_label="Windows", started_at=datetime(2026, 10, 2)),
        ]
        self.calls: list[tuple[str, tuple]] = []

    @staticmethod
    def _like(pattern, value):
        # แปลง LIKE (escape ด้วย \) เป็น regex
        out, i = "", 0
        while i < len(pattern):
            ch = pattern[i]
            if ch == "\\" and i + 1 < len(pattern):
                out += re.escape(pattern[i + 1]); i += 2; continue
            out += ".*" if ch == "%" else "." if ch == "_" else re.escape(ch)
            i += 1
        return re.fullmatch(out, value or "", re.I | re.S) is not None

    def query_all(self, sql, args=()):
        s = " ".join(sql.split()).lower()
        self.calls.append((s, tuple(args)))
        assert "conn_log" not in s and "dns_log" not in s
        if s.startswith("select id, natid_enc"):
            return [c for c in sorted(self.customers, key=lambda c: c["last_seen"], reverse=True)
                    if c["natid_masked"] != "PURGED"]
        if s.startswith("select id, natid_masked, last_seen"):   # staff: ไม่ดึง natid_enc
            return [{k: v for k, v in c.items() if k != "natid_enc"}
                    for c in sorted(self.customers, key=lambda c: c["last_seen"], reverse=True)
                    if c["natid_masked"] != "PURGED"]
        if s.startswith("select customer_id, username from voucher"):
            return [dict(customer_id=v["customer_id"], username=v["username"])
                    for v in self.vouchers if v["customer_id"] in args]
        if s.startswith("select v.customer_id, ps.hostname"):
            return [dict(customer_id=p["customer_id"], hostname=p["hostname"]) for p in
                    sorted(self.sessions, key=lambda p: p["started_at"], reverse=True)
                    if p["customer_id"] in args]
        if s.startswith("select v.username, v.status"):
            return [v for v in self.vouchers if self._like(args[0], v["username"])]
        if "from portal_session where hostname like" in s:
            return self._ps(lambda p: self._like(args[0], p["hostname"]))
        if "from portal_session where mac like" in s:
            return self._ps(lambda p: self._like(args[0], p["mac"]))
        if "from portal_session where ip like" in s:
            return self._ps(lambda p: self._like(args[0], p["ip"]))
        raise AssertionError(f"ไม่รู้จัก SQL: {s[:100]}")

    def _ps(self, pred):
        return [p for p in sorted(self.sessions, key=lambda p: p["started_at"], reverse=True) if pred(p)]


@pytest.fixture
def env(monkeypatch):
    client = base.make_client(monkeypatch)
    import admin.app as admin_app
    db = SuggestDB()
    orig = admin_app.query_all

    def routed(sql, args=()):
        s = " ".join(sql.split()).lower()
        if s.startswith(("select id, natid_enc", "select id, natid_masked, last_seen", "select customer_id", "select v.customer_id",
                         "select v.username, v.status")) or "from portal_session where" in s:
            return db.query_all(sql, args)
        return orig(sql, args)

    monkeypatch.setattr(admin_app, "query_all", routed)
    admin_app._attempts.clear()
    return client, db, admin_app


def _get(client, q):
    r = client.get("/logs/suggest", query_string={"q": q})
    return r, json.loads(r.get_data(as_text=True))


def _suggest_audits():
    return [a for a in base.AUDIT if a[1] == "suggest_natid"]


# ---------------------------------------------------------------- พื้นฐาน
def test_requires_login(env):
    client, _, _ = env
    r = client.get("/logs/suggest", query_string={"q": "abc"})
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_empty_q_returns_no_items(env):
    client, db, _ = env
    base._login_as(client, "admin")
    for q in ("", "   "):
        r, body = _get(client, q)
        assert r.status_code == 200 and body == {"items": []}
    assert db.calls == [] and not _suggest_audits()


# ---------------------------------------------------------------- ลูกค้า: admin vs staff
def test_admin_finds_customer_by_middle_digits(env):
    client, _, _ = env
    base._login_as(client, "admin")
    r, body = _get(client, "11017000")        # 8 หลัก เลยส่วนที่ masked แสดง
    cust = [i for i in body["items"] if i["group"] == "customer"]
    assert len(cust) == 1
    assert cust[0]["q"] == "1-1017-XXXXX-XX-0" and cust[0]["cid"] == 1
    assert cust[0]["label"] == "1-1017-00000-01-0", "admin เห็นเลขเต็มใน label เท่านั้น (q/cid ไม่มีเลขเต็ม)"
    assert "CAFE-AB12C" in cust[0]["detail"] and "Somchais-iPhone" in cust[0]["detail"]
    assert "5 ครั้ง" in cust[0]["detail"] and "2026-10-12 14:03" in cust[0]["detail"]


def test_staff_cannot_use_hidden_digits_but_can_use_visible_ones(env):
    client, db, _ = env
    base._login_as(client, "staff")
    _, body = _get(client, "11017000")        # หลักที่ 6-8 ตรวจไม่ได้ (ไม่ถอดรหัส) → เทียบแค่ 5 หลักแรกที่เห็น
    assert [i["cid"] for i in body["items"] if i["group"] == "customer"] == [1]
    _, body = _get(client, "11018000")        # 5 หลักแรกไม่ตรง
    assert not [i for i in body["items"] if i["group"] == "customer"]
    _, body = _get(client, "110")             # 3 หลักแรกอยู่บน masked
    assert [i["cid"] for i in body["items"] if i["group"] == "customer"] == [1]
    # พนักงานไม่ถอดรหัสและไม่ลง audit
    assert not _suggest_audits()


def test_staff_never_decrypts(env, monkeypatch):
    client, _, _ = env
    base._login_as(client, "staff")
    def boom(blob):
        raise AssertionError("staff ต้องไม่ถอดรหัส")
    monkeypatch.setattr(crypto, "natid_decrypt", boom)
    _, body = _get(client, "1101")
    assert body["items"]


def test_staff_full_13_digits_checks_last_digit(env):
    client, _, _ = env
    base._login_as(client, "staff")
    _, body = _get(client, NAT1)
    assert [i["cid"] for i in body["items"] if i["group"] == "customer"] == [1]
    _, body = _get(client, NAT1[:12] + "9")
    assert not [i for i in body["items"] if i["group"] == "customer"]


def test_admin_non_matching_middle_digits_not_found(env):
    client, _, _ = env
    base._login_as(client, "admin")
    _, body = _get(client, "11017999")
    assert not [i for i in body["items"] if i["group"] == "customer"]


def test_admin_json_has_full_id_only_in_label(env):
    """admin เห็นเลขเต็มรูปแบบ d-dddd-ddddd-dd-d ใน label เท่านั้น -- q/cid/detail (ที่ไปอยู่ใน URL) ไม่มี"""
    client, _, _ = env
    base._login_as(client, "admin")
    for q in ("1101700000010", "11017000", "31006", "1101"):
        r, body = _get(client, q)
        for it in body["items"]:
            assert not re.search(r"\d{13}", re.sub(r"-", "", it["q"])), q
            assert not re.search(r"\d{13}", re.sub(r"-", "", it["detail"])), q
            assert "natid_enc" not in it and "natid_hash" not in it
        text = r.get_data(as_text=True)
        assert NAT1 not in text and NAT2 not in text, "ไม่มีเลขเต็มแบบไม่มีขีด"
    _, body = _get(client, "31006")
    c = [i for i in body["items"] if i["group"] == "customer"]
    assert c[0]["label"] == "3-1006-00000-00-3" and c[0]["q"] == "3-1006-XXXXX-XX-3"


def test_staff_json_never_contains_13_digits(env):
    client, _, _ = env
    base._login_as(client, "staff")
    for q in ("1101700000010", "110", "31006"):
        r, body = _get(client, q)
        text = r.get_data(as_text=True)
        assert not re.search(r"\d{13}", re.sub(r"-", "", text)), q
        for it in body["items"]:
            assert "X" in it["label"] or it["group"] != "customer"


def test_admin_writes_exactly_one_audit_without_typed_digits(env):
    client, _, _ = env
    base._login_as(client, "admin")
    _get(client, "11017000")
    rows = _suggest_audits()
    assert len(rows) == 1
    staff_id, action, _target, _ip, detail = rows[0]
    assert staff_id == 1 and detail == "digits=8 matched=1"
    assert "11017000" not in detail
    _get(client, "99999")                      # ไม่พบก็ยังลง 1 แถว
    assert len(_suggest_audits()) == 2 and _suggest_audits()[1][4] == "digits=5 matched=0"


def test_purged_customer_never_suggested(env):
    client, db, _ = env
    db.customers[0]["natid_masked"] = "PURGED"
    base._login_as(client, "admin")
    _, body = _get(client, "11017000")
    assert not [i for i in body["items"] if i["group"] == "customer"]
    base._login_as(client, "staff")
    _, body = _get(client, "110")
    assert not [i for i in body["items"] if i["group"] == "customer"]


def test_undecryptable_row_is_skipped(env):
    client, db, _ = env
    db.customers.insert(0, dict(id=9, natid_enc=b"x", natid_masked="1-1017-XXXXX-XX-0",
                                last_seen=T, visit_count=1))
    base._login_as(client, "admin")
    r, body = _get(client, "11017000")
    assert r.status_code == 200
    assert [i["cid"] for i in body["items"] if i["group"] == "customer"] == [1]


def test_admin_rate_limit_429(env, monkeypatch):
    client, db, _ = env
    import admin.views.log_suggest as ls
    monkeypatch.setattr(ls, "SUGGEST_NATID_LIMIT", 3)
    base._login_as(client, "admin")
    for _ in range(3):
        assert _get(client, "11017")[0].status_code == 200
    n_audit = len(_suggest_audits())
    db.calls.clear()
    r, body = _get(client, "11017")
    assert r.status_code == 429 and body["items"] == [] and body["error"]
    assert not any(c[0].startswith("select id, natid_enc") for c in db.calls), "เกินลิมิตต้องไม่ถอดรหัส"
    assert len(_suggest_audits()) == n_audit


def test_default_rate_limit_is_120():
    import admin.views.log_suggest as ls
    assert ls.SUGGEST_NATID_LIMIT == 120


# ---------------------------------------------------------------- แหล่งอื่น
def test_voucher_prefix(env):
    client, db, _ = env
    base._login_as(client, "staff")
    for q in ("cafe-ab", "CAFEAB", "ab1"):
        _, body = _get(client, q)
        v = [i for i in body["items"] if i["group"] == "voucher"]
        assert v and v[0]["label"] == v[0]["q"] == "CAFE-AB12C", q
        assert v[0]["detail"] == "active · 1-1017-XXXXX-XX-0"
    # พารามิเตอร์เป็น prefix ที่ normalize แล้ว
    assert any(c[1] == ("CAFE-AB%",) for c in db.calls)


def test_hostname_escapes_wildcards(env):
    client, db, _ = env
    base._login_as(client, "staff")
    _, body = _get(client, "somchai")
    d = [i for i in body["items"] if i["group"] == "device"]
    assert len(d) == 1, "dedupe ตาม MAC"
    assert d[0]["label"] == "Somchais-iPhone" and d[0]["q"] == "AA:BB:CC:DD:EE:01"
    assert "iPhone" in d[0]["detail"] and "2026-10-12 14:03" in d[0]["detail"]
    _, body = _get(client, "%")
    assert not body["items"] or all(i["group"] != "device" for i in body["items"])
    _get(client, "desktop_7k")
    assert any(c[1] == ("%desktop\\_7k%",) for c in db.calls)
    _get(client, "a%b_c")
    assert any(c[1] == ("%a\\%b\\_c%",) for c in db.calls)
    _, body = _get(client, "d_sk")             # _ เป็นตัวอักษรธรรมดา ไม่ใช่ wildcard (ไม่ตรง DESKTOP)
    assert not [i for i in body["items"] if i["group"] == "device"]


def test_mac_partial_normalized(env):
    client, db, _ = env
    base._login_as(client, "staff")
    _, body = _get(client, "aabbc")
    m = [i for i in body["items"] if i["group"] == "mac"]
    assert len(m) == 1 and m[0]["label"] == "AA:BB:CC:DD:EE:01" and m[0]["detail"] == "Somchais-iPhone"
    assert any(c[0].endswith("limit 30") and c[1] == ("AA:BB:C%",) for c in db.calls)
    _, body = _get(client, "11-22-33")
    assert [i["label"] for i in body["items"] if i["group"] == "mac"] == ["11:22:33:44:55:66"]


def test_ip_prefix(env):
    client, _, _ = env
    base._login_as(client, "staff")
    _, body = _get(client, "192.168")
    ip = [i for i in body["items"] if i["group"] == "ip"]
    assert len(ip) == 1 and ip[0]["label"] == ip[0]["q"] == "192.168.1.20"
    assert "DESKTOP_7KQ2L" in ip[0]["detail"]
    _, body = _get(client, "10.10")
    assert [i["label"] for i in body["items"] if i["group"] == "ip"] == ["10.10.0.105"]


def test_max_8_items(env):
    client, db, _ = env
    db.customers = [_cust(i, NAT1) for i in range(1, 8)]
    db.vouchers = [dict(customer_id=1, username=f"CAFE-A000{i}", status="active", natid_masked="x")
                   for i in range(5)]
    base._login_as(client, "staff")
    _, body = _get(client, "11")
    assert len(body["items"]) <= 8
    assert body["items"][0]["group"] == "customer"


# ---------------------------------------------------------------- /logs?cid=
def _logs_sql(env_):
    client, db, admin_app = env_
    seen = []
    orig = admin_app.query_all

    def spy(sql, args=()):
        seen.append((" ".join(sql.split()), tuple(args)))
        return orig(sql, args)
    admin_app.query_all = spy
    return seen


def test_logs_cid_searches_by_customer(env, monkeypatch):
    client, db, admin_app = env
    seen = _logs_sql(env)
    base.CUSTOMERS[0]["natid_masked"] = "1-2345-XXXXX-XX-3"
    orig_one = admin_app.query_one

    def one(sql, args=()):
        if " ".join(sql.split()).lower().startswith("select id, natid_masked from customer"):
            return next((dict(id=c["id"], natid_masked=c["natid_masked"])
                         for c in base.CUSTOMERS if c["id"] == args[0]), None)
        return orig_one(sql, args)
    monkeypatch.setattr(admin_app, "query_one", one)

    base._login_as(client, "admin")
    base._conn(0)
    base._conn(5, mac="11:22:33:44:55:66", src="10.10.0.200", dst="1.1.1.1")
    html = client.get("/logs", query_string=base._q(q="1-2345-XXXXX-XX-3", cid="1")).get_data(as_text=True)
    assert "93.184.216.34" in html and "1.1.1.1" not in html
    sql = next(s for s in seen if "from conn_log cl" in s[0].lower())
    assert "c.id = %s" in sql[0] and 1 in sql[1]
    assert "kind=customer" in base.AUDIT[-1][4] and "q=1-2345-XXXXX-XX-3" in base.AUDIT[-1][4]

    # แก้ข้อความหลังเลือก → ทิ้ง cid ใช้การเดาชนิดตามปกติ (ที่นี่ = ถูกมองเป็นชื่อ kind=name)
    r = client.get("/logs", query_string=base._q(q="1-2345-XXXXX-XX-9", cid="1"))
    assert r.status_code == 200 and "kind=name" in base.AUDIT[-1][4]
    r = client.get("/logs", query_string=base._q(q="aa:bb:cc:dd:ee:01", cid="1"))
    assert r.status_code == 200 and "kind=mac" in base.AUDIT[-1][4]


def test_logs_without_cid_still_has_cid_param(env):
    client, _, _ = env
    base._login_as(client, "admin")
    r = client.get("/logs")
    assert r.status_code == 200


def test_logs_pages_no_store(env):
    """/logs และ /logs/suggest โชว์เลขบัตรเต็มให้ admin -- ห้ามอยู่ในแคชเบราว์เซอร์"""
    client, _, _ = env
    base._login_as(client, "admin")
    r = client.get("/logs/suggest", query_string={"q": "abc"})
    assert r.status_code == 200 and r.headers["Cache-Control"] == "no-store"
    r = client.get("/logs", query_string=base._q())
    assert r.status_code == 200 and r.headers["Cache-Control"] == "no-store"
