"""
Setup wizard ของ image (app/setup) -- M4 · ฐานข้อมูลจำลองในหน่วยความจำ ไม่ต้องมี MariaDB/root/เครือข่ายจริง
"""
import contextlib
import importlib
import json
import re

import pytest

CODE = "K7QM29XD"
GOOD_PW = "CafeWifi2026Secure"
UPLINK = {"nic": "eth0", "ip": "192.168.1.57", "prefix": 24, "gw": "192.168.1.1"}
STAFF: list[dict] = []
ROUTER_OK = {"ok": True, "dhcp": {"ok": True, "servers": []}, "ipv6": {"ok": True, "routers": []}}
ROUTER_DHCP_ON = {"ok": False, "dhcp": {"ok": False, "servers": [{"server_ip": "192.168.1.1"}]},
                  "ipv6": {"ok": True, "routers": []}}


class FakeCursor:
    lastrowid = None

    def __init__(self):
        self._rows = []

    def execute(self, sql, args=()):
        s = " ".join(sql.split()).lower()
        if s.startswith("select count(*) as n from staff"):
            self._rows = [{"n": len(STAFF)}]
        elif s.startswith("insert into staff"):
            STAFF.append({"id": len(STAFF) + 1, "username": args[0], "password_hash": args[1]})
            self.lastrowid = len(STAFF)
        else:
            self._rows = []

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeConn:
    def cursor(self):
        return FakeCursor()


@pytest.fixture
def wiz(tmp_path, monkeypatch):
    STAFF.clear()
    etc, run, state = tmp_path / "etc", tmp_path / "run", tmp_path / "state"
    for d in (etc, run, state):
        d.mkdir()
    (etc / "setup-code").write_text(CODE + "\n", encoding="utf-8")
    monkeypatch.setenv("ETC_DIR", str(etc))
    monkeypatch.setenv("SETUP_RUN_DIR", str(run))
    monkeypatch.setenv("APPLY_STATE_DIR", str(state))

    import common.db as db
    monkeypatch.setattr(db, "execute", lambda s, a=(): 1)   # audit.log
    mod = importlib.reload(importlib.import_module("setup.app"))
    monkeypatch.setattr(mod, "get_conn", lambda: contextlib.nullcontext(FakeConn()))
    monkeypatch.setattr(mod, "query_one", lambda s, a=(): {"n": len(STAFF)})
    from setup import netinfo
    monkeypatch.setattr(netinfo, "current_uplink", lambda: dict(UPLINK))
    (tmp_path / "net" / "eth0").mkdir(parents=True)
    monkeypatch.setattr(netinfo, "SYS_NET", tmp_path / "net")
    from tools import check_router
    calls = {"result": ROUTER_OK}
    monkeypatch.setattr(check_router, "check", lambda iface, *a, **k: calls["result"])
    mod.app.config.update(TESTING=True)
    c = mod.app.test_client()
    c.mod, c.etc, c.run, c.state, c.router = mod, etc, run, state, calls
    return c


def csrf(c, path="/code"):
    html = c.get(path).get_data(as_text=True)
    m = re.search(r'name="csrf" value="([^"]+)"', html)
    assert m, html[:300]
    return m.group(1)


def login(c, code="k7qm-29xd"):
    return c.post("/code", data={"csrf": csrf(c), "code": code})


def make_admin(c):
    return c.post("/admin", data={"csrf": csrf(c, "/admin"), "username": "owner", "password": GOOD_PW,
                                  "password_confirm": GOOD_PW})


def net_form(c, **over):
    d = {"csrf": csrf(c, "/network"), "nic": "eth0", "uplink_cidr": "192.168.1.57/24",
         "uplink_gw": "192.168.1.1", "client_cidr": "10.10.0.1/24", "gateway_name": "Baan & Co",
         "retention_days": "180"}
    d.update(over)
    return c.post("/network", data=d)


# ------------------------------------------------------------------ ① code
def test_every_page_requires_code(wiz):
    for p in ("/", "/admin", "/network", "/router"):
        r = wiz.get(p)
        assert r.status_code == 302 and r.headers["Location"].endswith("/code"), p


