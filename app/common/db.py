"""common/db.py — ตัวช่วยเชื่อมต่อ MariaDB (PyMySQL, ไม่ต้องคอมไพล์)"""
from __future__ import annotations

import os
from contextlib import contextmanager

import pymysql
from pymysql.cursors import DictCursor


def _env_int(name: str, default: int) -> int:
    try:
        v = int(os.environ.get(name, ""))
        return v if v > 0 else default
    except ValueError:
        return default


def _cfg() -> dict:
    return dict(
        host=os.environ.get("DB_HOST", "127.0.0.1"),
        port=int(os.environ.get("DB_PORT", "3306")),
        user=os.environ.get("DB_USER", "cafewifi"),
        password=os.environ.get("DB_PASS", ""),
        database=os.environ.get("DB_NAME", "cafewifi"),
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=False,
        # ไม่มี timeout = DB ค้าง/เครือข่ายหลุดแล้ว request (หรือ collector) แขวนตลอดไป
        # read 600 วิ: purge DELETE หลายล้านแถว/export/backup บน Pi ใช้เวลานานจริง -- กันแค่ "แขวนตลอดไป"
        # (หน้าเว็บถูกตัดที่ gunicorn --timeout 60 อยู่แล้ว) ปรับได้ทาง env หรือ get_conn(read_timeout=...)
        connect_timeout=_env_int("DB_CONNECT_TIMEOUT", 5),
        read_timeout=_env_int("DB_READ_TIMEOUT", 600),
        write_timeout=_env_int("DB_WRITE_TIMEOUT", 60),
    )


@contextmanager
def get_conn(**overrides):
    """overrides: ทับค่าจาก _cfg() เช่น read_timeout=300 สำหรับงานที่คิวรี่นานจริง"""
    conn = pymysql.connect(**{**_cfg(), **overrides})
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def query_one(sql: str, args: tuple = (), **conn_overrides) -> dict | None:
    with get_conn(**conn_overrides) as c, c.cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchone()


def query_all(sql: str, args: tuple = (), **conn_overrides) -> list[dict]:
    with get_conn(**conn_overrides) as c, c.cursor() as cur:
        cur.execute(sql, args)
        return list(cur.fetchall())


def execute(sql: str, args: tuple = (), **conn_overrides) -> int:
    """
    รันคำสั่งที่ไม่คืนแถว (INSERT/UPDATE/DELETE) คืนค่า rowcount (จำนวนแถวที่ถูกกระทบ)

    บั๊กเดิม: เคยคืน cur.lastrowid ซึ่งมีความหมายเฉพาะ INSERT ตาราง AUTO_INCREMENT เท่านั้น
    -- UPDATE/DELETE จะได้ 0 เสมอไม่ว่าจะกระทบกี่แถวจริง ผู้เรียกที่ต้องการเช็คว่า "แถวที่
    ต้องการอัปเดตมีอยู่จริงไหม" (เช่น `if not execute("UPDATE ... WHERE id=%s", (id,)):
    abort(404)`) จะเจอ False positive เสมอ ทั้งที่ UPDATE สำเร็จจริง -- ไม่มีผู้เรียกเดิมใน
    โปรเจกต์นี้ที่พึ่ง lastrowid จริงจัง (ทุกจุดเดิมไม่ได้ใช้ค่าที่คืนมาเลย) จึงเปลี่ยนเป็น
    rowcount ได้อย่างปลอดภัย และตรงกับความหมายที่ผู้เรียกส่วนใหญ่ต้องการมากกว่า
    """
    with get_conn(**conn_overrides) as c, c.cursor() as cur:
        cur.execute(sql, args)
        return cur.rowcount
