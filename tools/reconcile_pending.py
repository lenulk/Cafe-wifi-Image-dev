"""ยืนยัน pending FAS sessions กับ openNDS ก่อนนับว่าออนไลน์จริง."""
from __future__ import annotations

import ipaddress
import json
import logging
import math
import os
import subprocess
from datetime import datetime

from common import access, audit
from common.db import get_conn

log = logging.getLogger("cafe-wifi.reconcile_pending")


def gateway_clients(macs) -> dict | None:
    """สถานะใน openNDS ของ MAC ที่ระบุ (key = MAC ตัวพิมพ์เล็ก) -- คืน None ถ้าอ่านตัวใดตัวหนึ่งไม่ได้

    ถามทีละ MAC ด้วย `ndsctl json <mac>` ไม่ใช่ `ndsctl json` ทั้งก้อน -- วัดบน Pi จริง 2026-10-02:
    ทั้งก้อนใช้ ~0.27 + 1.1 วินาทีต่อลูกค้าหนึ่งคน (ลูกค้า 3 คน = 3.5 วิ, ร้าน 30 คน ≈ 34 วิ เกิน timeout
    10 วิ -> อ่านไม่ได้ทุกรอบ ลูกค้าใหม่ทุกคนค้าง pending ตลอดไป authenticated_at ว่าง log โยงหาตัวคน
    ไม่ได้) และระหว่างนั้น openNDS ตอบ busy กับคำสั่งอื่นทั้งหมด (deauth ของ cafe-enforce ด้วย)
    ทีละ MAC ใช้ ~1.4 วิ และปกติมี pending พร้อมกันแค่ 0-2 เครื่อง
    """
    from tools.enforce_voucher_expiry import run_ndsctl
    clients: dict = {}
    for mac in sorted({m.lower() for m in macs}):
        try:
            result = run_ndsctl(["ndsctl", "json", mac])  # ลองใหม่เองเมื่อ openNDS ตอบ busy (exit 4)
            if result.returncode != 0:
                raise subprocess.CalledProcessError(result.returncode, f"ndsctl json {mac}")
            data = json.loads(result.stdout.decode(errors="replace") or "{}") or {}
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            log.error("อ่านสถานะ openNDS ไม่ได้: %s", exc)
            return None
        if data:  # `{}` = openNDS ไม่รู้จัก MAC นี้
            clients[mac] = data
    return clients


def confirmed_at(client: dict | None, ip: str, started_at: datetime) -> datetime | None:
    """คืนเวลาที่ openNDS เปิดสิทธิ์จริง (session_start) ถ้ายืนยันได้ ไม่งั้นคืน None

    MAC อย่างเดียวไม่พอ: ต้องเป็น IP เดิมและ gateway session ที่เริ่มหลัง pending
    """
    if not client or not str(client.get("state", "")).lower().startswith("auth"):
        return None
    if str(client.get("ip") or client.get("clientip") or "") != ip:
        return None
    try:
        gateway_start = datetime.fromtimestamp(int(client["session_start"]))
    except (KeyError, TypeError, ValueError, OverflowError, OSError):
        return None
    return gateway_start if gateway_start >= started_at else None


def purge_orphan_claims() -> int:
    """R2-01: ลบ claim ที่ portal_session_id=NULL ซึ่งหลุด commit มาจาก /login รุ่นก่อนแก้

    แถวแบบนี้ไม่มี session ให้ผูก ลูปหลักจึงไม่เคยลบ และทำให้ MAC นั้นได้ 409 ตลอดไป
    แยก transaction จากลูปหลักและแตะแค่ตารางนี้ เพื่อไม่ให้ลำดับ lock ชนกับ /login
    (claim ของ /login ที่ยังไม่ commit จะผูก portal_session_id ก่อน commit เสมอ จึงไม่ถูกลบ)
    """
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM pending_mac_claim WHERE portal_session_id IS NULL")
        purged = cur.rowcount
    if purged:
        log.warning("ลบ pending_mac_claim ที่ค้างอยู่ %d รายการ", purged)
    return purged


