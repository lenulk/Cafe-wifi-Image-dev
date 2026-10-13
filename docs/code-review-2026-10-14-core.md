# รีวิวโค้ดทั้งก้อน — fas / common / logger / sql (14 ต.ค. 2026)

ทีมรีวิว: Sonnet 4 ตัว (แยกส่วน อ่านอย่างเดียว) → Opus ตรวจซ้ำกับโค้ดจริง
สถานะในตาราง: **ยืนยัน** = Opus เปิดโค้ด/รันทดสอบแล้วเห็นจริง · **น่าจะจริง** = เหตุผลถูก แต่ยังไม่ได้ทดลอง/ขึ้นกับสภาพบน Pi
ยกเว้นตามการตัดสินใจเดิม: เลขบัตรผ่าน HTTP, admin เห็นข้อมูลเต็ม, Pi ตัวเดียวสายเดียว

**แก้แล้ว (14 ต.ค.):** H1, H3, M3, M4, M5, M6, M7, M8, M9, M10, M11, M12 (ดัชนี sql/016) และหมวดต่ำ: nonce ภาษาไทย,
ขอบเวลา SESSION_MATCH (`<` ended_at ทุกจุด), flush backoff, offset หาย → log_gap, DB timeout, docker-compose 008–016, หมายเหตุ sql/008
· เพิ่มเติม: DSR ปิดคำขอ pending ของลูกค้าเป็น expired · parse dnsmasq รับ CRLF
**ยังเปิด:** M1, M2, H2 (ดูตารางข้างล่าง) · fas consent ไม่มีเวอร์ชันนโยบาย / double-tap deadlock / `/request` ซ่อนคำขอเก่า ·
`common/traffic.py` ใช้ขอบเวลาคนละแบบ (นับโควตา — ตั้งใจยังไม่แตะ) · ทั้งหมดที่แก้ผ่านเทสต์ในเครื่อง แต่**ยังไม่ได้รันบน Pi/MariaDB จริง**

## ⏳ ต้องตรวจบน Pi ก่อนแก้ (ห้ามแก้จากการเดา)

| ข้อ | ต้องดูอะไรบน Pi | คำสั่ง | ถ้าเจอ… |
|---|---|---|---|
| M1 DNS HTTPS/SVCB | dnsmasq รุ่นนี้พิมพ์ชนิด record ที่ไม่รู้จักยังไง | `dnsmasq --version` แล้ว `grep -oE 'query\[[^]]+\]' /var/log/cafe-wifi/dnsmasq.log \| sort \| uniq -c` (path ดูจาก install.sh) | มี `query[type=65]` / `query[type=64]` → แก้ `_QUERY_RE` ให้รับ `[\w=]+` และ map เลข→ชื่อ · ถ้าเป็น `query[HTTPS]` อยู่แล้ว = ปิดข้อนี้ |
| M2 บรรทัดหายตอน logrotate | dnsmasq เขียนไฟล์เก่าต่อหลัง rename นานแค่ไหน และ collector อ่านทันไหม | สั่ง `logrotate -f` กลางวันที่มีลูกค้า แล้วเทียบ `zcat dnsmasq.log-<วันนี้>* \| tail -50` กับ `SELECT ... FROM dns_log ORDER BY ts DESC` ช่วงเวลาเดียวกัน | บรรทัดท้ายไฟล์เก่าไม่มีใน DB → แก้ dns_collector ให้อ่าน fd เก่าต่ออีกสักครู่หลัง inode เปลี่ยน (หรือใช้ `copytruncate`) |
| H2 แยกสิทธิ์ DB + ยึด hash chain นอกเครื่อง | **งานออกแบบ ต้องคุยก่อน** — แยก user DB ต่อ service (logger INSERT-only, ไม่มีใคร UPDATE/DELETE audit_log), ผนึก conn_log/dns_log รายวันเข้า chain, ส่ง head hash ออกนอกเครื่อง (อีเมล/USB/พิมพ์) | — | ต้องทดสอบ install.sh + ทุก service บน Pi หลังแยก user |
| M2/M6 ผลจริงหลังแก้ | ดู audit `log_gap` หลังทดสอบ ENOBUFS / ปิด MariaDB 1 นาที | `systemctl stop mariadb; sleep 60; systemctl start mariadb` แล้วดูหน้า audit | ต้องเห็นแถว log_gap พร้อมจำนวนที่ทิ้ง |
| H3 install.sh ซ้ำ | หลังแก้: รัน `install.sh` ซ้ำ **โดยไม่ใส่** `--enable-partitions` บน Pi ที่เปิด partition ไว้ | `mysql -e "SELECT @@event_scheduler"` | ต้องยังเป็น `ON` |
| M12 ดัชนีใหม่ | หลังรัน sql/016 | `EXPLAIN SELECT DISTINCT mac FROM portal_session WHERE ip='10.10.0.50' AND authenticated_at <= NOW()` | ต้องใช้ `idx_ip_auth` |

