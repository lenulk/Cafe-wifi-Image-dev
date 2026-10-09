---
name: report-full-review-2026-10-09
description: "ตรวจเล่มฉบับขยายทั้งเล่มด้วยทีม Sonnet/Haiku (2026-10-09) — สิ่งที่แก้ตามข้อเท็จจริงในโค้ด, แจ้งเตือนผิดที่ไม่ต้องแก้, เรื่องที่ยังค้าง"
metadata:
  node_type: memory
  type: project
  originSessionId: f2ed9da0-38d0-46a7-8dde-5832bd15b718
  modified: 2026-10-09T03:33:09.174Z
---

2026-10-09 ตรวจทั้งเล่ม (ฉบับขยาย, 97 หน้า) ด้วย Sonnet 2 (ข้อเท็จจริง) + Haiku 3 (คำผิด/อ้างอิงข้าม) แล้ว Opus ตรวจซ้ำกับโค้ดทุกข้อ
แก้แล้ว 20 จุด (36 edits) — ข้อเท็จจริงจากโค้ดที่เล่มเคยเขียนผิด:
- บล็อกลูกค้าทำได้เฉพาะ admin (`customers.py:87-89 admin_required`) — ตาราง 3-6 แยกแถว /customers/<id>/block
- เลขบัตรถูกถอดรหัสทุกครั้งที่อนุมัติ (เทียบ 4 ตัวท้าย `access.py:97`) ไม่ใช่ "เฉพาะเมื่อจำเป็นตามกฎหมาย"
- คำขอที่ปฏิเสธ/หมดอายุ: ล้างแค่ natid_hash/natid_enc ทันที แถวลบตอนครบอายุเก็บ (`purge_old_data.py:135`)
- T3 ยังไม่ได้วัดอัตรา 10 ครั้ง/OS · IMG-04 = รันซ้ำหลังถูกขัดจังหวะ (ไม่ใช่ถอดไฟจริง) · 29 วิ บูต วัด ก.ย. กับ install.sh
- ช่วงเฝ้าดู 25.5 ชม. ยังมี log_gap (ก่อนแก้ N41/N45) · conntrack 488 ตอนลูกค้า 2 เครื่อง · T5 วัดกับขั้นตอนรหัสผ่านรุ่นก่อน
แจ้งเตือนผิดที่ไม่ต้องแก้: ปก "Authenticationand" (= ขึ้นบรรทัด), "&lt;id&gt;" (XML escape, PDF แสดง <id>),
"Chairman of Project Advisor" (ตรงเล่มตัวอย่าง), เมนู "ค้นหา log" (ชื่อเมนูจริงใน base.html), ลีนิกซ์/ลีนุกซ์ คนละคน
unit test 538/538 บน Docker ยืนยันซ้ำ 2026-10-09 (Debian 13.7, Py 3.13.16, x86_64, commit af43981, 43.8 วิ) ผลดิบเก็บที่ `รายงานเล่ม/ข้อมูลทดสอบ/2026-10-09_unit-tests_docker-debian13-py313.txt` (ยังไม่ commit) — คัดลอกเฉพาะ app tests tools sql install.sh เข้า container (image/ 5.3 GB ไม่ต้องใช้)
docs/hardware-test-log.md §4 ยังเขียน 22 ชม./63.8–67.2°C (ต่างจากเล่มที่ใช้ CSV 25.5 ชม.) — เดสก์ท็อปไม่แตะ docs ตาม [[two-machine-workflow]]

**Why:** รอบหน้าไม่ต้องตรวจซ้ำเรื่องเดิม และไม่หลงแก้แจ้งเตือนผิด
**How to apply:** ตารางเส้นเวลา 1-1 ต้อง keep-together (มีลูกศรยึดในเซลล์ ห้ามแบ่ง) · ตรวจซ้ำด้วย tblcheck/toc2/listpages ใน %TEMP%\ex ดู [[report-language-pass-2026-10-06]]