def expire_requests() -> int:
    """คำขอใช้งานที่ไม่มีใครอนุมัติทันเวลา -> expired และล้างเลขบัตร (hash/ciphertext) ทิ้งทันที"""
    with get_conn() as conn, conn.cursor() as cur:
        # B5 (PDPA): ล้างตัวตนทั้งชุดเหมือนตอนปฏิเสธ (masked ใส่ PURGED เพราะ NOT NULL) · mac/ip คงไว้
        cur.execute("UPDATE access_request SET status='expired', natid_hash=NULL, natid_enc=NULL, "
                    "natid_masked='PURGED', hostname=NULL, user_agent=NULL "
                    "WHERE status='pending' AND expires_at <= NOW()")
        return cur.rowcount


def _gateway_authenticated(mac: str) -> bool:
    clients = gateway_clients([mac])
    client = (clients or {}).get(mac.lower())
    return bool(client) and str(client.get("state", "")).lower().startswith("auth")


def _minutes_left(valid_until: datetime) -> int:
    return max(1, math.ceil((valid_until - datetime.now()).total_seconds() / 60))


def _auth_mac(mac: str, minutes: int) -> bool:
    """`ndsctl auth <mac> <นาที>` -- True ถ้า openNDS เปิดสิทธิ์ให้แล้ว (sessiontimeout = นาทีที่สิทธิ์เหลือ)"""
    from tools.enforce_voucher_expiry import run_ndsctl
    try:
        res = run_ndsctl(["ndsctl", "auth", mac.lower(), str(minutes)])
        if res.returncode != 0 and _gateway_authenticated(mac):
            # B2 (ยืนยันบน Pi 2026-10-16): MAC ที่ออนไลน์อยู่แล้ว (ลูกค้าส่งคำขอซ้ำจากแท็บที่เปิดค้าง
            # แล้วพนักงานอนุมัติทั้งคู่) -> openNDS ตอบ "Failed to authenticate client" exit 1 ทุกรอบ
            # จน pending หมด 180 วิ แล้วถูก deauth เป็น auth_timeout = ลูกค้าหลุดทั้งที่อนุมัติแล้ว
            # ใช้วิธีเดียวกับ sync_extended: deauth แล้ว auth ใหม่ทันที -> session_start ใหม่ ลูปยืนยันใน
            # run() ปิดแถวเดิมเป็น reauth (log ต่อเนื่อง) แล้วเลื่อนแถวใหม่เป็น authenticated
            log.warning("ndsctl auth %s: ออนไลน์อยู่แล้ว -- deauth แล้ว auth ใหม่", mac)
            run_ndsctl(["ndsctl", "deauth", mac.lower()])
            res = run_ndsctl(["ndsctl", "auth", mac.lower(), str(minutes)])
    except (OSError, subprocess.SubprocessError) as exc:
        log.error("ndsctl auth %s ล้มเหลว: %s", mac, exc)
        return False
    if res.returncode != 0:
        log.error("ndsctl auth %s ไม่สำเร็จ (exit %d): %s", mac, res.returncode,
                  (res.stdout or b"").decode(errors="replace")[:200])
        return False
    return True


def authorize_approved() -> int:
    """คำขอที่พนักงานอนุมัติแล้ว -> สั่ง openNDS เปิดสิทธิ์ให้ MAC นั้นโดยตรง (`ndsctl auth`)

    แทน redirect ของ FAS เดิม: ลูกค้าไม่ต้องทำอะไรต่อบนหน้าเว็บ (ยืนรอหน้าเคาน์เตอร์ได้เลย) และ
    ทำได้แค่ที่นี่เพราะ ndsctl ต้องใช้ root (Admin รันเป็น cafewifi) · sessiontimeout = นาทีที่ voucher
    เหลือ openNDS จึงตัดเองตรงเวลาแม้ cafe-enforce ยังไม่ถึงรอบ · ยืนยัน session ต่อด้วยลูปเดิมใน run()
    อ่านรายการก่อนแล้วค่อยเรียก ndsctl นอก transaction (ไม่ถือ lock ระหว่างรอ openNDS)
    """
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT ar.id, ar.mac, v.valid_until FROM access_request ar "
                    "JOIN portal_session ps ON ps.id = ar.portal_session_id "
                    "JOIN voucher v ON v.id = ar.voucher_id "
                    "WHERE ar.status='approved' AND ar.auth_sent_at IS NULL AND ps.state='pending'")
        todo = cur.fetchall()
    sent = 0
    for r in todo:
        # ยังไม่ทำเครื่องหมายถ้าไม่สำเร็จ -> รอบถัดไป (5 วิ) ลองใหม่ จนกว่า pending จะหมดเวลา (auth_timeout)
        if not _auth_mac(r["mac"], _minutes_left(r["valid_until"])):
            continue
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("UPDATE access_request SET auth_sent_at=NOW() WHERE id=%s", (r["id"],))
        sent += 1
    return sent