## สูง — กระทบความถูกต้องของหลักฐาน ม.26

| # | ที่ | ปัญหา | สถานะ |
|---|---|---|---|
| H1 | `app/logger/conn_collector.py:152-159` | ICMP: `id=` ตัวแรกคือ echo id ของ ping ไม่ใช่ conntrack id → ping สองเครื่องที่ใช้ echo id เดียวกัน (Windows ใช้ 1) ทับกันใน `_open` → **traffic ของเครื่อง A ถูกบันทึกเป็น MAC ของเครื่อง B** · DESTROY ไม่เคยเทียบ 5-tuple กับ NEW | ยืนยัน (โค้ด `kv_first.setdefault`) |
| H2 | `install.sh:924`, `app/logger/integrity.py` | user DB เดียวมี UPDATE/DELETE ทุกตาราง ใช้ร่วมทุก service · hash chain ไม่มีกุญแจ/ไม่มีจุดยึดนอกเครื่อง และ **ไม่ครอบ `conn_log`/`dns_log` ในฐานข้อมูลเลย** (ผนึกเฉพาะไฟล์ archive) → ใครได้รหัส DB แก้/ลบหลักฐานได้โดยไม่มีอะไรจับ | ยืนยัน (GRANT) · เชิงออกแบบ |
| H3 | `install.sh:1087-1091`, `:2371` | รัน install.sh ซ้ำโดยไม่ใส่ `--enable-partitions` → เขียน cnf ใหม่ไม่มี `event_scheduler = ON` → งานสร้าง partition หยุดเงียบ (`install.state` ถูกเขียนแต่ไม่เคยอ่านกลับ) · purge ยังทำงานเพราะใช้ DELETE | ยืนยัน |

## กลาง

| # | ที่ | ปัญหา | สถานะ |
|---|---|---|---|
| M1 | `app/logger/dns_collector.py:32` | `query\[(\w+)\]` ไม่จับ `query[type=65]` (HTTPS/SVCB จาก iOS/Chrome) → บรรทัดหายเงียบ | regex ยืนยัน · ขึ้นกับรุ่น dnsmasq ว่าพิมพ์ชื่อหรือเลข |
| M2 | `dns_collector.py:262-276` | ตอน logrotate: เปิดไฟล์ใหม่ทันทีที่ inode เปลี่ยน ไม่อ่านไฟล์เก่าจนหมด → บรรทัดช่วงหมุนไฟล์หายจาก `dns_log` ทุกวัน ไม่มี log_gap | น่าจะจริง |
| M3 | `dns_collector.py:114` | หา MAC ของ DNS ตอนเขียน DB (≥5 วิ หรือหลายชั่วโมงถ้า DB ล่ม) ไม่ใช่ตอนอ่านบรรทัด → IP เปลี่ยนมือแล้วได้ MAC ผิด (บั๊กเดียวกับ R2-02 ที่แก้ฝั่ง conn แล้ว) | น่าจะจริง |
| M4 | `integrity.py:36-39` | ไฟล์ .gz เสีย (SD card) → `sha256_file` โยน error → ทั้งรอบตรวจล้ม **ก่อน** เขียน `INTEGRITY_FAILED` · ทุกรอบหลังจากนั้นล้มเหมือนกัน | น่าจะจริง |
| M5 | `integrity.py:140-166` | ไฟล์ที่ไม่มีใน manifest ถูกผนึกเป็นของจริงโดยไม่เตือน · วันที่ไม่มีไฟล์ archive ไม่ถูกจับ | น่าจะจริง |
| M6 | `conn_collector.py:429-505`, `dns_collector.py:148-155` | จำนวนเหตุการณ์ที่ทิ้ง (DB ล่ม/ENOBUFS) อยู่แค่ในหน่วยความจำ · audit ENOBUFS มี cooldown 5 นาทีไม่มีจำนวน → บอกไม่ได้ว่าหลักฐานขาดไปเท่าไร | น่าจะจริง |
| M7 | `admin/views/customers.py:142`, `common/customer.py:44` | ลบข้อมูลลูกค้า (DSR): ทำ 3 UPDATE แยก commit + audit แบบ best-effort หลังลบ → พังกลางทางได้ข้อมูลค้าง และลองใหม่ไม่ได้ (ถูก PURGED แล้ว) / DB สะดุดตอนลบ = ไม่มี audit ว่าใครลบ | ยืนยัน |
| M8 | `common/crypto.py:164` | `constant_time_eq` ใช้ `hmac.compare_digest` กับ str → พิมพ์ภาษาไทยในช่อง setup token = 500 และไม่นับ rate limit · ค่าว่างเท่ากับค่าว่าง (ไฟล์ token ว่าง = ผ่าน) | ยืนยัน (รันแล้ว) |
| M9 | `common/device_info.py:92-108` | User-Agent แปลก ๆ ให้ `os_label` ยาว 214 ตัว (คอลัมน์ 64) → ลงทะเบียน 500 | ยืนยัน (รันแล้ว) |
| M10 | `app/fas/app.py:196`, `common/access.py:17` | rate limit ผูกกับ MAC และนับแค่ครั้งที่ผิด → คนเปลี่ยน MAC วนส่งเลขบัตรปลอมที่ checksum ถูก 50 ครั้ง = คิวเต็ม ลูกค้าจริงขอไม่ได้ (15 นาที วนได้เรื่อย ๆ) | น่าจะจริง |
| M11 | `tools/purge_old_data.py`, `common/customer.py` | PDPA: `portal_session` (MAC/IP/เวลา), `device`, `bypass_alert`, `audit_log.detail` ไม่เคยถูกลบ/ทำนิรนาม | ยืนยันจากรายชื่อตารางใน purge |
| M12 | `sql/001` | ไม่มีดัชนี `portal_session(ip, …)` แต่ logger ค้นด้วย ip ต่อ record ที่ไม่มี MAC → หลัง restart ช้า อาจล้น buffer | ยืนยัน |

