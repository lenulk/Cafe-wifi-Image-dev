# รีวิวโค้ด — tools/ (14 ต.ค. 2026)

ขอบเขต: `tools/*.py`, `tools/*.sh` (~2,600 บรรทัด) · ทีม: Sonnet 2 ตัว (A = enforce/reconcile/purge/check_disk,
B = backup/restore_keys/reset_admin/export_evidence/check_router/lab) อ่านอย่างเดียว → Opus ตรวจซ้ำข้อหลักกับโค้ด
บริบท: cafe-enforce (root, ทุก 5 นาที + 45 วิหลัง openNDS เริ่ม), cafe-reconcile (root, ทุก 5 วิ), cafe-maintenance
(root, 03:30: purge → backup → check_disk → integrity → check_time, ทุกบรรทัดมี `-` = exit code ถูกกลบ)

**แก้แล้ว (14 ต.ค., มีเทสต์ทุกข้อ, 846 ผ่าน / 6 ล้มเดิมของ Windows):** T3, T6 (transaction ต่อขั้น + ลบทีละ 10,000 แถว +
`purge_failed` ใน audit), T7 (นาฬิกาเร็วกว่า log ล่าสุด > 30 วัน = ข้ามการลบทั้งหมด + `purge_skipped_clock`), T9 (+ timer
`cafe-check-disk` ทุก 15 นาที, audit ระดับเดิมซ้ำได้ทุก 6 ชม.), U1–U8, U10–U12 ·
**T8 (เจ้าของตัดสิน):** ไม่ลบอัตโนมัติ — เพิ่มปุ่ม `/audit/scrub` (แอดมิน + ยืนยันรหัสผ่าน + เหตุผล, cutoff ≥ 180 วัน) แทน MAC /
เลขบัตร (ปิดบางหลักหรือเต็ม) / เลข 13 หลักด้วย `[ลบแล้ว]` **ไม่ลบแถว** (เก็บว่าใครทำอะไรเมื่อไหร่) ลง audit `audit_scrub` ก่อน+หลัง ·
**ไม่แก้:** T10 (ย้ายการตั้ง `auth_sent_at` ไปก่อน ndsctl ทำให้ crash = ไม่ลองซ้ำเลย แย่กว่าเดิม; auth ซ้ำปัจจุบันไม่เสียหาย) ·
**ผลบน Pi 16 ต.ค.:** T1 ไม่เกิดที่ 3 เครื่อง (openNDS คืนสิทธิ์ครบใน ~32 วิ ก่อนรอบ enforce 45 วิ) · T2 ไม่เกิด · T4 คนใหม่ได้เน็ต 8.9 วิ คนที่ถูกปิด ~1 วิ (3–4 เครื่อง) · **ยังเปิด (Pi):** T1/T4 ที่ 10+ เครื่อง, T5, T11 + **partition DROP** (event `cafewifi_partition_maintenance` ใน sql/003 ใช้ `CURDATE()`
— การตรวจนาฬิกาของ T7 ไม่ครอบคลุม ต้องแก้ใน stored procedure และลองกับ MariaDB จริง) ·
หมายเหตุ: `app/setup/restore.py::write_keys` ยังไม่ fsync เหมือน U5 (ต่ำ)

## สูง

| # | ที่ | ปัญหา | สถานะ |
|---|---|---|---|
| T1 | `enforce_voucher_expiry.py:228`, `:386-403` | `ndsctl json` ตอบสำเร็จแต่รายชื่อยังไม่ครบ (openNDS เพิ่งรีสตาร์ทและกำลังคืนสิทธิ์ทีละเครื่อง) → session ของเครื่องที่ยังไม่ถูกคืนถูกปิดเป็น `gone` → openNDS คืนสิทธิ์ตามมา = ออนไลน์โดยไม่มี session (log โยงหาคนไม่ได้ ช่วงสั้น) → รอบถัดไปถูกตัดเป็น orphan = ลูกค้าที่จ่ายแล้วหลุดทั้งร้าน | ทดสอบบน Pi 16 ต.ค. ด้วยมือถือ 3 เครื่อง: คืนสิทธิ์ครบใน ~32 วิ (< 45 วิ ของรอบ enforce) ไม่มี gone/orphan วิดีโอไม่สะดุด · **ร้านที่มีหลายสิบเครื่องยังไม่ได้วัด** (ข้อจำกัด) |

## กลาง