def sync_extended() -> int:
    """ปุ่มต่อเวลาในแดชบอร์ด -> ให้ openNDS ตัดตามเวลาใหม่ (sql/012_voucher_extend.sql)

    openNDS 10.1.3 ไม่มีคำสั่งแก้เวลาของเครื่องที่ออนไลน์อยู่ และ `auth` ซ้ำไม่ได้ -- ต้อง deauth แล้ว auth
    ทันทีด้วยนาทีที่เหลือใหม่ (วัดบน Pi: เน็ตใช้ได้ต่อ, session ในฐานข้อมูลเป็นแถวเดิม log ต่อเนื่อง)
    ล้างธงเมื่อทำครบทุกเครื่อง ถ้าบางเครื่องไม่สำเร็จคงธงไว้ให้รอบถัดไป (5 วิ) ลองใหม่
    """
    from tools.enforce_voucher_expiry import run_ndsctl
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT v.id, v.status, v.valid_until, c.is_blocked FROM voucher v "
                    "JOIN customer c ON c.id = v.customer_id WHERE v.auth_sync_needed = 1")
        vouchers = cur.fetchall()
        sessions = {}
        for v in vouchers:
            cur.execute("SELECT mac FROM portal_session WHERE voucher_id=%s AND state='authenticated' "
                        "AND ended_at IS NULL", (v["id"],))
            sessions[v["id"]] = [r["mac"] for r in cur.fetchall()]
    done = 0
    # ปุ่ม "ปิดสิทธิ์" ตั้งธงนี้ด้วย (2026-10-04) -- เดิมต้องรอ cafe-enforce รอบถัดไปสูงสุด 5 นาที
    # พนักงานเห็นลูกค้ายังใช้เน็ตได้หลังกดปิดแล้ว · ใช้ตัวตัดตัวเดียวกับ cafe-enforce (deauth + ปิด session +
    # log terminate_cause ครบ) แทนการ deauth เองที่นี่ ผลจึงเหมือนรอบปกติทุกอย่าง แค่เร็วขึ้น
    # ลูกค้าที่ถูกระงับ (B6) นับเป็น "ตาย" ด้วย: ไม่ใช่ deauth+auth ต่อให้ใหม่ แต่ให้ cafe-enforce ตัดทิ้ง
    dead = [v for v in vouchers if v.get("is_blocked")
            or not (v["status"] == "active" and v["valid_until"] > datetime.now())]
    dead_ok = True
    if dead and any(sessions[v["id"]] for v in dead):
        from tools import enforce_voucher_expiry
        try:
            summary = enforce_voucher_expiry.run(deauth=True)
        except Exception as exc:  # noqa: BLE001 -- คงธงไว้ให้รอบถัดไป (5 วิ) ลองใหม่
            log.error("ตัดเครื่องของสิทธิ์ที่ถูกปิดไม่สำเร็จ: %s", exc)
            dead_ok = False
        else:
            # T3: run() ไม่ raise เมื่อ ndsctl deauth ล้ม แต่นับใน deauth_failed -- ถ้าล้างธงตอนนี้
            # ลูกค้าที่ถูกปิดสิทธิ์/ระงับจะยังออนไลน์ถึงรอบ cafe-enforce (5 นาที) จึงคงธงให้ลูป 5 วิ ลองใหม่
            failed = getattr(summary, "deauth_failed", 0)
            if failed:
                log.error("ตัดเครื่องของสิทธิ์ที่ถูกปิดไม่ครบ (deauth ล้มเหลว %s เครื่อง) -- คงธงไว้ลองใหม่", failed)
                dead_ok = False
    for v in vouchers:
        ok = True
        if v in dead and not dead_ok:
            continue
        if v not in dead:
            minutes = max(1, math.ceil((v["valid_until"] - datetime.now()).total_seconds() / 60))
            for mac in sessions[v["id"]]:
                try:
                    run_ndsctl(["ndsctl", "deauth", mac.lower()])
                    res = run_ndsctl(["ndsctl", "auth", mac.lower(), str(minutes)])
                except (OSError, subprocess.SubprocessError) as exc:
                    log.error("ต่อเวลา %s ที่ openNDS ล้มเหลว: %s", mac, exc)
                    ok = False
                    continue
                if res.returncode != 0:
                    log.error("ต่อเวลา %s ที่ openNDS ไม่สำเร็จ (exit %d)", mac, res.returncode)
                    ok = False
        if ok:
            with get_conn() as conn, conn.cursor() as cur:
                cur.execute("UPDATE voucher SET auth_sync_needed=0 WHERE id=%s", (v["id"],))
            done += 1
    return done


