---
name: admin-sees-everything-unmasked
description: "Admin dashboard intentionally shows everything unmasked (full natid etc.); only staff gets masked — don't flag admin visibility as a leak"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 5d3fd741-97ba-4504-a0b7-ff3d7e36894a
  modified: 2026-10-13T18:03:07.833Z
---

ผู้ใช้ย้ำ (2026-10-14): หน้าแดชบอร์ดของ **admin ดูได้หมด ไม่ปิดบัง** — เลขบัตรเต็ม, ข้อมูลลูกค้าทุกคน
การปิดบัง (masked) ใช้กับ role `staff` เท่านั้น (ทุกการเปิดดูของ admin ยังลง audit ตามเดิม)

**Why:** เป็นการตัดสินใจออกแบบที่ผู้ใช้ยอมรับแล้ว ไม่ใช่ช่องโหว่ — รีวิวโค้ดที่ทักว่า "admin เห็นข้อมูลเต็ม" ถือเป็นแจ้งเตือนผิด

**How to apply:** เวลารีวิว/ตอบผลรีวิว อย่าเสนอให้ปิดบังข้อมูลฝั่ง admin หรือนับเป็นปัญหา PDPA
แต่ปัญหา "จับคู่ log ผิดคน" (attribution) ยังเป็นบั๊กจริงแม้ฝั่ง admin เพราะทำให้หลักฐานไม่ตรงกับ /logs และ export
(ดู R2-10 ใน common/log_mapping.py) · เกี่ยวกับ [[log-search-upgrade-2026-10-12]], [[customer-self-registration-decision]]
