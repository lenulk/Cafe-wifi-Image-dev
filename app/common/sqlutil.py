"""common/sqlutil.py — ตัวช่วยเล็ก ๆ ที่หน้า log หลายหน้าใช้ร่วมกัน"""
from __future__ import annotations

import logging
import re
import time


def like_escape(s: str) -> str:
    """escape ตัวแทน LIKE (% _) และเครื่องหมาย \\ ให้เป็นตัวอักษรธรรมดา (MySQL ใช้ \\ เป็น escape ตั้งต้น)"""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def format_natid(nid: str) -> str:
    """1234567890123 -> '1-2345-67890-12-3' (รูปแบบเลขบัตรไทย) · ไม่ใช่ 13 หลักคืนค่าเดิม"""
    d = re.sub(r"\D", "", nid or "")
    if len(d) != 13:
        return nid
    return f"{d[0]}-{d[1:5]}-{d[5:10]}-{d[10:12]}-{d[12]}"


# ---------------------------------------------------------------- ตรวจคอลัมน์ที่มาจาก migration
# Pi บางตัวอาจยังไม่รัน migration -- เจอแล้วจำตลอด · ไม่เจอ/error เช็กใหม่ทุก recheck วินาที (รัน migration ทีหลังได้โดยไม่ต้อง restart)
COLUMN_STATE: dict = {}  # (table, column) -> {"ok": bool, "checked": monotonic | None}
_log = logging.getLogger(__name__)


def has_column(fetch_count, table: str, column: str, recheck: float = 300.0, state: dict | None = None) -> bool:
    """fetch_count(sql, args) -> จำนวนแถวที่เจอ · state = dict {"ok","checked"} ของผู้เรียกเอง (ไม่ใส่ = ใช้ COLUMN_STATE)"""
    st = state if state is not None else COLUMN_STATE.setdefault((table, column), {"ok": False, "checked": None})
    if st["ok"]:
        return True
    now = time.monotonic()
    if st["checked"] is not None and now - st["checked"] < recheck:
        return False
    st["checked"] = now
    try:
        st["ok"] = bool(fetch_count(
            "SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() "
            "AND TABLE_NAME = %s AND COLUMN_NAME = %s", (table, column)))
    except Exception:  # noqa: BLE001
        _log.warning("เช็กคอลัมน์ %s.%s ไม่สำเร็จ -- ถือว่ายังไม่มี", table, column, exc_info=True)
        return False
    if not st["ok"]:
        _log.warning("%s ยังไม่มีคอลัมน์ %s -- รัน migration ที่เกี่ยวข้อง", table, column)
    return st["ok"]