# สถานะใน neighbor table ที่แปลว่าเครื่อง "อยู่ตรงนี้ตอนนี้" (เพิ่งคุยกับ Pi) -- STALE/FAILED คือเครื่องที่อาจ
# ออกไปแล้ว ต้องไม่ถาม openNDS ทุก 5 วิให้เปลือง ndsctl
_PRESENT_STATES = {"REACHABLE", "DELAY", "PROBE"}


def present_clients() -> dict[str, str]:
    """MAC (ตัวใหญ่) -> IP ของเครื่องในวงลูกค้าที่เพิ่งมีความเคลื่อนไหว อ่านจาก neighbor table ของเคอร์เนล
    (ไม่ใช้ `ndsctl json` ทั้งก้อน -- ช้า ~1.1 วิต่อลูกค้าและยึด openNDS ไว้ ดู gateway_clients)"""
    try:
        net = ipaddress.ip_interface(os.environ.get("CLIENT_CIDR") or "10.10.0.1/24").network
        r = subprocess.run(["ip", "-j", "-4", "neigh", "show"], capture_output=True, timeout=5)
        entries = json.loads(r.stdout or b"[]") if r.returncode == 0 else []
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        log.warning("อ่าน neighbor table ไม่ได้: %s", exc)
        return {}
    found = {}
    for e in entries:
        mac, ip = e.get("lladdr"), e.get("dst")
        if not mac or not ip or not _PRESENT_STATES & set(e.get("state") or []):
            continue
        try:
            if ipaddress.ip_address(ip) in net:
                found[mac.upper()] = ip
        except ValueError:
            continue
    return found


