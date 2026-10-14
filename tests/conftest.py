"""ค่าตั้งต้นสำหรับการทดสอบ — ใช้กุญแจปลอม ไม่แตะ secrets.env ของจริง"""
import os
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))  # ให้ import `tools.xxx` (อยู่ที่รากรีโป ไม่ใช่ใต้ app/) ได้ด้วย

os.environ.setdefault("NATID_PEPPER", "aa" * 32)
os.environ.setdefault("NATID_DEK", "bb" * 32)
os.environ.setdefault("SECRET_KEY", "cc" * 32)
os.environ.setdefault("GATEWAY_NAME", "Cafe-Guest-Test")
# DB จำลองของแต่ละไฟล์เทสต์ไม่รู้จักตาราง rate_attempt -- ใช้ตัวนับในหน่วยความจำ (ตัวนับแบบ DB มีเทสต์แยก)
os.environ.setdefault("RATE_LIMIT_BACKEND", "memory")

import contextlib
import time

import pytest


@pytest.fixture(autouse=True)
def _session_login_at(monkeypatch):
    """A1: Admin ถือ session หมดอายุสัมบูรณ์จาก session["login_at"] (ไม่มี = หมดอายุ)
    เทสต์ที่ยัด session["staff_id"] ตรง ๆ ผ่าน session_transaction ไม่ได้ผ่านหน้า login -- เติม login_at ให้
    อัตโนมัติเมื่อไม่ได้ระบุ · เทสต์ที่ต้องการ session ไม่มี login_at ตั้ง client._no_login_at = True"""
    from flask.testing import FlaskClient
    orig = FlaskClient.session_transaction

    @contextlib.contextmanager
    def wrapped(self, *a, **kw):
        with orig(self, *a, **kw) as sess:
            yield sess
            if (sess.get("staff_id") and "login_at" not in sess
                    and not getattr(self, "_no_login_at", False)):
                sess["login_at"] = int(time.time())

    monkeypatch.setattr(FlaskClient, "session_transaction", wrapped)
