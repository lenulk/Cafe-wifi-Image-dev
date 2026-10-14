"""
admin/views/audit_view.py — หน้าดู audit_log (เฉพาะ admin)

ใครทำอะไรเมื่อไหร่ในระบบ (เปิดเลขบัตร, ออกสิทธิ์, ส่งออก log, จัดการพนักงาน ฯลฯ) -- การเปิดดูหน้านี้เองก็ถูกบันทึก
เป็น action "view_audit" ทุกครั้ง (ผู้ตรวจสอบต้องถูกตรวจสอบได้ด้วย) · ตัวช่วยกลางเรียกผ่าน core.* ตอนรันเสมอ
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta

from flask import flash, g, redirect, render_template, request, session, url_for

from common import audit, crypto
from common.sqlutil import like_escape as _like_escape

from admin import app as core
from admin.routes import Routes
from admin.views.logs import LOG_RANGES, _resolve_log_range

routes = Routes()

AUDIT_PAGE_SIZE = 50
VIEW_AUDIT = "view_audit"
Q_MAX = 100          # ความยาวช่องค้นข้อความ
Q_AUDIT_MAX = 50     # ส่วนของ q ที่ลงใน audit

# ---- ล้างข้อมูลลูกค้าในแถว audit เก่า (T8) -- ไม่ลบแถว แค่ตัด MAC/เลขบัตรออกจาก target/detail
SCRUB_MIN_DAYS = 180     # ขั้นต่ำเท่าอายุเก็บ log (LOG_RETENTION_DAYS ตั้งสูงกว่านี้ได้ ต่ำกว่าไม่ได้)
SCRUB_BATCH = 1000
SCRUB_MASK = "[ลบแล้ว]"
_MAC_RE = re.compile(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2}){5}(?![0-9A-Fa-f])")
# 1-2345-XXXXX-XX-3 (รูปแบบ crypto.mask_natid) และรูปมีขีดแบบเต็ม 1-2345-67890-12-3
_NATID_MASKED_RE = re.compile(r"(?<!\d)\d-\d{4}-(?:X{5}|\d{5})-(?:X{2}|\d{2})-\d(?!\d)", re.I)
_DIGITS13_RE = re.compile(r"(?<!\d)\d{13}(?!\d)")


def scrub_text(text):
    """ตัด MAC / เลขบัตร (ปิดบังบางส่วนหรือเต็ม) ออกจากข้อความ · None/ว่างคืนตามเดิม"""
    if not text:
        return text
    out = _MAC_RE.sub(SCRUB_MASK, text)
    out = _NATID_MASKED_RE.sub(SCRUB_MASK, out)
    return _DIGITS13_RE.sub(SCRUB_MASK, out)


def _scrub_floor_days() -> int:
    try:
        return max(SCRUB_MIN_DAYS, int(os.environ.get("LOG_RETENTION_DAYS", SCRUB_MIN_DAYS)))
    except ValueError:
        return SCRUB_MIN_DAYS


def _known_actions() -> list[str]:
    """ค่าคงที่ใน common/audit.py (ตัวพิมพ์เล็กล้วน) + ค่าสตริงอิสระที่โค้ดอื่นเขียน"""
    consts = {v for k, v in vars(audit).items()
              if k.isupper() and isinstance(v, str) and v}
    consts.add(VIEW_AUDIT)
    return sorted(consts)


@routes.get("/audit")
@core.login_required
@core.admin_required
def audit_log_page():
    staff_f = (request.args.get("staff") or "").strip()[:64]
    action_f = (request.args.get("action") or "").strip()[:64]
    q = (request.args.get("q") or "").strip()[:Q_MAX]
    ip_f = (request.args.get("client_ip") or "").strip()[:45]
    rng = request.args.get("range", "today")
    if rng not in LOG_RANGES:
        rng = "today"
    start_raw = (request.args.get("start") or "").strip()
    end_raw = (request.args.get("end") or "").strip()
    try:
        page = max(1, int(request.args.get("page") or 1))
    except ValueError:
        page = 1

    params = dict(staff=staff_f, action=action_f, q=q, client_ip=ip_f, range=rng,
                  start=start_raw, end=end_raw)

    staff_names = [r["username"] for r in
                   core.query_all("SELECT username FROM staff ORDER BY username LIMIT 500")]
    db_actions = [r["action"] for r in core.query_all(
        "SELECT DISTINCT action FROM audit_log ORDER BY action LIMIT 200")]
    actions = sorted(set(_known_actions()) | set(db_actions))
    latest = datetime.now() - timedelta(days=_scrub_floor_days())
    ctx = dict(scrub_latest=latest.strftime("%Y-%m-%d"), scrub_days=_scrub_floor_days(),
               params=params, ranges=LOG_RANGES, staff_names=staff_names, actions=actions,
               rows=[], page=page, has_next=False, has_prev=page > 1,
               start_dt=None, end_dt=None)

    start, end, error = _resolve_log_range(rng, start_raw, end_raw)
    if error:
        return render_template("audit_log.html", error=error, **ctx), 400
    ctx.update(start_dt=start, end_dt=end)

    where = ["a.ts BETWEEN %s AND %s"]
    args: list = [start, end]
    if staff_f:
        where.append("s.username = %s"); args.append(staff_f)
    if action_f:
        where.append("a.action = %s"); args.append(action_f)
    if ip_f:
        where.append("a.client_ip = %s"); args.append(ip_f)
    if q:
        where.append("a.detail LIKE %s ESCAPE '\\\\'"); args.append(f"%{_like_escape(q)}%")

    sql = ("SELECT a.id, a.ts, s.username AS staff_username, a.staff_id, a.action, a.target, "
           "a.client_ip, a.detail FROM audit_log a LEFT JOIN staff s ON s.id = a.staff_id "
           "WHERE " + " AND ".join(where) + " ORDER BY a.ts DESC, a.id DESC LIMIT %s OFFSET %s")

    detail = (f"staff={staff_f or '-'} action={action_f or '-'} ip={ip_f or '-'} "
              f"q={q[:Q_AUDIT_MAX] or '-'} start={start.isoformat()} end={end.isoformat()} page={page}")
    audit.log_required(VIEW_AUDIT, staff_id=session["staff_id"], client_ip=g.client_ip, detail=detail)

    rows = core.query_all(sql, tuple(args + [AUDIT_PAGE_SIZE + 1, (page - 1) * AUDIT_PAGE_SIZE]))
    has_next = len(rows) > AUDIT_PAGE_SIZE
    ctx.update(rows=rows[:AUDIT_PAGE_SIZE], has_next=has_next)
    return render_template("audit_log.html", error=None, **ctx)


@routes.post("/audit/scrub")
@core.login_required
@core.admin_required
def audit_scrub():
    """admin ล้าง MAC/เลขบัตรในแถว audit ที่เก่ากว่าวันที่กำหนด · ไม่ลบแถว ไม่แตะ staff_id/action/ts/client_ip

    ยืนยันรหัสผ่านซ้ำเหมือน /keys/backup · เขียน audit "เริ่ม" ก่อนแก้ (fail closed แบบ export: เขียน audit
    ไม่ได้ = ไม่แก้อะไร) แล้วเขียนอีกแถวตอนจบพร้อมจำนวน -- ทั้งสองแถวใหม่กว่า cutoff จึงไม่ถูกล้างเอง
    """
    bucket = f"auditscrub:{session['staff_id']}"
    if core.rate_limited(bucket):
        flash("ลองผิดหลายครั้งเกินไป รอ 10 นาทีแล้วลองใหม่", "err")
        return redirect(url_for("audit_log_page"))
    reason = (request.form.get("reason") or "").strip()
    cutoff_raw = (request.form.get("cutoff") or "").strip()
    current = request.form.get("current_password") or ""

    errors: list[str] = []
    cutoff = None
    try:
        cutoff = datetime.strptime(cutoff_raw, "%Y-%m-%d")
    except ValueError:
        errors.append("วันที่ไม่ถูกต้อง (ต้องเป็นรูปแบบ ปี-เดือน-วัน)")
    if cutoff is not None:
        days = _scrub_floor_days()
        now = datetime.now()
        if cutoff > now:
            errors.append("วันที่ต้องไม่อยู่ในอนาคต")
        elif cutoff > now - timedelta(days=days):
            errors.append(f"ล้างได้เฉพาะแถวที่เก่ากว่า {days} วัน -- เลือกวันที่ก่อน "
                          f"{(now - timedelta(days=days)):%d/%m/%Y}")
    if len(reason) < 10:
        errors.append("ต้องระบุเหตุผลอย่างน้อย 10 ตัวอักษร")
    row = core.query_one("SELECT password_hash FROM staff WHERE id = %s", (session["staff_id"],))
    if not row or not crypto.verify_password(row["password_hash"], current):
        core.record_attempt(bucket)
        errors.append("รหัสผ่านบัญชีแอดมินไม่ถูกต้อง")
    if errors:
        for e in errors:
            flash(e, "err")
        return redirect(url_for("audit_log_page"))

    sid, ip = session["staff_id"], g.client_ip
    audit.log_required(audit.AUDIT_SCRUB, staff_id=sid, client_ip=ip,
                       detail=f"เริ่ม cutoff={cutoff:%Y-%m-%d} เหตุผล: {reason}")
    changed = scanned = last_id = 0
    while True:
        batch = core.query_all(
            "SELECT id, target, detail FROM audit_log WHERE ts < %s AND id > %s "
            "ORDER BY id LIMIT %s", (cutoff, last_id, SCRUB_BATCH))
        if not batch:
            break
        for r in batch:
            new_t, new_d = scrub_text(r["target"]), scrub_text(r["detail"])
            if new_t != r["target"] or new_d != r["detail"]:
                core.execute("UPDATE audit_log SET target = %s, detail = %s WHERE id = %s",
                             (new_t, new_d, r["id"]))
                changed += 1
        scanned += len(batch)
        last_id = batch[-1]["id"]
        if len(batch) < SCRUB_BATCH:
            break
    audit.log_required(audit.AUDIT_SCRUB, staff_id=sid, client_ip=ip,
                       detail=f"เสร็จ cutoff={cutoff:%Y-%m-%d} ตรวจ={scanned} แก้={changed} เหตุผล: {reason}")
    flash(f"ล้างข้อมูลลูกค้าใน audit แล้ว {changed} แถว (ตรวจ {scanned} แถว)", "success")
    return redirect(url_for("audit_log_page"))
