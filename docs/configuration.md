# อ้างอิงการตั้งค่า (Configuration Reference)

เอกสารนี้รวบรวมตัวแปรสภาพแวดล้อม ไฟล์/เส้นทางบน Pi พอร์ตที่เปิด systemd unit/timer และค่าที่ปรับได้ (tunables)
ของ Cafe-WiFi โดยอ้างอิงจากโค้ดจริง (`install.sh`, `image/firstboot/`, `image/setup/`, `app/`, `tools/`) ไม่ใช่ PROJECT_PLAN.md
ขั้นตอนติดตั้งดู [install-from-image.md](install-from-image.md) ส่วนการต่อเราเตอร์ ISP ดู [isp-router-runbook.md](isp-router-runbook.md)

**สารบัญ**

1. [ตัวแปรสภาพแวดล้อม (`/etc/cafe-wifi/secrets.env`)](#1-ตัวแปรสภาพแวดล้อม)
2. [ความไม่สอดคล้องของตัวแปร](#2-ความไม่สอดคล้องของตัวแปร)
3. [ไฟล์และเส้นทางบน Pi](#3-ไฟล์และเส้นทางบน-pi)
4. [พอร์ตและ listener](#4-พอร์ตและ-listener)
5. [systemd units และ timers](#5-systemd-units-และ-timers)
6. [ค่าที่ปรับได้ (Tunables)](#6-ค่าที่ปรับได้-tunables)

> หมายเหตุ: ตัวอย่างค่าในเอกสารนี้เป็น placeholder ทั้งหมด ห้ามนำค่าจริงของเครื่องใดมาใส่ในเอกสาร/Git
> เว็บเซิร์ฟเวอร์หน้าบ้านคือ **nginx** (ไม่ใช่ Caddy) และ DHCP/DNS คือ **dnsmasq**

---

## 1. ตัวแปรสภาพแวดล้อม

ไฟล์ `/etc/cafe-wifi/secrets.env` (mode `0640`, `root:cafewifi`) ถูกเขียนโดย `gen_secrets()` ใน `install.sh:722-830`
(เขียนลง `secrets.env.new` แล้ว `mv` แบบ atomic) และโหลดผ่าน `EnvironmentFile=` ของทุก service ที่เป็นโค้ดของเรา
(`cafe-fas`, `cafe-admin`, `cafe-logger`, `cafe-maintenance`, `cafe-enforce`, `cafe-reconcile`, `cafe-bypass-detect`, `cafe-wifi-setup`)

**ใครสร้าง:** บน image ผู้สร้างจริงคือ `install.sh --stage firstboot` ที่ `cafe-wifi-firstboot.sh` เรียก (ครั้งแรกที่บูต)
ส่วน `--stage site` (เรียกโดย `app/setup/apply.py` หลัง wizard) **ไม่สุ่มกุญแจใหม่** แต่อัปเดตเฉพาะค่าเครือข่าย/ชื่อร้าน/อายุ log
ในไฟล์เดิม (`install.sh:733-763`) ถ้าไม่มี `NATID_DEK` ในไฟล์เดิมจะ `die` และไม่แตะต่อ
ติดตั้งแบบ `install.sh` ตรง ๆ (ไม่ผ่าน image) ก็สร้างครั้งแรกที่ `gen_secrets()` เช่นกัน

### 1.1 กุญแจและฐานข้อมูล

| ตัวแปร | ความหมาย | ค่าเริ่มต้น | ผู้สร้าง | ผู้อ่าน (โค้ด) |
|---|---|---|---|---|
| `DB_HOST` | host ของ MariaDB | `127.0.0.1` (ฮาร์ดโค้ดใน `install.sh:782`) | install.sh | `app/common/db.py:13`, `tools/backup_db.py:230` |
| `DB_PORT` | พอร์ต MariaDB | `3306` | install.sh | `app/common/db.py:14`, `tools/backup_db.py:231` |
| `DB_NAME` | ชื่อ DB | `cafewifi` | install.sh (ไม่มี flag; ตัวแปรที่ install.sh:61) | `app/common/db.py:17`, `tools/backup_db.py:224`, `tools/restore_keys.py:114` |
| `DB_USER` | ผู้ใช้ DB | `cafewifi` | install.sh | `app/common/db.py:15`, `tools/backup_db.py:232` |
| `DB_PASS` | รหัสผ่าน DB (สุ่ม 28 ตัวอักษร `A-Za-z0-9` หรือ `--db-pass`) | สุ่ม | install.sh (`openssl rand -base64 32`) | `app/common/db.py:16`, `tools/backup_db.py:233` (ส่งผ่าน `MYSQL_PWD` ไม่ใส่ใน argv) |
| `NATID_PEPPER` | HMAC pepper ของ hash เลขบัตร (hex 64 ตัว = 32 ไบต์) | สุ่ม `openssl rand -hex 32` | install.sh | `app/common/crypto.py` (ผ่าน `os.environ`), `app/setup/restore.py:99`, `app/common/keybackup.py` |
| `NATID_DEK` | กุญแจ AES-256-GCM เข้ารหัสเลขบัตร (hex 64 ตัว) **หายแล้วถอดข้อมูลเดิมไม่ได้** | สุ่ม | install.sh | `app/common/crypto.py`, `app/common/keybackup.py:60`, `tools/restore_keys.py:36` |
| `SECRET_KEY` | Flask session secret (hex 64 ตัว) | สุ่ม | install.sh | `app/admin/app.py:40`, `app/fas/app.py:37`, `app/setup/app.py:47` — ถ้าไม่มี จะใช้ค่าสุ่มชั่วคราวและ log error (login หลุดทุกครั้งที่ restart) |
| `FAS_KEY` | shared key ระหว่าง openNDS กับ FAS (hex 32 ตัว) — ต้องตรงกับ `faskey` ใน `/etc/config/opennds` | สุ่ม `openssl rand -hex 16` | install.sh (รอบหลัง ๆ อ่านจากไฟล์เดิม `install.sh:1757`) | `app/fas/app.py:49` |

`NATID_DEK`, `NATID_PEPPER`, `SECRET_KEY`, `FAS_KEY`, `DB_PASS` คือ `REQUIRED_KEYS` ที่ไฟล์สำรองกุญแจ (`.cwkey`) ต้องมี
(`app/common/keybackup.py:33`) — ดูวิธีสำรอง/กู้ใน [backup-usb.md](backup-usb.md)

### 1.2 เครือข่ายและพอร์ตของแอป

| ตัวแปร | ความหมาย | ค่าที่ install.sh เขียน | ผู้อ่าน |
|---|---|---|---|
| `FAS_PORT` | พอร์ต **backend** ของ gunicorn ฝั่ง portal (bind `127.0.0.1`) | `18080` (= `FAS_BACKEND`, `install.sh:68`) | `app/fas/app.py:374` |
| `ADMIN_PORT` | พอร์ต **backend** ของ gunicorn ฝั่ง Admin (bind `127.0.0.1`) | `18443` (= `ADMIN_BACKEND`, `install.sh:67`) | `app/admin/app.py:392` |
| `NDS_PORT` | พอร์ต gateway ของ openNDS | `2050` | `app/fas/app.py:53` |
| `GATEWAY_NAME` | ชื่อร้าน/ชื่อบนหน้า portal และ `gatewayname` ของ openNDS | `Cafe-Guest` (หรือค่าจาก wizard / `--ssid` / `cafewifi.conf`) | `app/fas/app.py:50`, `app/admin/app.py:206`, `app/setup/app.py:255` |
| `GATEWAY_IP` | IP ของ Pi ฝั่งลูกค้า (ตัดจาก `CLIENT_CIDR`) | `10.10.0.1` | `app/fas/app.py:51`, `app/admin/views/overview.py:36,54` |
| `CLIENT_CIDR` | วง IP ฝั่งลูกค้า (เช่น `10.10.0.1/24`) | `10.10.0.1/24` | `app/logger/conn_collector.py:435` |
| `GATEWAY_AUTHDIR` | ชื่อ authdir ที่ openNDS ใช้ใน FAS | `opennds_auth` | `app/fas/app.py:52` |
| `UPLINK_IP` | IP ของ Pi ฝั่งเราเตอร์ | จาก `--uplink-cidr` (เช่น `192.168.1.2`) | `app/logger/bypass_detector.py:97` |
| `UPLINK_GW` | IP ของเราเตอร์ ISP | จาก `--uplink-gw` | `app/logger/bypass_detector.py:97` |
| `UPLINK_NETWORK` | CIDR วง uplink ที่คำนวณจาก `UPLINK_CIDR` (`cidr_to_network`) | เช่น `192.168.1.0/24` | `app/logger/bypass_detector.py:88` |
| `SSH_ALT_PORT` | พอร์ต SSH สำรองสำหรับวงลูกค้า (key เท่านั้น) | สุ่ม 20000–59999 ครั้งแรก แล้วคงเดิม (`install.sh:176-181`) | `app/admin/views/overview.py:35` (แสดงบนหน้าสถานะ) ; `install.sh:174` อ่านกลับจากไฟล์ |

> ระวัง: `ADMIN_PORT`/`FAS_PORT` ใน `secrets.env` เป็นพอร์ต **หลัง nginx** (18443/18080) ต่างจากพอร์ตที่ผู้ใช้เข้า
> (nginx `ADMIN_PORT` 8443, `FAS_PORT` 8080 ซึ่งเป็นตัวแปรฝั่ง shell ของ install.sh เท่านั้น ไม่ได้ลง secrets.env) ดูหัวข้อ 4

### 1.3 เส้นทาง การเก็บ log และ backup

| ตัวแปร | ความหมาย | ค่าเริ่มต้น (โค้ด / install.sh) | ผู้อ่าน |
|---|---|---|---|
| `ETC_DIR` | โฟลเดอร์ config | `/etc/cafe-wifi` | `app/admin/app.py:34`, `app/setup/*.py`, `tools/restore_keys.py:34` |
| `LOG_DIR` | โฟลเดอร์ log | `/var/log/cafe-wifi` | `app/admin/app.py:36`, `app/common/health.py:164`, `app/logger/{integrity,run_all,telemetry}.py`, `tools/{backup_db,check_disk}.py` |
| `LOG_RETENTION_DAYS` | อายุเก็บ log (วัน); ขั้นต่ำตามกฎหมาย 90 (`purge_old_data.py:40`, wizard `netinfo.py:19`) | `180` | `tools/purge_old_data.py:110`, `app/logger/integrity.py:338`, `app/common/customer.py:67`, `app/setup/app.py:254` |
| `CUSTOMER_RETENTION_DAYS` | อายุเก็บข้อมูลลูกค้า (ไม่บังคับ; ไม่ตั้ง = ใช้ `LOG_RETENTION_DAYS`) | **ไม่ถูกเขียนลง secrets.env** (ดูหัวข้อ 2) | `tools/purge_old_data.py:113-116`, `app/common/customer.py:68` (ใช้ค่ามากกว่าระหว่างสองตัว) |
| `BACKUP_DIR` | ที่เก็บ dump DB บนเครื่อง | `/var/backups/cafe-wifi` | `tools/backup_db.py:220` |
| `BACKUP_RETENTION_DAYS` | เก็บ dump ในเครื่องกี่วัน | `14` | `tools/backup_db.py:221` |
| `OFFSITE_BACKUP_DIR` | ปลายทางสำเนานอก SD (USB label `CAFEBACKUP`) | `/mnt/cafebackup/cafe-wifi` | `tools/backup_db.py:222` ; ว่าง = ข้ามเงียบ ๆ |
| `OFFSITE_REQUIRE_SEPARATE_DEVICE` | `1` = ต้องเป็นอุปกรณ์แยกจากดิสก์หลัก ไม่งั้นไม่คัดลอก | `1` | `tools/backup_db.py:238` |
| `DISK_WARN_PCT` / `DISK_CRIT_PCT` | เกณฑ์เตือนดิสก์ (%) | `80` / `90` (ไม่ถูกเขียนลง secrets.env — ใช้ default ในโค้ด) | `tools/check_disk.py:83-84`, `app/common/health.py:49-50` |

### 1.4 ตัวแปรที่ไม่ได้อยู่ใน secrets.env (ค่าปริยายในโค้ด / ใช้ตอนทดสอบ-ติดตั้ง)

| ตัวแปร | ความหมาย | ค่าปริยาย | ผู้อ่าน |
|---|---|---|---|
| `RATE_LIMIT_BACKEND` | `db` (ตาราง `rate_attempt`) หรือ `memory` | `db` | `app/common/ratelimit.py:21` — เทสต์ตั้ง `memory` ใน `tests/conftest.py` |
| `BYPASS_ALERT_COOLDOWN_MIN` | นาทีกันแจ้งเตือน bypass ซ้ำ | `60` | `app/logger/bypass_detector.py:95` |
| `CA_PUBLIC_DIR` | โฟลเดอร์ใบรับรองสาธารณะ (ให้ดาวน์โหลด) | `/var/lib/cafe-wifi-ca` | `app/admin/views/overview.py:45` |
| `OPT_DIR` | โฟลเดอร์โค้ด | `/opt/cafe-wifi` | `app/setup/apply.py:27`, `app/setup/restore.py:31` |
| `SETUP_RUN_DIR` | โฟลเดอร์คำขอจาก wizard (tmpfs) | `/run/cafe-wifi-setup` | `app/setup/{app,apply,restore}.py` |
| `APPLY_STATE_DIR` | โฟลเดอร์สถานะของ apply (root) | `/run/cafe-wifi-apply` | `app/setup/{app,apply,restore}.py` |
| `CAFEWIFI_RESTORE_PASSPHRASE` | รหัสผ่านไฟล์ `.cwkey` สำหรับ `tools/restore_keys.py` (ไม่ตั้ง = ถามด้วย `getpass`) | – | `tools/restore_keys.py:73` |

ตัวแปร `CAFEWIFI_*` ของ `cafe-wifi-firstboot.sh` ใช้ทดสอบนอก Pi เท่านั้น (`image/firstboot/test_firstboot.sh`):
`CAFEWIFI_ETC_DIR`, `CAFEWIFI_INSTALL_SH`, `CAFEWIFI_LED_DIR`, `CAFEWIFI_APP_USER`, `CAFEWIFI_SKIP_OS_IDENTITY`,
`CAFEWIFI_NM_CONF_DIR`, `CAFEWIFI_SYSTEMCTL`, `CAFEWIFI_BOOT_DIR` (`cafe-wifi-firstboot.sh:24-36,53`)

### 1.5 ไฟล์ตั้งค่าอื่นที่ผู้ใช้/ช่างวางเอง

**`cafewifi.conf` บน bootfs** (`/boot/firmware` หรือ `/boot`) — อ่านโดย `read_conf()` ใน `cafe-wifi-firstboot.sh:78-100` โดย *ไม่ source* ไฟล์
รับเฉพาะคีย์ที่รู้จัก แล้ว**ลบไฟล์ทิ้ง**หลังใช้เสร็จ:

| คีย์ | ความหมาย |
|---|---|
| `GATEWAY_NAME` | ชื่อร้าน → ส่งเป็น `--ssid` ให้ install.sh |
| `SSH_PUBKEY` | public key ของช่าง → สร้างบัญชีช่าง (ตรวจด้วย `ssh-keygen -l`) |
| `TECH_USER` | ชื่อบัญชีช่าง (ค่าปริยาย `cafeadmin`, `DEFAULT_TECH_USER`) |
| `SETUP_CODE` | รหัสตั้งค่า 8–32 ตัว `A-Z0-9` (ไม่ระบุ = สุ่ม 8 ตัวจากชุด 31 ตัวอักษร แล้วเขียน `SETUP-CODE.txt` ลง bootfs) |

ไฟล์ธง/ไฟล์ว่างบน bootfs: `factory-reset` (วางแล้วบูต = กลับสู่โหมดตั้งค่าโดยไม่ลบข้อมูล, `cafe-wifi-factory-reset.service`) ,`SETUP-CODE.txt`

**พารามิเตอร์ `install.sh`** (`usage()` ที่ `install.sh:264-295`): `--nic`, `--uplink-cidr` (default `192.168.1.2/24`),
`--uplink-gw` (`192.168.1.1`), `--ssh-port`, `--host-dns` (`1.1.1.1,8.8.8.8`), `--client-cidr` (`10.10.0.1/24`),
`--dhcp-range` (`10.10.0.100,10.10.0.250`), `--ssid`, `--admin-port` (`8443`), `--fas-port` (`8080`), `--db-pass`,
`--retention-days` (`180`), `--backup-retention-days` (`14`), `--opennds-ref` (`v10.1.3`), `--trusted-mac`,
`--stage`, `-y`, `--skip-network`, `--skip-opennds`, `--enable-partitions`, `--dry-run`, `--uninstall`
(`DHCP_LEASE=4h`, `NTP_SERVERS=time1.nimt.or.th ...` ตั้งใน `install.sh:60,74` ไม่มี flag)

Wizard (`app/setup/netinfo.py:126-137`) แปลงค่าที่กรอกเป็น `--stage site --nic --uplink-cidr --uplink-gw --client-cidr --dhcp-range --ssid --retention-days`

---

## 2. ความไม่สอดคล้องของตัวแปร

เทียบ `.env.example` ↔ โค้ดที่อ่าน (`os.environ`) ↔ สิ่งที่ `install.sh` เขียนลง `secrets.env`

| ประเด็น | รายละเอียด |
|---|---|
| ใช้ในโค้ดแต่**ไม่มีใน `.env.example`** | `GATEWAY_IP`, `CLIENT_CIDR`, `NDS_PORT`, `GATEWAY_AUTHDIR`, `SSH_ALT_PORT`, `OFFSITE_REQUIRE_SEPARATE_DEVICE` (install.sh เขียนลง secrets.env ทั้งหมด); `RATE_LIMIT_BACKEND`, `BYPASS_ALERT_COOLDOWN_MIN`, `CA_PUBLIC_DIR`, `OPT_DIR`, `SETUP_RUN_DIR`, `APPLY_STATE_DIR`, `CAFEWIFI_RESTORE_PASSPHRASE` (ไม่มีใครเขียนลง secrets.env ใช้ค่า default ในโค้ด) |
| อยู่ใน `.env.example` แต่ install.sh **ไม่เขียน** | `CUSTOMER_RETENTION_DAYS`, `DISK_WARN_PCT`, `DISK_CRIT_PCT` (โค้ดอ่านได้ถ้าเพิ่มเอง; ไม่ตั้ง = fallback/default) |
| `.env.example` ที่ไม่มีโค้ดอ่าน | ไม่พบ — ทุกตัวแปรใน `.env.example` ถูกอ่านอย่างน้อย 1 จุดในโค้ด (`UPLINK_*` อ่านเฉพาะ `bypass_detector.py`) |
| ค่าใน `.env.example` ต่างจากที่ install.sh เขียน | `OFFSITE_BACKUP_DIR` ตัวอย่างคือ `/mnt/usb-backup/cafe-wifi` แต่ install.sh เขียน `/mnt/cafebackup/cafe-wifi` และ **เปิดให้เองแล้ว** (คอมเมนต์ใน `.env.example` ที่บอกว่า install.sh ไม่เขียนค่านี้ **ล้าสมัย**); `.env.example` ไม่มี `OFFSITE_REQUIRE_SEPARATE_DEVICE` ; `.env.example` ไม่มี `SSH_ALT_PORT` |
| ชื่อซ้ำความหมายต่างกัน | `ADMIN_PORT`/`FAS_PORT` ใน install.sh (`8443`/`8080`, พอร์ตของ nginx) ≠ ใน secrets.env/.env.example (`18443`/`18080`, พอร์ต gunicorn) — `install.state` (`install.sh:2349-2350`) บันทึกชุด nginx |
| ค่าปริยายไม่ตรงกัน | `GATEWAY_IP` ปริยายเป็น `10.10.0.1` ใน `fas/app.py:51` แต่ใน `overview.py:36,54` ใช้ `os.environ.get("GATEWAY_IP") or "10.10.0.1"`; `CLIENT_CIDR` ปริยายว่างใน `conn_collector.py:435` (ไม่ใช่ `10.10.0.1/24`) |
| ค่าปริยายของ `LOG_RETENTION_DAYS` | โค้ดใช้ `"180"` เป็น default ใน 4 จุดแยกกัน (ไม่มีค่ากลาง) |
| คอมเมนต์ล้าสมัยในโค้ด | `app/admin/app.py:~66` และ `app/fas/app.py` ยังเขียนว่า rate limit "ในหน่วยความจำ" แต่จริง ๆ ใช้ตาราง `rate_attempt` เป็นหลัก (memory เป็น fallback เมื่อ DB ล่ม — `ratelimit.py:35-37`) |
| ตัวแปรของ app/tools | `tools/lab_*.sh` / `lab_*.py` เป็นสคริปต์ทดสอบแล็บ ไม่อยู่ในขอบเขตเอกสารนี้ |

---

## 3. ไฟล์และเส้นทางบน Pi

| เส้นทาง | วัตถุประสงค์ | สร้างโดย / หมายเหตุ |
|---|---|---|
| `/opt/cafe-wifi/` | โค้ดแอป (`app/`, `tools/`, `install.sh`, `venv/`, `netsetup.sh`, `check_time.sh`) | `OPT_DIR`, `install.sh:714` |
| `/opt/cafe-wifi/venv/` | Python virtualenv (gunicorn ฯลฯ) | `VENV_DIR` |
| `/etc/cafe-wifi/` | config ทั้งหมด (`0750 root:cafewifi`) | `install.sh:715` |
| `/etc/cafe-wifi/secrets.env` | กุญแจ + พารามิเตอร์ (หัวข้อ 1) | `0640 root:cafewifi` |
| `/etc/cafe-wifi/setup.token` | โทเคนครั้งแรกของ Admin (สร้างพร้อม secrets, `install.sh:822-830`) | `0640` |
| `/etc/cafe-wifi/setup-code` | รหัสตั้งค่าของ wizard (ลบเมื่อ wizard เสร็จ) | firstboot / `apply.py` ลบ |
| `/etc/cafe-wifi/.firstboot-done` | ธงบูตแรกเสร็จ | `cafe-wifi-firstboot.sh` (ขั้นสุดท้าย) |
| `/etc/cafe-wifi/.site-done` | ธง wizard เสร็จ (ปิด wizard ถาวร) | `app/setup/apply.py:76`; factory-reset ลบ |
| `/etc/cafe-wifi/install.state` | บันทึกผลติดตั้ง (`INSTALLED_AT`, `NIC`, `LAST_STAGE` ...) | `install.sh:2340-2353` |
| `/etc/cafe-wifi/tls/server.{crt,key}` | ใบรับรอง self-signed ของ Admin (RSA 2048, 825 วัน, SAN `admin.cafe.wifi`, `cafe.wifi`, `localhost`, IP ฝั่งลูกค้า, name-constrained) | `make_tls_cert()` `install.sh:2128-2160`; key `0640 root:cafewifi` |
| `/var/lib/cafe-wifi-ca/cafe-wifi.crt` | สำเนาใบรับรอง (สาธารณะ ไม่มีกุญแจ) ให้เครื่องพนักงานติดตั้งเป็น CA | `CA_PUBLIC_DIR`; ดาวน์โหลด `http://<GATEWAY_IP>:8080/cafe-wifi.crt` |
| `/etc/config/opennds` | config openNDS แบบ UCI (`0640 root`) — **ตัวที่ openNDS อ่านจริง** | `install.sh:1796-1850`; ดูคีย์สำคัญด้านล่าง |
| `/etc/dnsmasq.d/cafe-wifi.conf` | DHCP (`dhcp-range`, lease `4h`), DNS (upstream `1.1.1.1`/`8.8.8.8`), `address=/cafe.wifi/…`, `address=/admin.cafe.wifi/…`, `log-queries` | `install.sh:1361-1398` |
| `/var/lib/misc/dnsmasq.leases` | lease file (ชื่อตายตัว openNDS ใช้ตรวจ) | อ่านโดย `app/common/device_info.py:18` |
| `/etc/nftables.conf` | ruleset (input/forward/nat/raw; `flush ruleset`) แก้แล้ว `nft -f` | `install.sh:1426-1590` |
| `/etc/sysctl.d/99-cafe-wifi.conf` | `ip_forward=1`, `rp_filter=0`, `arp_ignore/announce`, `rmem_max=32 MiB`, `rmem_default=16 MiB` (แก้ ENOBUFS N45) | `install.sh:1254-1262` |
| `/etc/nginx/{conf.d,sites-available}/cafe-wifi.conf` | reverse proxy portal + Admin | `install.sh:2172-2235` |
| `/etc/ssh/sshd_config.d/40-cafe-wifi.conf` | `Port 22` + `Port $SSH_ALT_PORT` (key เท่านั้นผ่าน `Match LocalPort`) | `configure_ssh()` |
| `/etc/NetworkManager/conf.d/99-cafe-wifi-unmanage-<nic>.conf` / `99-cafe-wifi-dns.conf` | ให้ NM ปล่อย NIC และไม่ทับ DNS | `install.sh:1240,153`; factory-reset ลบไฟล์ unmanage |
| `/etc/systemd/resolved.conf.d/99-cafe-wifi.conf` | DNS ของ Pi เอง (กรณีมี resolved) | `install.sh:142` |
| `/etc/logrotate.d/cafe-wifi` | หมุน `*.log` รายวัน → `archive/` (`rotate -1` ไม่ลบเอง, compress, append-only `chattr +a`) | `install.sh:2267-2294` |
| `/etc/fstab` (บรรทัด `LABEL=CAFEBACKUP`) | mount USB สำรอง `/mnt/cafebackup` (`nofail`, automount) | `configure_backup_usb()` `install.sh:232-251` |
| `/var/log/cafe-wifi/` | log ทั้งหมด (`0750 cafewifi`): `install.log`, `<svc>-access.log`/`-error.log`, `dnsmasq.log`, `time-accuracy*.log`, `factory-reset.log`, `backup-status.json`, `collector-*.json` (telemetry), `collector-dns.offset.json` | `LOG_DIR` |
| `/var/log/cafe-wifi/archive/` | log ที่หมุนแล้ว (`.log-YYYY-MM-DD[.gz]`, append-only) | logrotate |
| `/var/backups/cafe-wifi/` | dump DB `cafewifi-YYYYMMDD-HHMMSS.sql.gz` (`0600`) | `tools/backup_db.py:225-226` |
| `/mnt/cafebackup/cafe-wifi/` | สำเนาสำรองบน USB | `OFFSITE_BACKUP_DIR` |
| `/run/cafe-wifi-setup/` | `apply.json` / `restore.json` คำขอจาก wizard (tmpfs) | `RuntimeDirectory` ของ `cafe-wifi-setup.service` |
| `/run/cafe-wifi-apply/` | `status.json`, `apply.log` (root) | `cafe-wifi-apply.service` |
| `/etc/systemd/system/opennds.service.d/cafe-wifi-{heartbeat,orphan-sweep,time-sync}.conf` | drop-in ของ openNDS: ล้าง heartbeat, สั่ง `cafe-enforce` หลัง start 45 วินาที, รอ `time-sync.target` | `install.sh:1724-1745` |
| `/usr/local/sbin/cafe-wifi-firstboot` | สคริปต์บูตแรก/factory-reset | image |

**คีย์ openNDS สำคัญ (`/etc/config/opennds`, `install.sh:1796-1850`)**: `gatewayinterface=cafe-wifi-cli0` (macvlan, `CLI_IFACE`),
`gatewayport=2050`, `fasport=8080`, `faspath=/login`, `fas_secure_enabled=2`, `faskey=<FAS_KEY>`,
`sessiontimeout=1440` (นาที = 24 ชม.), `preauthidletimeout=10`, `authidletimeout=30`, `checkinterval=60`,
`users_to_router` (ดูหัวข้อ 4), `walledgarden_fqdn_list` = captive.apple.com, connectivitycheck.gstatic.com, www.msftconnecttest.com, detectportal.firefox.com, nmcheck.gnome.org,
และ `list trustedmac` ตาม `--trusted-mac`

---

## 4. พอร์ตและ listener

| พอร์ต | บริการ | bind | จากวงลูกค้า (`10.10.0.0/24`) | จาก uplink/เราเตอร์ | หลักฐาน |
|---|---|---|---|---|---|
| 53 udp/tcp | dnsmasq DNS (ดัก DNS ที่ชี้ไป resolver อื่นให้ DNAT มาที่ Pi) | `cafe-wifi-cli0` / `CLIENT_GW` | เข้าได้ | – | `install.sh:1361-1373`, nftables nat prerouting |
| 67 udp | dnsmasq DHCP | `cafe-wifi-cli0` | เข้าได้ (+ `udp sport 68 dport 67` จาก 0.0.0.0) | – | nftables input |
| 2050 tcp | openNDS gateway (`NDS_PORT`) | วงลูกค้า | เข้าได้ | – | nftables input; `gatewayport` |
| 80 tcp | nginx (`default_server`, `server_name cafe.wifi _`) → portal. หมายเหตุ: openNDS มี nat rule ดักพอร์ต 80 ไปหน้า openNDS ก่อนเสมอ | ทุก interface | เข้าได้ | เข้าได้ | `install.sh:2179` |
| 8080 tcp (`FAS_PORT`) | nginx → gunicorn portal `127.0.0.1:18080`; `/cafe-wifi.crt` ดาวน์โหลดใบรับรอง | ทุก interface | เข้าได้ | เข้าได้ | `install.sh:2178-2190` |
| 443 tcp | nginx HTTPS → Admin `127.0.0.1:18443` (`https://admin.cafe.wifi`) | ทุก interface | **เข้าได้** (option B) | เข้าได้ | `install.sh:2205`, memory `admin-access-from-customer-lan` |
| 8443 tcp (`ADMIN_PORT`) | nginx HTTPS เช่นเดียวกัน | ทุก interface | **เข้าได้** (openNDS `users_to_router` ต้องมี `ADMIN_PORT`) | เข้าได้ | `install.sh:2206`, `1841` |
| 22 tcp | sshd (รหัสผ่าน/คีย์ตามปกติ) | ทุก interface | **ถูก drop** | เข้าได้ | nftables input |
| `SSH_ALT_PORT` tcp (สุ่ม 20000–59999) | sshd สำรอง **เฉพาะ publickey** (`Match LocalPort`) | ทุก interface | เข้าได้ แต่จำกัด `ct state new limit rate 6/minute burst 6` | เข้าได้ | `install.sh:1496-ish` (input), `configure_ssh()` |
| 18080 / 18443 tcp | gunicorn portal / Admin (`FAS_BACKEND`/`ADMIN_BACKEND`) | **`127.0.0.1` เท่านั้น** | ไม่ | ไม่ | `install.sh:1895` |
| 3306 tcp | MariaDB | localhost | ไม่ | ไม่ | `DB_HOST=127.0.0.1` |
| 80 tcp (`[::]:80`) | **setup wizard** (ก่อน `.site-done` เท่านั้น; ใช้พอร์ต 80 ร่วมกับ nginx จึงถูกหยุดก่อน `install.sh --stage site`) | `[::]` | – | วงเราเตอร์ (`http://cafewifi.local`) | `cafe-wifi-setup.service` |

หลักการไฟร์วอลล์ (`install.sh:1426-1590`): `input` policy `drop`, **IPv6 drop ทั้งหมด**, `forward` ปิดกั้นลูกค้าไป RFC1918 (`10/8`, `172.16/12`, `192.168/16`),
ลูกค้า↔ลูกค้า (client isolation) และ DoT (853) ส่วน `output` policy `accept`, NAT masquerade วงลูกค้า
openNDS มีชั้นของตัวเองคือ chain `ndsRTR` — การตั้ง `list users_to_router` **แทนที่ค่า default ทั้งหมด** จึงต้องระบุให้ครบ:
`udp 53`, `tcp 53`, `udp 67`, `tcp 22`, `tcp 443`, `tcp ADMIN_PORT`, `tcp SSH_ALT_PORT` (`install.sh:1832-1842`; `gatewayport`/`fasport` openNDS เติมเอง)
ตัวอย่างสถานะที่ตรวจจริงบน Pi อยู่ใน [hardware-test-log.md](hardware-test-log.md) §3.9

---

## 5. systemd units และ timers

### 5.1 services ที่รันค้าง

| Unit | หน้าที่ | หมายเหตุ |
|---|---|---|
| `cafe-fas.service` | portal ลูกค้า (gunicorn `fas.app:app`, `127.0.0.1:18080`) | `--workers 1 --threads 4 --timeout 60`; `Restart=on-failure`, `RestartSec=5`; user `cafewifi` (`install.sh:1879-1895`) |
| `cafe-admin.service` | Admin (gunicorn `admin.app:app`, `127.0.0.1:18443`) | ตัวเดียวกัน |
| `cafe-logger.service` | ตัวเก็บ conn/DNS log (`python -m logger.run_all`) | ต้องการ `AF_NETLINK` (`install.sh:1918-1937`) |
| `opennds.service` | captive portal gateway (build จาก tag `v10.1.3`) | restart = ลูกค้าออนไลน์หลุด จึงไม่ restart ตอนอัปเดต |
| `dnsmasq.service`, `nginx.service`, `nftables.service`, `mariadb.service` | DHCP/DNS, reverse proxy, firewall, DB | จากแพ็กเกจ OS |
| `cafe-wifi-netsetup.service` | ตั้ง IP uplink + macvlan ทุกครั้งที่บูต (oneshot) | `Before=network-online.target dnsmasq nftables opennds` |
| `cafe-wifi-conntrack-acct.service` | เปิด `nf_conntrack_acct`/`timestamp` และ timeout established 7440 | `install.sh:1617-1630` |

### 5.2 timers

| Timer → Service | กำหนดเวลา | งาน |
|---|---|---|
| `cafe-maintenance.timer` | `OnCalendar=*-*-* 03:30:00`, `Persistent=true` (`install.sh:1991-1992`) | รันตามลำดับ (`ExecStart=-` ล้มได้ไม่หยุดตัวถัดไป): `tools.purge_old_data` → `tools.backup_db` → `tools.check_disk` → `logger.integrity` → `check_time.sh` |
| `cafe-enforce.timer` | `OnBootSec=2min`, `OnUnitActiveSec=5min` (`install.sh:2043-2044`) | `tools.enforce_voucher_expiry` — deauth สิทธิ์หมดอายุ/เก็บ session ค้าง (ยังถูกเรียกเพิ่ม 45 วินาทีหลัง openNDS start ผ่าน drop-in) |
| `cafe-reconcile.timer` | `OnBootSec=5sec`, `OnUnitInactiveSec=5sec`, `AccuracySec=1s` (`install.sh:2074-2077`) | `tools.reconcile_pending` — ยืนยันคำขอที่อนุมัติแล้วกับ openNDS (`ndsctl auth`) ; ตั้ง `AccuracySec=1s` เพราะค่า default 1 นาทีทำให้ปิดสิทธิ์ช้า ~26 วินาที |
| `cafe-bypass-detect.timer` | `OnBootSec=1min`, `OnUnitActiveSec=1min` (`install.sh:2116-2117`) | `logger.bypass_detector` — หาอุปกรณ์แปลกปลอมในวง uplink |

เปิดใช้งานใน `start_services()` (`install.sh:2306-2334`): `cafe-fas`, `cafe-admin` (restart ทุกครั้ง), `cafe-maintenance.timer`, `cafe-enforce.timer`;
และถ้าไม่ใช้ `--skip-network`: `cafe-logger`, `opennds`, `cafe-bypass-detect.timer`, `cafe-reconcile.timer`

### 5.3 units ของ image (firstboot / wizard)

| Unit | เงื่อนไข / หน้าที่ |
|---|---|
| `cafe-wifi-firstboot.service` | oneshot, `ConditionPathExists=!.firstboot-done`; `TimeoutStartSec=15min`; รันก่อน ssh/nginx/dnsmasq/opennds และ service ของแอป |
| `cafe-wifi-factory-reset.service` | รันเมื่อมีไฟล์ `factory-reset` บน bootfs; กลับสู่โหมดตั้งค่าโดยไม่ลบข้อมูล; `TimeoutStartSec=5min` |
| `cafe-wifi-setup.service` | wizard บน `[::]:80` (gunicorn, user `cafewifi`, `AmbientCapabilities=CAP_NET_BIND_SERVICE CAP_NET_RAW`); เงื่อนไข: มี `.firstboot-done` และ**ไม่มี** `.site-done` |
| `cafe-wifi-apply.path` → `cafe-wifi-apply.service` | ปลุกเมื่อมี `/run/cafe-wifi-setup/apply.json`; รัน `setup.apply` (root); `TimeoutStartSec=40min` |
| `cafe-wifi-restore.path` → `cafe-wifi-restore.service` | ปลุกเมื่อมี `restore.json`; กู้กุญแจ+DB จาก USB; `TimeoutStartSec=40min` |

---

## 6. ค่าที่ปรับได้ (Tunables)

| ค่า | ค่าปัจจุบัน | ตำแหน่ง | หมายเหตุ |
|---|---|---|---|
| เก็บ log (วัน) | 180 (ขั้นต่ำ 90 สูงสุดที่ wizard ยอม 3650) | env `LOG_RETENTION_DAYS`; `app/setup/netinfo.py:19-20`; `tools/purge_old_data.py:38-46` | ต่ำกว่า 90 → `compute_log_cutoff` ปฏิเสธ (ม.26) |
| เก็บข้อมูลลูกค้า (วัน) | = `LOG_RETENTION_DAYS` | env `CUSTOMER_RETENTION_DAYS`; `purge_old_data.py:113-116`; `app/common/customer.py:67-68` | ใช้ค่ามากกว่าเพื่อไม่ลบ log ที่ยังต้องผูกกับตัวตน |
| เก็บ dump DB บนเครื่อง | 14 วัน | env `BACKUP_RETENTION_DAYS`; `tools/backup_db.py:114-121` (นับจาก mtime, pattern `*.sql.gz`) | |
| เกณฑ์ดิสก์ | เตือน 80% / วิกฤต 90% | `tools/check_disk.py:27-28`; env `DISK_WARN_PCT`/`DISK_CRIT_PCT` | บันทึก audit `disk_alert` |
| ความคลาดเคลื่อนนาฬิกา | เตือนเมื่อ > 10 ms | `install.sh` (`check_time.sh`); `app/common/health.py:39` `CHRONY_OK_MS` | NTP: `time1.nimt.or.th`, `time2.nimt.or.th`, `th.pool.ntp.org` (`install.sh:74`) |
| Rate limit login Admin ต่อ IP | 5 ครั้ง / 600 วินาที | `app/admin/app.py:69-70` | ใช้กับ `login:<ip>` และ `setup:<ip>` |
| Rate limit login Admin ต่อ username | 10 ครั้ง / 600 วินาที | `app/admin/app.py:74`, ใช้ที่ `:309` | สูงกว่าต่อ IP เพื่อไม่ให้ลูกค้าแกล้งล็อกบัญชีพนักงานง่ายเกินไป |
| Rate limit กรอกบัตร (portal) | 5 ครั้ง / 600 วินาที | `app/fas/app.py:57-58,197` | |
| Rate limit อื่นใน Admin | ใช้ `rate_limited(bucket)` ค่าปริยาย 5/600s | `app/admin/views/keys.py:57`, `staff.py:163` | |
| ที่เก็บตัวนับ | DB ตาราง `rate_attempt` (`sql/013`) ; ถอยไป memory เมื่อ DB ล่ม | `app/common/ratelimit.py:20-46` | |
| Setup wizard lockout | ผิด 5 ครั้ง → ล็อก 15 นาที | `app/setup/app.py:41-42` | หน้า restore: ผิด `RESTORE_MAX_FAILS=10` (`:43`) |
| Setup wizard session | 60 นาที, cookie `cafewifi_setup`, `SameSite=Strict` | `app/setup/app.py:48-51` | request ≤ 64 KiB |
| Admin session | 8 ชั่วโมง, `Secure`+`HttpOnly`+`SameSite=Lax`; request ≤ 1 MiB | `app/admin/app.py:41-45` | portal request ≤ 256 KiB (`fas/app.py:38`) |
| รหัสตั้งค่า (setup code) | 8 ตัวจาก 31 ตัวอักษร (ตัด I,L,O,0,1) | `cafe-wifi-firstboot.sh:33,110` | จาก `cafewifi.conf` ได้ 8–32 ตัว |
| รหัสคำขอใช้งาน | 4 ตัวอักษร, หมดอายุ 15 นาที, ค้างได้ไม่เกิน 50 คำขอ | `app/common/access.py:15-16,23` | |
| รอ openNDS ยืนยัน session | 180 วินาที | `app/common/access.py:17` `PENDING_SECONDS` | |
| ระยะเวลาสิทธิ์ที่ออกได้ | 1, 2, 3, 4, 8, 12, 24 ชม. | `app/admin/views/access.py:26` `PACKAGE_HOURS` | |
| จำนวนเครื่องต่อสิทธิ์ | สูงสุด 5 | `app/admin/views/access.py:160` | |
| ปุ่มต่อเวลา | +30 / +60 / +120 นาที | `app/admin/views/access.py:163` `EXTEND_CHOICES_MIN` | |
| โควตา (MB) ต่อสิทธิ์ | ไม่บังคับ ต้อง > 0 | `app/admin/views/access.py:30-36` | |
| openNDS timeout | session 1440, preauth idle 10, auth idle 30, checkinterval 60 (นาที/วินาทีตามนิยามของ openNDS) | `install.sh:1822-1825` | ไม่ได้เป็นตัวกำหนดอายุสิทธิ์จริง — ระบบตัดสิทธิ์เองด้วย `cafe-enforce` |
| Grace ก่อนปิด session ที่หายไป | 180 วินาที | `tools/enforce_voucher_expiry.py:104` `GONE_GRACE_SECONDS` | |
| ndsctl busy retry | 20 ครั้ง ห่าง 0.25 วินาที | `tools/enforce_voucher_expiry.py:182-184` | |
| bypass alert cooldown | 60 นาที | env `BYPASS_ALERT_COOLDOWN_MIN`; `bypass_detector.py:95` | |
| DHCP lease | 4 ชั่วโมง | `install.sh:60` `DHCP_LEASE` | ไม่มี flag |
| buffer ของ conntrack | netlink 32 MiB, queue 20000 เหตุการณ์, pending 20000, open conns 131072 | `app/logger/conn_collector.py:44-52` ; `dns_collector.py:131` | ต้องคู่กับ sysctl `rmem_default=16 MiB` |
| รายงาน Admin cache | 300 วินาที | `app/admin/views/overview.py:228` | |
| หลักฐาน (evidence export) | รายคน/เครื่อง ≤ 186 วัน, ทุกเครื่อง ≤ 7 วัน | `app/admin/views/customers.py:151,154` | |
| หน้า log | 50 แถว/หน้า, CSV ≤ 5000 แถว | `app/admin/views/logs.py:27,178` | |
| ทดสอบความเร็ว | cooldown 60 วินาที, ดาวน์ 25 MB/อัป 8 MB, เพดาน 8 วินาที/ขา | `app/common/sysinfo.py:142-144` | ใช้ `speed.cloudflare.com` |
| Passphrase ไฟล์สำรองกุญแจ | ขั้นต่ำ 12 ตัวอักษร | `app/common/keybackup.py:32` | |
| ใบรับรอง Admin | 825 วัน, RSA 2048 | `install.sh:2152` | ออกใหม่ถ้าไม่มี SAN `admin.cafe.wifi`/IP ลูกค้า/NameConstraints |
| ช่วง DHCP / วงลูกค้า | `10.10.0.100–250` ใน `10.10.0.1/24` | `install.sh:57-59` | เปลี่ยนผ่าน wizard หรือ `--client-cidr`, `--dhcp-range` |
| nftables ICMP | echo-request ≤ 10/s, echo-reply จาก uplink ≤ 300/s | `install.sh` ในบล็อก input | |

> ไม่แน่ชัด: เลขบรรทัดในบล็อก heredoc ของ install.sh อาจเลื่อนเมื่อมีการแก้ไฟล์ — ใช้ชื่อฟังก์ชัน
> (`gen_secrets`, `configure_ssh`, `make_tls_cert`, `start_services`, `configure_backup_usb`) ค้นหาแทนเมื่อเลขบรรทัดไม่ตรง
> และตำแหน่งกฎ `SSH_ALT_PORT` ในไฟร์วอลล์ให้ดูใน `write_file /etc/nftables.conf` ของ `install.sh`
