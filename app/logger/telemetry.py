"""สถานะ collector แบบไฟล์ขนาดเล็ก เพื่อให้หน้า Admin ตรวจความคืบหน้าได้แม้ DB ล่ม."""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path

log = logging.getLogger("cafe-wifi.telemetry")


class CollectorTelemetry:
    def __init__(self, name: str, directory: str | os.PathLike | None = None):
        if name not in {"conn", "dns"}:
            raise ValueError(name)
        self.path = Path(directory or os.environ.get("LOG_DIR", "/var/log/cafe-wifi")) / f"collector-{name}.json"
        self.name = name
        self.received = self.written = self.dropped = self.unmapped = 0
        self.last_event_at = self.last_write_at = None
        self.last_error = None
        self._last_heartbeat = 0.0

    def previous_heartbeat(self) -> str | None:
        """R2-06: heartbeat ล่าสุดของรอบก่อน (อ่านก่อนเขียนทับ) = จุดที่ collector เงียบไป"""
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))["heartbeat_at"]
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def event(self) -> None:
        self.received += 1
        self.last_event_at = datetime.now().isoformat()

    def write(self, count: int) -> None:
        self.written += count
        if count:
            self.last_write_at = datetime.now().isoformat()
            self.last_error = None

    def drop(self, count: int) -> None:
        self.dropped += count
        self.last_error = f"ทิ้ง {count} เหตุการณ์ล่าสุด"

    def missing_mac(self, count: int) -> None:
        self.unmapped += count

    def error(self, detail: str) -> None:
        self.last_error = detail[:200]

    def heartbeat(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_heartbeat < 5:
            return
        self._last_heartbeat = now
        data = dict(name=self.name, heartbeat_at=datetime.now().isoformat(),
                    received=self.received, written=self.written, dropped=self.dropped,
                    unmapped=self.unmapped, last_event_at=self.last_event_at,
                    last_write_at=self.last_write_at, last_error=self.last_error)
        tmp = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        try:
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, self.path)
        except OSError as exc:
            log.warning("บันทึกสถานะ %s ไม่สำเร็จ: %s", self.name, exc)


def read_collector_status(directory: str | os.PathLike,
                          now: datetime | None = None) -> dict[str, dict]:
    now = now or datetime.now()
    result = {}
    for name in ("conn", "dns"):
        path = Path(directory) / f"collector-{name}.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            age = (now - datetime.fromisoformat(data["heartbeat_at"])).total_seconds()
            data["healthy"] = 0 <= age <= 20
            data["age_seconds"] = int(age)
        except (OSError, ValueError, KeyError, TypeError):
            data = dict(name=name, healthy=False, age_seconds=None,
                        received=0, written=0, dropped=0, unmapped=0,
                        last_write_at=None, last_error="ยังไม่พบ heartbeat")
        result[name] = data
    return result


class GapLedger:
    """
    ตัวนับเหตุการณ์ที่ทิ้ง/หายของ collector ที่ทนต่อ cooldown และ DB ล่ม

    เดิมจำนวนที่ทิ้งไปอยู่แค่ใน log ไฟล์/telemetry (หายตอน restart) และ audit LOG_GAP ถูกจำกัดที่
    1 แถวต่อ 300 วินาทีโดย "ทิ้ง" เหตุการณ์ที่ซ้ำในช่วงนั้นทั้งดุ้น ตอนนี้สะสมตัวเลขไว้ในหน่วยความจำ
    เขียนรวมเป็น `dropped=<n>` เมื่อพ้น cooldown / ตอนปิดตัวปกติ และถ้าเขียนไม่สำเร็จ (DB ล่ม)
    ตัวเลขยังอยู่ให้เขียนรอบหน้า -- ห้ามหายเงียบ
    """

    def __init__(self, target: str, cooldown: float = 300.0, clock=time.monotonic):
        self.target = target
        self.cooldown = cooldown
        self._clock = clock
        self._lock = threading.Lock()
        self._dropped = 0     # จำนวนที่รู้แน่ (ขอบล่าง) -- ENOBUFS ไม่บอกจำนวนจึงนับเป็น incident
        self._incidents = 0
        self._reasons: list[str] = []
        self._last_write: float | None = None

    @property
    def pending(self) -> int:
        return self._dropped + self._incidents

    def add(self, dropped: int, reason: str) -> None:
        with self._lock:
            self._dropped += dropped
            self._incidents += 1
            if reason and reason not in self._reasons and len(self._reasons) < 5:
                self._reasons.append(reason)
        self.flush()

    def flush(self, force: bool = False) -> bool:
        """เขียนยอดสะสมลง audit_log ถ้าพ้น cooldown (หรือ force) -- คืน True ถ้าเขียนแล้ว"""
        with self._lock:
            if not (self._dropped or self._incidents):
                return False
            now = self._clock()
            if not force and self._last_write is not None and now - self._last_write < self.cooldown:
                return False
            reason = "; ".join(self._reasons)
            detail = f"dropped={self._dropped} incidents={self._incidents} reason={reason}"
            try:
                from common import audit
                audit.log_required(audit.LOG_GAP, target=self.target, detail=detail[:200])
            except Exception:
                log.exception("บันทึก audit_log LOG_GAP ของ %s ไม่สำเร็จ — เก็บยอดไว้เขียนรอบหน้า",
                              self.target)
                self._last_write = now  # DB ล่ม: อย่าไล่เชื่อมต่อทุกลูป รอ cooldown
                return False
            self._dropped = self._incidents = 0
            self._reasons = []
            self._last_write = now
            return True


class FlushBackoff:
    """หน่วงการ flush ซ้ำหลังเขียน DB ล้มเหลว: min(60, 2**ครั้งที่ล้ม) วินาที, รีเซ็ตเมื่อสำเร็จ
    (เดิม DB ล่ม + buffer >= batch_size = ต่อ/log.exception ทุกบรรทัดที่อ่านเข้ามา)"""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self.failures = 0
        self._not_before = 0.0

    def ready(self) -> bool:
        return self._clock() >= self._not_before

    def failed(self) -> None:
        self.failures += 1
        self._not_before = self._clock() + min(60, 2 ** self.failures)

    def ok(self) -> None:
        self.failures = 0
        self._not_before = 0.0