def test_post_without_csrf_rejected(wiz):
    assert wiz.post("/code", data={"code": CODE}).status_code == 400


def test_code_normalized_and_accepted(wiz):
    r = login(wiz)
    assert r.status_code == 302
    assert wiz.get("/").headers["Location"].endswith("/admin")


def test_wrong_code_locks_after_5(wiz):
    for i in range(5):
        r = login(wiz, "WRONG000")
        assert r.status_code == 400
    r = login(wiz)                       # ถูกแล้วก็ยังเข้าไม่ได้ช่วงล็อก
    assert r.status_code == 429 and "ล็อก" in r.get_data(as_text=True)


def test_new_code_invalidates_old_session(wiz):
    login(wiz)
    (wiz.etc / "setup-code").write_text("ZZZZ2222\n")    # เตรียมการ์ดใหม่
    assert wiz.get("/admin").headers["Location"].endswith("/code")


# ------------------------------------------------------------------ ② admin
def test_weak_password_rejected(wiz):
    login(wiz)
    r = wiz.post("/admin", data={"csrf": csrf(wiz, "/admin"), "username": "owner",
                                 "password": "short", "password_confirm": "short"})
    assert r.status_code == 400 and STAFF == []


def test_admin_created_once(wiz):
    login(wiz)
    assert make_admin(wiz).headers["Location"].endswith("/network")
    assert len(STAFF) == 1 and GOOD_PW not in STAFF[0]["password_hash"]
    assert wiz.get("/admin").headers["Location"].endswith("/network")


# ------------------------------------------------------------------ ③ network
def test_network_suggests_current_lease(wiz):
    login(wiz); make_admin(wiz)
    html = wiz.get("/network").get_data(as_text=True)
    assert 'value="192.168.1.57/24"' in html and 'value="192.168.1.1"' in html and 'value="10.10.0.1/24"' in html


def test_network_prefills_shop_name_from_firstboot(wiz, monkeypatch):
    monkeypatch.setenv("GATEWAY_NAME", "Baan Cafe")
    login(wiz); make_admin(wiz)
    assert 'value="Baan Cafe"' in wiz.get("/network").get_data(as_text=True)


def test_network_keeps_retention_after_factory_reset(wiz, monkeypatch):
    monkeypatch.setenv("LOG_RETENTION_DAYS", "365")
    login(wiz); make_admin(wiz)
    assert 'value="365"' in wiz.get("/network").get_data(as_text=True)


def test_network_rejects_overlap_and_short_retention(wiz):
    login(wiz); make_admin(wiz)
    r = net_form(wiz, client_cidr="192.168.1.200/24", retention_days="30")
    body = r.get_data(as_text=True)
    assert r.status_code == 400 and "ชน" in body and "90" in body


def test_network_rejects_dangerous_shop_name(wiz):
    login(wiz); make_admin(wiz)
    assert net_form(wiz, gateway_name="x'; rm -rf /").status_code == 400


# ------------------------------------------------------------------ ④ router + ⑤ apply
def test_apply_hidden_until_router_check_passes(wiz):
    login(wiz); make_admin(wiz); net_form(wiz)
    html = wiz.get("/router").get_data(as_text=True)
    assert "บันทึกและเปิดระบบ" not in html
    tok = csrf(wiz, "/router")
    r = wiz.post("/apply", data={"csrf": tok})          # ยิงตรงก็ไม่ได้
    assert r.status_code == 302 and not (wiz.run / "apply.json").exists()


def test_router_dhcp_on_blocks_apply(wiz):
    login(wiz); make_admin(wiz); net_form(wiz)
    wiz.router["result"] = ROUTER_DHCP_ON
    wiz.post("/router/check", data={"csrf": csrf(wiz, "/router")})
    html = wiz.get("/router").get_data(as_text=True)
    assert "ยังเปิดอยู่" in html and "192.168.1.1" in html and "บันทึกและเปิดระบบ" not in html


