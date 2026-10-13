---
name: log-search-upgrade-2026-10-12
description: "12 ต.ค. อัปเกรดหน้าค้นหา log (autocomplete, เลขเต็มเฉพาะ admin, site/port/CIDR, /logs/summary, /audit, sql 014/015) — ยังไม่ commit และยังไม่ทดสอบบน Pi"
metadata:
  node_type: memory
  type: project
  originSessionId: 6f59361a-78b0-40bb-bcdd-48416e093d88
  modified: 2026-10-11T21:39:26.712Z
---

งานบน branch `image` (ยังไม่ commit ณ 2026-10-12) ผ่านเทสต์ 645 ตัว ส่วน 10 ตัวที่พังเป็นปัญหาเฉพาะ Windows ที่พังตั้งแต่ HEAD เดิมอยู่แล้ว
(backup_db 4, logger rotated 1, logger_restart 4, sysinfo speed 1) **ไม่ต้องไล่แก้**

การตัดสินใจของเจ้าของ:
- admin เห็นเลขบัตรเต็มในตาราง log, CSV, รายการแนะนำ และหน้าสรุป
- staff เห็นแบบ masked เสมอ
- autocomplete ของ admin จับคู่จากเลขเต็มที่ถอดรหัส
- staff จับคู่ได้เฉพาะหลักที่เห็น (1–5 และหลักสุดท้าย) เพื่อกันการเดาเลขเต็มทีละหลัก

**Why:** PDPA — ทุกการถอดรหัสต้องลง audit (`suggest_natid`, `view_natid_log`, EXPORT_LOG detail `natid_full=n`) โดยห้ามลงตัวเลขที่พิมพ์
เลขเต็มต้องไม่ไปอยู่ใน URL: ตอนเลือกลูกค้าให้ส่ง q=masked + `cid`

**How to apply:** ยังต้องทดสอบบน Pi จริงตามรายการด้านล่าง
1. รัน migration 015 **ก่อน** restart cafe-logger เพราะ INSERT dst_name จะล้มถ้ายังไม่มีคอลัมน์
2. วัด `tools/bench_dns_search.py` (C7 qname_rev) และวัดเวลา ALTER 014 จริง ตัวเลข "1–3 นาที/ล้านแถว" ยังเป็นการเดา
3. C8 lookup ค้นจาก dns_log.answer ซึ่ง**ไม่มี index** (ใช้ idx_ts ย้อนสูงสุด 6 ชม./batch) ต้องดูว่าโหลดหนักแล้ว batch ช้าลงหรือไม่
4. เปิดหน้า /logs ใน browser ดู dropdown ของ autocomplete (JS ยังไม่เคยรันจริง เครื่องนี้ไม่มี node)
