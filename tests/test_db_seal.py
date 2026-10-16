"""logger/db_seal.py -- ผนึกแถว log ในฐานข้อมูลรายวัน (A8/H2) · ใช้ store จำลอง ไม่ต้องมี MariaDB"""
from datetime import date, datetime, timedelta

import pytest

from logger import db_seal as ds

TODAY = date(2026, 10, 16)
COLS = {"audit_log": ["id", "ts", "action", "detail"],
        "conn_log": ["id", "ts", "mac", "bytes_out"],
        "dns_log": ["id", "ts", "mac", "qname"]}


class FakeStore:
    def __init__(self):
        self.rows = {t: [] for t in ds.TABLES}
        self.sealed: list[ds.Seal] = []
        self.next_id = 1

    def put(self, table, ts, **kw):
        row = dict(id=self.next_id, ts=ts, **kw)
        self.next_id += 1
        self.rows[table].append(row)
        return row

    def columns(self, table):
        return COLS[table]

    def day_rows(self, table, columns, day):
        rows = [r for r in self.rows[table] if day <= r["ts"].date() < day + timedelta(days=1)]
        return iter(sorted(({c: r.get(c) for c in columns} for r in rows), key=lambda r: r["id"]))

    def first_day(self, table):
        return min((r["ts"].date() for r in self.rows[table]), default=None)

    def newest_log(self):
        ts = [r["ts"] for t in ("conn_log", "dns_log") for r in self.rows[t]]
        return max(ts, default=None)

    def seals(self):
        return list(self.sealed)

    def add(self, s):
        self.sealed.append(s)


def _seed(store, days_back=5):
    for d in range(days_back, 0, -1):
        day = datetime.combine(TODAY - timedelta(days=d), datetime.min.time())
        store.put("conn_log", day + timedelta(hours=10), mac="AA:BB:CC:DD:EE:01", bytes_out=100 * d)
        store.put("dns_log", day + timedelta(hours=10, seconds=1), mac="AA:BB:CC:DD:EE:01", qname=f"d{d}.example")
        store.put("audit_log", day + timedelta(hours=11), action="login_ok", detail=None)


def test_seals_every_table_and_day_up_to_lag_in_one_chain():
    st = FakeStore()
    _seed(st, 5)
    sealed = ds.seal_pending(st, TODAY, now=datetime(2026, 10, 16, 3, 30))
    # 5 วันก่อน .. วันที่ today-2 = 4 วัน × 3 ตาราง (วันล่าสุด 1 วันยังไม่ผนึกเพราะ lag 2 วัน)
    assert len(sealed) == 4 * 3
    assert max(s.seal_date for s in sealed) == TODAY - timedelta(days=ds.SEAL_LAG_DAYS)
    assert sealed[0].prev_chain is None
    assert all(b.prev_chain == a.chain_sha256 for a, b in zip(sealed, sealed[1:]))
    assert ds.verify_chain(st.seals()) == []
    # รอบถัดไปไม่ผนึกซ้ำ
    assert ds.seal_pending(st, TODAY, now=datetime(2026, 10, 16, 3, 30)) == []


def test_untouched_data_verifies_clean():
    st = FakeStore()
    _seed(st)
    ds.seal_pending(st, TODAY)
    issues, checked = ds.verify(st, TODAY, retention_days=180)
    assert issues == [] and checked == 12


@pytest.mark.parametrize("tamper", ["delete", "update", "insert"])
def test_any_change_to_a_sealed_day_is_detected(tamper):
    st = FakeStore()
    _seed(st)
    ds.seal_pending(st, TODAY)
    target_day = TODAY - timedelta(days=3)
    rows = st.rows["dns_log"]
    victim = next(r for r in rows if r["ts"].date() == target_day)
    if tamper == "delete":
        rows.remove(victim)
    elif tamper == "update":
        victim["qname"] = "innocent.example"
    else:
        st.put("dns_log", victim["ts"] + timedelta(minutes=5), mac="AA:BB:CC:DD:EE:02", qname="planted.example")
    issues, _ = ds.verify(st, TODAY, retention_days=180)
    assert [(i.target, i.kind) for i in issues] == [(f"dns_log:{target_day}", "rows_mismatch")]