## ต่ำ

- `fas/app.py:87` nonce ภาษาไทย → 500 (ใครก็ได้ในวง Wi-Fi ทำ log ล้น traceback) — ยืนยันจากโค้ด
- `common/log_mapping.py` SESSION_MATCH ขอบเวลา `<=` ทั้งสองฝั่ง: session ปิด T กับ session ใหม่เริ่ม T (MAC/IP เดิม) → แถวที่ T ไม่ระบุตัว · session ค้าง (ended_at NULL) ทำให้แถวหลังจากนั้นไม่ระบุตัว — ปลอดภัย (ไม่ชี้ผิดคน) แต่หลักฐานหาย
- `conn_collector.py:618` DB ล่มแล้วลอง flush ทุกเหตุการณ์ (ไม่มี backoff) → log ล้น + คิวเต็ม
- `dns_collector.py:165` ไฟล์ offset หาย → ข้ามบรรทัดช่วงที่ logger ดับโดยไม่บันทึก gap
- `fas`: consent เก็บแค่เวลา ไม่มีเวอร์ชันนโยบาย · double-tap อาจ deadlock 500 · `/request` ซ่อนคำขอที่เก่ากว่า 1 วัน
- `common/db.py` ไม่มี connect/read timeout
- `docker-compose.yaml` ใช้แค่ sql 001/005/006/007 → เทสต์ใน Docker ไม่ตรง schema จริง
- `sql/008` มี UPDATE ข้อมูลที่รันซ้ำทุกครั้งที่ re-run install.sh (ตอนนี้ปลอดภัย แต่เปราะ)

## ส่วนที่ทีมตรวจแล้วแน่น (ย่อ)

ไม่พบทางได้เน็ตโดยไม่ผ่านอนุมัติ · nonce ผูก IP + MAC จาก ARP ใช้ครั้งเดียว · FAS payload AES ปลอมไม่ได้ ·
SQL ใช้พารามิเตอร์ทั้งหมด · Jinja autoescape ไม่มี `|safe` · AES-GCM nonce สุ่มใหม่ทุกครั้ง กุญแจหาย = ล้มแบบปิด ·
checksum เลขบัตรถูก · purge ไม่ลบก่อน 90 วัน · batch insert ล้างบัฟเฟอร์หลัง commit สำเร็จเท่านั้น ·
verify_chain จับไฟล์ถูกแก้/แถวกลางหาย/ไฟล์หายได้
