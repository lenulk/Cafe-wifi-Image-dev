"""
logger/db_seal.py — ผนึกแถว log ในฐานข้อมูลรายวันด้วย hash chain แล้วตรวจย้อนหลังทุกคืน (A8/H2, 16 ต.ค. 2026)

ปัญหาที่ปิด: logger.integrity ผนึกแค่ "ไฟล์" log ที่หมุนแล้ว -- แถวใน conn_log/dns_log/audit_log (ตัวที่หน้า /logs,
/evidence และเจ้าหน้าที่ใช้จริง) ไม่มีอะไรยืนยันเลย ใครได้รหัสฐานข้อมูลลบ/แก้/เพิ่มแถวย้อนหลังได้เงียบ ๆ

หลักการ:
  ผนึก   แต่ละ (ตาราง, วัน) = SHA-256 ของทุกแถวในวันนั้นเรียงตาม id (ทุกคอลัมน์, รูปแบบคงที่) + จำนวนแถว
         ต่อกันเป็นสายเดียว chain = sha256(prev_chain | ตาราง | วัน | จำนวน | rows_sha256 | คอลัมน์)
         ผนึกวันที่ผ่านไปแล้วอย่างน้อย SEAL_LAG_DAYS วัน (กันแถวที่เขียนช้าตอน DB ล่ม/collector ตามอ่าน)
  ตรวจ   คิด hash ของวันที่ผนึกแล้วใหม่ เทียบกับที่บันทึก -- เพิ่ม/ลบ/แก้แถวแม้แถวเดียว = ไม่ตรง
         + ตรวจสาย chain ทั้งเส้น (log_seal เป็น append-only ด้วย trigger ใน sql/018)
  ยึด    chain ล่าสุด (head) ไปไว้นอกเครื่อง: หน้า Admin แสดงให้จด/พิมพ์ และ backup_db เขียนลง USB ทุกคืน
         -- คนที่คุมเครื่องได้ทั้งหมดอาจสร้างสายใหม่ทั้งเส้นได้ แต่จะไม่ตรงกับ head ที่จดไว้นอกเครื่อง

ตรวจเฉพาะวันที่ข้อมูลยังไม่ถูกเปลี่ยนตามปกติ: conn/dns ภายในระยะเก็บ (purge ลบที่เก่ากว่า), audit_log ภายใน
179 วัน (ปุ่มล้างข้อมูลแก้ได้เฉพาะแถวเก่ากว่า 180 วัน) · ต่อคืนตรวจ RECENT_DAYS วันล่าสุด + วันเก่าแบบหมุนเวียน
(ทุกวันในระยะถูกตรวจอย่างน้อยทุก ROTATION_DAYS คืน) ไม่ให้งานตี 3 ยาวเกินบนร้านที่ log เยอะ
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta

log = logging.getLogger("cafe-wifi.db_seal")

TABLES = ("audit_log", "conn_log", "dns_log")   # ลำดับคงที่ = ลำดับในสายของแต่ละวัน
SEAL_LAG_DAYS = 2
RECENT_DAYS = 7
ROTATION_DAYS = 14
AUDIT_MUTABLE_AFTER_DAYS = 180   # ตรงกับ trigger audit_log_scrub_only และ cutoff ขั้นต่ำของ /audit/scrub
CLOCK_SKEW_DAYS = 30


@dataclass(frozen=True)
class Seal:
    table_name: str
    seal_date: date
    row_count: int
    min_id: int | None
    max_id: int | None
    columns: str
    rows_sha256: str
    prev_chain: str | None
    chain_sha256: str


@dataclass(frozen=True)
class SealIssue:
    target: str
    kind: str     # 'rows_mismatch' | 'chain_broken'
    detail: str


def _canon(v):
    if isinstance(v, datetime):
        return v.isoformat(" ")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, (bytes, bytearray)):
        return v.hex()
    return str(v)


def hash_rows(rows, columns: list[str]) -> tuple[str, int, int | None, int | None]:
    """SHA-256 ของแถวตามลำดับที่ได้มา -- 1 บรรทัด JSON ต่อแถว (รูปแบบตายตัว ไม่ขึ้นกับ driver/locale)
    คืน (sha256, จำนวน, id น้อยสุด, id มากสุด)"""
    h = hashlib.sha256()
    n, lo, hi = 0, None, None
    for r in rows:
        h.update(json.dumps([r[c] for c in columns], ensure_ascii=False, default=_canon, separators=(",", ":")).encode("utf-8"))
        h.update(b"\n")
        n += 1
        rid = r.get("id")
        if rid is not None:
            lo = rid if lo is None else min(lo, rid)
            hi = rid if hi is None else max(hi, rid)
    return h.hexdigest(), n, lo, hi


def chain_hash(prev: str | None, table: str, day: date, count: int, rows_sha: str, columns: str) -> str:
    raw = f"{prev or ''}|{table}|{day.isoformat()}|{count}|{rows_sha}|{columns}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def verify_chain(seals: list[Seal]) -> list[SealIssue]:
    """seals เรียงตาม id -- ทุกแถวต้องอ้าง chain ของแถวก่อนหน้า และ chain ต้องคิดซ้ำได้ตรง"""
    issues, prev = [], None
    for s in seals:
        tgt = f"{s.table_name}:{s.seal_date}"
        if s.prev_chain != prev:
            issues.append(SealIssue(tgt, "chain_broken", f"prev_chain ไม่ต่อจากแถวก่อนหน้า ({(prev or '-')[:16]}…)"))
        want = chain_hash(s.prev_chain, s.table_name, s.seal_date, s.row_count, s.rows_sha256, s.columns)
        if want != s.chain_sha256:
            issues.append(SealIssue(tgt, "chain_broken", "chain_sha256 คิดซ้ำไม่ตรง — แถวผนึกถูกแก้"))
        prev = s.chain_sha256
    return issues


def days_to_verify(seals: list[Seal], today: date, retention_days: int) -> list[Seal]:
    """เลือกแถวผนึกที่ตรวจคืนนี้: อยู่ในช่วงที่ข้อมูลต้องไม่เปลี่ยน และ (ล่าสุด RECENT_DAYS วัน หรือถึงรอบหมุนเวียน)"""
    return [s for s in seals if verifiable(s, today, retention_days)
            and ((today - s.seal_date).days <= SEAL_LAG_DAYS + RECENT_DAYS
                 or s.seal_date.toordinal() % ROTATION_DAYS == today.toordinal() % ROTATION_DAYS)]


def verifiable(s: Seal, today: date, retention_days: int) -> bool:
    """ข้อมูลของวันนี้ยังต้องไม่เปลี่ยนไหม -- เก่ากว่านี้ purge (conn/dns) หรือปุ่มล้างข้อมูล (audit) แก้ได้ตามปกติ"""
    limit = (AUDIT_MUTABLE_AFTER_DAYS - 1) if s.table_name == "audit_log" else (retention_days - 2)
    return (today - s.seal_date).days <= limit


class Store:
    """ฐานข้อมูลจริง (common.db) -- แยกเป็นคลาสเพื่อให้เทสต์ใส่ตัวจำลองได้"""

    def columns(self, table: str) -> list[str]:
        from common.db import query_all
        return [r["Field"] for r in query_all(f"SHOW COLUMNS FROM {table}")]

    def day_rows(self, table: str, columns: list[str], day: date):
        from common.db import iter_rows
        cols = ", ".join(f"`{c}`" for c in columns)
        return iter_rows(f"SELECT {cols} FROM {table} WHERE ts >= %s AND ts < %s ORDER BY id",
                         (day, day + timedelta(days=1)))

    def first_day(self, table: str) -> date | None:
        from common.db import query_one
        row = query_one(f"SELECT MIN(ts) AS t FROM {table}")
        return row["t"].date() if row and row["t"] else None

    def newest_log(self) -> datetime | None:
        from common.db import query_one
        ts = [r["t"] for t in ("conn_log", "dns_log") if (r := query_one(f"SELECT MAX(ts) AS t FROM {t}")) and r["t"]]
        return max(ts, default=None)

    def seals(self) -> list[Seal]:
        from common.db import query_all
        rows = query_all("SELECT table_name, seal_date, row_count, min_id, max_id, columns, rows_sha256, "
                         "prev_chain, chain_sha256 FROM log_seal ORDER BY id")
        return [Seal(**r) for r in rows]

    def last(self) -> Seal | None:
        from common.db import query_one
        r = query_one("SELECT table_name, seal_date, row_count, min_id, max_id, columns, rows_sha256, "
                      "prev_chain, chain_sha256 FROM log_seal ORDER BY id DESC LIMIT 1")
        return Seal(**r) if r else None

    def add(self, s: Seal) -> None:
        from common.db import execute
        execute("INSERT INTO log_seal (table_name, seal_date, row_count, min_id, max_id, columns, rows_sha256, "
                "prev_chain, chain_sha256) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (s.table_name, s.seal_date, s.row_count, s.min_id, s.max_id, s.columns, s.rows_sha256,
                 s.prev_chain, s.chain_sha256))


def seal_pending(store, today: date, now: datetime | None = None) -> list[Seal]:
    """ผนึกทุก (ตาราง, วัน) ที่ยังไม่ผนึก ตั้งแต่วันแรกที่มีข้อมูลถึง today - SEAL_LAG_DAYS
    นาฬิกาน่าสงสัย (ล้ำหน้า log ล่าสุดเกิน CLOCK_SKEW_DAYS) = ไม่ผนึก -- ผนึกวันที่ยังเก็บไม่ครบจะทำให้ตรวจไม่ผ่านตลอดไป"""
    now = now or datetime.now()
    newest = store.newest_log()
    if newest is not None and now > newest + timedelta(days=CLOCK_SKEW_DAYS):
        raise RuntimeError(f"นาฬิกาเครื่อง ({now:%Y-%m-%d}) ล้ำหน้า log ล่าสุด ({newest:%Y-%m-%d}) เกิน "
                           f"{CLOCK_SKEW_DAYS} วัน — ไม่ผนึก")
    existing = store.seals()
    done = {(s.table_name, s.seal_date) for s in existing}
    prev = existing[-1].chain_sha256 if existing else None
    last = today - timedelta(days=SEAL_LAG_DAYS)
    starts = {}
    for t in TABLES:
        sealed_days = [s.seal_date for s in existing if s.table_name == t]
        starts[t] = (max(sealed_days) + timedelta(days=1)) if sealed_days else (store.first_day(t) or last)
    first = min(starts.values())
    out: list[Seal] = []
    cols_cache: dict[str, list[str]] = {}
    day = first
    while day <= last:
        for t in TABLES:
            if day < starts[t] or (t, day) in done:
                continue
            cols = cols_cache.setdefault(t, store.columns(t))
            rows_sha, n, lo, hi = hash_rows(store.day_rows(t, cols, day), cols)
            colstr = ",".join(cols)
            seal = Seal(t, day, n, lo, hi, colstr, rows_sha, prev,
                        chain_hash(prev, t, day, n, rows_sha, colstr))
            store.add(seal)
            out.append(seal)
            prev = seal.chain_sha256
        day += timedelta(days=1)
    return out


def verify(store, today: date, retention_days: int, everything: bool = False) -> tuple[list[SealIssue], int]:
    """คืน (ปัญหา, จำนวนวันที่คิด hash ซ้ำ) · everything=True = ตรวจทุกวันในช่วงที่ตรวจได้ ไม่หมุนเวียน"""
    seals = store.seals()
    issues = verify_chain(seals)
    todo = ([s for s in seals if verifiable(s, today, retention_days)] if everything
            else days_to_verify(seals, today, retention_days))
    for s in todo:
        cols = s.columns.split(",")
        rows_sha, n, _, _ = hash_rows(store.day_rows(s.table_name, cols, s.seal_date), cols)
        if rows_sha != s.rows_sha256 or n != s.row_count:
            issues.append(SealIssue(
                f"{s.table_name}:{s.seal_date}", "rows_mismatch",
                f"แถวของวันนี้ไม่ตรงกับที่ผนึกไว้ (ผนึก {s.row_count} แถว ตอนนี้ {n} แถว) — "
                "อาจถูกลบ/แก้/เพิ่มย้อนหลัง"))
    return issues, len(todo)


def head(store) -> Seal | None:
    return store.last()


ANCHOR_FILE = "log-seal-anchor.txt"


def write_anchor(directory, store=None, now: datetime | None = None) -> str | None:
    """เขียน head ของสายผนึกต่อท้ายไฟล์บน USB สำรอง (เรียกจาก backup_db หลังคัดลอกสำเร็จ) คืนบรรทัดที่เขียน
    ไฟล์นี้เพิ่มอย่างเดียว ไม่ถูก prune -- ถ้าวันหนึ่งสายในเครื่องถูกสร้างใหม่ทั้งเส้น head เก่าบน USB จะหาไม่เจอ"""
    from pathlib import Path
    h = head(store or Store())
    if h is None:
        return None
    line = (f"{(now or datetime.now()).isoformat(timespec='minutes')} head={h.table_name}:{h.seal_date} "
            f"chain={h.chain_sha256}")
    with open(Path(directory) / ANCHOR_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())
    return line


def main() -> int:  # pragma: no cover
    import argparse

    from common import audit
    p = argparse.ArgumentParser(description="ผนึก/ตรวจแถว log ในฐานข้อมูล")
    p.add_argument("--verify-all", action="store_true", help="ตรวจทุกวันในช่วงที่ตรวจได้ (ไม่หมุนเวียน)")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO)
    store = Store()
    today = date.today()
    retention = int(os.environ.get("LOG_RETENTION_DAYS", "180"))
    rc = 0
    try:
        sealed = seal_pending(store, today)
        log.info("ผนึกใหม่ %d รายการ", len(sealed))
    except Exception as exc:  # noqa: BLE001 -- ยังตรวจต่อ
        log.error("ผนึกไม่สำเร็จ: %s", exc)
        audit.log(audit.INTEGRITY_FAILED, target="log_seal", detail=f"kind=seal_failed {exc}"[:500])
        rc = 1
    issues, checked = verify(store, today, retention, everything=args.verify_all)
    for i in issues:
        log.error("[%s] %s: %s", i.kind, i.target, i.detail)
        audit.log(audit.INTEGRITY_FAILED, target=i.target, detail=f"kind={i.kind} {i.detail}")
    h = head(store)
    log.info("ตรวจซ้ำ %d วัน ปัญหา %d · head %s %s", checked, len(issues),
             f"{h.table_name}:{h.seal_date}" if h else "-", h.chain_sha256 if h else "-")
    return 1 if issues or rc else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
