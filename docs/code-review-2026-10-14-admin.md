# รีวิวโค้ด — Admin dashboard (ส่วนที่ไม่ใช่หน้า log) (14 ต.ค. 2026)

ขอบเขต: `app/admin/app.py`, `routes.py`, `views/{staff,keys,audit_view,access,customers,overview}.py` + template ที่เกี่ยวข้อง
ทีม: Sonnet 2 ตัว (A = auth/staff/keys/audit, B = access/customers/overview) อ่านอย่างเดียว → Opus ตรวจซ้ำข้อหลักกับโค้ด
ยกเว้นตามการออกแบบ: แอดมินเห็นทุกอย่างไม่ปิดบัง, Admin เปิดให้วงลูกค้า, Pi ตัวเดียวสายเดียว, เลขบัตรผ่าน HTTP

**ภาพรวม:** ไม่พบช่องที่ staff ขึ้นเป็น admin, ไม่มี route ขาด guard, CSRF ครบทุก POST, SQL parameterized ทั้งหมด,
ไม่มี `|safe`, approve ซ้ำ/พร้อมกันไม่ออก voucher ซ้ำ, อนุมัติผูก MAC/IP จากคำขอที่ FAS บันทึก (ไม่รับจากฟอร์ม)

## สูง

| # | ที่ | ปัญหา | สถานะ |
|---|---|---|---|
| B1 | `views/customers.py:243-244` | ไฟล์ CSV ในซิปหลักฐานมี BOM นำหน้า แต่ `manifest.json` คิด SHA-256 จากเนื้อหาไม่รวม BOM — README สั่งให้เจ้าหน้าที่ `sha256sum` ไฟล์ .csv แล้วเทียบ → **ไม่ตรงทุกครั้ง** หลักฐานดูเหมือนถูกแก้ · เทสต์ไม่เจอเพราะ `lstrip` BOM ก่อนคิด hash | ยืนยัน (Opus อ่านโค้ดแล้ว) · ทดสอบในเครื่องได้ |

## กลาง

| # | ที่ | ปัญหา | สถานะ |
|---|---|---|---|
| A1 | `app.py:44` | session ต่ออายุ 8 ชม. ทุก request — หน้า /requests (reload 5 วิ) หรือ /status (poll 10 วิ) ค้างไว้ = ไม่หมดอายุเลย · logout แค่ล้าง cookie ฝั่งเบราว์เซอร์ | ยืนยัน · ทดสอบในเครื่องได้ (เพดานเวลาสัมบูรณ์) |
| A2 | `app.py:195`, `:311` | คนไม่ล็อกอินเขียน `audit_log` ได้ไม่จำกัด (POST ไม่มี token → CSRF_REJECT, /login ที่ถูก rate limit ยังเขียน LOGIN_FAIL ทุกครั้ง) · audit ไม่ถูก purge → SD เต็มได้ และแถวจริงจมหาย | ยืนยัน · ทดสอบในเครื่องได้ |
| B5 | `views/access.py:238`, `common/customer.py:375` | คำขอที่ reject/expire เหลือ `natid_masked`, hostname, user_agent จนถึง purge 180 วัน และ `anonymize_customer` หาแถวพวกนี้ไม่เจอ (natid_hash = NULL, ไม่มี voucher) | ยืนยัน · ทดสอบในเครื่องได้ |
| B6 | `views/customers.py:87-102` | block/unblock: audit แบบกลืน error และอยู่นอก transaction · เป็น toggle (แอดมิน 2 คนกดสวนกัน = พลิกกลับ) · ไม่ตั้ง `auth_sync_needed` (หลุดช้าสูงสุด 5 นาที) · ต่อเวลาให้ลูกค้าที่ถูกระงับได้ | ยืนยัน · ทดสอบในเครื่องได้ |
| B2 | `views/access.py:138` | อนุมัติ MAC ที่ auth อยู่แล้วใน openNDS → `ndsctl auth` ซ้ำไม่ได้ → หมด 180 วิแล้ว deauth = voucher ออกแล้ว นาฬิกาเดิน แต่ลูกค้าไม่มีเน็ต และเครื่องเดิมถูกตัด | น่าจะจริง · **ต้องลองบน Pi** |
| B3 | `views/access.py:156` | ndsctl ล้ม/reconcile ค้าง/IP เปลี่ยน → จบที่ `auth_timeout` แต่หน้า /requests ยังแสดง "อนุมัติ" พนักงานไม่รู้ | ยืนยันเส้นทาง · **ต้องลองบน Pi** (การแสดงผลแก้ในเครื่องได้) |
| B4 | `views/customers.py:214-247` | /evidence ดึง conn+dns ทั้งช่วงเข้า RAM (สูงสุด 186 วันต่อคน) ไม่มี LIMIT/สตรีม · gunicorn `--workers 1 --timeout 60` เกิน = Admin ล่มทั้งตัว | ยืนยัน · **ต้องวัดปริมาณจริงบน Pi** |
| B7 | `views/overview.py:74` | `/status/live` เรียก `getaddrinfo` ไม่มี timeout + HTTP 3 วิ · เน็ตล่ม + เปิดหลายแท็บ = กิน thread ครบ 4 ตัว หน้าอนุมัติค้าง | น่าจะจริง · **ต้องลองบน Pi** (ถอดสาย WAN) |

