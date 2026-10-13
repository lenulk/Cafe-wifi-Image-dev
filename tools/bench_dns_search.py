"""
tools/bench_dns_search.py — วัดความเร็วค้นโดเมนใน dns_log: วิธีเดิม vs วิธีใหม่ (qname_rev)

รัน "บน Pi" กับ MariaDB จริง -- ไม่เขียนลง dns_log จริงเด็ดขาด ใช้ตารางสำเนา dns_log_bench เท่านั้น

  (a) เดิม : qname LIKE '%x%'  AND ts BETWEEN (31 วัน)       -- ใช้ดัชนีไม่ได้ ต้องสแกน
  (b) ใหม่ : domain_condition() = (qname = x OR qname_rev LIKE 'rev(.x)%') AND ts BETWEEN

ตัวอย่าง (จากรากโปรเจกต์ ใช้ venv ของแอป และ DB_* จาก env หรือ /etc/cafe-wifi/secrets.env):
  python -m tools.bench_dns_search --seed 1000000      # สร้าง dns_log_bench + ใส่แถวสังเคราะห์ + วัด
  python -m tools.bench_dns_search                     # วัดซ้ำกับตารางที่มีอยู่
  python -m tools.bench_dns_search --cleanup           # DROP dns_log_bench

หมายเหตุ: (a) นับแบบ substring ส่วน (b) นับ "โดเมนนั้นหรือซับโดเมน" จำนวนแถวจึงต่างกันได้เล็กน้อย
"""
from __future__ import annotations

import argparse
import os
import random
import statistics
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))

BENCH = "dns_log_bench"
RUNS = 5
SEED_DAYS = 30
BATCH = 5000

# โดเมนยอดนิยม (น้ำหนักสูง) + ซับโดเมนทั่วไป -- ที่เหลือเป็น long tail สุ่มสร้าง
POPULAR = ["google.com", "facebook.com", "line.me", "tiktok.com", "youtube.com", "instagram.com",
           "apple.com", "microsoft.com", "shopee.co.th", "lazada.co.th", "netflix.com", "x.com"]
SUBS = ["www", "api", "cdn", "static", "m", "graph", "edge", "play", "mail", "img"]
SEARCH_DOMAINS = ["google.com", "line.me", "shopee.co.th", "tiktok.com", "rare-site-0042.example.org"]


def load_env_file() -> None:
    """ถ้าไม่ได้ตั้ง DB_PASS ใน env ให้อ่านจาก /etc/cafe-wifi/secrets.env (ถ้าอ่านได้)"""
    if os.environ.get("DB_PASS"):
        return
    f = Path(os.environ.get("ETC_DIR", "/etc/cafe-wifi")) / "secrets.env"
    try:
        for line in f.read_text(encoding="utf-8").splitlines():
            k, sep, v = line.partition("=")
            if sep and k.strip() in ("DB_HOST", "DB_PORT", "DB_USER", "DB_PASS", "DB_NAME"):
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))
    except OSError:
        pass


def make_domains(n_tail: int = 3000) -> tuple[list[str], list[float]]:
    names, weights = [], []
    for i, d in enumerate(POPULAR):
        names.append(d)
        weights.append(1000.0 / (i + 1))
        for j, s in enumerate(SUBS[:6]):
            names.append(f"{s}.{d}")
            weights.append(1000.0 / (i + 1) / (j + 2))
    for i in range(n_tail):
        names.append(f"site-{i:04d}.example.{random.choice(['com', 'net', 'org', 'co.th'])}")
        weights.append(2.0 / (i + 1) ** 0.5)
    names.append("rare-site-0042.example.org")
    weights.append(0.5)
    return names, weights


def print_table(rows: list[tuple]) -> None:
    hdr = ("domain", "old ms", "new ms", "speedup", "old rows", "new rows")
    w = [max(len(str(r[i])) for r in [hdr] + rows) for i in range(len(hdr))]
    fmt = "  ".join("{:<%d}" % x for x in w)
    print(fmt.format(*hdr))
    print(fmt.format(*["-" * x for x in w]))
    for r in rows:
        print(fmt.format(*[str(c) for c in r]))


def ensure_bench_table(cur, recreate: bool) -> None:
    if recreate:
        cur.execute(f"DROP TABLE IF EXISTS {BENCH}")
    cur.execute(f"CREATE TABLE IF NOT EXISTS {BENCH} LIKE dns_log")
    # ถ้า dns_log ยังไม่ได้ใช้ migration 014 ให้เติมในตารางเบนช์เอง (ไม่แตะ dns_log จริง)
    t0 = time.perf_counter()
    cur.execute(f"ALTER TABLE {BENCH} "
                "ADD COLUMN IF NOT EXISTS qname_rev VARCHAR(255) AS (REVERSE(qname)) PERSISTENT, "
                "ADD INDEX IF NOT EXISTS idx_qname_rev (qname_rev)")
    print(f"[bench] เตรียมตาราง {BENCH} {time.perf_counter() - t0:.2f}s")


