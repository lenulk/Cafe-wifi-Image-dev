"""Gateway confirmation must match state, IP, and a new gateway session."""
import pytest

from datetime import datetime, timedelta

import tools.reconcile_pending as rp
from tools.reconcile_pending import confirmed_at


def test_confirmed_at_requires_fresh_gateway_session():
    now = datetime.now().replace(microsecond=0)
    client = dict(state="Authenticated", ip="10.10.0.105",
                  session_start=str(int(now.timestamp())))
    assert confirmed_at(client, "10.10.0.105", now) == now
    assert confirmed_at(client, "10.10.0.106", now) is None
    assert confirmed_at({**client, "state": "Preauthenticated"}, "10.10.0.105", now) is None
    assert confirmed_at({**client, "session_start": str(int((now - timedelta(minutes=5)).timestamp()))},
                        "10.10.0.105", now) is None
    assert confirmed_at({**client, "session_start": None}, "10.10.0.105", now) is None


class _FakeCursor:
    def __init__(self, pending):
        self.pending = pending
        self.executed = []
        self._last = ""

    def execute(self, sql, args=()):
        self.executed.append((sql, args))
        self._last = sql

    def fetchall(self):
        return self.pending if "ps.state='pending'" in self._last else []

    def fetchone(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


ORIG_AUTHORIZE = rp.authorize_approved
ORIG_EXPIRE = rp.expire_requests
ORIG_RESUME = rp.resume_returning
ORIG_QUOTA = rp.enforce_live_quota


@pytest.fixture(autouse=True)
def _no_request_steps(monkeypatch):
    """เทสต์ชุดเดิมดูแค่การยืนยัน pending -- ขั้นคำขอใช้งานมีเทสต์ของตัวเองท้ายไฟล์"""
    monkeypatch.setattr(rp, "authorize_approved", lambda: 0)
    monkeypatch.setattr(rp, "expire_requests", lambda: 0)
    monkeypatch.setattr(rp, "sync_extended", lambda: 0)
    monkeypatch.setattr(rp, "resume_returning", lambda: 0)
    monkeypatch.setattr(rp, "enforce_live_quota", lambda: 0)


class _FakeConn:
    def __init__(self, cur):
        self.cur = cur

    def cursor(self):
        return self.cur

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _run(monkeypatch, row, clients):
    import tools.enforce_voucher_expiry as enforce
    cur = _FakeCursor([row])
    deauthed = []
    monkeypatch.setattr(rp, "gateway_clients", lambda macs: clients)
    monkeypatch.setattr(rp, "get_conn", lambda: _FakeConn(cur))
    monkeypatch.setattr(rp, "purge_orphan_claims", lambda: 0)
    monkeypatch.setattr(rp.audit, "log", lambda *a, **k: None)
    monkeypatch.setattr(enforce, "deauth_mac", lambda mac: deauthed.append(mac) or True)
    return rp.run(), cur.executed, deauthed


def _pending_row(now, pending_until):
    return dict(id=7, voucher_id=3, mac="aa:bb:cc:dd:ee:ff", ip="10.10.0.105",
                started_at=now - timedelta(seconds=180), pending_until=pending_until,
                status="active", valid_until=now + timedelta(hours=1))


def test_confirmed_near_deadline_is_promoted_not_timed_out(monkeypatch):
    """R2-08: openNDS เปิดสิทธิ์แล้วก่อน reconcile รอบถัดไป -> ต้อง promote ไม่ใช่ auth_timeout"""
    now = datetime.now().replace(microsecond=0)
    opened = now - timedelta(seconds=2)
    row = _pending_row(now, pending_until=now - timedelta(seconds=1))
    clients = {row["mac"]: dict(state="Authenticated", ip=row["ip"],
                                session_start=str(int(opened.timestamp())))}
    (promoted, expired), executed, deauthed = _run(monkeypatch, row, clients)
    assert (promoted, expired) == (1, 0)
    assert deauthed == []
    assert not any("auth_timeout" in sql for sql, _ in executed)
    # authenticated_at ต้องเป็นเวลาที่ openNDS เปิดสิทธิ์จริง ไม่ใช่ NOW() ตอน timer มาเจอ
    (sql, args), = [(s, a) for s, a in executed if "state='authenticated', authenticated_at" in s]
    assert "NOW()" not in sql
    assert args == (opened, row["id"])


def test_unconfirmed_past_deadline_still_times_out(monkeypatch):
    now = datetime.now().replace(microsecond=0)
    row = _pending_row(now, pending_until=now - timedelta(seconds=1))
    (promoted, expired), executed, deauthed = _run(monkeypatch, row, {})
    assert (promoted, expired) == (0, 1)
    assert deauthed == [row["mac"]]
    assert any("auth_timeout" in sql for sql, _ in executed)


def test_unreadable_gateway_does_not_time_out_pending(monkeypatch):
    """ndsctl ล้ม (busy/รีสตาร์ท) ตอน pending เลยกำหนดพอดี -> ห้ามตัดสิทธิ์ ต้องรอรอบถัดไป"""
    now = datetime.now().replace(microsecond=0)
    row = _pending_row(now, pending_until=now - timedelta(seconds=1))
    (promoted, expired), executed, deauthed = _run(monkeypatch, row, None)
    assert (promoted, expired) == (0, 0)
    assert deauthed == []
    assert not any("auth_timeout" in sql for sql, _ in executed)


def test_reauth_closes_old_session_and_charges_its_voucher(monkeypatch):
    now = datetime.now().replace(microsecond=0)
    opened = now - timedelta(seconds=2)
    row = _pending_row(now, pending_until=now + timedelta(minutes=1))
    old = dict(id=4, voucher_id=99, started_at=now - timedelta(hours=1),
               authenticated_at=now - timedelta(hours=1))
    clients = {row["mac"]: dict(state="Authenticated", ip=row["ip"],
                                session_start=str(int(opened.timestamp())))}

    class ReauthCursor(_FakeCursor):
        rowcount = 1

        def fetchall(self):
            if "AND state='authenticated' AND ended_at IS NULL FOR UPDATE" in self._last:
                return [old]
            return super().fetchall()

        def fetchone(self):
            if "FROM conn_log" in self._last:
                return {"bo": 3_000_000, "bi": 2_000_000}
            return None

    cur = ReauthCursor([row])
    monkeypatch.setattr(rp, "gateway_clients", lambda macs: clients)
    monkeypatch.setattr(rp, "get_conn", lambda: _FakeConn(cur))
    monkeypatch.setattr(rp, "purge_orphan_claims", lambda: 0)
    monkeypatch.setattr(rp.audit, "log", lambda *a, **k: None)

    assert rp.run() == (1, 0)
    traffic = [(sql, args) for sql, args in cur.executed if "FROM conn_log" in sql]
    closes = [(sql, args) for sql, args in cur.executed
              if sql.startswith("UPDATE portal_session SET state='closed'")]
    bumps = [(sql, args) for sql, args in cur.executed
             if sql.startswith("UPDATE voucher SET used_mb")]
    assert len(traffic) == 1 and traffic[0][1] == (row["mac"], old["authenticated_at"], opened)
    assert len(closes) == 1 and closes[0][1] == (opened, "reauth", 3_000_000, 2_000_000, old["id"])
    assert len(bumps) == 1 and bumps[0][1] == (5, old["voucher_id"])
    assert row["voucher_id"] != old["voucher_id"]


def test_no_pending_does_not_touch_ndsctl(monkeypatch):
    """ไม่มี pending = ไม่เรียก ndsctl เลย (ndsctl json ยึด openNDS ~1.1 วิต่อลูกค้า)"""
    called = []
    cur = _FakeCursor([])
    monkeypatch.setattr(rp, "gateway_clients", lambda macs: called.append(macs) or {})
    monkeypatch.setattr(rp, "get_conn", lambda: _FakeConn(cur))
    monkeypatch.setattr(rp, "purge_orphan_claims", lambda: 0)
    assert rp.run() == (0, 0)
    assert called == []


def test_gateway_clients_queries_each_pending_mac(monkeypatch):
    import json as _json
    import tools.enforce_voucher_expiry as enforce
    calls = []

    class R:
        returncode = 0

        def __init__(self, out):
            self.stdout = out

    def fake(cmd, timeout=10):
        calls.append(cmd)
        mac = cmd[-1]
        return R(b"{}" if mac.endswith("99") else _json.dumps({"mac": mac, "state": "Authenticated"}).encode())

    monkeypatch.setattr(enforce, "run_ndsctl", fake)
    got = rp.gateway_clients({"AA:BB:CC:DD:EE:01", "aa:bb:cc:dd:ee:99"})
    assert calls == [["ndsctl", "json", "aa:bb:cc:dd:ee:01"], ["ndsctl", "json", "aa:bb:cc:dd:ee:99"]]
    assert set(got) == {"aa:bb:cc:dd:ee:01"}


def test_gateway_clients_failure_is_none(monkeypatch):
    import tools.enforce_voucher_expiry as enforce

    class R:
        returncode, stdout = 4, b""

    monkeypatch.setattr(enforce, "run_ndsctl", lambda cmd, timeout=10: R())
    assert rp.gateway_clients({"AA:BB:CC:DD:EE:01"}) is None


class _AuthCursor:
    def __init__(self, rows):
        self.rows, self.executed, self.rowcount = rows, [], 0

    def execute(self, sql, args=()):
        self.executed.append((" ".join(sql.split()), args))
        self.rowcount = 2

    def fetchall(self):
        return self.rows

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


ORIG_SYNC = rp.sync_extended


def _auth_env(monkeypatch, rows, returncode=0):
    import tools.enforce_voucher_expiry as enforce
    cur = _AuthCursor(rows)
    calls = []

    class R:
        stdout = b"ok"

    def fake(cmd, timeout=10):
        calls.append(cmd)
        r = R()
        r.returncode = returncode
        return r

    monkeypatch.setattr(rp, "get_conn", lambda: _FakeConn(cur))
    monkeypatch.setattr(enforce, "run_ndsctl", fake)
    return cur, calls


def test_authorize_approved_runs_ndsctl_auth_with_remaining_minutes(monkeypatch):
    rows = [dict(id=5, mac="AA:BB:CC:DD:EE:01",
                 valid_until=datetime.now() + timedelta(minutes=90, seconds=30))]
    cur, calls = _auth_env(monkeypatch, rows)
    assert ORIG_AUTHORIZE() == 1
    assert calls == [["ndsctl", "auth", "aa:bb:cc:dd:ee:01", "91"]], "MAC ตัวเล็ก + นาทีที่เหลือ (ปัดขึ้น)"
    assert any("set auth_sent_at=now()" in sql.lower() and args == (5,) for sql, args in cur.executed)


def test_authorize_failure_is_retried_next_round(monkeypatch):
    rows = [dict(id=5, mac="AA:BB:CC:DD:EE:01", valid_until=datetime.now() + timedelta(hours=1))]
    cur, calls = _auth_env(monkeypatch, rows, returncode=1)
    assert ORIG_AUTHORIZE() == 0
    assert not any("auth_sent_at" in sql.lower() for sql, _ in cur.executed if "update" in sql.lower())


def _b2_env(monkeypatch, state, second_auth_rc=0):
    import tools.enforce_voucher_expiry as enforce
    rows = [dict(id=7, mac="00:E0:4C:36:04:06", valid_until=datetime.now() + timedelta(minutes=59, seconds=30))]
    cur = _AuthCursor(rows)
    calls = []

    class R:
        def __init__(self, rc, out=b""):
            self.returncode, self.stdout = rc, out

    def fake(cmd, timeout=10):
        calls.append(cmd)
        if cmd[1] == "json":
            return R(0, ('{"ip":"10.10.0.209","state":"%s"}' % state).encode())
        if cmd[1] == "auth":
            n = sum(1 for c in calls if c[1] == "auth")
            return R(1, b"Failed to authenticate client") if n == 1 else R(second_auth_rc)
        return R(0)

    monkeypatch.setattr(rp, "get_conn", lambda: _FakeConn(cur))
    monkeypatch.setattr(enforce, "run_ndsctl", fake)
    return cur, calls


def test_authorize_already_online_mac_deauths_then_auths(monkeypatch):
    """B2 (Pi 2026-10-16): auth ซ้ำ MAC ที่ออนไลน์อยู่ = exit 1 -> ต้อง deauth แล้ว auth ใหม่ ไม่ใช่รอจน auth_timeout"""
    cur, calls = _b2_env(monkeypatch, "Authenticated")
    assert ORIG_AUTHORIZE() == 1
    mac = "00:e0:4c:36:04:06"
    assert calls == [["ndsctl", "auth", mac, "60"], ["ndsctl", "json", mac],
                     ["ndsctl", "deauth", mac], ["ndsctl", "auth", mac, "60"]]
    assert any("set auth_sent_at=now()" in sql.lower() and args == (7,) for sql, args in cur.executed)


def test_authorize_failure_on_offline_mac_does_not_deauth(monkeypatch):
    """auth ล้มด้วยเหตุอื่น (เครื่องไม่ได้ออนไลน์) -> ห้าม deauth ใคร รอรอบถัดไปตามเดิม"""
    cur, calls = _b2_env(monkeypatch, "Preauthenticated")
    assert ORIG_AUTHORIZE() == 0
    assert not any(c[1] == "deauth" for c in calls)
    assert not any("auth_sent_at" in sql.lower() for sql, _ in cur.executed if "update" in sql.lower())


def test_authorize_query_targets_only_unsent_pending(monkeypatch):
    cur, calls = _auth_env(monkeypatch, [])
    ORIG_AUTHORIZE()
    (sql, _), = cur.executed
    assert "ar.status='approved'" in sql and "ar.auth_sent_at is null" in sql.lower()
    assert "ps.state='pending'" in sql
    assert calls == []


def test_expire_requests_clears_pii(monkeypatch):
    cur = _AuthCursor([])
    monkeypatch.setattr(rp, "get_conn", lambda: _FakeConn(cur))
    assert ORIG_EXPIRE() == 2
    (sql, _), = cur.executed
    assert "status='expired'" in sql and "natid_hash=NULL" in sql and "natid_enc=NULL" in sql
    # B5: ล้างตัวตนครบชุดเหมือนตอนปฏิเสธ (masked NOT NULL -> PURGED) · mac/ip ไม่แตะ
    assert "natid_masked='PURGED'" in sql and "hostname=NULL" in sql and "user_agent=NULL" in sql
    assert " mac=" not in sql and ", ip=" not in sql



# ---------------------------------------------------------------- ปุ่มต่อเวลา (sql/012)
class _SyncCursor:
    def __init__(self, vouchers, macs):
        self.vouchers, self.macs, self.executed, self._rows = vouchers, macs, [], []
        self.rowcount = 0

    def execute(self, sql, args=()):
        self.executed.append((sql, args))
        s = sql.lower()
        if "where v.auth_sync_needed" in s:
            self._rows = self.vouchers
        elif "from portal_session where voucher_id" in s:
            self._rows = [dict(mac=m) for m in self.macs.get(args[0], [])]
        else:
            self._rows = []

    def fetchall(self):
        return self._rows

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _sync_env(monkeypatch, vouchers, macs, returncode=0):
    import tools.enforce_voucher_expiry as enforce
    cur = _SyncCursor(vouchers, macs)
    calls = []

    class R:
        stdout = b""

    def fake(cmd, timeout=10):
        calls.append(cmd)
        r = R()
        r.returncode = returncode
        return r
    monkeypatch.setattr(rp, "get_conn", lambda: _FakeConn(cur))
    monkeypatch.setattr(enforce, "run_ndsctl", fake)
    return cur, calls


def test_sync_extended_reauths_every_online_device_with_new_minutes(monkeypatch):
    """openNDS ไม่ยอม auth เครื่องที่ออนไลน์ซ้ำ -- ต้อง deauth แล้ว auth ด้วยนาทีใหม่ แล้วล้างธง"""
    v = dict(id=9, status="active", valid_until=datetime.now() + timedelta(minutes=119, seconds=30))
    cur, calls = _sync_env(monkeypatch, [v], {9: ["AA:BB:CC:DD:EE:01", "AA:BB:CC:DD:EE:02"]})
    assert ORIG_SYNC() == 1
    assert calls == [["ndsctl", "deauth", "aa:bb:cc:dd:ee:01"], ["ndsctl", "auth", "aa:bb:cc:dd:ee:01", "120"],
                     ["ndsctl", "deauth", "aa:bb:cc:dd:ee:02"], ["ndsctl", "auth", "aa:bb:cc:dd:ee:02", "120"]]
    assert any("auth_sync_needed=0" in s and a == (9,) for s, a in cur.executed)


def test_sync_extended_keeps_flag_when_ndsctl_fails(monkeypatch):
    v = dict(id=9, status="active", valid_until=datetime.now() + timedelta(hours=1))
    cur, calls = _sync_env(monkeypatch, [v], {9: ["AA:BB:CC:DD:EE:01"]}, returncode=1)
    assert ORIG_SYNC() == 0
    assert not any("auth_sync_needed=0" in s for s, _ in cur.executed), "รอบถัดไปต้องลองใหม่"


def test_sync_revoked_voucher_cuts_online_device_now_via_enforce(monkeypatch):
    """ปุ่มปิดสิทธิ์ตั้งธง -> รอบนี้ (5 วิ) เรียกตัวตัดของ cafe-enforce ทันที ไม่รอรอบ 5 นาที แล้วล้างธง"""
    import tools.enforce_voucher_expiry as enforce
    v = dict(id=9, status="revoked", valid_until=datetime.now() + timedelta(hours=1))
    cur, calls = _sync_env(monkeypatch, [v], {9: ["AA:BB:CC:DD:EE:01"]})
    ran = []
    monkeypatch.setattr(enforce, "run", lambda deauth=True: ran.append(deauth))
    assert ORIG_SYNC() == 1
    assert ran == [True], "ต้องตัดผ่าน cafe-enforce (ปิด session + log ครบ)"
    assert calls == [], "ไม่ re-auth เครื่องของสิทธิ์ที่ถูกปิด"
    assert any("auth_sync_needed=0" in s and a == (9,) for s, a in cur.executed)


def test_sync_revoked_keeps_flag_when_enforce_fails(monkeypatch):
    import tools.enforce_voucher_expiry as enforce
    v = dict(id=9, status="revoked", valid_until=datetime.now() + timedelta(hours=1))
    cur, _ = _sync_env(monkeypatch, [v], {9: ["AA:BB:CC:DD:EE:01"]})

    def boom(deauth=True):
        raise RuntimeError("ndsctl busy")
    monkeypatch.setattr(enforce, "run", boom)
    assert ORIG_SYNC() == 0
    assert not any("auth_sync_needed=0" in s for s, _ in cur.executed), "รอบถัดไปต้องลองใหม่"


def test_sync_revoked_keeps_flag_when_enforce_reports_deauth_failed(monkeypatch):
    """T3: enforce.run() ไม่ raise เมื่อ ndsctl deauth ล้ม แต่คืน deauth_failed > 0 -> ต้องคงธงไว้ลองใหม่"""
    import tools.enforce_voucher_expiry as enforce
    v = dict(id=9, status="revoked", valid_until=datetime.now() + timedelta(hours=1))
    cur, _ = _sync_env(monkeypatch, [v], {9: ["AA:BB:CC:DD:EE:01"]})
    monkeypatch.setattr(enforce, "run", lambda deauth=True: enforce.EnforceSummary(deauth_failed=1))
    assert ORIG_SYNC() == 0
    assert not any("auth_sync_needed=0" in s for s, _ in cur.executed), "รอบถัดไปต้องลองใหม่"


def test_sync_dead_voucher_without_online_device_just_clears_flag(monkeypatch):
    import tools.enforce_voucher_expiry as enforce
    v = dict(id=9, status="revoked", valid_until=datetime.now() + timedelta(hours=1))
    cur, calls = _sync_env(monkeypatch, [v], {})
    monkeypatch.setattr(enforce, "run", lambda deauth=True: pytest.fail("ไม่มีเครื่องออนไลน์ ไม่ต้องตัด"))
    assert ORIG_SYNC() == 1 and calls == []


def test_sync_blocked_customer_active_voucher_is_cut_not_reauthed(monkeypatch):
    """B6: ระงับลูกค้า -> ตั้ง auth_sync_needed บน voucher ที่ยัง active · ต้องตัดผ่าน cafe-enforce ไม่ใช่ deauth+auth ต่อใหม่"""
    import tools.enforce_voucher_expiry as enforce
    v = dict(id=9, status="active", is_blocked=1, valid_until=datetime.now() + timedelta(hours=1))
    cur, calls = _sync_env(monkeypatch, [v], {9: ["AA:BB:CC:DD:EE:01"]})
    ran = []
    monkeypatch.setattr(enforce, "run", lambda deauth=True: ran.append(deauth))
    assert ORIG_SYNC() == 1
    assert ran == [True] and calls == [], "ห้ามเรียก ndsctl auth ซ้ำให้ลูกค้าที่ถูกระงับ"
    assert any("auth_sync_needed=0" in s and a == (9,) for s, a in cur.executed)


def test_main_treats_lock_conflict_as_retry_next_round(monkeypatch):
    """Pi 2026-10-16: อนุมัติชน expire_requests() -> 1213 · ต้องไม่ทำให้ unit Failed แต่ error อื่นยังต้องดัง"""
    import pymysql
    monkeypatch.setattr(rp, "run", lambda: (_ for _ in ()).throw(
        pymysql.err.OperationalError(1213, "Deadlock found")))
    assert rp.main() == 0
    monkeypatch.setattr(rp, "run", lambda: (_ for _ in ()).throw(
        pymysql.err.OperationalError(2003, "Can't connect")))
    with pytest.raises(pymysql.err.OperationalError):
        rp.main()


# ---------------------------------------------------------------- เครื่องที่อนุมัติแล้วกลับมา
def test_present_clients_keeps_only_active_neighbors_in_client_net(monkeypatch):
    import json as _json
    entries = [
        {"dst": "10.10.0.105", "lladdr": "9e:31:8b:2f:68:a8", "state": ["REACHABLE"]},
        {"dst": "10.10.0.106", "lladdr": "aa:bb:cc:dd:ee:02", "state": ["STALE"]},
        {"dst": "10.10.0.107", "state": ["FAILED"]},
        {"dst": "172.20.18.1", "lladdr": "00:ea:bd:18:3f:7f", "state": ["DELAY"]},
    ]

    class R:
        returncode, stdout = 0, _json.dumps(entries).encode()

    monkeypatch.setenv("CLIENT_CIDR", "10.10.0.1/24")
    monkeypatch.setattr(rp.subprocess, "run", lambda *a, **k: R())
    assert rp.present_clients() == {"9E:31:8B:2F:68:A8": "10.10.0.105"}


class _ResumeCursor(_AuthCursor):
    def __init__(self, rows):
        super().__init__(rows)
        self.lastrowid = 42


def _resume_env(monkeypatch, rows, client, reserve_err=None, auth_ok=True):
    cur = _ResumeCursor(rows)
    conn = _FakeConn(cur)
    rolled = []
    conn.rollback = lambda: rolled.append(True)
    reserved, authed, audited = [], [], []
    monkeypatch.setattr(rp, "present_clients", lambda: {"9E:31:8B:2F:68:A8": "10.10.0.105"})
    monkeypatch.setattr(rp, "get_conn", lambda: conn)
    monkeypatch.setattr(rp, "gateway_clients", lambda macs: {} if client is None else {"9e:31:8b:2f:68:a8": client})
    monkeypatch.setattr(rp.access, "reserve_pending_session",
                        lambda cur, v, mac, ip, h=None, o=None: reserved.append((v, mac, ip, h, o))
                        or ((reserve_err, None) if reserve_err else (None, 42)))
    monkeypatch.setattr(rp, "_auth_mac", lambda mac, minutes: authed.append((mac, minutes)) or auth_ok)
    monkeypatch.setattr(rp.audit, "log", lambda *a, **k: audited.append((a, k)))
    return cur, reserved, authed, audited, rolled


def _bound(minutes=80):
    return dict(mac="9E:31:8B:2F:68:A8", id=6, max_devices=2, hostname="Redmi-Note-14-5G",
                os_label="Android 16", valid_until=datetime.now() + timedelta(minutes=minutes, seconds=-30))


def test_resume_returning_reauths_bound_device_under_same_voucher(monkeypatch):
    """Pi 2026-10-16: openNDS รีสตาร์ทตอน Redmi จอดับ -> ตื่นมาต้องได้เน็ตต่อด้วยสิทธิ์เดิม ไม่ใช่หน้าลงทะเบียน"""
    cur, reserved, authed, audited, _ = _resume_env(
        monkeypatch, [_bound()], {"ip": "10.10.0.105", "state": "Preauthenticated"})
    assert ORIG_RESUME() == 1
    assert reserved == [({"id": 6, "max_devices": 2}, "9E:31:8B:2F:68:A8", "10.10.0.105",
                         "Redmi-Note-14-5G", "Android 16")]
    assert authed == [("9E:31:8B:2F:68:A8", 80)]
    assert audited and audited[0][0][0] == rp.audit.DEVICE_RESUME
    (sql, args), = cur.executed
    assert "v.status='active'" in sql and "v.valid_until > now()" in sql.lower()
    assert "not c.is_blocked" in sql.lower(), "ลูกค้าที่ถูกระงับห้ามได้สิทธิ์คืน"
    assert "ps.state='pending'" in sql and "ps.ended_at is null" in sql.lower(), "เครื่องที่มี session อยู่แล้วห้ามซ้ำ"
    assert args == ("9E:31:8B:2F:68:A8",)


def test_resume_skips_device_opennds_knows_at_another_ip(monkeypatch):
    _, reserved, authed, _, _ = _resume_env(monkeypatch, [_bound()], {"ip": "10.10.0.199", "state": "Preauthenticated"})
    assert ORIG_RESUME() == 0 and reserved == [] and authed == []


def test_resume_device_unknown_to_opennds_is_preemptively_authed(monkeypatch):
    """Pi: มือถือจอดับไม่เปิดหน้า portal -> `ndsctl json <mac>` = {} แต่ ndsctl auth เปิดสิทธิ์ล่วงหน้าได้"""
    _, reserved, authed, _, _ = _resume_env(monkeypatch, [_bound()], None)
    assert ORIG_RESUME() == 1 and len(reserved) == 1 and len(authed) == 1


def test_resume_no_bound_device_does_not_touch_ndsctl(monkeypatch):
    _resume_env(monkeypatch, [], {"ip": "10.10.0.105"})
    monkeypatch.setattr(rp, "gateway_clients", lambda macs: pytest.fail("ไม่มีเครื่องที่ต้องคืนสิทธิ์ ไม่ต้องถาม openNDS"))
    assert ORIG_RESUME() == 0


def test_resume_reserve_refused_rolls_back_and_skips_auth(monkeypatch):
    _, _, authed, audited, rolled = _resume_env(
        monkeypatch, [_bound()], {"ip": "10.10.0.105"}, reserve_err="ครบจำนวนเครื่อง")
    assert ORIG_RESUME() == 0 and rolled == [True] and authed == [] and audited == []


def test_resume_auth_failure_is_not_counted(monkeypatch):
    _, _, authed, audited, _ = _resume_env(monkeypatch, [_bound()], {"ip": "10.10.0.105"}, auth_ok=False)
    assert ORIG_RESUME() == 0 and len(authed) == 1 and audited == []


def test_resume_uses_longest_remaining_voucher_when_mac_bound_twice(monkeypatch):
    rows = [_bound(120), {**_bound(30), "id": 3}]
    _, reserved, authed, _, _ = _resume_env(monkeypatch, rows, {"ip": "10.10.0.105"})
    assert ORIG_RESUME() == 1 and reserved[0][0]["id"] == 6 and authed == [("9E:31:8B:2F:68:A8", 120)]


# ---------------------------------------------------------------- โควตานับสดจาก openNDS (T5)
def _quota_env(monkeypatch, rows, clients):
    cur = _AuthCursor(rows)
    monkeypatch.setattr(rp, "get_conn", lambda: _FakeConn(cur))
    monkeypatch.setattr(rp, "gateway_clients", lambda macs: clients)
    return cur


def _quota_row(mac="9E:31:8B:2F:68:A8", used_mb=0):
    return dict(id=24, quota_mb=500, used_mb=used_mb, mac=mac)


def test_live_quota_cuts_when_opennds_counters_reach_quota(monkeypatch):
    """T5 Pi 2026-10-16: ใช้จริง 1,058 MB ฐานข้อมูลเห็น 126 MB (conn_log นับเมื่อการเชื่อมต่อปิด) -> ต้องดูตัวนับสด"""
    clients = {"9e:31:8b:2f:68:a8": {"download_this_session": "480000", "upload_this_session": "10000"}}
    cur = _quota_env(monkeypatch, [_quota_row(used_mb=10)], clients)   # 10 MB + ~501.8 MB สด
    assert ORIG_QUOTA() == 2   # _AuthCursor.rowcount คงที่ 2 -- ดูแค่ว่าสั่ง UPDATE
    assert any("status='used_up', auth_sync_needed=1" in s and a == (24,) for s, a in cur.executed)


def test_live_quota_below_quota_is_left_alone(monkeypatch):
    clients = {"9e:31:8b:2f:68:a8": {"download_this_session": "300000", "upload_this_session": "1000"}}
    cur = _quota_env(monkeypatch, [_quota_row()], clients)
    assert ORIG_QUOTA() == 0 and not any("used_up" in s for s, _ in cur.executed if s.startswith("UPDATE"))


def test_live_quota_sums_every_device_of_the_voucher(monkeypatch):
    rows = [_quota_row("AA:BB:CC:DD:EE:01"), _quota_row("AA:BB:CC:DD:EE:02")]
    clients = {"aa:bb:cc:dd:ee:01": {"download_this_session": "250000"},
               "aa:bb:cc:dd:ee:02": {"download_this_session": "250000"}}
    cur = _quota_env(monkeypatch, rows, clients)
    assert ORIG_QUOTA() == 2, "โควตาผูกกับสิทธิ์ ไม่ใช่เครื่อง: 2 x 256 MB = เกิน 500"


def test_live_quota_unreadable_gateway_does_nothing(monkeypatch):
    cur = _quota_env(monkeypatch, [_quota_row()], None)
    assert ORIG_QUOTA() == 0 and len(cur.executed) == 1


def test_live_quota_no_quota_sessions_does_not_touch_ndsctl(monkeypatch):
    _quota_env(monkeypatch, [], {})
    monkeypatch.setattr(rp, "gateway_clients", lambda macs: pytest.fail("ไม่มีสิทธิ์ที่มีโควตา ไม่ต้องถาม openNDS"))
    assert ORIG_QUOTA() == 0