def resume_returning() -> int:
    """เครื่องที่พนักงานอนุมัติแล้ว (ผูกใน `device`) กลับมาในวงลูกค้าขณะสิทธิ์ยังไม่หมด -> เปิดสิทธิ์เดิมให้เอง

    พบบน Pi 2026-10-16: openNDS รีสตาร์ท (ติดตั้งทับ/รีบูต/ไฟดับ) คืนสิทธิ์ให้เฉพาะเครื่องที่มีทราฟฟิกตอนนั้น
    Redmi ที่จอดับอยู่หลุดจากรายชื่อ -> cafe-enforce ปิด session เป็น disconnected -> ตื่นมาเจอหน้าลงทะเบียน
    ทั้งที่สิทธิ์เหลืออีก 80 นาที (ลูกค้าต้องยื่นบัตรใหม่ พนักงานต้องอนุมัติซ้ำ) · กรณีเดียวกับลูกค้าที่ไม่ได้ใช้
    เกิน authidletimeout หรือเดินออกไปแล้วกลับมา

    เปิด session ใหม่ (pending) ภายใต้ voucher เดิม แล้ว `ndsctl auth` -- ลูปยืนยันใน run() เลื่อนเป็น
    authenticated ด้วยเวลาจริงของ openNDS เหมือนการอนุมัติปกติ log ช่วงใหม่จึงโยงถึงลูกค้าคนเดิม
    ไม่คืนสิทธิ์ถ้าสิทธิ์ถูกปิด/หมดเวลา/ครบโควตา (status != active) หรือลูกค้าถูกระงับ
    """
    present = present_clients()
    if not present:
        return 0
    marks = ",".join(["%s"] * len(present))
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT d.mac, v.id, v.max_devices, v.valid_until, "
            "(SELECT p.hostname FROM portal_session p WHERE p.mac=d.mac AND p.voucher_id=v.id "
            " ORDER BY p.id DESC LIMIT 1) AS hostname, "
            "(SELECT p.os_label FROM portal_session p WHERE p.mac=d.mac AND p.voucher_id=v.id "
            " ORDER BY p.id DESC LIMIT 1) AS os_label "
            "FROM device d JOIN voucher v ON v.id = d.voucher_id "
            "JOIN customer c ON c.id = v.customer_id "
            f"WHERE d.mac IN ({marks}) AND v.status='active' AND v.valid_until > NOW() "
            "AND NOT c.is_blocked AND NOT EXISTS (SELECT 1 FROM portal_session ps WHERE ps.mac=d.mac "
            "AND (ps.state='pending' OR (ps.state='authenticated' AND ps.ended_at IS NULL))) "
            "ORDER BY v.valid_until DESC", tuple(present))
        rows = cur.fetchall()
    todo: dict = {}
    for r in rows:  # MAC เดียวผูกหลายสิทธิ์ได้ (มาซ้ำคนละวัน) -- ใช้สิทธิ์ที่เหลือนานสุด
        todo.setdefault(r["mac"].upper(), r)
    if not todo:
        return 0
    clients = gateway_clients(todo)
    if clients is None:
        return 0
    resumed = 0
    for mac, r in todo.items():
        client = clients.get(mac.lower())
        ip = present[mac]
        # openNDS ไม่รู้จักเครื่องนี้ก็ได้ (มือถือที่จอดับไม่เปิดหน้า portal เอง -- เจอบน Pi) เพราะ `ndsctl auth`
        # เปิดสิทธิ์ล่วงหน้าโดยหา IP จาก ARP เอง (Pre-emptive Authentication) · แต่ถ้ารู้จักแล้วต้องเป็น IP เดียวกัน
        # ไม่งั้นลูปยืนยันจะไม่ผ่านแล้วกลายเป็น auth_timeout
        if client and str(client.get("ip") or client.get("clientip") or "") != ip:
            continue
        with get_conn() as conn, conn.cursor() as cur:
            err, session_id = access.reserve_pending_session(
                cur, {"id": r["id"], "max_devices": r["max_devices"]}, mac, ip,
                r.get("hostname"), r.get("os_label"))
            if err:
                conn.rollback()
                log.warning("คืนสิทธิ์ %s ไม่ได้: %s", mac, err)
                continue
        # auth ไม่สำเร็จ -> แถว pending หมดเวลาใน 180 วิ แล้วลูปยืนยันเก็บเป็น auth_timeout จากนั้นรอบถัดไปลองใหม่
        if not _auth_mac(mac, _minutes_left(r["valid_until"])):
            continue
        resumed += 1
        log.info("คืนสิทธิ์เดิมให้ %s (voucher %s, session %s)", mac, r["id"], session_id)
        audit.log(audit.DEVICE_RESUME, target=mac, client_ip=ip,
                  detail=f"voucher={r['id']} session={session_id}")
    return resumed