## ต่ำ

- A3 `app.py:310` ล็อกชื่อ "admin" จากวงลูกค้าได้ (10 ครั้ง/10 นาที ต่อชื่อ ไม่ผูก IP) — trade-off ที่เขียนไว้แล้ว · ในเครื่องได้
- A4 `app.py:321` ไม่มีชื่อ/บัญชีปิด = ข้าม argon2 ตอบเร็วกว่า → เดาชื่อพนักงานจากเวลาได้ · ในเครื่องได้
- A5 `/setup` ไม่ตรวจ `isascii()` ชื่อผู้ใช้, ไม่ตัด display_name 128 ตัว, หน้า 503 บอก path ไฟล์ token · ในเครื่องได้
- A6 รหัสชั่วคราวไม่หมดอายุ (แอดมินที่เห็นรหัสล็อกอินแทนพนักงานได้ก่อนเจ้าตัว) · reset-password ใส่บัญชีที่ปิดได้ · ในเครื่องได้
- A7 แอดมิน 2 คนปิด/ลด role กันพร้อมกัน → deadlock 500 (ปลอดภัย ไม่เหลือ admin 0) · สร้างชื่อซ้ำพร้อมกัน → IntegrityError 500 · ต้อง MariaDB จริง
- A8 `audit_log` ไม่มี hash chain และ user ของแอปลบ/แก้ได้ · ต้องดู GRANT บน Pi
- B8 CSV ไม่กัน formula injection (qname/hostname ขึ้นต้น `=`) — ไม่ควรแก้เนื้อหาหลักฐาน ให้เขียนเตือนใน README · ในเครื่องได้
- B9 `start` แบบมี timezone → naive/aware TypeError 500 · ในเครื่องได้
- B10 ลูกค้าที่มี voucher เหลือ 2 นาที เครื่องใหม่ได้แค่ 2 นาที ต้องกดต่อเวลาเอง · เรื่องการใช้งาน
- B11 `quota_mb` ไม่มีเพดาน (INT) → 500 ถ้าโพสต์เอง · ในเครื่องได้
- B12 ลูกค้าใหม่ถูกอนุมัติ 2 คำขอพร้อมกัน → gap lock แล้ว INSERT ชน UNIQUE → 500 (ไม่ออกสิทธิ์ซ้ำ) · ต้อง MariaDB จริง

## ส่วนที่ตรวจแล้วแน่น

route ทุกตัวมี guard ถูก (reveal/block/erase/evidence/keys/audit/staff = admin เท่านั้น) · CSRF รวมที่ `gate()` + เทสต์กันฟอร์มลืม token ·
session fixation กันด้วย `session.clear()` · เปลี่ยนรหัส/ปิดบัญชี/เปลี่ยน role = session เก่าหลุดทันที · argon2id + นโยบายรหัสผ่าน ·
`safe_next` กัน open redirect · /setup ปิดถาวร + token constant-time · กัน admin เหลือ 0 · /keys/backup ยืนยันรหัสซ้ำ + `log_required` ·
reveal ลง audit แบบ required ก่อน decrypt · erase ถูกกันโดย retention ม.26 · revoke atomic + ตัดทุก session ของ voucher ·
extend whitelist 30/60/120 · ทุก SQL parameterized · ไม่มี subprocess ที่รับ input ผู้ใช้

## ⏳ ลำดับทดสอบบน Pi

| ข้อ | ทดสอบ | ผลที่ต้องได้ |
|---|---|---|
| B2 | มือถือที่ออนไลน์อยู่ ขอใหม่แล้วให้พนักงานอนุมัติ | ถ้าเน็ตหลุด = ยืนยัน → approve ต้องตรวจ/deauth ก่อน หรือเลี่ยงการ auth ซ้ำ |
| B3 | `systemctl stop opennds` แล้วอนุมัติ รอ 3 นาที ดูหน้า /requests | ต้องเห็นว่าเปิดเน็ตไม่สำเร็จ |
| B4 | export หลักฐานทุกเครื่อง 7 วัน และรายคน 186 วัน จับ RAM/เวลา | เกิน 60 วิหรือ RAM พุ่ง = ต้องสตรีม/จำกัดแถว |
| B7 | ถอดสาย WAN เปิด /status 4 แท็บ แล้วลองอนุมัติ | หน้าอนุมัติต้องไม่ค้าง |
| A7, A8, B12 | กดพร้อมกันจาก 2 เครื่อง · `SHOW GRANTS` ของ user แอป | ไม่ 500 · user แอปไม่มี DELETE/UPDATE บน audit_log |