def test_editing_a_seal_row_breaks_the_chain():
    st = FakeStore()
    _seed(st)
    ds.seal_pending(st, TODAY)
    from dataclasses import replace
    st.sealed[4] = replace(st.sealed[4], rows_sha256="0" * 64)   # แก้ hash ให้ตรงกับข้อมูลที่แก้แล้ว
    kinds = {i.kind for i in ds.verify_chain(st.seals())}
    assert kinds == {"chain_broken"}


def test_empty_days_are_sealed_so_later_inserts_are_caught():
    st = FakeStore()
    st.put("conn_log", datetime(2026, 10, 10, 9), mac="AA:BB:CC:DD:EE:01", bytes_out=1)
    ds.seal_pending(st, TODAY)
    quiet = date(2026, 10, 12)
    assert any(s.table_name == "conn_log" and s.seal_date == quiet and s.row_count == 0 for s in st.seals())
    st.put("conn_log", datetime(2026, 10, 12, 9), mac="AA:BB:CC:DD:EE:09", bytes_out=999)
    issues, _ = ds.verify(st, TODAY, retention_days=180)
    assert [i.target for i in issues] == [f"conn_log:{quiet}"]


def test_days_beyond_retention_or_scrub_window_are_not_rehashed():
    st = FakeStore()
    old = datetime.combine(TODAY - timedelta(days=200), datetime.min.time())
    st.put("conn_log", old, mac="AA:BB:CC:DD:EE:01", bytes_out=1)
    st.put("audit_log", old, action="login_ok", detail="mac=AA:BB:CC:DD:EE:01")
    st.put("dns_log", datetime(2026, 10, 15, 8), mac="AA:BB:CC:DD:EE:01", qname="now.example")  # ร้านยังเปิดอยู่
    ds.seal_pending(st, TODAY)
    st.rows["conn_log"].clear()                        # purge ตามอายุ
    st.rows["audit_log"][0]["detail"] = "mac=[ลบแล้ว]"   # ปุ่มล้างข้อมูล (เก่ากว่า 180 วัน)
    issues, _ = ds.verify(st, TODAY, retention_days=180, everything=True)
    assert issues == []


def test_nightly_verify_is_bounded_but_covers_every_day_within_rotation():
    st = FakeStore()
    _seed(st, 120)
    ds.seal_pending(st, TODAY)
    seals = st.seals()
    nightly = ds.days_to_verify(seals, TODAY, 180)
    assert len(nightly) < len(seals) / 4, "ไม่คิด hash ทุกวันทุกคืน"
    covered = set()
    for k in range(ds.ROTATION_DAYS):
        covered |= {(s.table_name, s.seal_date) for s in ds.days_to_verify(seals, TODAY + timedelta(days=k), 180)}
    assert covered >= {(s.table_name, s.seal_date) for s in seals}


def test_suspect_clock_refuses_to_seal():
    st = FakeStore()
    _seed(st)
    with pytest.raises(RuntimeError, match="ล้ำหน้า"):
        ds.seal_pending(st, TODAY + timedelta(days=60), now=datetime(2026, 12, 15))
    assert st.seals() == []


def test_hash_rows_is_stable_for_thai_text_none_and_datetimes():
    rows = [dict(id=1, ts=datetime(2026, 10, 9, 11, 10, 16, 250000), mac=None, qname="ร้านกาแฟ.ไทย")]
    a = ds.hash_rows(iter(rows), ["id", "ts", "mac", "qname"])
    b = ds.hash_rows(iter([dict(rows[0])]), ["id", "ts", "mac", "qname"])
    assert a == b and a[1:] == (1, 1, 1)
    c = ds.hash_rows(iter([dict(rows[0], ts=datetime(2026, 10, 9, 11, 10, 16, 251000))]), ["id", "ts", "mac", "qname"])
    assert c[0] != a[0], "ต่างกันแค่มิลลิวินาทีก็ต้องจับได้"
