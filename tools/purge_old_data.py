"""
tools/purge_old_data.py — ลบข้อมูลที่พ้นระยะเวลาที่ต้องเก็บแล้ว (T11)

รันทุกวันผ่าน cafe-maintenance.timer (ตั้งโดย install.sh)

กติกาการลบ (ดู §6.1, §6.2 ใน PROJECT_PLAN.md):
  * conn_log / dns_log: ลบแถวที่เก่ากว่า LOG_RETENTION_DAYS (กฎหมายบังคับ >= 90 วัน)
  * customer: "ล้างข้อมูลระบุตัวตน" (ไม่ใช่ลบแถวทิ้ง — แถวต้องอยู่รักษาสาย FK ของ
    voucher/device/portal_session ดูเหตุผลเต็มใน purge_stale_customers()) เฉพาะรายที่
    (1) ไม่มี voucher ที่ยัง active/ยังไม่หมดอายุ และ
    (2) last_seen เก่ากว่า CUSTOMER_RETENTION_DAYS (ไม่แตะใครที่ยังมีรหัสใช้งานอยู่จริง)
  * portal_session / device / bypass_alert: ข้อมูลโยง log -> ตัวบุคคล (MAC/IP/hostname) -- ใช้ประโยชน์
    ได้เฉพาะตอนที่ log ที่โยงยังอยู่ จึงลบด้วย cutoff เดียวกับ conn_log/dns_log (PDPA: ไม่เก็บเกินจำเป็น,
    ม.26 ไม่เสีย เพราะ log ที่เก่าเท่ากันถูกลบไปพร้อมกัน)
  * audit_log และ log_manifest: ไม่ลบอัตโนมัติ — เป็นหลักฐานตรวจสอบ ต้องลบด้วยมือถ้าจำเป็น

ทุกการลบจะถูกสรุปจำนวนแถวแล้วเขียนลง audit_log เอง (ตรวจสอบย้อนหลังได้ว่าลบอะไรไปเมื่อไหร่)
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta

log = logging.getLogger("cafe-wifi.purge")

DELETE_BATCH = 10000          # T6: แถวต่อ DELETE ต่อ commit (ตาราง log ใหญ่ ไม่ถือ lock/undo ก้อนเดียว)
CLOCK_SKEW_DAYS = 30          # T7: now ล้ำหน้า log ล่าสุดเกินนี้ = ไม่เชื่อนาฬิกา


@dataclass(frozen=True)
class PurgeSummary:
    conn_log_deleted: int = 0
    dns_log_deleted: int = 0
    customers_deleted: int = 0
    sessions_deleted: int = 0
    devices_deleted: int = 0
    bypass_alerts_deleted: int = 0
    cutoff_logs: datetime | None = None
    cutoff_customers: datetime | None = None
    access_requests_deleted: int = 0
    failed_steps: tuple = ()      # T6: ชื่อขั้นที่ล้ม (ขั้นอื่นยังทำต่อ) -> main() exit != 0
    skipped_clock: bool = False   # T7: นาฬิกาน่าสงสัย -> ข้ามขั้นลบทั้งหมดรอบนี้

    def total(self) -> int:
        return (self.conn_log_deleted + self.dns_log_deleted + self.customers_deleted
                + self.sessions_deleted + self.devices_deleted + self.bypass_alerts_deleted)


def compute_log_cutoff(retention_days: int, now: datetime | None = None) -> datetime:
    """แยกเป็นฟังก์ชันล้วน ๆ ให้ทดสอบตรรกะวันที่ได้โดยไม่ต้องมี DB"""
    if retention_days < 90:
        raise ValueError(
            f"LOG_RETENTION_DAYS={retention_days} ต่ำกว่าขั้นต่ำตามกฎหมาย (90 วัน) — "
            "พ.ร.บ.คอมพิวเตอร์ ม.26 ปฏิเสธไม่ให้ purge ถ้าตั้งค่าต่ำกว่านี้"
        )
    now = now or datetime.now()
    return now - timedelta(days=retention_days)


def compute_customer_cutoff(retention_days: int, now: datetime | None = None) -> datetime:
    now = now or datetime.now()
    return now - timedelta(days=retention_days)


def batched_delete(execute_fn, sql: str, args: tuple = (), batch: int = DELETE_BATCH) -> int:
    """
    T6: รัน `sql LIMIT n` ซ้ำจนกว่าจะลบได้น้อยกว่า batch · execute_fn ต้อง commit เองต่อครั้ง
    (run() ส่งตัวที่เปิด connection ใหม่ต่อชุด) -> ล้มกลางคันก็ไม่ rollback ชุดที่ลบไปแล้ว
    """
    total = 0
    while True:
        n = execute_fn(f"{sql} LIMIT {int(batch)}", args)
        total += n
        if n < batch:
            return total


def purge_conn_and_dns_logs(execute_fn, cutoff: datetime, batch: int = DELETE_BATCH) -> tuple[int, int]:
    """execute_fn(sql, args) -> จำนวนแถวที่ได้รับผลกระทบ (DELETE ... ; ROW_COUNT()) · แบ่งชุดละ `batch` แถว"""
    n_conn = batched_delete(execute_fn, "DELETE FROM conn_log WHERE ts < %s", (cutoff,), batch)
    n_dns = batched_delete(execute_fn, "DELETE FROM dns_log WHERE ts < %s", (cutoff,), batch)
    return n_conn, n_dns


def clock_is_suspect(newest_log: datetime | None, now: datetime,
                     skew_days: int = CLOCK_SKEW_DAYS) -> bool:
    """
    T7: now ล้ำหน้า log ล่าสุดเกิน skew_days = นาฬิกาอาจกระโดดไปข้างหน้า (NTP/RTC ผิด) -> ห้ามลบ
    ไม่มี log เลย = ไม่มีอะไรให้เทียบ/ให้เสีย -> ไม่น่าสงสัย
    ปลอดภัยเสมอเพราะผลคือ "เก็บข้อมูลนานขึ้น": ร้านที่ปิดเกิน 30 วันแค่ไม่ purge จนกว่าจะมี traffic ใหม่
    """
    if newest_log is None:
        return False
    return now > newest_log + timedelta(days=skew_days)


def purge_session_data(execute_fn, cutoff: datetime, batch: int = DELETE_BATCH) -> tuple[int, int, int]:
    """
    portal_session (mac/ip/hostname/เวลา) · device (mac/last_ip) · bypass_alert (mac/ip) ที่พ้น cutoff
    คืน (sessions, devices, bypass_alerts) · ต้องเรียกหลัง purge_stale_customers (ที่นับกิจกรรมล่าสุดจาก session)

    session: เฉพาะที่ปิดแล้ว (state='closed') และจบ/เริ่มก่อน cutoff -- ไม่แตะที่ยังออนไลน์/รอยืนยัน
      · ข้ามแถวที่ pending_mac_claim ยังอ้างถึง (FK fk_pending_session) แทนการลบ claim ของคนอื่น
    device: ไม่มีคอลัมน์เวลาใช้ล่าสุด จึงอิง voucher -- ลบเฉพาะเครื่องของ voucher ที่หมดอายุก่อน cutoff
      และไม่ active (ไม่มีตารางไหนอ้าง device.id; ที่อ้างคือ device -> voucher ทางเดียว)
    """
    n_ps = batched_delete(
        execute_fn,
        "DELETE FROM portal_session WHERE state = 'closed' AND COALESCE(ended_at, started_at) < %s "
        "AND NOT EXISTS (SELECT 1 FROM pending_mac_claim c WHERE c.portal_session_id = portal_session.id)",
        (cutoff,), batch)
    # multi-table DELETE ใช้ LIMIT ไม่ได้ (จำนวนแถวระดับเครื่องต่อ voucher จึงไม่ใหญ่)
    n_dev = execute_fn(
        "DELETE d FROM device d JOIN voucher v ON v.id = d.voucher_id "
        "WHERE v.valid_until < %s AND v.status <> 'active'", (cutoff,))
    n_byp = batched_delete(execute_fn, "DELETE FROM bypass_alert WHERE detected_at < %s", (cutoff,), batch)
    return n_ps, n_dev, n_byp


def purge_stale_customers(query_all_fn, query_one_fn, execute_fn, cutoff: datetime,
                          retention_days: int, now: datetime | None = None) -> int:
    """
    ล้าง (anonymize) ข้อมูลระบุตัวตนของลูกค้าที่ไม่มี voucher ค้างอยู่ (active หรือยังไม่หมดอายุ)
    และไม่ได้มาร้านมานานแล้ว ทำเป็น 2 ขั้น (SELECT แล้วอัปเดตทีละราย) แทนคำสั่งเดียว
    เพื่อให้ debug/ตรวจสอบง่ายและเขียน audit ได้ละเอียดกว่า

    บั๊กเดิม (C2): ฟังก์ชันนี้เคย `DELETE FROM customer` ตรง ๆ แต่ `fk_voucher_customer`
    ไม่ได้ระบุ `ON DELETE` ไว้ (ค่าปริยายของ InnoDB คือ RESTRICT) และลูกค้าทุกรายมี voucher
    อย่างน้อย 1 ใบเสมอ (สร้างคู่กันตอนออก voucher ที่หน้า /issue) -- พอ voucher หมดอายุแล้ว
    และ last_seen เก่าเกิน cutoff, DELETE จะชน FK constraint แตกทันที ทำให้ systemd oneshot
    (cafe-maintenance.service) หยุดกลางคัน และ ExecStart บรรทัดถัดไปในหน่วยเดียวกัน
    (logger.integrity, check_time.sh) ไม่ถูกรันตามไปด้วยแบบเงียบ ๆ

    แก้เป็น "ล้างข้อมูลระบุตัวตน" (เคลียร์ natid_hash/natid_enc/natid_masked) แทนการลบ
    ทั้งแถว -- แถว customer ยังคงอยู่เพื่อรักษาสาย FK ที่ voucher/device/portal_session
    อ้างถึงอยู่ (ยังใช้เป็นหลักฐานจำนวนครั้ง/อุปกรณ์ตาม ม.26 ได้ แม้ตัวตนจะถูกลบไปแล้ว)
    ตรงกับเจตนาจริงของ retention policy คือ "ลบ PII เมื่อพ้นกำหนด" ไม่ใช่ "ลบแถว" -- ตรรกะ
    การล้าง 1 คนใช้ร่วมกับ DSR (N6, CODING_BRIEF.md) ผ่าน common.customer.anonymize_customer()
    เพื่อไม่ให้ 2 เส้นทางเขียนตรรกะเดียวกันซ้ำกันคนละที่ (ดู docstring ของฟังก์ชันนั้น)
    """
    from common.customer import anonymize_customer, retention_hold_until

    # หมายเหตุ: 'PURGED' ในเงื่อนไข WHERE ข้างล่างต้องตรงกับ natid_masked ที่
    # anonymize_customer() เขียนจริง (common/customer.py) -- ถ้าจะเปลี่ยนค่านี้ต้องแก้ทั้งคู่พร้อมกัน
    stale = query_all_fn("""
        SELECT c.id FROM customer c
        WHERE c.last_seen < %s
          AND c.natid_masked != 'PURGED'
          AND NOT EXISTS (
              SELECT 1 FROM voucher v
              WHERE v.customer_id = c.id AND (v.status = 'active' OR v.valid_until >= NOW())
          )
    """, (cutoff,))
    count = 0
    for row in stale:
        if retention_hold_until(query_one_fn, row["id"], retention_days=retention_days,
                                now=now):
            continue
        anonymize_customer(execute_fn, row["id"])
        count += 1
    return count


def run(retention_days: int | None = None, customer_retention_days: int | None = None,
        now: datetime | None = None) -> PurgeSummary:
    from common import audit
    from common.db import get_conn

    retention_days = retention_days or int(os.environ.get("LOG_RETENTION_DAYS", "180"))
    # บั๊กเดิม: docstring ด้านบนบอกว่าตั้งผ่าน CUSTOMER_RETENTION_DAYS ได้ แต่โค้ดไม่เคยอ่าน
    # ตัวแปรนี้จริง ๆ เลย -- มีแต่ fallback ไปใช้ retention_days ของ log เสมอ
    customer_retention_days = (
        customer_retention_days
        or (int(os.environ["CUSTOMER_RETENTION_DAYS"]) if os.environ.get("CUSTOMER_RETENTION_DAYS") else None)
        or retention_days
    )

    now = now or datetime.now()
    log_cutoff = compute_log_cutoff(retention_days, now)
    cust_cutoff = compute_customer_cutoff(customer_retention_days, now)

    def _exec(sql, args=()):
        # ทุกคำสั่งเปิด connection ใหม่ = commit ต่อชุด (T6)
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(sql, args)
            return cur.rowcount

    failed: list[str] = []

    def _step(name, fn, default=0):
        """T6: ขั้นหนึ่งล้ม = log + audit แล้วทำขั้นอื่นต่อ (ไม่ rollback ขั้นที่เสร็จแล้ว)"""
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            log.error("purge ขั้น %s ล้มเหลว: %s", name, exc)
            failed.append(name)
            audit.log("purge_failed", target=name, detail=f"{type(exc).__name__}: {exc}"[:500])
            return default

    # T7: ตรวจนาฬิกาก่อนลบอะไรที่ขึ้นกับเวลา -- รวมถึง session/คำขอ/ลูกค้า เพราะลบก่อน log ที่โยงอยู่
    # จะทำให้ log โยงหาตัวคนไม่ได้ · (การ DROP partition ทำโดย event cafewifi_partition_maintenance
    # ใน MariaDB ซึ่งไม่ผ่านไฟล์นี้)
    def _newest_log():
        with get_conn() as conn, conn.cursor() as cur:
            newest = []
            for tbl in ("conn_log", "dns_log"):
                cur.execute(f"SELECT MAX(ts) AS newest FROM {tbl}")
                row = cur.fetchone()
                v = row["newest"] if isinstance(row, dict) else (row[0] if row else None)
                if v is not None:
                    newest.append(v)
            return max(newest) if newest else None

    newest = _step("clock_check", _newest_log, default=None)
    if "clock_check" in failed:
        # ตรวจนาฬิกาไม่ได้ = ไม่รู้ว่าปลอดภัยไหม -> ไม่ลบอะไรที่ขึ้นกับเวลา (เก็บนานขึ้นปลอดภัยกว่า)
        return PurgeSummary(cutoff_logs=log_cutoff, cutoff_customers=cust_cutoff,
                            failed_steps=tuple(failed), skipped_clock=True)
    if clock_is_suspect(newest, now):
        log.error("นาฬิกาน่าสงสัย: now=%s ล้ำหน้า log ล่าสุด %s เกิน %d วัน -- ข้ามการลบรอบนี้",
                  now.isoformat(), newest, CLOCK_SKEW_DAYS)
        audit.log("purge_skipped_clock", detail=(
            f"now={now.isoformat()} newest_log={newest.isoformat()} skew_days={CLOCK_SKEW_DAYS}"))
        return PurgeSummary(cutoff_logs=log_cutoff, cutoff_customers=cust_cutoff, skipped_clock=True)

    def _logs():
        return purge_conn_and_dns_logs(_exec, log_cutoff)

    def _customers():
        # anonymize_customer ต้องอยู่ transaction เดียวกันทั้งรายการ -> ขั้นนี้ใช้ connection เดียว
        with get_conn() as conn, conn.cursor() as cur:
            def ex(sql, args=()):
                cur.execute(sql, args)
                return cur.rowcount
            return purge_stale_customers(
                lambda sql, args=(): (cur.execute(sql, args), cur.fetchall())[1],
                lambda sql, args=(): (cur.execute(sql, args), cur.fetchone())[1],
                ex, cust_cutoff, max(retention_days, customer_retention_days), now)

    # ลำดับเดิม: log -> anonymize ลูกค้า (นับกิจกรรมจาก session) -> session/device/bypass
    n_conn, n_dns = _step("logs", _logs, default=(0, 0))
    n_cust = _step("customers", _customers)
    n_ps, n_dev, n_byp = _step("session_data", lambda: purge_session_data(_exec, log_cutoff),
                               default=(0, 0, 0))
    _step("voucher_reveal", lambda: _exec("DELETE FROM voucher_reveal WHERE expires_at < NOW()"))
    # คำขอใช้งานเก่า (มี natid_masked/ชื่อเครื่อง/User-Agent) -- เก็บเท่าอายุ log พอ
    # ร่องรอยการอนุมัติยังอยู่ใน audit_log
    n_req = _step("access_request", lambda: batched_delete(
        _exec, "DELETE FROM access_request WHERE created_at < %s", (log_cutoff,)))
    _step("rate_attempt", lambda: _exec("DELETE FROM rate_attempt WHERE ts < NOW() - INTERVAL 1 DAY"))

    summary = PurgeSummary(conn_log_deleted=n_conn, dns_log_deleted=n_dns,
                           customers_deleted=n_cust, sessions_deleted=n_ps,
                           devices_deleted=n_dev, bypass_alerts_deleted=n_byp, cutoff_logs=log_cutoff,
                           cutoff_customers=cust_cutoff, access_requests_deleted=n_req,
                           failed_steps=tuple(failed))

    audit.log("purge_old_data", detail=(
        f"conn_log=-{n_conn} dns_log=-{n_dns} customer_anonymized={n_cust} access_request=-{n_req} "
        f"portal_session=-{n_ps} device=-{n_dev} bypass_alert=-{n_byp} "
        f"log_cutoff={log_cutoff.isoformat()} customer_cutoff={cust_cutoff.isoformat()}"
        + (f" failed={','.join(failed)}" if failed else "")
    ))
    log.info("purge เสร็จ: conn_log -%d, dns_log -%d, customer anonymized %d", n_conn, n_dns, n_cust)
    return summary


def main() -> int:  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    try:
        summary = run()
    except ValueError as exc:
        log.error(str(exc))
        return 1
    return 1 if summary.failed_steps else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