def seed(conn, n: int) -> None:
    names, weights = make_domains()
    now = datetime.now()
    start = now - timedelta(days=SEED_DAYS)
    span = SEED_DAYS * 86400
    sql = (f"INSERT INTO {BENCH} (ts, client_ip, mac, qname, qtype, answer, event_kind) "
           "VALUES (%s,%s,%s,%s,%s,%s,%s)")
    macs = [f"aa:bb:cc:00:{i // 256:02x}:{i % 256:02x}" for i in range(120)]
    t0 = time.perf_counter()
    done = 0
    with conn.cursor() as cur:
        while done < n:
            k = min(BATCH, n - done)
            qs = random.choices(names, weights=weights, k=k)
            rows = []
            for q in qs:
                ts = start + timedelta(seconds=random.random() * span)
                rows.append((ts, "10.10.0." + str(random.randint(2, 250)), random.choice(macs), q,
                             random.choice(["A", "A", "AAAA", "HTTPS"]), "93.184.216.34", "query"))
            cur.executemany(sql, rows)
            conn.commit()
            done += k
            if done % (BATCH * 20) == 0 or done == n:
                print(f"[bench] seed {done}/{n}  {time.perf_counter() - t0:.1f}s")
    with conn.cursor() as cur:
        cur.execute(f"ANALYZE TABLE {BENCH}")
        cur.fetchall()


def timed(conn, sql: str, args: list) -> tuple[float, int]:
    ms = []
    cnt = 0
    for _ in range(RUNS):
        with conn.cursor() as cur:
            t0 = time.perf_counter()
            cur.execute(sql, args)
            cnt = cur.fetchone()["c"]
            ms.append((time.perf_counter() - t0) * 1000)
    return statistics.median(ms), cnt


def explain(conn, sql: str, args: list) -> None:
    with conn.cursor() as cur:
        cur.execute("EXPLAIN " + sql, args)
        for r in cur.fetchall():
            print(f"    type={r.get('type')} key={r.get('key')} rows={r.get('rows')} "
                  f"filtered={r.get('filtered')} extra={r.get('Extra')}")


def run_bench(conn) -> None:
    from common.domain_match import domain_condition

    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) AS c FROM {BENCH}")
        total = cur.fetchone()["c"]
    print(f"[bench] ตาราง {BENCH}: {total} แถว  (median ของ {RUNS} รอบ, ช่วง ts 31 วัน)\n")
    if not total:
        print("ตารางว่าง -- รันด้วย --seed N ก่อน")
        return
    t_to = datetime.now()
    t_from = t_to - timedelta(days=31)
    out = []
    for dom in SEARCH_DOMAINS:
        old_sql = f"SELECT COUNT(*) AS c FROM {BENCH} dl WHERE dl.qname LIKE %s AND dl.ts BETWEEN %s AND %s"
        old_args = ["%" + dom + "%", t_from, t_to]
        cond, cargs = domain_condition("dl", dom)
        new_sql = f"SELECT COUNT(*) AS c FROM {BENCH} dl WHERE {cond} AND dl.ts BETWEEN %s AND %s"
        new_args = cargs + [t_from, t_to]
        print(f"== {dom}")
        print("  EXPLAIN เดิม:")
        explain(conn, old_sql, old_args)
        print("  EXPLAIN ใหม่:")
        explain(conn, new_sql, new_args)
        mo, co = timed(conn, old_sql, old_args)
        mn, cn = timed(conn, new_sql, new_args)
        out.append((dom, f"{mo:.1f}", f"{mn:.1f}", f"{mo / mn:.1f}x" if mn else "-", co, cn))
    print("\n== สรุป ==")
    print_table(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, metavar="N", help="สร้างตาราง dns_log_bench ใหม่ + ใส่ N แถวสังเคราะห์")
    ap.add_argument("--cleanup", action="store_true", help=f"DROP TABLE {BENCH} แล้วจบ")
    a = ap.parse_args()

    load_env_file()
    try:
        from common.db import get_conn
        ctx = get_conn()
        conn = ctx.__enter__()
    except Exception as exc:  # noqa: BLE001
        print(f"เชื่อมต่อ MariaDB/MySQL ไม่ได้: {exc}\n"
              "(ตั้ง DB_HOST/DB_USER/DB_PASS/DB_NAME หรือรันบน Pi ที่มี /etc/cafe-wifi/secrets.env)",
              file=sys.stderr)
        return 2
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT VERSION() AS v")
            ver = cur.fetchone()["v"]
        print(f"[bench] เซิร์ฟเวอร์ {ver}  ฐานข้อมูล {os.environ.get('DB_NAME', 'cafewifi')}")
        if a.cleanup:
            with conn.cursor() as cur:
                cur.execute(f"DROP TABLE IF EXISTS {BENCH}")
            conn.commit()
            print(f"[bench] ลบ {BENCH} แล้ว")
            return 0
        with conn.cursor() as cur:
            ensure_bench_table(cur, recreate=bool(a.seed))
        conn.commit()
        if a.seed:
            seed(conn, a.seed)
        run_bench(conn)
        return 0
    finally:
        try:
            ctx.__exit__(None, None, None)
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    raise SystemExit(main())
