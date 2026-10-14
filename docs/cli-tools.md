# อ้างอิงเครื่องมือบรรทัดคำสั่ง (CLI Tools Reference)

เอกสารนี้อธิบายสคริปต์ใน `tools/`, `image/` และ `app/logger/run_all.py` ว่ารันอย่างไร ต้องใช้สิทธิ์อะไร อ่านเขียนอะไร และมีความเสี่ยงแค่ไหน ข้อมูลทั้งหมดอ้างจากซอร์สโค้ดและ `install.sh` (ไม่ได้รันสคริปต์จริงเพื่อจัดทำเอกสาร) ส่วนที่ยืนยันจากโค้ดไม่ได้จะเขียนว่า "ไม่แน่ชัด"

สคริปต์ที่รันอัตโนมัติผ่าน systemd มี 5 ตัว คือ `purge_old_data`, `backup_db` (รายวัน 03:30 ผ่าน `cafe-maintenance.timer`), `check_disk` (ทุก 15 นาทีผ่าน `cafe-check-disk.timer` และซ้ำอีกครั้งใน maintenance 03:30), `enforce_voucher_expiry` (ทุก 5 นาที) และ `reconcile_pending` (ทุกประมาณ 5 วินาที) ที่เหลือเป็นเครื่องมือที่รันด้วยมือ หรือถูกเรียกจากเว็บ/ตัวติดตั้ง

## สารบัญ

