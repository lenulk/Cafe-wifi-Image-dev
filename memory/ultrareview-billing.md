---
name: ultrareview-billing
description: "/code-review ultra had 3 free runs (all used 2026-10-14); after that it needs \"usage credits\" — the \"Cloud session credits $100\" do NOT pay for it"
metadata:
  node_type: memory
  type: reference
  originSessionId: 5d3fd741-97ba-4504-a0b7-ff3d7e36894a
  modified: 2026-10-13T19:39:35.997Z
---

- 2026-10-14 ใช้ ultrareview ฟรีครบ 3/3 แล้ว (รีวิวโค้ด log search/logger 3 รอบ)
- ครั้งที่ 4 ระบบตอบ "Free ultrareviews used. Turn on usage credits" แล้ว "Usage credits exhausted. Top up"
  → https://claude.ai/settings/usage — **เครดิต "Cloud session credits $100" (หมดอายุ 5 พ.ย.) ใช้จ่าย ultrareview ไม่ได้**
  และยอด $100 ไม่ลดเลยตลอด 3 รอบฟรี
- ultrareview รีวิวได้แค่ diff ≤ 8,000 บรรทัด / 500 ไฟล์ และไม่สน path ที่ใส่ — ต้องใช้ branch ฐานที่ใกล้กว่า
  (ทำ branch ชั่วคราวจาก commit ก่อนงาน แล้ว checkout เฉพาะโฟลเดอร์โค้ดมา commit) · ถ้าจะรีวิวทั้งก้อน
  ให้ทำ branch ฐานที่ลบโฟลเดอร์นั้นทิ้ง
- ทางเลือกไม่เสียเงิน: `/code-review high` ในเครื่อง หรือรีวิวแบบแบ่งทีม (Sonnet หา, Opus ตรวจซ้ำ) ตาม [[model-routing-preference]]
