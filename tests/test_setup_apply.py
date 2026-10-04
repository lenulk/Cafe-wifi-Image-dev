"""setup/apply.py (ฝั่ง root ของ wizard) -- ไม่รันคำสั่งจริง: แทน systemctl / install.sh / check_router ด้วยตัวจำลอง"""
import importlib
import json
import os
import subprocess

import pytest

GOOD = {"nic": "eth0", "uplink_cidr": "192.168.1.57/24", "uplink_gw": "192.168.1.1",
        "client_cidr": "10.10.0.1/24", "gateway_name": "Shop", "retention_days": 180}
OK = {"ok": True, "dhcp": {"ok": True, "servers": []}, "ipv6": {"ok": True, "routers": []}}


@pytest.fixture
def ap(tmp_path, monkeypatch):
    etc, run, state, net = tmp_path / "etc", tmp_path / "run", tmp_path / "state", tmp_path / "net"
    for d in (etc, run, net / "eth0"):
        d.mkdir(parents=True)
    (etc / "setup-code").write_text("K7QM29XD\n")
    monkeypatch.setenv("ETC_DIR", str(etc))
    monkeypatch.setenv("SETUP_RUN_DIR", str(run))
    monkeypatch.setenv("APPLY_STATE_DIR", str(state))
    monkeypatch.setenv("OPT_DIR", str(tmp_path / "opt"))
    mod = importlib.reload(importlib.import_module("setup.apply"))
    from setup import netinfo
    monkeypatch.setattr(netinfo, "SYS_NET", net)
    calls = {"systemctl": [], "install": [], "rc": 0, "router": OK}
    monkeypatch.setattr(mod, "systemctl", lambda *a: calls["systemctl"].append(a))
    monkeypatch.setattr(mod, "led", lambda t: None)

    def fake_run(cmd, **kw):
        calls["install"].append(cmd)
        return subprocess.CompletedProcess(cmd, calls["rc"])
    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    from tools import check_router
    monkeypatch.setattr(check_router, "check", lambda iface, *a, **k: calls["router"])
    mod.calls, mod.etc, mod.run, mod.state = calls, etc, run, state
    return mod


def req(ap, data):
    (ap.run / "apply.json").write_text(json.dumps(data), encoding="utf-8")


def status(ap):
    return json.loads((ap.state / "status.json").read_text(encoding="utf-8"))


def test_no_request_is_noop(ap):
    assert ap.main() == 0 and ap.calls["install"] == []


def test_success_runs_site_and_closes_wizard(ap):
    req(ap, GOOD)
    assert ap.main() == 0
    cmd = ap.calls["install"][0]
    assert cmd[2:4] == ["--stage", "site"] and "--uplink-cidr" in cmd and "192.168.1.57/24" in cmd
    assert (ap.etc / ".site-done").exists()
    assert not (ap.etc / "setup-code").exists(), "setup code ต้องใช้ไม่ได้อีกหลังตั้งเสร็จ"
    assert ("stop", "cafe-wifi-setup.service") in ap.calls["systemctl"]
    assert any(c[0] == "disable" for c in ap.calls["systemctl"])
    assert status(ap)["state"] == "done"
    assert not (ap.run / "apply.json").exists()


def test_router_still_dhcp_blocks_install(ap):
    ap.calls["router"] = {"ok": False, "dhcp": {"ok": False, "servers": [{"server_ip": "192.168.1.1"}]},
                          "ipv6": {"ok": True, "routers": []}}
    req(ap, GOOD)
    assert ap.main() == 1
    assert ap.calls["install"] == []
    assert "DHCP" in status(ap)["message"]
    assert ("start", "cafe-wifi-setup.service") in ap.calls["systemctl"], "ต้องเปิด wizard กลับให้ช่างเห็นสาเหตุ"
    assert not (ap.etc / ".site-done").exists()


def test_tampered_request_rejected(ap):
    # ไฟล์คำขอเขียนได้โดยผู้ใช้ cafewifi -- ต้อง validate ซ้ำ ไม่ส่งต่อให้ install.sh ตรง ๆ
    req(ap, {**GOOD, "gateway_name": "x$(reboot)", "nic": "eth0; rm -rf /"})
    assert ap.main() == 1 and ap.calls["install"] == []


def test_install_failure_reported_and_retryable(ap):
    ap.calls["rc"] = 3
    req(ap, GOOD)
    assert ap.main() == 1
    st = status(ap)
    assert st["state"] == "failed" and "rc=3" in st["message"]
    assert not (ap.etc / ".site-done").exists() and (ap.etc / "setup-code").exists()


@pytest.mark.skipif(not hasattr(os, "O_NOFOLLOW"), reason="ต้องมี O_NOFOLLOW (Linux)")
def test_symlinked_request_refused(ap, tmp_path):
    secret = tmp_path / "shadow"
    secret.write_text(json.dumps(GOOD))
    os.symlink(secret, ap.run / "apply.json")
    assert ap.main() == 1 and ap.calls["install"] == []


def test_done_already_ignores_request(ap):
    (ap.etc / ".site-done").write_text("x")
    req(ap, GOOD)
    assert ap.main() == 0 and ap.calls["install"] == []
