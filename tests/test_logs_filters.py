"""
T-LogsFilters — ช่อง "ปลายทาง" (site), พอร์ต/โปรโตคอล, ช่วง IP (CIDR), การจับคู่โดเมนด้วย qname_rev
และชื่อปลายทาง dst_name ในหน้า /logs

ตรวจ SQL+args ที่ประกอบขึ้นจริง (ดักที่ core.query_all) -- ไม่ต้องจำลองข้อมูลทั้งชุด
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import test_logs_search as base  # noqa: E402

COLS = {("dns_log", "qname_rev"): True, ("conn_log", "dst_name"): True}


@pytest.fixture
def env(monkeypatch):
    client = base.make_client(monkeypatch)
    from admin import app as core
    from admin.views import logs
    COLS.update({("dns_log", "qname_rev"): True, ("conn_log", "dst_name"): True})
    monkeypatch.setattr(logs, "_has_column", lambda t, c: COLS.get((t, c), False))
    seen: list = []
    result: list = []

    def spy(sql, args=()):
        s = " ".join(sql.split())
        seen.append((s, tuple(args)))
        return list(result) if "FROM conn_log cl" in s or "FROM dns_log dl" in s else []

    monkeypatch.setattr(core, "query_all", spy)
    base._login_as(client, "admin")
    client.seen, client.result = seen, result
    return client


def _main(client):
    """SQL ค้นหลัก (ตัวสุดท้ายที่ SELECT จาก conn_log/dns_log ของหน้านี้)"""
    return [x for x in client.seen if "FROM conn_log cl" in x[0] or "FROM dns_log dl" in x[0]][-1]


def _get(client, **kw):
    return client.get("/logs", query_string=base._q(**kw))


# ---------------------------------------------------------------- site (AND กับ q)
def test_site_ip_and_q_conn(env):
    r = _get(env, q="aa:bb:cc:dd:ee:01", site="93.184.216.34")
    assert r.status_code == 200
    sql, args = _main(env)
    assert "AND cl.mac = %s" in sql and "AND cl.dst_ip = %s" in sql
    assert "93.184.216.34" in args and "AA:BB:CC:DD:EE:01" in args
    html = r.get_data(as_text=True)
    assert "ปลายทาง: <strong>IP 93.184.216.34" in html and "MAC AA:BB:CC:DD:EE:01" in html and " + " in html


def test_site_ip_dns_matches_answer(env):
    _get(env, log_type="dns", q="aa:bb:cc:dd:ee:01", site="93.184.216.34", answers="1")
    sql, args = _main(env)
    assert "AND dl.mac = %s" in sql and "AND dl.answer = %s" in sql


def test_site_ip_dns_without_answers_box_still_finds_answers(env):
    # dl.answer มีเฉพาะแถว answer -- ถ้ายังกรอง event_kind='query' จะได้ 0 แถวเสมอ (ผลลบลวง)
    for site in ("93.184.216.34", "93.184.216.0/24"):
        r = _get(env, log_type="dns", site=site)
        assert r.status_code == 200
        sql, _ = _main(env)
        assert "dl.answer" in sql and "event_kind = 'query'" not in sql
        assert "แสดงคำตอบ DNS ให้อัตโนมัติ" in r.get_data(as_text=True)


def test_main_q_ip_dns_also_shows_answers(env):
    for q in ("93.184.216.34", "93.184.216.0/24"):
        r = _get(env, log_type="dns", q=q)
        assert r.status_code == 200
        sql, _ = _main(env)
        assert "dl.answer" in sql and "event_kind = 'query'" not in sql
        assert "แสดงคำตอบ DNS ให้อัตโนมัติ" in r.get_data(as_text=True)


def test_site_domain_dns_keeps_query_only_default(env):
    _get(env, log_type="dns", site="example.com")
    assert "dl.event_kind = 'query'" in _main(env)[0]


def test_site_only_without_q_searches(env):
    r = env.get("/logs", query_string={"site": "1.1.1.1"})
    assert r.status_code == 200
    assert "cl.dst_ip = %s" in _main(env)[0]
    assert "site=1.1.1.1" in base.AUDIT[0][4]


def test_site_domain_dns_uses_qname_rev(env):
    _get(env, log_type="dns", q="aa:bb:cc:dd:ee:01", site="Facebook.com")
    sql, args = _main(env)
    assert "(dl.qname = %s OR dl.qname_rev LIKE %s)" in sql
    assert "facebook.com" in args and "moc.koobecaf.%" in args


def test_site_domain_conn_dst_name_with_null_fallback(env):
    r = _get(env, q="aa:bb:cc:dd:ee:01", site="facebook.com")
    sql, args = _main(env)
    assert "(cl.dst_name = %s OR cl.dst_name LIKE %s)" in sql
    assert "cl.dst_name IS NULL AND cl.dst_ip IN (SELECT d2.answer FROM dns_log d2" in sql
    assert "(d2.qname = %s OR d2.qname_rev LIKE %s)" in sql
    assert "facebook.com" in args and "%.facebook.com" in args
    assert "เฉพาะแถวเก่าที่ไม่มีชื่อ" in r.get_data(as_text=True)


def test_site_name_is_substring(env):
    _get(env, log_type="dns", site="face_book")
    sql, args = _main(env)
    assert "dl.qname LIKE %s" in sql and "qname_rev" not in sql
    assert "%face\\_book%" in args


def test_site_bad_value_is_400(env):
    r = _get(env, site="<script>")
    assert r.status_code == 400 and "ช่องปลายทาง" in r.get_data(as_text=True)
    assert not base.AUDIT


def test_site_carried_in_pagination_csv_tabs(env):
    env.result.extend({"ts": datetime(2026, 8, 1, 10, i), "started_at": None, "mac": None, "src_ip": "10.10.0.5",
                       "src_port": 1, "dst_ip": "1.1.1.1", "dst_name": None, "dst_port": 443, "proto": "tcp",
                       "bytes_out": 1, "bytes_in": 1, "voucher_username": None, "natid_masked": None,
                       "customer_id": None, "device_hostname": None, "device_os": None} for i in range(51))
    html = _get(env, q="1.1.1.1", site="example.com", port="443", proto="tcp").get_data(as_text=True)
    assert "page=2" in html
    for frag in ("site=example.com", "port=443", "proto=tcp"):
        assert html.count(frag) >= 4, frag      # แท็บ 2 + ถัดไป + CSV (+ ลิงก์ค้นต่อ)


def test_site_in_audit_detail(env):
    _get(env, q="aa:bb:cc:dd:ee:01", site="example.com", port="443", proto="udp")
    d = base.AUDIT[-1][4]
    assert "site=example.com" in d and "site_kind=domain" in d and "port=443" in d and "proto=udp" in d
    base.AUDIT.clear()
    _get(env)
    d = base.AUDIT[-1][4]
    assert "site=-" in d and "port=-" in d and "proto=-" in d


# ---------------------------------------------------------------- port / proto
def test_port_and_proto_filters(env):
    _get(env, port="443", proto="udp")
    sql, args = _main(env)
    assert "AND cl.dst_port = %s" in sql and "AND cl.proto = %s" in sql
    assert 443 in args and "udp" in args


def test_proto_other(env):
    _get(env, proto="other")
    sql, args = _main(env)
    assert "cl.proto NOT IN ('tcp', 'udp', 'icmp')" in sql and "other" not in args


@pytest.mark.parametrize("kw", [dict(port="0"), dict(port="65536"), dict(port="abc"), dict(port="-1"),
                                dict(proto="sctp"), dict(proto="tcp;drop")])
def test_port_proto_invalid_400(env, kw):
    assert _get(env, **kw).status_code == 400
    assert not base.AUDIT


def test_port_proto_ignored_and_hidden_on_dns_tab(env):
    r = _get(env, log_type="dns", port="999999", proto="zzz")
    assert r.status_code == 200
    sql, _ = _main(env)
    assert "dst_port" not in sql and "proto" not in sql
    html = r.get_data(as_text=True)
    assert 'name="port"' not in html and 'name="proto"' not in html
    assert 'name="port"' in _get(env).get_data(as_text=True)


# ---------------------------------------------------------------- CIDR
def test_cidr_q_conn(env):
    r = _get(env, q="192.168.50.7/24")
    assert r.status_code == 200
    sql, args = _main(env)
    assert sql.count("INET6_ATON(cl.src_ip) BETWEEN INET6_ATON(%s) AND INET6_ATON(%s)") == 1
    assert "INET6_ATON(cl.dst_ip) BETWEEN" in sql and " OR " in sql
    assert "cl.src_ip LIKE '%%.%%'" in sql and "cl.dst_ip LIKE '%%.%%'" in sql
    assert args[2:6] == ("192.168.50.0", "192.168.50.255", "192.168.50.0", "192.168.50.255")
    assert "ช่วง IP 192.168.50.0/24" in r.get_data(as_text=True)
    assert "kind=cidr" in base.AUDIT[0][4]


def test_cidr_q_dns_and_ipv6_guard(env):
    _get(env, log_type="dns", q="2001:db8:1::/48")
    sql, args = _main(env)
    assert "INET6_ATON(dl.client_ip) BETWEEN" in sql and "INET6_ATON(dl.answer) BETWEEN" in sql
    assert "dl.answer LIKE '%%:%%'" in sql
    assert "2001:db8:1::" in args


def test_cidr_site_conn_and_dns(env):
    _get(env, q="aa:bb:cc:dd:ee:01", site="157.240.0.0/16")
    sql, args = _main(env)
    assert "INET6_ATON(cl.dst_ip) BETWEEN" in sql and "cl.src_ip" not in sql.split("WHERE cl.ts", 1)[1]
    assert "157.240.0.0" in args and "157.240.255.255" in args
    _get(env, log_type="dns", site="157.240.0.0/16")
    sql, _ = _main(env)
    assert "INET6_ATON(dl.answer) BETWEEN" in sql


@pytest.mark.parametrize("val", ["10.0.0.0/8", "0.0.0.0/0", "10.0.0.0/15", "2001:db8::/32", "::/0"])
def test_cidr_too_wide_rejected(env, val):
    for key in ("q", "site"):
        r = _get(env, **{key: val})
        assert r.status_code == 400 and "กว้างเกินไป" in r.get_data(as_text=True), (key, val)


@pytest.mark.parametrize("val", ["10.0.0.0/16", "2001:db8:1::/48", "10.1.2.3/32"])
def test_cidr_limits_accepted(env, val):
    assert _get(env, q=val).status_code == 200
    assert _get(env, site=val).status_code == 200


def test_cidr_garbage_rejected(env):
    assert _get(env, q="1.2.3.4/99").status_code == 400
    assert _get(env, site="foo/bar").status_code == 400


# ---------------------------------------------------------------- domain_condition / fallback
def test_q_domain_dns_uses_domain_condition_when_detected(env):
    r = _get(env, log_type="dns", q="facebook.com")
    sql, args = _main(env)
    assert "(dl.qname = %s OR dl.qname_rev LIKE %s)" in sql and "dl.qname LIKE" not in sql
    assert "โดเมนย่อย" in r.get_data(as_text=True)


def test_q_domain_dns_falls_back_to_like_without_qname_rev(env):
    COLS[("dns_log", "qname_rev")] = False
    r = _get(env, log_type="dns", q="facebook.com")
    sql, args = _main(env)
    assert "dl.qname LIKE %s" in sql and "qname_rev" not in sql and "%facebook.com%" in args
    assert "โดเมนย่อย" not in r.get_data(as_text=True)


def test_q_name_stays_substring_even_with_qname_rev(env):
    _get(env, log_type="dns", q="tracker")
    sql, args = _main(env)
    assert "ps.hostname LIKE %s" in sql and "dl.qname LIKE %s" in sql and "qname_rev" not in sql


def test_conn_domain_subquery_uses_rev_and_dst_name(env):
    _get(env, q="facebook.com")
    sql, args = _main(env)
    assert "cl.dst_name IS NULL" in sql and "d2.qname_rev LIKE %s" in sql
    assert "%.facebook.com" in args


def test_conn_domain_without_dst_name_column_keeps_old_approximation(env):
    COLS[("conn_log", "dst_name")] = False
    COLS[("dns_log", "qname_rev")] = False
    r = _get(env, q="example.com")
    sql, args = _main(env)
    assert "dst_name" not in sql
    assert "cl.dst_ip IN (SELECT d2.answer FROM dns_log d2 WHERE d2.qname LIKE %s" in sql
    assert "ประมาณจาก IP" in r.get_data(as_text=True)


def test_has_column_detects_and_caches(monkeypatch):
    from admin import app as core
    from admin.views import logs
    logs._COLUMN_CACHE.clear()
    calls = []
    monkeypatch.setattr(core, "query_one", lambda s, a=(): calls.append(a) or {"ok": 1})
    assert logs._has_column("dns_log", "qname_rev") is True
    assert logs._has_column("dns_log", "qname_rev") is True
    assert len(calls) == 1 and calls[0] == ("dns_log", "qname_rev")
    logs._COLUMN_CACHE.clear()

    def boom(s, a=()):
        raise RuntimeError("db down")
    monkeypatch.setattr(core, "query_one", boom)
    assert logs._has_column("conn_log", "dst_name") is False
    monkeypatch.setattr(core, "query_one", lambda s, a=(): None)
    assert logs._has_column("conn_log", "dst_name") is False
    logs._COLUMN_CACHE.clear()


# ---------------------------------------------------------------- dst_name แสดงผล + CSV
def _row(**kw):
    r = {"ts": datetime(2026, 8, 1, 10, 0), "started_at": None, "mac": None, "src_ip": "10.10.0.5",
         "src_port": 1, "dst_ip": "157.240.1.35", "dst_name": "star.facebook.com", "dst_port": 443,
         "proto": "tcp", "bytes_out": 1, "bytes_in": 1, "voucher_username": None, "natid_masked": None,
         "customer_id": None, "device_hostname": None, "device_os": None}
    r.update(kw)
    return r


def test_dst_name_selected_and_shown(env):
    env.result.append(_row())
    html = _get(env).get_data(as_text=True)
    assert "cl.dst_name," in _main(env)[0]
    tbl = html[html.index("<table>"):]
    assert tbl.index("star.facebook.com") < tbl.index("157.240.1.35")
    env.result[:] = [_row(dst_name=None)]
    assert "star.facebook.com" not in _get(env).get_data(as_text=True)


def test_dst_name_not_selected_without_column(env):
    COLS[("conn_log", "dst_name")] = False
    env.result.append(_row(dst_name=None))
    assert _get(env).status_code == 200
    assert "dst_name" not in _main(env)[0]


def test_csv_has_dst_name(env):
    env.result.append(_row())
    lines = _get(env, format="csv").get_data(as_text=True).splitlines()
    header = lines[0].lstrip("﻿").split(",")
    assert header[header.index("dst_ip") + 1] == "dst_name"
    assert "star.facebook.com" in lines[1]
