---
name: model-routing-preference
description: "User wants Sonnet/Haiku subagents for simple/bulk work to save tokens; Opus only orchestrates, reviews, does hard parts"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 944b2b79-d0b8-4298-a787-6dbb42e38b35
  modified: 2026-10-13T16:26:12.491Z
---

ใช้ subagent model sonnet / haiku ทำงานง่ายหรืองานปริมาณมาก (ร่างเนื้อหาจากเอกสารที่มีอยู่, สแกนหาข้อมูลลับ, ตรวจซ้ำ) — Opus เป็นคนสั่งงาน คุมงาน และทำส่วนที่ยาก (ออกแบบโครง, แผนภาพ, ตรวจทานขั้นสุดท้าย)

**Why:** ผู้ใช้สั่งชัดเจน 2026-10-13 ระหว่างทำคู่มือสาธารณะ — ต้องการลดการใช้โทเคน
**How to apply:** งานหลายส่วนที่ขนานกันได้ → spawn Agent model=sonnet (เนื้อหา) / haiku (สแกน/เช็กลิสต์) พร้อม prompt ครบในตัว; Opus อ่านผลแบบย่อแล้วตรวจ ไม่ต้องอ่านไฟล์ต้นทางทั้งหมดเอง ดู [[report-full-review-2026-10-09]]