| # | ที่ | ปัญหา | สถานะ |
|---|---|---|---|
| T3 | `reconcile_pending.py:141-147` | `sync_extended` ไม่ดู `summary.deauth_failed` → ndsctl ล้มแต่ล้างธง `auth_sync_needed` → ปิดสิทธิ์/ระงับแล้วลูกค้ายังออนไลน์ถึง 5 นาที | ยืนยัน (Opus) · ในเครื่อง |
| T6 | `purge_old_data.py:150-165` | purge ทั้งหมดใน transaction เดียว DELETE ไม่แบ่งชุด → timeout 600 วิ หรือ error ตัวเดียว = rollback ทั้งคืน ซ้ำทุกคืนเงียบ ๆ (ข้อมูลเกิน retention สะสม = PDPA) | น่าจะจริง · ตรรกะในเครื่อง / เวลาจริงบน Pi |
| T7 | `purge_old_data.py:45-53` | ไม่ตรวจนาฬิกา — NTP ให้เวลาเดินหน้าผิด = ลบ/DROP partition ของ log ที่ยังไม่ครบ 180 วัน (กู้ไม่ได้) | น่าจะจริง · ในเครื่อง |
| T8 | `purge_old_data.py:15`, `access.py:155` | `audit_log` ไม่ถูก purge แต่เก็บ MAC + เลขบัตรแบบปิดบางหลักตลอดไป และ `anonymize_customer` ไม่แตะ | ยืนยัน · **ต้องตัดสินใจเชิงนโยบาย** |
| T9 | `check_disk.py:86-101` | ตรวจวันละครั้ง · ดิสก์เต็มแล้ว `write_alert` ล้มก่อนถึง audit และ path ถัดไปไม่ถูกตรวจ · `LOG_DIR` ไม่มี = ไม่ตรวจอะไรเลย · % คิดจาก total (ต่ำกว่า df) | ยืนยัน · ในเครื่อง |
| U1 | `backup_db.py:241` | offsite copy ล้ม (USB เต็ม) = ไม่ prune USB → เต็มถาวร · `.tmp` ค้างไม่ถูกลบ | ยืนยัน · ในเครื่อง |
| U2 | `backup_db.py:248` | จับแค่ `BackupError` — ValueError/OSError หลุด ไม่เขียน status → /status โชว์ผลสำเร็จเก่า | ยืนยัน · ในเครื่อง |
| U5 | `restore_keys.py:55`, `:105-117` | `secrets.env` ว่าง/ไม่มี → `merge` คืนไฟล์สำรองทั้งก้อน (FAS_KEY/SECRET_KEY/DB_PASS ของเครื่องเก่า) ขัด allowlist · ไฟล์ใหม่ตาม umask + ไม่ fsync ก่อน replace | ยืนยัน (Opus) · ในเครื่อง |
| U7 | `export_evidence.py:274` | `--natid <เลข 13 หลัก>` ทาง argv → เลขเต็มอยู่ใน `ps`, shell history, sudo log | ยืนยัน · ในเครื่อง |
| U11 | `check_router.py:134-147` | RA ตัดสั้น → `struct.error` ไม่ถูกจับ → `/router/check` ของ wizard 500 (apply ถูกครอบด้วย `main()` แล้วตั้งแต่ 5dfece5) | ยืนยัน (Opus) · ในเครื่อง |
| T2 | `enforce_voucher_expiry.py:344-401` | transaction ยาวทั้งรอบ + อ่าน openNDS หลัง snapshot → อนุมัติระหว่างรอบ = ถูกตัดเป็น orphan · ล็อก voucher ค้างระหว่างรอ ndsctl | ทดสอบบน Pi 16 ต.ค.: สั่ง enforce + อนุมัติ + ปิดสิทธิ์พร้อมกัน — คนใหม่ไม่ถูกตัดเป็น orphan ✅ |
| T4 | `reconcile_pending.py:144`, `:186` | revoke/block ทำให้ reconcile (5 วิ) รัน enforce เต็มรวม `ndsctl json` (~1.1 วิ/ลูกค้า) + ถือ FOR UPDATE ระหว่าง deauth | ทดสอบบน Pi 16 ต.ค. (4 เครื่อง): คนใหม่ได้เน็ต 8.9 วิ (รวมรอบ timer 5 วิ) คนที่ถูกปิดหลุด ~1 วิ · 10+ เครื่องยังไม่ได้วัด |
| T5 | `enforce_voucher_expiry.py:107`, `conn_collector.py:62` | นับโควตาตอน conntrack DESTROY เท่านั้น + ไม่ส่งโควตาให้ openNDS → ดาวน์โหลดก้อนเดียวเกินโควตาได้หลาย GB | ยืนยันกลไก · **ต้อง Pi** (ข้อจำกัดเชิงออกแบบ) |
| U9 | `export_evidence.py:220` | CLI export ไม่มีเพดานช่วงเวลา/แถว ดึงเข้า RAM ทั้งก้อน (คู่กับ B4 ของ admin) | ✅ **วัดบน Pi 16 ต.ค. แล้วแก้** — 29k แถว 2.75 วิ RAM 60 MB · ร้านจริงคาด ~550k แถว/วัน → สตรีมด้วย `common.db.iter_rows` + `write_csv_stream` (hash ระหว่างเขียน, bytes ตรงแบบเดิม) → RAM 31 MB คงที่ · รายคน (--natid) ยังรวมในหน่วยความจำ (ปริมาณจำกัดตามคนเดียว) |