def test_full_flow_writes_validated_request(wiz):
    login(wiz); make_admin(wiz); net_form(wiz)
    wiz.post("/router/check", data={"csrf": csrf(wiz, "/router")})
    assert "บันทึกและเปิดระบบ" in wiz.get("/router").get_data(as_text=True)
    r = wiz.post("/apply", data={"csrf": csrf(wiz, "/router")})
    assert r.status_code == 200 and "ห้ามถอดไฟ" in r.get_data(as_text=True)
    req = json.loads((wiz.run / "apply.json").read_text(encoding="utf-8"))
    assert req == {"nic": "eth0", "uplink_cidr": "192.168.1.57/24", "uplink_gw": "192.168.1.1",
                   "client_cidr": "10.10.0.1/24", "gateway_name": "Baan & Co", "retention_days": 180}


def test_failed_apply_status_shown(wiz):
    login(wiz); make_admin(wiz); net_form(wiz)
    (wiz.state / "status.json").write_text(json.dumps({"state": "failed", "message": "DHCP ของเราเตอร์ยังเปิดอยู่",
                                                        "log_tail": "rc=1"}), encoding="utf-8")
    html = wiz.get("/router").get_data(as_text=True)
    assert "บันทึกไม่สำเร็จ" in html and "DHCP ของเราเตอร์ยังเปิดอยู่" in html


def test_closed_after_site_done(wiz):
    (wiz.etc / ".site-done").write_text("x")
    assert wiz.get("/code").status_code == 410


# ------------------------------------------------------------------ netinfo
def test_suggest_avoids_overlapping_client_net():
    from setup import netinfo
    s = netinfo.suggest({"nic": "eth0", "ip": "10.10.0.20", "prefix": 16, "gw": "10.10.0.1"})
    assert s["client_cidr"] == "10.20.0.1/24"
    s = netinfo.suggest({"nic": "eth0", "ip": "10.0.0.5", "prefix": 8, "gw": "10.0.0.1"})
    assert s["client_cidr"] == "172.31.0.1/24"
    assert s["uplink_cidr"] == "10.0.0.5/8"


def test_install_args_dhcp_range_follows_client_net():
    from setup import netinfo
    v = {"nic": "eth0", "uplink_cidr": "192.168.1.57/24", "uplink_gw": "192.168.1.1",
         "client_cidr": "10.20.0.1/24", "gateway_name": "A", "retention_days": 180}
    args = netinfo.install_args(v)
    assert args[args.index("--dhcp-range") + 1] == "10.20.0.100,10.20.0.250"
    v["client_cidr"] = "10.20.0.150/24"
    args = netinfo.install_args(v)
    assert args[args.index("--dhcp-range") + 1] == "10.20.0.10,10.20.0.99"


def test_validate_rejects_non_24_client():
    from setup import netinfo
    _, errs = netinfo.validate({"nic": "eth0", "uplink_cidr": "192.168.1.5/24", "uplink_gw": "192.168.1.1",
                                "client_cidr": "10.10.0.1/16", "retention_days": 180}, check_nic_exists=False)
    assert any("/24" in e for e in errs)


# ------------------------------------------------------------------ รีวิว 14 ต.ค. (S3, S5-S7, S11, S12)
def test_wrong_code_lock_is_per_ip_not_whole_box(wiz):
    """S3: เครื่องหนึ่งกดผิดจนล็อก ต้องไม่กันช่างที่อยู่อีก IP"""
    for _ in range(5):
        r = wiz.post("/code", data={"csrf": csrf(wiz), "code": "WRONG000"},
                     environ_overrides={"REMOTE_ADDR": "10.0.0.66"})
        assert r.status_code == 400
    r = wiz.post("/code", data={"csrf": csrf(wiz), "code": CODE},
                 environ_overrides={"REMOTE_ADDR": "10.0.0.66"})
    assert r.status_code == 429
    other = wiz.mod.app.test_client()
    tok = re.search(r'name="csrf" value="([^"]+)"', other.get("/code").get_data(as_text=True)).group(1)
    r = other.post("/code", data={"csrf": tok, "code": CODE}, environ_overrides={"REMOTE_ADDR": "10.0.0.7"})
    assert r.status_code == 302