- [ตารางสรุป](#ตารางสรุป)
- [ข้อตกลงร่วมก่อนรันด้วยมือ](#ข้อตกลงร่วมก่อนรันด้วยมือ)
- [ใช้ในระบบจริง (production)](#ใช้ในระบบจริง-production)
- [ใช้กับ image / SD card](#ใช้กับ-image--sd-card)
- [ใช้ในแล็บทดสอบเท่านั้น (lab_*)](#ใช้ในแล็บทดสอบเท่านั้น-lab_)
- [ข้อสังเกตจากการอ่านโค้ด](#ข้อสังเกตจากการอ่านโค้ด)

## ตารางสรุป

| script | หน้าที่ | รันอัตโนมัติ? | ต้องใช้ root? |
|---|---|---|---|
| `tools/purge_old_data.py` | ลบ conn_log/dns_log ที่เก่ากว่าเกณฑ์ และล้างข้อมูลระบุตัวตนของลูกค้าที่ไม่ได้มาร้านนาน | ใช่ `cafe-maintenance.timer` รายวัน 03:30 | ใช่ (unit ไม่มี `User=` จึงรันเป็น root) |
| `tools/backup_db.py` | สำรองฐาน `cafewifi` เป็น `.sql.gz` และคัดลอกออกนอกเครื่องถ้าตั้งค่าไว้ | ใช่ `cafe-maintenance.timer` รายวัน 03:30 | ใช่ (root ตาม unit) |
| `tools/check_disk.py` | เตือนเมื่อดิสก์ `LOG_DIR` และ `/` ใช้เกิน 80%/90% | ใช่ `cafe-check-disk.timer` ทุก 15 นาที (และ `cafe-maintenance.timer` 03:30) | ใช่ (root ตาม unit) |
| `tools/enforce_voucher_expiry.py` | หมดอายุ voucher, ตัด session ด้วย `ndsctl deauth`, ปิด session ที่หลุดไปแล้ว | ใช่ `cafe-enforce.timer` ทุก 5 นาที | ใช่ (root ตาม unit และ docstring ของ `deauth_mac`) |
| `tools/reconcile_pending.py` | ยืนยัน pending session กับ openNDS แล้วเปิดสิทธิ์ใน DB | ใช่ `cafe-reconcile.timer` ทุกประมาณ 5 วินาที | ใช่ (`User=root` ใน unit) |
| `tools/reset_admin.py` | ตั้งรหัสผ่านผู้ดูแลระบบใหม่จากบรรทัดคำสั่ง | ไม่ (รันด้วยมือ) | ใช่ (ตาม docstring) |
| `tools/export_evidence.py` | ส่งออก CSV หลักฐาน conn_log/dns_log พร้อม manifest SHA-256 | ไม่ (เว็บ `/evidence` ก็เรียกโมดูลนี้ด้วย) | ไม่แน่ชัด |
| `tools/restore_keys.py` | กู้ `NATID_DEK` และ `NATID_PEPPER` จากไฟล์ `.cwkey` | ไม่ (รันด้วยมือ หรือจากตัวช่วยกู้คืนในเว็บ) | ใช่ (ยกเว้นตั้ง `ETC_DIR` เอง) |
| `tools/check_router.py` | ตรวจว่าเราเตอร์ร้านปิด DHCP และ IPv6 RA แล้ว | ไม่ (เรียกจาก setup wizard) | ไม่จำเป็น แต่ต้องมี `CAP_NET_RAW` |
| `app/logger/run_all.py` | จุดเริ่มของ `cafe-logger.service` ที่เก็บ conntrack และ dnsmasq log | ใช่ เป็น service ทำงานตลอด | ไม่ (รันเป็น `cafewifi` พร้อม ambient capabilities) |
| `image/check-image.sh` | ตรวจว่า rootfs ของ image ไม่มีความลับติดมา | ไม่ (`image/build.sh` เรียกตอน build) | ไม่แน่ชัด |
| `image/prepare-sd.ps1` | เขียน `cafewifi.conf` ลง bootfs ของการ์ด | ไม่ (รันบน Windows) | ไม่ (ไม่ใช่ root) |
| `image/publish-public.sh` | สร้าง commit บน branch `public` สำหรับ repo สาธารณะ | ไม่ | ไม่ |
| `tools/lab_issue_voucher.py` | ออก voucher ทดสอบผ่านเส้นทาง `/issue` ตัวจริง | ไม่ (แล็บ) | ใช่ (ตาม docstring) |
| `tools/lab_ra_sim.py` | ส่ง ICMPv6 Router Advertisement จำลอง | ไม่ (แล็บ) | ใช่ (raw socket) |
| `tools/lab_client.sh` | สร้างลูกค้าจำลองใน network namespace | ไม่ (แล็บ) | ใช่ |
| `tools/lab_e2e_register.sh` | ทดสอบลงทะเบียน -> อนุมัติ -> ออกเน็ต ด้วยลูกค้าจำลอง | ไม่ (แล็บ) | ใช่ (ใช้ `sudo bash`) |
| `tools/lab_fulltest.sh` | ทดสอบรวมทั้งระบบบน Pi จริง (49 ข้อในรอบล่าสุดที่บันทึกไว้) | ไม่ (แล็บ) | ใช่ (ใช้ `sudo bash`) |

## ข้อตกลงร่วมก่อนรันด้วยมือ

- **systemd unit** โหลดค่าจาก `/etc/cafe-wifi/secrets.env` ด้วย `EnvironmentFile=` (`install.sh` บรรทัด ~1976, 2019, 2057, 2093) ไม่ต้อง `export`
- **รันด้วยมือ** ต้องโหลดไฟล์นี้ให้ตัวแปรถูก export ก่อน และรันเป็นโมดูลจาก `/opt/cafe-wifi` ตามรูปแบบนี้ (เป็นรูปแบบที่ docstring ของ `tools/reset_admin.py` และ `tools/lab_issue_voucher.py` ใช้)

  ```bash
  sudo bash -c 'set -a; . /etc/cafe-wifi/secrets.env; set +a; cd /opt/cafe-wifi && PYTHONPATH=/opt/cafe-wifi venv/bin/python -m tools.<module> <args>'
  ```

- `sudo -E` **ใช้ไม่ได้** เพราะ environment ของผู้ใช้ทั่วไปไม่มี `DB_PASS` (ระบุใน docstring ของ `tools/reset_admin.py`)
- `secrets.env` มี mode `0640` เป็นเจ้าของ `root:<APP_USER>` (`install.sh` บรรทัด ~772–834) จึงควรรันด้วย root
- ไฟล์ log อยู่ใต้ `LOG_DIR` (ค่าปริยาย `/var/log/cafe-wifi`) และ `audit_log` ในฐานข้อมูลเก็บร่องรอยการลบ/ส่งออก
- ตรวจผลงานอัตโนมัติได้ด้วย `systemctl list-timers` และ `journalctl -u cafe-maintenance.service` (ชื่อ unit ตาม `install.sh`)

---

## ใช้ในระบบจริง (production)

### tools/purge_old_data.py

- **หน้าที่:** ลบแถว `conn_log` และ `dns_log` ที่เก่ากว่า `LOG_RETENTION_DAYS` ล้างข้อมูลระบุตัวตนของลูกค้า (ไม่ลบแถว customer) ที่ไม่มี voucher ค้างอยู่และไม่ได้มาร้านนานเกิน `CUSTOMER_RETENTION_DAYS` ลบ `voucher_reveal` ที่หมดอายุ ลบ `access_request` ที่เก่ากว่า log cutoff และลบ `rate_attempt` ที่เก่ากว่า 1 วัน (`tools/purge_old_data.py`, ฟังก์ชัน `run`)
- **รันอย่างไร:**
  ```bash
  sudo bash -c 'set -a; . /etc/cafe-wifi/secrets.env; set +a; cd /opt/cafe-wifi && PYTHONPATH=/opt/cafe-wifi venv/bin/python -m tools.purge_old_data'
  ```
- **อาร์กิวเมนต์:** ไม่มี (ไม่ได้ใช้ `argparse` และ `main()` ไม่อ่าน `sys.argv`)
- **ตัวแปรสภาพแวดล้อม:**
  - `LOG_RETENTION_DAYS` ค่าปริยาย `180`
  - `CUSTOMER_RETENTION_DAYS` ค่าปริยายเท่ากับ `LOG_RETENTION_DAYS`
  - `DB_*` จาก `secrets.env`
- **อ่าน/เขียน:** อ่านและลบในตาราง `conn_log`, `dns_log`, `customer`, `voucher`, `voucher_reveal`, `access_request`, `rate_attempt` และเขียน `audit_log` หนึ่งแถว (action `purge_old_data`) สรุปจำนวนที่ลบ
- **ไม่ลบ:** `audit_log` และ `log_manifest` (ระบุไว้ใน docstring ว่าต้องลบด้วยมือถ้าจำเป็น)
- **Exit code:** `0` สำเร็จ, `1` เมื่อ `LOG_RETENTION_DAYS` ต่ำกว่า 90 (`compute_log_cutoff` โยน `ValueError` และ `main` คืน 1) และ exception อื่นที่ไม่ได้จับจะให้ exit code 1 ตามค่าปริยายของ Python
- **รันอัตโนมัติ:** ใช่ บรรทัด `ExecStart=-${VENV_DIR}/bin/python -m tools.purge_old_data` ใน `cafe-maintenance.service` (`install.sh` บรรทัด ~1979) ทำงานเป็นลำดับแรกก่อน backup
- **ความปลอดภัย:** **ทำลายข้อมูลถาวร** ไม่มีโหมดทดสอบหรือ dry-run การลบ `conn_log` เป็นข้อมูลหลักฐาน ดังนั้นให้ตั้ง retention ตามที่กฎหมายกำหนดเท่านั้น ใน `docker-compose.yaml` (service `jobs`, profile `jobs`) ก็เรียกโมดูลนี้ได้ ซึ่งเป็นการทดสอบ ไม่ใช่ระบบจริง

### tools/backup_db.py

- **หน้าที่:** สำรองฐาน `DB_NAME` ด้วย `mysqldump --single-transaction --no-tablespaces` ต่อ pipe เข้า `gzip` ไฟล์ทำชื่อ `.tmp` ก่อนแล้วจึง rename เมื่อสำเร็จ (atomic) ถ้าตั้ง `OFFSITE_BACKUP_DIR` จะคัดลอกไฟล์ไปที่นั้น ลบไฟล์ backup เก่าตาม retention และเขียนสถานะให้หน้า `/status` (`tools/backup_db.py` ส่วนต้นไฟล์และฟังก์ชัน `run`)
- **รันอย่างไร:**
  ```bash
  sudo bash -c 'set -a; . /etc/cafe-wifi/secrets.env; set +a; cd /opt/cafe-wifi && PYTHONPATH=/opt/cafe-wifi venv/bin/python -m tools.backup_db'
  ```
- **อาร์กิวเมนต์:** ไม่มี (`main()` เรียก `run()` โดยไม่รับค่า)
- **ตัวแปรสภาพแวดล้อม:**
  - `BACKUP_DIR` ค่าปริยาย `/var/backups/cafe-wifi`
  - `BACKUP_RETENTION_DAYS` ค่าปริยาย `14`
  - `OFFSITE_BACKUP_DIR` ว่าง = ข้ามการคัดลอกออกนอกเครื่อง
  - `BACKUP_TIMEOUT_SEC` เพดานเวลา dump ทั้งก้อน ค่าปริยาย `3600` เกินแล้วฆ่า mysqldump/gzip ลบ `.tmp` และถือว่าล้มเหลว
  - `OFFSITE_REQUIRE_SEPARATE_DEVICE=1` ถ้าตั้งไว้ จะไม่คัดลอกลงอุปกรณ์เดียวกับ backup (กันการคัดลอกลง SD ใบเดิมโดยไม่รู้ตัว)
  - `DB_NAME` (ค่าปริยาย `cafewifi`), `DB_HOST` (`127.0.0.1`), `DB_PORT` (`3306`), `DB_USER` (`cafewifi`), `DB_PASS`
  - `LOG_DIR` ใช้เขียน `backup-status.json`
- **อ่าน/เขียน:**
  - เขียน `<BACKUP_DIR>/<DB_NAME>-<YYYYmmdd-HHMMSS>.sql.gz` โหมด `0600` (สร้าง `.tmp` ด้วย `O_EXCL` 0600 ตั้งแต่แรก) แล้วตรวจว่าท้ายสตรีมมี `-- Dump completed` ก่อน rename — ไม่ครบ = ล้มเหลว ไม่ rename
  - เขียน `<OFFSITE_BACKUP_DIR>/<ชื่อไฟล์>` ถ้าคัดลอกได้ (โหมด `0600` ถ้า filesystem รองรับ)
  - เขียน `<LOG_DIR>/backup-status.json` (ไม่มีความลับ มีเวลา ขนาด และผลการคัดลอก)
  - ลบไฟล์ `*.sql.gz` ใน `BACKUP_DIR` และโฟลเดอร์ offsite ที่เก่ากว่า retention (prune offsite ทำแม้รอบนั้นคัดลอกล้ม เช่น USB เต็ม; USB ไม่ได้เสียบไม่ทำให้พัง) และลบ `*.sql.gz.tmp` ค้างที่เก่ากว่า 1 วันทั้งสองที่
- **ไม่ใช้** `--routines` และ `--triggers` ตามคอมเมนต์ในไฟล์ (สิทธิ์ของ `DB_USER` ไม่พอ) โครงสร้าง schema อยู่ใน `sql/*.sql` ต้องรันตอน restore เอง
- **Exit code:** `0` สำเร็จ, `1` เมื่อ `BackupError`/`ValueError`/`OSError` (ไม่พบ `mysqldump` หรือ `gzip`, dump ล้มเหลว/เกินเวลา/ไม่ครบ, gzip ล้มเหลว, ดิสก์เต็ม) และเขียน `backup-status.json` เป็น `ok=false` พร้อมข้อความเสมอ ความล้มเหลวของ offsite **ไม่ทำให้ exit code เป็น 1** (ตามคอมเมนต์ในโค้ด)
- **รันอัตโนมัติ:** ใช่ `cafe-maintenance.service` บรรทัด `ExecStart=-...tools.backup_db` (`install.sh` บรรทัด ~1980) ทำงานหลัง purge
- **ความปลอดภัย:**
  - ไฟล์ dump มี `natid_enc` (ข้อมูลเข้ารหัส) ถอดรหัสได้ต้องมี `secrets.env` คู่กัน
  - `prune_old_backups` **ลบไฟล์** ที่เก่ากว่า retention โดยไม่ถาม
  - ถ้า OFFSITE เป็นโฟลเดอร์ธรรมดาบน SD เดียวกัน จะไม่ช่วยเมื่อการ์ดพัง ควรตั้ง `OFFSITE_REQUIRE_SEPARATE_DEVICE=1` และใช้ USB ที่มี label `CAFEBACKUP` (ตาม `docs/backup-usb.md` และคอมเมนต์ใน `backup_db.py`)

### tools/check_disk.py

- **หน้าที่:** ตรวจการใช้พื้นที่ของ `LOG_DIR` และ `/` ถ้าเกิน `DISK_WARN_PCT` (ค่าปริยาย 80) เขียนบรรทัดลง `alert.log` และบันทึก audit `DISK_ALERT` ถ้าเกิน `DISK_CRIT_PCT` (ค่าปริยาย 90) จะระดับ critical (`tools/check_disk.py`, ค่าคงที่ `DEFAULT_WARN_PCT`, `DEFAULT_CRIT_PCT`)
- **รันอย่างไร:**
  ```bash
  sudo bash -c 'set -a; . /etc/cafe-wifi/secrets.env; set +a; cd /opt/cafe-wifi && PYTHONPATH=/opt/cafe-wifi venv/bin/python -m tools.check_disk'
  ```
- **อาร์กิวเมนต์:** ไม่มี
- **ตัวแปรสภาพแวดล้อม:** `LOG_DIR`, `DISK_WARN_PCT`, `DISK_CRIT_PCT`
- **อ่าน/เขียน:** อ่านสถานะดิสก์ผ่าน `shutil.disk_usage` เขียน `<LOG_DIR>/alert.log` (เฉพาะกรณี warn/crit) และ `audit_log`
- **Exit code:** `1` ถ้ามี path ใดอยู่ระดับ `crit` มิฉะนั้น `0` (ระดับ warn ไม่ทำให้ exit code เป็น 1)
- **รันอัตโนมัติ:** ใช่ `cafe-check-disk.service` + `cafe-check-disk.timer` (`OnBootSec=5min`, `OnUnitActiveSec=15min`) และยังมีบรรทัด `ExecStart=-...tools.check_disk` ใน `cafe-maintenance.service` ด้วย (`install.sh`)
- **ความปลอดภัย:** อ่านอย่างเดียว ปลอดภัย แต่บันทึก alert ทุกครั้งที่รัน (ไม่ dedupe)

### tools/enforce_voucher_expiry.py

- **หน้าที่:** ทำงานตามลำดับในฟังก์ชัน `run` ดังนี้
  1. ตั้ง `voucher.status = 'expired'` ให้ voucher ที่หมดอายุ
  2. ตั้ง `used_up` เมื่อใช้เกิน `quota_mb` และตั้ง flag quota
  3. หา session ที่ยังเปิดอยู่ (`ended_at IS NULL`) ของ voucher ที่ไม่ active หรือเจ้าของถูกระงับ แล้วสั่ง `ndsctl deauth <mac>` ถ้าตัดสำเร็จจึงปิด session ในฐานข้อมูล
  4. ปิด session ที่ openNDS ไม่มี MAC นั้นแล้ว (สถานะ `gone`)
  5. ตัด (`deauth`) MAC ที่ openNDS ให้ใช้เน็ตแต่ไม่มี session ในฐานข้อมูล (orphan, N44) และบันทึก audit `orphan_deauth`

  (`tools/enforce_voucher_expiry.py` docstring และฟังก์ชัน `run`)
- **รันอย่างไร:**
  ```bash
  sudo bash -c 'set -a; . /etc/cafe-wifi/secrets.env; set +a; cd /opt/cafe-wifi && PYTHONPATH=/opt/cafe-wifi venv/bin/python -m tools.enforce_voucher_expiry'
  ```
- **อาร์กิวเมนต์:** ไม่มี `main()` เรียก `run()` โดยใช้ `deauth=True` เสมอ ไม่มีโหมด dry-run
- **อ่าน/เขียน:** DB ตาราง `voucher`, `portal_session`, `conn_log` (รวม bytes ผ่าน `common/traffic.py`), `audit_log` และเรียกคำสั่ง `ndsctl json` และ `ndsctl deauth` (สร้าง MAC เป็นตัวพิมพ์เล็ก)
- **Exit code:** `main()` คืน `0` เสมอ ความผิดพลาดที่ไม่ได้จับจะเป็น traceback และ exit code 1 (ตามค่าปริยาย)
- **รันอัตโนมัติ:** ใช่ `cafe-enforce.timer`: `OnBootSec=2min`, `OnUnitActiveSec=5min` (`install.sh` บรรทัด ~2038–2045) ส่วน `cafe-enforce.service` (`install.sh` บรรทัด ~2012–2034) ไม่มี `User=` จึงรันเป็น root พร้อม `NoNewPrivileges=yes`, `PrivateTmp=no`, `ProtectSystem=strict`, `ReadWritePaths=/tmp`, `ProtectHome=yes` และ `RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX`
- **ความปลอดภัย:**
  - **กระทบลูกค้าที่ใช้เน็ตอยู่จริง** การรันด้วยมือจะตัดลูกค้าที่ voucher หมดอายุทันที ไม่มีตัวป้องกันหรือ dry-run
  - ถ้า `deauth` ไม่สำเร็จ โค้ดจะ**ไม่ปิด session ในฐานข้อมูล** (`continue` ในลูป) เพื่อให้รอบถัดไปลองตัดซ้ำ ผลคือ DB กับ openNDS อาจไม่ตรงกันชั่วคราว
  - ถ้าไม่มี `ndsctl` บนเครื่อง จะเตือนและข้ามการตัดด้วย (ไม่ปิด session ใน DB เช่นกัน ตามโค้ดของ `deauth_mac`)
  - ต้องรันด้วย root เพราะ `ndsctl` อ่าน `/etc/config/opennds` (0640 root:root) และต่อ `/tmp/ndsctl.sock` (docstring ของ `deauth_mac`)

### tools/reconcile_pending.py

- **หน้าที่:** สำหรับ pending session ที่รอการยืนยัน ถาม openNDS ด้วย `ndsctl json <mac>` ทีละ MAC ถ้า openNDS ยืนยันว่าเปิดสิทธิ์แล้วจริง (state `auth*`, IP ตรง, เวลาเริ่มหลัง pending) จะเปลี่ยน `portal_session.state` เป็น `authenticated` ปิด session เก่าของ MAC นั้นเป็น `reauth` เพิ่มแถว `device` และลบ `pending_mac_claim` ที่เกี่ยวข้อง ยังมี `purge_orphan_claims()` ลบ claim ที่ไม่มี session และนับ pending ที่หมดเวลา (`tools/reconcile_pending.py`)
- **รันอย่างไร:** โดยปกติให้ timer ทำ หากต้องรันด้วยมือ:
  ```bash
  sudo bash -c 'set -a; . /etc/cafe-wifi/secrets.env; set +a; cd /opt/cafe-wifi && PYTHONPATH=/opt/cafe-wifi venv/bin/python -m tools.reconcile_pending'
  ```
- **อาร์กิวเมนต์:** ไม่มี
- **อ่าน/เขียน:** DB ตาราง `portal_session`, `pending_mac_claim`, `device`, `voucher`, `conn_log`, `audit_log` (action `LOGIN_OK` เมื่อมีการยืนยันอย่างน้อย 1 รายการ) และเรียก `ndsctl json`
- **Exit code:** `main()` คืน `0` เสมอ (ข้อผิดพลาดที่ไม่ได้จับจะได้ exit code 1 ตามค่าปริยาย)
- **รันอัตโนมัติ:** ใช่ `cafe-reconcile.timer`: `OnBootSec=5sec`, `OnUnitInactiveSec=5sec`, `AccuracySec=1s` (`install.sh` บรรทัด ~2069–2080) และ `cafe-reconcile.service` มี `User=root` (`install.sh` บรรทัด ~2050–2066) มี `NoNewPrivileges=yes`
- **ความปลอดภัย:** รันทุก 5 วินาที ไม่พบการใช้ `flock` หรือ lockfile ในโค้ด (มีเพียง DB transaction) จึงไม่ควรรันด้วยมือระหว่างที่ timer ทำงาน ยกเว้นเพื่อดีบัก

### tools/reset_admin.py

- **หน้าที่:** ตั้งรหัสผ่านใหม่ให้ผู้ใช้ใน `staff` ที่ระบุ เมื่อลืมรหัสผ่านผู้ดูแลระบบ (`tools/reset_admin.py`)
- **รันอย่างไร:**
  ```bash
  sudo bash -c 'set -a; . /etc/cafe-wifi/secrets.env; set +a; cd /opt/cafe-wifi && PYTHONPATH=/opt/cafe-wifi venv/bin/python -m tools.reset_admin <username>'
  ```
- **อาร์กิวเมนต์:** `<username>` ตัวเดียวเท่านั้น ถ้าจำนวนอาร์กิวเมนต์ไม่ใช่ 1 จะพิมพ์ docstring แล้วคืน `2`
- **การโต้ตอบ:** ถามรหัสผ่านใหม่และยืนยันด้วย `getpass` (ไม่แสดงบนหน้าจอ) ต้องผ่าน `crypto.check_admin_password`
- **Audit:** เขียน `audit_log` action `staff_reset_password` (target = username, detail มี `actor=` จาก `SUDO_USER` หรือผู้ล็อกอิน และ `via=CLI`) ใน transaction เดียวกับ UPDATE — เขียน audit ไม่ได้ = rollback รหัสผ่านไม่เปลี่ยน
- **อ่าน/เขียน:** อ่าน `staff` ด้วย `username` แล้วอัปเดต `password_hash`, `is_active = 1`, `must_change_password = 0`, `password_changed_at = NOW()` (session เก่าที่ login ด้วยรหัสเดิมจะหลุด)
- **Exit code:** `0` สำเร็จ, `1` ไม่พบผู้ใช้ / รหัสไม่ผ่านเกณฑ์ / ยืนยันรหัสไม่ตรงกัน, `2` จำนวนอาร์กิวเมนต์ผิด
- **รันอัตโนมัติ:** ไม่ (รันด้วยมือ) ไม่พบการอ้างอิงใน `install.sh`
- **ความปลอดภัย:**
  - **จะเปิดใช้งานบัญชีที่ถูกปิดไว้** (`is_active = 1`) ตามคำสั่ง SQL ใน `reset_admin.py`
  - ใช้ได้เฉพาะคนที่มีสิทธิ์ root บนเครื่อง (ตาม docstring)
  - คำสั่งใน `app/admin/templates/setup_closed.html` (บรรทัด 8) ไม่มีการโหลด `secrets.env` และไม่มี `cd` ซึ่งตามโค้ดน่าจะไม่ทำงาน (ไม่ได้ทดสอบ) ดูหัวข้อ[ข้อสังเกต](#ข้อสังเกตจากการอ่านโค้ด)

### tools/export_evidence.py

- **หน้าที่:** ส่งออกแถว `conn_log` และ `dns_log` ในช่วงเวลาที่กำหนดเป็น CSV คู่กับ `manifest_*.json` ที่มี SHA-256 ของไฟล์ ใช้เป็นหลักฐานตามคำสั่งเจ้าหน้าที่ ทุกครั้งที่ส่งออกจะบันทึก audit ก่อนดึงข้อมูล (`log_required`) (`tools/export_evidence.py`)
- **เส้นทางอื่นที่เรียกโมดูลนี้:** หน้าเว็บ `/evidence` ใน `app/admin/views/customers.py` (บรรทัด ~161) ใช้ฟังก์ชัน `export()` เดียวกัน
- **รันอย่างไร:**
  ```bash
  sudo bash -c 'set -a; . /etc/cafe-wifi/secrets.env; set +a; cd /opt/cafe-wifi && PYTHONPATH=/opt/cafe-wifi venv/bin/python -m tools.export_evidence --mac <mac-address> --from <YYYY-MM-DD> --to <YYYY-MM-DD>'
  ```
  ค้นด้วยเลขบัตร **แนะนำให้ไม่ใส่เลขในบรรทัดคำสั่ง** (เลขจะค้างใน shell history / `ps` / sudo log) ใช้แบบใดแบบหนึ่งนี้แทน:
  ```bash
  # พิมพ์ตอนถาม (ไม่แสดงเลขบนจอ)
  sudo bash -c 'set -a; . /etc/cafe-wifi/secrets.env; set +a; cd /opt/cafe-wifi && PYTHONPATH=/opt/cafe-wifi venv/bin/python -m tools.export_evidence --natid --from <YYYY-MM-DD> --to <YYYY-MM-DD>'
  # หรืออ่านจาก stdin หนึ่งบรรทัด
  read -rs NID; echo "$NID" | sudo bash -c '... -m tools.export_evidence --natid-stdin --from <YYYY-MM-DD> --to <YYYY-MM-DD>'; unset NID
  ```
- **อาร์กิวเมนต์:**
  | flag | ค่า | หมายเหตุ |
  |---|---|---|
  | `--mac` | MAC address | กรองเฉพาะเครื่องนี้ (ทำให้เป็นตัวพิมพ์ใหญ่ `:` คั่น ตาม `normalize_mac`) ใช้ร่วมกับ `--natid` ไม่ได้ |
  | `--natid` | เลขบัตร 13 หลัก (ไม่ใส่ค่า หรือ `-` = ถามด้วย getpass เมื่อเป็น TTY / อ่านจาก stdin เมื่อเป็น pipe) | ส่งออกเฉพาะข้อมูลของลูกค้ารายนี้ ถ้าใส่เลขตรง ๆ จะพิมพ์คำเตือนภาษาไทยทาง stderr · ใช้ร่วมกับ `--mac` ไม่ได้ |
  | `--natid-stdin` | (ไม่มีค่า) | อ่านเลขบัตรหนึ่งบรรทัดจาก stdin (TTY = ถามแบบไม่แสดงเลข) · ใช้ร่วมกับ `--mac`/`--natid` ไม่ได้ |
  | `--from` | `YYYY-MM-DD` | บังคับ ใช้ `datetime.fromisoformat` |
  | `--to` | `YYYY-MM-DD` หรือ `YYYY-MM-DDTHH:MM:SS` | บังคับ วันที่เปล่าหมายถึง **สิ้นวันนั้น** (`parse_range_end`) |
  | `--out` | โฟลเดอร์ | ค่าปริยาย `/var/log/cafe-wifi/exports` |

  ไม่ใส่ `--mac` หรือ `--natid` จะส่งออกทุกเครื่อง
- **อ่าน/เขียน:**
  - เขียน `<out>/conn_log_<tag>_<stamp>.csv`, `<out>/dns_log_<tag>_<stamp>.csv` และ `<out>/manifest_<tag>_<stamp>.json` โดย `tag` เป็น MAC ที่ตัด `:` หรือ `customer<id>` และไม่มีเลขบัตรเต็มในชื่อไฟล์ (ตาม docstring) ไฟล์ตั้งสิทธิ์ `0600` สร้างด้วย `O_EXCL`+`O_NOFOLLOW` ไม่เขียนทับไฟล์เดิม — export ซ้ำในวินาทีเดียวกันได้ชื่อต่อท้าย `-2`, `-3`
  - เขียน `audit_log` ด้วย `EXPORT_LOG` สองแถวเมื่อรันจาก CLI: ก่อนดึงข้อมูล (`requested range=... actor=<SUDO_USER/ผู้ล็อกอิน>`) และหลังสำเร็จ (`completed` + จำนวนแถว + sha256 ของแต่ละไฟล์ + โฟลเดอร์ปลายทาง · ไม่มีเลขบัตร)
- **Exit code:** `0` สำเร็จ, `1` ไม่พบลูกค้าตาม `--natid` (พิมพ์ข้อความแล้วคืน 1) ข้อผิดพลาดของ argparse หรือ `ValueError` (เช่น `--to` ก่อน `--from`) ทำให้ `p.error` คืน `2`
- **รันอัตโนมัติ:** ไม่
- **ความปลอดภัย:**
  - ข้อมูลจำนวนมาก เก็บไฟล์ไว้อย่างปลอดภัยและลบด้วยมือเอง
  - `--natid <เลข>` ยังใช้ได้แต่เลขอยู่ใน shell history, `ps` และ sudo log — ใช้ `--natid` เฉย ๆ หรือ `--natid-stdin` แทน (หรือหน้าเว็บ `/evidence`)
  - CLI ไม่มี `staff_id` (ไม่ใช่ session เว็บ) จึงบันทึกผู้ทำใน `detail` เป็น `actor=` (`SUDO_USER` หรือผู้ล็อกอิน) แทน
  - ใน docker-test ใช้ช่วง `2000-01-01`–`2100-01-01` (`docs/docker-test.md`) ซึ่งเป็นการทดสอบเท่านั้น

### tools/restore_keys.py

- **หน้าที่:** กู้คืนกุญแจข้อมูลจากไฟล์ `.cwkey` ที่ดาวน์โหลดจากหน้า "สำรองกุญแจ" แทนเฉพาะสองค่า `NATID_DEK` และ `NATID_PEPPER` ส่วนค่าอื่นในเครื่องปัจจุบันยังคงเดิม (`tools/restore_keys.py`, allowlist `RESTORE`)
- **รันอย่างไร:**
  ```bash
  sudo /opt/cafe-wifi/venv/bin/python -m tools.restore_keys /path/to/<ไฟล์>.cwkey
  sudo /opt/cafe-wifi/venv/bin/python -m tools.restore_keys /path/to/<ไฟล์>.cwkey --check
  ```
  รันจาก `/opt/cafe-wifi` (มี `sys.path` ชี้ไปที่ root ของโปรเจกต์อยู่แล้วในไฟล์)
- **อาร์กิวเมนต์:**
  - `file` (จำเป็น) พาธของไฟล์ `.cwkey`
  - `--check` ตรวจรหัสผ่านและความสมบูรณ์ของไฟล์เท่านั้น ไม่เขียนอะไร
- **ตัวแปรสภาพแวดล้อม:**
  - `CAFEWIFI_RESTORE_PASSPHRASE` รหัสผ่านของไฟล์สำรอง (ถ้าไม่ตั้งจะถามด้วย `getpass`)
  - `ETC_DIR` ค่าปริยาย `/etc/cafe-wifi` ถ้าตั้งค่านี้เอง ไม่ต้องเป็น root (ตามเงื่อนไขในโค้ด)
- **อ่าน/เขียน:**
  - อ่าน `.cwkey`
  - เขียน `<ETC_DIR>/secrets.env` (ย้ายของเดิมไปเป็น `secrets.env.before-restore-<เวลา>` ก่อน) ผ่านไฟล์ชั่วคราว `secrets.env.new`
  - **ถ้า `secrets.env` เดิมไม่มีหรือว่าง จะปฏิเสธ (exit `2`)** — ไม่กู้ทั้งก้อนจากไฟล์สำรอง (FAS_KEY/SECRET_KEY/DB_PASS ของเครื่องเก่าจะไม่ตรงกับเครื่องนี้) ให้กู้ด้วยตัวช่วยกู้คืนแบบเต็มหรือติดตั้งเครื่องใหม่ก่อน
  - ไฟล์ `secrets.env.new` และ `.before-restore-*` สร้างโหมด `0600` ด้วย `O_EXCL` + `fsync` แล้ว `os.replace` + fsync โฟลเดอร์ (สิทธิ์/เจ้าของของไฟล์จริงคัดลอกจาก `secrets.env` เดิม)
- **Exit code:** `0` สำเร็จ หรือกุญแจชุดนี้ใช้อยู่แล้ว, `1` ไม่ใช่ root, `2` ไฟล์ไม่ถูกต้อง หรือไฟล์สำรองไม่มี `NATID_DEK`/`NATID_PEPPER`, `3` รหัสผ่านไฟล์สำรองผิด
- **รันอัตโนมัติ:** ไม่ เรียกจาก `app/setup/restore.py` (บรรทัด ~119–122) ด้วย `restore_keys.merge(...)` ซึ่งเป็นตัวช่วยกู้คืนของ wizard
- **ความปลอดภัย:**
  - หลังกู้ต้องรีสตาร์ท service ตามที่พิมพ์ไว้ท้ายโปรแกรม (`systemctl restart cafe-admin cafe-fas cafe-logger`)
  - ไฟล์ `.before-restore-*` ยังคงมีกุญแจเดิมและต้องเก็บไว้ตามนโยบาย (ไม่มีการลบอัตโนมัติ)
  - ตัวแปรที่ไม่ได้อยู่ใน allowlist จะไม่ถูกเขียนทับ (`FAS_KEY`, `SECRET_KEY`, `DB_PASS` ของเครื่องใหม่คงเดิม ตาม docstring)

### tools/check_router.py

- **หน้าที่:** ตรวจว่าเราเตอร์ของร้านปิด DHCP และ IPv6 Router Advertisement ฝั่ง LAN แล้ว ก่อนเปิด portal โดยส่ง DHCPDISCOVER ด้วย MAC สุ่มแบบ locally administered และส่ง Router Solicitation แล้วฟัง RA (`tools/check_router.py`, ฟังก์ชัน `check`, `probe_dhcp`, `probe_ipv6_ra`)
- **รันอย่างไร:**
  ```bash
  sudo /opt/cafe-wifi/venv/bin/python -m tools.check_router --iface eth0
  python3 tools/check_router.py --iface eth0 --json
  ```
  (ตัวเลือก `--iface` ค่าปริยาย `eth0` ต้องตรงกับพอร์ต LAN ฝั่งลูกค้าของ Pi)
- **อาร์กิวเมนต์:**
  | flag | ค่าปริยาย | หมายเหตุ |
  |---|---|---|
  | `--iface` | `eth0` | อินเทอร์เฟซที่ใช้ทดสอบ |
  | `--dhcp-timeout` | `20.0` วินาที | รอ DHCP OFFER |
  | `--ra-timeout` | `10.0` วินาที | รอ Router Advertisement |
  | `--json` | ปิด | พิมพ์ผลเป็น JSON บรรทัดเดียว |
- **ต้องใช้สิทธิ์:** `CAP_NET_RAW` ไม่จำเป็นต้องเป็น root ใน `cafe-wifi-setup.service` ให้ `AmbientCapabilities=CAP_NET_BIND_SERVICE CAP_NET_RAW` (`image/setup/cafe-wifi-setup.service` บรรทัด 23–24)
- **อ่าน/เขียน:** ไม่เขียนไฟล์และไม่แก้ฐานข้อมูล เป็นการส่งแพ็กเก็ตทดสอบ (DHCPDISCOVER และ Router Solicitation) บนวง LAN ซ้ำตามจำนวนครั้งภายในช่วง timeout
- **Exit code:** `0` ทั้ง DHCP และ IPv6 ปิดแล้ว, `1` อย่างน้อยหนึ่งอย่างยังเปิดอยู่หรือ socket ล้มเหลว (`OSError`)
- **รันอัตโนมัติ:** ไม่ ถูกเรียกโดย wizard ที่ `app/setup/app.py` (บรรทัด ~281) และ `app/setup/apply.py` (บรรทัด ~116) ผ่าน `check_router.check(nic)`
- **ความปลอดภัย:** ปลอดภัยต่อข้อมูล แต่ส่ง DHCPDISCOVER ออกทาง broadcast ทุกครั้งที่รัน ทำให้ DHCP server บนวงเห็นคำขอนี้

### app/logger/run_all.py

- **หน้าที่:** entrypoint ของ `cafe-logger.service` เริ่ม thread สองตัว (`conn_collector` อ่านเหตุการณ์ conntrack และ `dns_collector` อ่าน `dnsmasq.log`) จับ `SIGTERM`/`SIGINT` ให้ปิดนุ่มนวล และรอ collector ทำ flush สูงสุด 20 วินาที (`app/logger/run_all.py`)
- **รันอย่างไร:** ไม่มีคำสั่งรันด้วยมือที่แนะนำ ให้ systemd เป็นผู้จัดการ ตัวอย่างจาก unit:
  ```bash
  /opt/cafe-wifi/venv/bin/python -m logger.run_all
  ```
  (ต้องตั้ง `PYTHONPATH=/opt/cafe-wifi` และ `LOG_DIR` ถ้าไม่ใช่ค่าปริยาย)
- **อาร์กิวเมนต์:** ไม่มี
- **ตัวแปรสภาพแวดล้อม:** `LOG_DIR` ค่าปริยาย `/var/log/cafe-wifi` (ใช้หาพาธ `dnsmasq.log`) และค่า DB จาก `secrets.env`
- **อ่าน/เขียน:** อ่าน conntrack (ผ่าน collector) อ่าน `dnsmasq.log` และเขียนลง DB ตาราง `conn_log` และ `dns_log`
- **Exit code:** `0` ปิดเรียบร้อย, `1` collector ตัวใดตัวหนึ่งหยุดทำงาน หรือ collector ไม่หยุดภายใน 20 วินาทีหลังสั่งปิด
- **รันอัตโนมัติ:** ใช่ `cafe-logger.service` (`install.sh` บรรทัด ~1920–1945): `User=${APP_USER}`, `Type=simple`, `Restart=on-failure`, `RestartSec=10`, `AmbientCapabilities=CAP_NET_ADMIN CAP_NET_RAW`, `KillMode=mixed`
- **ความปลอดภัย:** ไม่ควรรันซ้อนกับ `cafe-logger.service` ที่กำลังทำงาน (ข้อสรุปจากการออกแบบ ไม่ได้ตรวจด้วยการรันจริง) เพราะจะมี collector สองชุดอ่านแหล่งเดียวกัน

---

## ใช้กับ image / SD card

### image/check-image.sh

- **หน้าที่:** ตรวจว่า rootfs ของ image ไม่มีความลับประจำเครื่องติดไป เช่น `secrets.env`, `setup.token`, `tls/server.key`, `config/opennds`, ฐาน `cafewifi`, SSH host keys, random-seed และบัญชีที่มีรหัสผ่านใช้ได้ พร้อมตรวจว่ามีไฟล์ที่ต้องมี เช่น firstboot, `setup/app.py`, `tools/check_router.py`, `venv/bin/python` (`image/check-image.sh`)
- **รันอย่างไร:**
  ```bash
  bash image/check-image.sh <rootfs>
  bash image/check-image.sh --clean <rootfs>
  ```
- **อาร์กิวเมนต์:**
  - `--clean` **ลบ** `etc/ssh/ssh_host_*` และ `var/lib/systemd/random-seed` ใน rootfs ก่อนตรวจ ใช้ตอน build เท่านั้น
  - `<rootfs>` (จำเป็น) พาธของ rootfs ต้องมีโฟลเดอร์ `etc`
- **อ่าน/เขียน:** อ่าน rootfs ทั้งหมดที่ระบุ (`shadow`, `machine-id`, ...) ถ้ามี `--clean` จะลบไฟล์ใน rootfs ด้วย
- **Exit code:** `0` ผ่าน, `1` มีรายการไม่ผ่าน ("ห้ามแจก image นี้"), `2` ไม่ใช่ rootfs
- **รันอัตโนมัติ:** ไม่ เรียกจาก `image/build.sh` บรรทัด 113 ด้วย `bash "${SRC}/image/check-image.sh" /mnt/verify | tee "${name}.check.txt"` เพื่อตรวจ image ที่ build เสร็จ
- **ความปลอดภัย:**
  - `--clean` ทำลายไฟล์ในพาธที่ส่งเข้าไป ห้ามชี้ไปที่ระบบปฏิบัติการจริงของเครื่อง
  - ไม่มีการตรวจ uid ในสคริปต์ ไม่แน่ชัดว่าต้องใช้ root หรือไม่ (ตามที่ `build.sh` ใช้ mount loop จึงต้องมีสิทธิ์)
  - ใช้ตรวจ `.img` ที่ mount แล้วได้ก่อนแจก (ตามคอมเมนต์ในไฟล์)

### image/prepare-sd.ps1

- **หน้าที่:** เขียนไฟล์ `cafewifi.conf` ลงไดรฟ์ bootfs ของการ์ดที่ flash แล้ว โดยมี `GATEWAY_NAME` (ชื่อร้าน), `SETUP_CODE` (8 ตัว แสดงเป็น XXXX-XXXX), `TECH_USER` และ `SSH_PUBKEY` (ถ้ามี) Pi จะอ่านแล้วลบไฟล์นี้เองตอนบูตครั้งแรก (`image/prepare-sd.ps1` ส่วนต้น)
- **รันอย่างไร:**
  ```powershell
  powershell -ExecutionPolicy Bypass -File image\prepare-sd.ps1
  powershell -ExecutionPolicy Bypass -File image\prepare-sd.ps1 -ShopName "<ชื่อร้าน>" -SshKey $HOME\.ssh\<key>.pub
  powershell -ExecutionPolicy Bypass -File image\prepare-sd.ps1 -FactoryReset
  ```
- **อาร์กิวเมนต์:**
  | พารามิเตอร์ | ค่าปริยาย | หมายเหตุ |
  |---|---|---|
  | `-Drive` | ค้นหาอัตโนมัติ | ไดรฟ์ที่มี `config.txt` และ `cmdline.txt` ถ้าพบหลายไดรฟ์จะหยุดและให้ระบุ |
  | `-ShopName` | ถามด้วย `Read-Host` | สูงสุด 64 ตัว ห้ามมี `'` `"` `\` `` ` `` และ `$` |
  | `-SshKey` | ถามด้วย `Read-Host` (ค่าเริ่มต้น `~\.ssh\id_ed25519.pub`) | ต้องเป็น public key เท่านั้น |
  | `-TechUser` | `cafeadmin` | ชื่อผู้ใช้ SSH ของช่าง รูปแบบ `^[a-z_][a-z0-9_-]{0,31}$` |
  | `-FactoryReset` | ปิด | ไม่เขียน `GATEWAY_NAME` และวางไฟล์ `factory-reset` ลงใน bootfs |
- **อ่าน/เขียน:** เขียน `<bootfs>\cafewifi.conf` (UTF-8 ไม่มี BOM) ลบ `SETUP-CODE.txt` ถ้ามี และถ้า `-FactoryReset` จะสร้างไฟล์ว่าง `factory-reset`
- **Exit code:** ใช้ `throw` เมื่อผิดพลาด (ไม่ได้กำหนดค่า exit code เฉพาะ)
- **รันอัตโนมัติ:** ไม่ (รันบน Windows ด้วยมือ)
- **ความปลอดภัย:**
  - setup code แสดงบนหน้าจอครั้งเดียว ต้องจดหรือติดสติกเกอร์ไว้ (ตามข้อความในสคริปต์)
  - `-FactoryReset` ตาม comment ของไฟล์ไม่ลบข้อมูลลูกค้า log และบัญชีแอดมิน แต่เปิดโหมดตั้งค่าใหม่ จึงควรใช้เฉพาะเมื่อจำเป็น
  - ห้ามเลือกไฟล์ private key ให้ `-SshKey` (สคริปต์ตรวจรูปแบบแล้ว)

### image/publish-public.sh

- **หน้าที่:** สร้าง commit สำหรับ repo สาธารณะ โดยคัดลอกเฉพาะไฟล์ใน allowlist `ALLOW` และไฟล์ที่ map ไว้ใน `MAP` (README, `.gitignore`, workflow, รูปภาพ, เว็บไซต์ GitHub Pages) ลง commit ใหม่ที่ชี้ branch `public` ไม่แตะ working tree (`image/publish-public.sh`)
- **รันอย่างไร:**
  ```bash
  bash image/publish-public.sh "<ข้อความ commit>"
  ```
  ไฟล์ไม่ push เอง ตามคอมเมนต์ในสคริปต์ให้รันคำสั่งนี้ต่อเอง (ตามคอมเมนต์):
  ```bash
  git push public refs/heads/public:refs/heads/main
  ```
- **อาร์กิวเมนต์:** ข้อความ commit (จำเป็น)
- **อ่าน/เขียน:** อ่าน git objects ของ HEAD เขียน index ชั่วคราว (`mktemp`) และสร้าง commit ใหม่ แล้ว `git branch -f public` (เขียนทับ branch `public` ในเครื่อง)
- **Exit code:** `0` สำเร็จหรือไม่มีการเปลี่ยนแปลง, `1` มีไฟล์ที่จะเผยแพร่ยังไม่ commit
- **รันอัตโนมัติ:** ไม่
- **ความปลอดภัย:** ใช้ allowlist จึงไม่มีไฟล์นอกรายการหลุดออกไป เพิ่มไฟล์ที่ต้องเผยแพร่ต้องแก้ `ALLOW` ในสคริปต์เอง ขั้นตอน push ต้องทำด้วยมือ

---

## ใช้ในแล็บทดสอบเท่านั้น (lab_*)

ทุกสคริปต์ในหมวดนี้ออกแบบมาเพื่อแล็บ ห้ามรันบนเครื่องที่มีลูกค้าใช้งานจริง ยกเว้นที่ระบุไว้ต่างออกไป

`install.sh` **ไม่คัดลอก** `tools/lab_*` และ `tools/bench_*` ลง `/opt/cafe-wifi` (ลบทิ้งทุกครั้งที่ติดตั้งทับ) — ไฟล์เหล่านี้มีอยู่ใน repo เท่านั้น รันจากเครื่องพัฒนาหรือคัดลอกเข้า Pi เองเมื่อจะทดสอบ

### tools/lab_issue_voucher.py

- **หน้าที่:** ออก voucher ทดสอบผ่านเส้นทาง `/issue` ตัวจริงของ Admin โดยใช้ Flask test client และตั้ง session เป็น `staff_id = 1` (ข้ามเฉพาะขั้นพิมพ์รหัสพนักงาน) พิมพ์ `code password` (`tools/lab_issue_voucher.py`)
- **รันอย่างไร:**
  ```bash
  sudo bash -c 'set -a; . /etc/cafe-wifi/secrets.env; set +a; cd /opt/cafe-wifi && PYTHONPATH=/opt/cafe-wifi venv/bin/python tools/lab_issue_voucher.py <เลขบัตรทดสอบ 13 หลัก> <ชั่วโมง> <จำนวนเครื่อง> [โควตา MB]'
  ```
- **อาร์กิวเมนต์ (ตำแหน่ง):** `natid` (ควรใช้เลขที่ checksum ถูกแต่ไม่ใช่ของคนจริง), `hours`, `devices`, `quota_mb` (ไม่บังคับ ค่าว่างคือไม่จำกัด)
- **อ่าน/เขียน:** เขียนแถว voucher และ audit จริงลงฐานข้อมูลผ่านเส้นทาง `/issue`
- **Exit code:** `1` ถ้า `/issue` ไม่คืน 302 (พิมพ์ข้อความ error ของหน้าเว็บ), ไม่มี exit code ระบุชัดในกรณีสำเร็จ (ได้ `0` ตามค่าปริยาย)
- **รันอัตโนมัติ:** ไม่
- **ความปลอดภัย:** **ข้าม login ของแอดมิน** (ตั้ง session เป็น staff 1 และ role admin) และสร้าง voucher จริงในฐานข้อมูล ห้ามใช้บนระบบจริง

### tools/lab_ra_sim.py

- **หน้าที่:** จำลองเราเตอร์ที่ยังเปิด IPv6 โดยส่ง ICMPv6 Router Advertisement prefix `2001:db8:cafe::/64` ทุกวินาทีบนอินเทอร์เฟซที่กำหนด ใช้ทดสอบ IMG-07 ของ `check_router` (`tools/lab_ra_sim.py`)
- **รันอย่างไร:** รันบนเครื่อง Linux อื่นในวงเดียวกับ Pi
  ```bash
  sudo python3 tools/lab_ra_sim.py --iface eth0 --seconds 40
  sudo python3 tools/lab_ra_sim.py --iface eth0 --seconds 40 --withdraw
  ```
  บน Windows ตาม docstring ให้ใช้ `netsh interface ipv6 ...` แทน
- **อาร์กิวเมนต์:**
  | flag | ค่าปริยาย | หมายเหตุ |
  |---|---|---|
  | `--iface` | `eth0` | อินเทอร์เฟซที่ส่ง |
  | `--seconds` | `40` | ระยะเวลาส่ง |
  | `--withdraw` | ปิด | ส่ง RA ถอนตัว (lifetime 0) เพื่อจำลองการปิด IPv6 |
- **อ่าน/เขียน:** ส่งแพ็กเก็ต raw ผ่าน `AF_PACKET` ไม่เขียนไฟล์
- **Exit code:** `0`
- **รันอัตโนมัติ:** ไม่
- **ความปลอดภัย:** ประกาศ IPv6 ให้เครื่องทุกเครื่องในวงที่ส่งไปเห็น ห้ามรันบนวงลูกค้าจริง

### tools/lab_client.sh

- **หน้าที่:** สร้างลูกค้าจำลองบน Pi เอง ด้วย network namespace และ macvlan บน `eth0` มี MAC ของตัวเอง ขอ IP จาก dnsmasq ด้วย `busybox udhcpc` และวิ่งผ่าน nftables กับ openNDS เหมือนเครื่องจริง (`tools/lab_client.sh` ส่วนหัว)
- **รันอย่างไร (ต้องเป็น root):**
  ```bash
  sudo bash tools/lab_client.sh up <ns> <mac>
  sudo bash tools/lab_client.sh login <ns> <รหัสคำขอ> <รหัสผ่าน>
  sudo bash tools/lab_client.sh run <ns> <คำสั่ง...>
  sudo bash tools/lab_client.sh down <ns>
  ```
  `<ns>` คือชื่อ namespace (ตัวอย่างในสคริปต์ใช้ `cta`) และ `<mac>` ควรเป็นรูปแบบ `02:xx:...` (locally administered)
- **อาร์กิวเมนต์:** คำสั่งย่อย `up`, `down`, `run`, `login`
- **อ่าน/เขียน:**
  - สร้าง `/etc/netns/<ns>/resolv.conf`, `/tmp/udhcpc-<ns>.sh`, `/tmp/client-<ns>.ip` และ cookie jar `/tmp/cj-<ns>`
  - `down` ลบ namespace และไฟล์ชั่วคราวเหล่านี้ ไม่ลบ session ใน openNDS (สคริปต์เตือนให้รัน `ndsctl deauth <mac>` เอง)
- **Exit code:** `up` คืน `1` ถ้าตั้ง MAC ไม่ได้ `login` คืน `1` ถ้าไม่ได้ HTTP 302
- **รันอัตโนมัติ:** ไม่
- **ความปลอดภัย:** แก้ไข network stack ของ eth0 ชั่วคราว ใช้ในแล็บเท่านั้น
- **หมายเหตุ:** `tools/lab_e2e_register.sh` และ `tools/lab_fulltest.sh` อ้างถึง `/root/cafe-client-test/client.sh` ซึ่งไม่อยู่ใน repo ต้องคัดลอกจาก `tools/lab_client.sh` ไปไว้ที่นั่นก่อน (ตามคอมเมนต์ในไฟล์ทั้งสอง)

### tools/lab_e2e_register.sh

- **หน้าที่:** ทดสอบวงจรครบ ลูกค้าจำลองขอใช้งาน (ส่งเลขบัตรทดสอบที่ฝังในสคริปต์และ UA Android), แล้วอนุมัติผ่าน `/requests` จริง (Flask test client ตั้ง `staff_id = 1`), รอ openNDS เปิดสิทธิ์, ทดสอบออกเน็ต และ query ฐานข้อมูลตรวจผล
- **รันอย่างไร:**
  ```bash
  sudo bash tools/lab_e2e_register.sh [4 ตัวท้ายของเลขบัตร (ค่าปริยาย 0010)]
  ```
- **อาร์กิวเมนต์:** ตัวเลข 4 หลักท้ายเลขบัตรที่พนักงานพิมพ์ (ค่าปริยาย `0010`)
- **อ่าน/เขียน:**
  - เขียน `/tmp/approve.py` (ไฟล์ชั่วคราวที่ path คงที่)
  - ใช้ `secrets.env` ผ่าน `env` และเขียนทับ `access_request`/`voucher`/`portal_session` ผ่าน `/requests`
  - เรียก `ndsctl deauth` และ `ndsctl json` กับ MAC ทดสอบ
- **Exit code:** ไม่ได้กำหนดชัด (มีแค่ `set -u`) ผลการรันจึงไม่ได้สะท้อนว่าผ่านหรือไม่ (ไม่แน่ชัด)
- **รันอัตโนมัติ:** ไม่
- **ความปลอดภัย:** อนุมัติคำขอจริงในฐานข้อมูล ใช้แล็บเท่านั้น

### tools/lab_fulltest.sh

- **หน้าที่:** ทดสอบรวมทั้งระบบบน Pi จริงในหลายหมวด ได้แก่ ระบบพื้นฐาน (service, DNS, นาฬิกา, conntrack), ลูกค้าขอใช้งาน, พนักงานเข้า `https://admin.cafe.wifi` และอนุมัติ, ต่อเวลาและปิดสิทธิ์, openNDS คืนสิทธิ์เอง (orphan), SSH จากวงลูกค้า, log/หลักฐาน/การป้องกันการเดารหัส และผลสำรองข้อมูล แต่ละข้อใช้ `PASS`/`FAIL` (`tools/lab_fulltest.sh`)
- **รันอย่างไร:**
  ```bash
  sudo bash tools/lab_fulltest.sh
  FT_SSH_USER=<ชื่อผู้ใช้ SSH> sudo bash tools/lab_fulltest.sh
  ```
  ตัวแปร `FT_SSH_USER` ไม่บังคับ ถ้าไม่ตั้งจะใช้ `cafeadmin` ถ้ามี ไม่เช่นนั้น `ras`
- **อาร์กิวเมนต์:** ไม่มี ใช้ตัวแปร `FT_SSH_USER` เท่านั้น
- **อ่าน/เขียน (สิ่งที่สคริปต์ทำกับระบบจริง):**
  - สร้างหรืออัปเดตบัญชี `ft-staff` ในตาราง `staff` ด้วยรหัสสุ่มต่อรอบ (ไม่ลบแถว)
  - เพิ่ม public key ชั่วคราวลงใน `authorized_keys` ของผู้ใช้ SSH ที่เลือก แล้วลบด้วย `sed` ใน `cleanup`
  - `UPDATE` และ `DELETE` บาง row ของ `rate_attempt`, `portal_session`, `access_request` เฉพาะ MAC ของลูกค้าจำลอง
  - รัน `tools.enforce_voucher_expiry` ด้วยมือในขั้นที่ 5
  - **รีสตาร์ต `cafe-admin`** ในขั้นที่ 7
  - เขียนไฟล์ชั่วคราวที่ `/tmp/ft*`
- **Exit code:** สคริปต์จบด้วย `echo` ทำให้ exit code เป็น `0` เสมอ แม้มี `FAIL` ต้องดูผลจากบรรทัด `== สรุป: PASS n  FAIL m`
- **รันอัตโนมัติ:** ไม่ (รันด้วยมือบน Pi ที่ทดสอบ)
- **ความปลอดภัย:**
  - ต้องรันตอนไม่มีลูกค้าจริงใช้ระบบ เพราะรีสตาร์ต `cafe-admin` และเปลี่ยนสิทธิ์ในฐานข้อมูล
  - สคริปต์ใช้ `trap cleanup EXIT` เพื่อปิดบัญชี `ft-staff` และลบ key ชั่วคราว (ไม่ได้ลบแถวบัญชี เพราะอาจถูกอ้างอิง FK)
  - ข้อความใน `cleanup` ระบุว่าเคยเกิดปัญหาเมื่อพยายามลบ (ดูคอมเมนต์ในไฟล์)

---

## ข้อสังเกตจากการอ่านโค้ด

สิ่งที่พบระหว่างจัดทำเอกสาร ยังไม่ได้แก้ไขใด ๆ (ตามกติกาของงานนี้ไม่ได้แก้ไฟล์อื่น)

1. **คำสั่ง `reset_admin` ในหน้าเว็บไม่ตรงกับโค้ด:** `app/admin/templates/setup_closed.html` บรรทัด 8 แสดงคำสั่ง `sudo /opt/cafe-wifi/venv/bin/python -m tools.reset_admin <username>` โดยไม่โหลด `secrets.env` และไม่มี `cd` หรือ `PYTHONPATH` ตาม docstring ของ `tools/reset_admin.py` ควรใช้รูปแบบ `set -a; . secrets.env` ตามเอกสารนี้ (ไม่ได้ทดสอบว่าคำสั่งเดิมล้มเหลวจริง)
2. **`PROJECT_PLAN.md` บรรทัด 1198** ยังเขียน `sudo -E ... tools.reset_admin admin` ซึ่ง docstring ของ `reset_admin.py` ระบุว่าใช้ไม่ได้
3. **`export_evidence` ไม่บันทึกผู้ดำเนินการในโหมด CLI:** `_cli()` เรียก `export(...)` โดยไม่ส่ง `staff_id` ทำให้ `audit_log` มี `staff_id` ว่าง ตามโค้ดที่อ่าน (เส้นทางเว็บอาจส่งค่าไปต่างจากนี้ ไม่ได้ตรวจ)
4. **`--natid` รับเลขบัตรเต็มทางบรรทัดคำสั่ง** ค่าอาจค้างใน shell history และ `ps` ได้
5. **`lab_fulltest.sh` ไม่คืน exit code ตามผลทดสอบ** แม้มี FAIL ก็จบด้วย `0`
6. **สคริปต์แล็บพึ่ง `/root/cafe-client-test/client.sh` ที่ไม่มีใน repo** (`lab_e2e_register.sh`, `lab_fulltest.sh`)
7. **`lab_e2e_register.sh` เขียน `/tmp/approve.py` ที่ path คงที่** อาจถูกแทนที่ก่อนรันได้ในเครื่องที่มีผู้ใช้หลายคน (ใช้แล็บเท่านั้น)
8. **`enforce_voucher_expiry.py` และ `reconcile_pending.py` ไม่มี lockfile หรือ flock** ถ้ารันซ้อนกับ timer อาจทำงานทับกันได้ (ไม่ได้ทดสอบ)
9. **`check_disk` ระดับ warn ไม่ทำให้ exit code เป็น 1** ตั้งใจตามโค้ด ถ้าต้องการให้ monitor ภายนอกจับได้ต้องอ่าน `alert.log` หรือ journal