## ต่ำ

- T10 `reconcile_pending.py:101` ndsctl auth สำเร็จแต่ตั้ง `auth_sent_at` ไม่ทัน → auth ซ้ำ → อาจจบที่ auth_timeout · ในเครื่อง
- T11 deauth→auth ใน `sync_extended` ชนจังหวะ `ndsctl json` ของ enforce · Pi (โอกาสต่ำมาก)
- U3 `backup_db.py:94` `communicate()` ไม่มี timeout → mysqldump ค้าง = check_disk/integrity ของคืนนั้นไม่รัน · ในเครื่อง (เทสต์ pipe ล้มบน Windows อยู่แล้ว)
- U4 `.tmp` ของ backup สร้างตาม umask ก่อน chmod 0600 · ไม่ตรวจว่า dump ครบ (`-- Dump completed`) · ในเครื่อง
- U6 `reset_admin.py` ไม่ลง audit (ใคร/บัญชีไหน/เมื่อไหร่) · ในเครื่อง
- U8 export จาก CLI ลง audit ไม่มีผู้ทำ (`SUDO_USER`) และไม่มีผลลัพธ์ (แถว/sha256) · ในเครื่อง
- U10 export ชื่อไฟล์ระดับวินาที + `O_TRUNC` ไม่มี `O_EXCL` → export ซ้ำในวินาทีเดียวเขียนทับ · ในเครื่อง
- U12 `install.sh:880` คัดลอก `lab_*` ลงเครื่องจริงด้วย (ไม่ถูกรันอัตโนมัติ แต่ช่างรันพลาดจะทิ้งบัญชีแอดมิน/SSH key) · ในเครื่อง (harness)

## ส่วนที่ตรวจแล้วแน่น

ndsctl ใช้ argv list + MAC ผ่าน regex · deauth ล้มไม่ปิด session · `close_session` กันนับ used_mb ซ้ำ ·
expired/used_up/revoked/blocked ถูกตัดครบ · โควตารวมทุกเครื่องของ voucher · retention < 90 วันถูกปฏิเสธทั้ง Python และ
stored procedure · DROP partition ใช้ขอบบน < cutoff · backup ส่งรหัสผ่านทาง `MYSQL_PWD` + ตรวจ exit ทั้ง 2 โปรเซส +
prune หลัง dump สำเร็จเท่านั้น + DEK ไม่อยู่ใน dump · restore_keys มี allowlist/สำเนาก่อนเขียน/`--check` ·
reset_admin ใช้ getpass + argon2 + ตั้ง password_changed_at · export audit ก่อนดึงข้อมูล (fail-closed) + ไฟล์ 0600 ·
check_router ไม่มี subprocess + ชื่อ NIC ผ่าน regex · lab script ไม่มี unit/timer เรียก

## ⏳ ลำดับทดสอบบน Pi

| ข้อ | ทดสอบ | ผลที่ต้องได้ |
|---|---|---|
| T1 | มีลูกค้าออนไลน์ 3+ เครื่อง → `systemctl restart opennds` → ดู `portal_session` และ audit `orphan_deauth` หลัง 45 วิ / 5 นาที | ไม่มี session ถูกปิดเป็น gone แล้วเครื่องถูกตัดเป็น orphan |
| T2 | อนุมัติระหว่าง cafe-enforce กำลังรัน (`journalctl -fu cafe-enforce`) | ลูกค้าต้องไม่ถูกตัดเป็น orphan |
| T4 | ลูกค้า 10+ เครื่อง กดปิดสิทธิ์ 1 คน แล้วอนุมัติคนใหม่ทันที | คนใหม่ได้เน็ตภายในไม่กี่วินาที |
| T5 | voucher 100 MB ดาวน์โหลดไฟล์ 1 GB ทางเดียว | บันทึกว่าเกินได้เท่าไร → เขียนเป็นข้อจำกัดในเล่ม หรือส่งโควตาให้ openNDS |
| ~~T6/U9~~ | ✅ 16 ต.ค. — purge < 1 วิ (ไม่มีข้อมูลเกิน 180 วัน) · export แก้เป็นสตรีม | — |