def test_non_ascii_csrf_is_400_not_500(wiz):
    """S7: compare_digest(str ภาษาไทย) เคยโยน TypeError"""
    wiz.get("/code")
    assert wiz.post("/code", data={"csrf": "ก", "code": CODE}).status_code == 400


@pytest.mark.parametrize("name", ["a\x00b", "a\x0bNATID_DEK=x", "a\x85b", "a b", "a‎b", "tab\there"])
def test_shop_name_rejects_control_and_unicode_line_breaks(name):
    """S5/S6: NUL ทำ apply (root) ล้ม · VT/NEL/U+2028 ถูก splitlines() แยกเป็นบรรทัดใหม่"""
    from setup import netinfo
    _, errs = netinfo.validate({"nic": "eth0", "uplink_cidr": "192.168.1.5/24", "uplink_gw": "192.168.1.1",
                                "client_cidr": "10.10.0.1/24", "gateway_name": name, "retention_days": 180},
                               check_nic_exists=False)
    assert any("ชื่อร้าน" in e for e in errs)


def test_shop_name_thai_still_ok():
    from setup import netinfo
    v, errs = netinfo.validate({"nic": "eth0", "uplink_cidr": "192.168.1.5/24", "uplink_gw": "192.168.1.1",
                                "client_cidr": "10.10.0.1/24", "gateway_name": "ร้านกาแฟบ้านสวน ☕",
                                "retention_days": 180}, check_nic_exists=False)
    assert not errs and v["gateway_name"] == "ร้านกาแฟบ้านสวน ☕"


@pytest.mark.parametrize("nic,cidr", [("lo", "10.10.0.1/24"), ("wlan0", "10.10.0.1/24"), ("..", "10.10.0.1/24"),
                                      ("eth0", "127.0.5.1/24"), ("eth0", "169.254.3.1/24")])
def test_validate_rejects_wrong_nic_and_non_rfc1918_client(nic, cidr):
    """S12"""
    from setup import netinfo
    _, errs = netinfo.validate({"nic": nic, "uplink_cidr": "192.168.1.5/24", "uplink_gw": "192.168.1.1",
                                "client_cidr": cidr, "retention_days": 180}, check_nic_exists=False)
    assert errs


def test_router_result_in_cookie_is_bounded(wiz):
    """S11: RA/DHCP offer จำนวนมากจากอุปกรณ์ในวงต้องไม่ดัน cookie เกิน 4 KB"""
    login(wiz); make_admin(wiz); net_form(wiz)
    many = [{"router_ip": f"fe80::{i:x}", "prefixes": ["2001:db8::/64"] * 20, "junk": "x" * 200}
            for i in range(200)]
    wiz.router["result"] = {"ok": False, "dhcp": {"ok": True, "servers": []},
                            "ipv6": {"ok": False, "routers": many}}
    r = wiz.post("/router/check", data={"csrf": csrf(wiz, "/router")})
    assert r.status_code == 302
    assert len(r.headers.get("Set-Cookie", "")) < 4000
    html = wiz.get("/router").get_data(as_text=True)
    assert "fe80::0" in html and "ยังเปิดอยู่" in html


def test_apply_refused_while_restore_running(wiz):
    """S12: ห้ามรัน --stage site ซ้อนกับการกู้ฐานข้อมูล"""
    login(wiz); make_admin(wiz); net_form(wiz)
    wiz.post("/router/check", data={"csrf": csrf(wiz, "/router")})
    (wiz.state / "restore.json").write_text(json.dumps({"state": "running"}), encoding="utf-8")
    r = wiz.post("/apply", data={"csrf": csrf(wiz, "/router")})
    assert r.status_code == 302 and r.headers["Location"].endswith("/restore")
    assert not (wiz.run / "apply.json").exists()