def enforce_live_quota() -> int:
    """voucher ที่มีโควตา: รวมยอดสดจากตัวนับของ openNDS (download/upload_this_session หน่วย kB) -> ครบแล้วตัดทันที

    T5 บน Pi 2026-10-16 (Redmi, โควตา 500 MB): ใช้จริง 1,058 MB ใน ~2 นาทีโดยยังไม่ถูกตัด -- ยอดใน conn_log
    ถูกบันทึกเมื่อการเชื่อมต่อปิด (speedtest/ดาวน์โหลดเปิดค้างยาว ฐานข้อมูลเห็นแค่ 126 MB) และ cafe-enforce รันทุก
    5 นาที · ที่ 270 Mbit/s ช่วงช้านั้นใช้เกินได้หลาย GB
    ตั้ง used_up + auth_sync_needed -> sync_extended() รอบเดียวกันเรียก cafe-enforce ตัด + ปิด session เป็น
    quota_exceeded ตามเส้นทางปกติ · ถาม openNDS เฉพาะเครื่องของ voucher ที่มีโควตา (~1.4 วิ/เครื่อง)
    """
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT v.id, v.quota_mb, v.used_mb, ps.mac FROM portal_session ps "
                    "JOIN voucher v ON v.id = ps.voucher_id "
                    "WHERE ps.state='authenticated' AND ps.ended_at IS NULL "
                    "AND v.status='active' AND v.quota_mb IS NOT NULL")
        rows = cur.fetchall()
    if not rows:
        return 0
    clients = gateway_clients({r["mac"] for r in rows})
    if clients is None:
        return 0
    from common.traffic import BYTES_PER_MB
    from tools.enforce_voucher_expiry import _kb
    live: dict[int, int] = {}
    info: dict[int, dict] = {}
    for r in rows:
        c = clients.get(r["mac"].lower()) or {}
        live[r["id"]] = live.get(r["id"], 0) + (
            _kb(c.get("download_this_session")) + _kb(c.get("upload_this_session"))) * 1024
        info[r["id"]] = r
    hit = 0
    for vid, live_bytes in sorted(live.items()):
        v = info[vid]
        used = int(v["used_mb"] or 0) * BYTES_PER_MB + live_bytes
        if used < int(v["quota_mb"]) * BYTES_PER_MB:
            continue
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("UPDATE voucher SET status='used_up', auth_sync_needed=1 "
                        "WHERE id=%s AND status='active'", (vid,))
            hit += cur.rowcount
        log.warning("voucher %s ใช้ครบโควตาแล้ว (%d/%s MB นับสดจาก openNDS) -- ตัดทันที",
                    vid, used // BYTES_PER_MB, v["quota_mb"])
    return hit


def run() -> tuple[int, int]:
    expire_requests()
    authorize_approved()
    enforce_live_quota()   # ก่อน sync_extended: ตัดในรอบเดียวกันได้เลย
    sync_extended()
    resume_returning()
    # ถาม openNDS เฉพาะเมื่อมี pending จริง (ส่วนใหญ่ของเวลาไม่มี) -- ไม่ยึด ndsctl ไว้ทุก 5 วิโดยเปล่า
    # ประโยชน์ และอ่านนอก transaction เพื่อไม่ถือ lock ของ portal_session ไว้ระหว่างรอ ndsctl
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT ps.mac FROM portal_session ps WHERE ps.state='pending'")
        pending_macs = {r["mac"] for r in cur.fetchall()}
    clients = gateway_clients(pending_macs) if pending_macs else {}
    promoted = expired = 0
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM fas_context WHERE expires_at < "
                    "DATE_SUB(NOW(), INTERVAL 1 DAY)")
        cur.execute("SELECT ps.id, ps.voucher_id, ps.mac, ps.ip, ps.started_at, "
                    "ps.pending_until, v.status, v.valid_until "
                    "FROM portal_session ps JOIN voucher v ON v.id=ps.voucher_id "
                    "WHERE ps.state='pending' ORDER BY ps.id FOR UPDATE")
        pending = cur.fetchall()
        # อ่าน ndsctl ไม่ได้ (openNDS กำลังรีสตาร์ท หรือ ndsctl ตอบ busy เพราะ cafe-enforce/คนดูแล
        # เรียกพร้อมกัน -- เจอจริงบน Pi 2026-10-02 exit 4) = ไม่รู้ว่าใครได้สิทธิ์แล้ว ต้องข้ามทั้งรอบ
        # เดิมยังตัด pending ที่เลยกำหนดทิ้งเป็น auth_timeout ทั้งที่ลูกค้าอาจออนไลน์แล้วจริง
        if clients is None:
            pending = []
        for row in pending:
            # R2-08: ตรวจการยืนยันจาก openNDS ก่อน timeout -- ลูกค้าที่กดตาม redirect ใกล้
            # วินาทีสุดท้ายของ pending ถูกเปิดสิทธิ์ไปแล้ว ต้องไม่ถูกตัดทิ้งว่า auth_timeout
            gateway_start = None
            if clients is not None:
                client = clients.get(row["mac"].lower())
                gateway_start = confirmed_at(client, row["ip"], row["started_at"])
            if gateway_start is None and row["pending_until"] <= datetime.now():
                from tools.enforce_voucher_expiry import deauth_mac
                if not deauth_mac(row["mac"]):
                    log.error("pending %s หมดเวลาแต่ตัดสิทธิ์ที่ gateway ไม่สำเร็จ", row["id"])
                    continue
                cur.execute("UPDATE portal_session SET state='closed', ended_at=NOW(), "
                            "terminate_cause='auth_timeout' WHERE id=%s AND state='pending'",
                            (row["id"],))
                cur.execute("DELETE FROM pending_mac_claim WHERE mac=%s AND portal_session_id=%s",
                            (row["mac"], row["id"]))
                expired += 1
                continue
            if gateway_start is None:
                continue
            if row["status"] != "active" or row["valid_until"] <= datetime.now():
                from tools.enforce_voucher_expiry import deauth_mac
                if not deauth_mac(row["mac"]):
                    log.error("voucher ไม่ active แต่ตัด MAC %s ไม่สำเร็จ", row["mac"])
                    continue
                cur.execute("UPDATE portal_session SET state='closed', ended_at=NOW(), "
                            "terminate_cause='voucher_invalid' WHERE id=%s", (row["id"],))
                cur.execute("DELETE FROM pending_mac_claim WHERE mac=%s AND portal_session_id=%s",
                            (row["mac"], row["id"]))
                continue
            cur.execute("SELECT id, voucher_id, started_at, authenticated_at FROM portal_session WHERE mac=%s "
                        "AND state='authenticated' AND ended_at IS NULL FOR UPDATE",
                        (row["mac"],))
            for old in cur.fetchall():
                from common.traffic import sum_session_traffic_bytes
                from tools.enforce_voucher_expiry import close_session

                def lookup(sql, args=()):
                    cur.execute(sql, args)
                    return cur.fetchone()

                def execute(sql, args=()):
                    cur.execute(sql, args)
                    return cur.rowcount

                bo, bi = sum_session_traffic_bytes(
                    lookup, row["mac"], old["authenticated_at"] or old["started_at"], gateway_start)
                close_session(execute, old["id"], old["voucher_id"], bo, bi,
                              "reauth", ended_at=gateway_start)
            cur.execute("INSERT INTO device (voucher_id, mac, last_ip) VALUES (%s,%s,%s) "
                        "ON DUPLICATE KEY UPDATE last_ip=VALUES(last_ip)",
                        (row["voucher_id"], row["mac"], row["ip"]))
            # R2-08: ใช้เวลาที่ openNDS เปิดสิทธิ์จริง ไม่ใช่เวลาที่ timer มาเจอ (ช้ากว่าได้หลายวินาที)
            # ไม่งั้น DNS query ชุดแรกหลังเปิดสิทธิ์จะมี ts < authenticated_at และโยงหาลูกค้าไม่ได้
            cur.execute("UPDATE portal_session SET state='authenticated', authenticated_at=%s "
                        "WHERE id=%s AND state='pending'", (gateway_start, row["id"]))
            cur.execute("DELETE FROM pending_mac_claim WHERE mac=%s AND portal_session_id=%s",
                        (row["mac"], row["id"]))
            promoted += 1
    purge_orphan_claims()
    if promoted:
        audit.log(audit.LOGIN_OK, detail=f"confirmed={promoted}")
    if expired:
        log.warning("pending session หมดเวลา %d รายการ", expired)
    return promoted, expired


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    try:
        run()
    except Exception as exc:  # noqa: BLE001
        # พบบน Pi 2026-10-16: กดอนุมัติชนจังหวะ expire_requests() -> MySQL 1213 deadlock ทั้งรอบ unit ขึ้น Failed
        # transaction ของรอบนี้ rollback หมดแล้ว timer รอบถัดไป (5 วิ) ทำต่อเอง -- ไม่ใช่ความผิดพลาดที่ต้องปลุกใคร
        if getattr(exc, "args", None) and exc.args[0] in (1213, 1205):
            log.warning("ฐานข้อมูลชนล็อก (MySQL %s) -- รอบถัดไปทำต่อ", exc.args[0])
            return 0
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
