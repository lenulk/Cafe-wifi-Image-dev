# คู่มือดูแลระบบและแก้ปัญหา (Operations & Troubleshooting)

คู่มือนี้สำหรับ **ช่างที่ SSH เข้า Pi ได้แล้ว** — รวม service/timer ที่ต้องรู้จัก, วิธีตรวจสุขภาพ, สำรอง/กู้คืน,
เก็บ/ลบข้อมูลตามอายุ, ตรวจ log integrity, รีเซ็ตรหัส/รีเซ็ตเครื่อง และตารางแก้ปัญหา "อาการ → สาเหตุ → ตรวจ → แก้"
ทุกข้ออ้างอิงจากโค้ดจริง (`install.sh`, `app/`, `tools/`, `image/`) และบันทึกทดสอบบนฮาร์ดแวร์จริงใน `memory/`

เอกสารที่เกี่ยวข้อง (ไม่ซ้ำเนื้อหากัน): [install-from-image.md](install-from-image.md) (ติดตั้ง + ตาราง "แก้ปัญหา" ขั้นต้น) ·
[backup-usb.md](backup-usb.md) (USB สำรอง + กู้คืน) · [isp-router-runbook.md](isp-router-runbook.md) (ตั้งเราเตอร์ร้าน) ·
[hardware-test-log.md](hardware-test-log.md) (หลักฐานทดสอบจริง)

**สารบัญ**
1. [ข้อมูลพื้นฐานที่ต้องรู้ก่อน](#1-ข้อมูลพื้นฐานที่ต้องรู้ก่อน)
2. [Service และ timer](#2-service-และ-timer)
3. [ตรวจสุขภาพระบบ](#3-ตรวจสุขภาพระบบ)
4. [สำรองข้อมูลและกู้คืน](#4-สำรองข้อมูลและกู้คืน)
5. [เก็บ/ลบข้อมูลตามอายุ (retention)](#5-เก็บลบข้อมูลตามอายุ-retention)
6. [ตรวจ log integrity และส่งออกหลักฐาน](#6-ตรวจ-log-integrity-และส่งออกหลักฐาน)
7. [บังคับอายุ voucher](#7-บังคับอายุ-voucher)
8. [รีเซ็ตรหัสแอดมิน / Factory reset](#8-รีเซ็ตรหัสแอดมิน--factory-reset)
9. [ไฟดับ: ระบบทำอะไรตอนบูตกลับมา](#9-ไฟดับ-ระบบทำอะไรตอนบูตกลับมา)
10. [อัปเดต / รัน install.sh ซ้ำอย่างปลอดภัย](#10-อัปเดต--รัน-installsh-ซ้ำอย่างปลอดภัย)
11. [ตารางแก้ปัญหา](#11-ตารางแก้ปัญหา)
12. [ก่อนส่งมอบร้าน (hardening checklist)](#12-ก่อนส่งมอบร้าน-hardening-checklist)

---

## 1. ข้อมูลพื้นฐานที่ต้องรู้ก่อน

| สิ่งที่ต้องรู้ | ค่า | ที่มา |
|---|---|---|
| โค้ดที่รันจริง | `/opt/cafe-wifi/` (venv ที่ `/opt/cafe-wifi/venv`) | `install.sh` (`OPT_DIR`, `VENV_DIR`) |
| ความลับ/ค่าตั้ง (`secrets.env`) | `/etc/cafe-wifi/secrets.env` (รวม `DB_PASS`, `NATID_DEK`, `NATID_PEPPER`, `FAS_KEY`, `SSH_ALT_PORT`) | `install.sh` `ETC_DIR` |
| log ทั้งหมด | `/var/log/cafe-wifi/` (archive ที่ผนึกแล้วอยู่ใต้ `archive/`) | `LOG_DIR` |
| สำรอง DB ในเครื่อง | `/var/backups/cafe-wifi/` (เก็บ 14 วัน) | `BACKUP_DIR`, `BACKUP_RETENTION_DAYS` |
| สำรอง DB บน USB | `/mnt/cafebackup/cafe-wifi/` (USB label `CAFEBACKUP`) | `BACKUP_USB_MNT` |
| SSH | image: ผู้ใช้ช่าง + **SSH key เท่านั้น** (ปิด password); จากวงลูกค้าเข้าได้เฉพาะพอร์ตสำรองแบบสุ่ม (`SSH_ALT_PORT` ใน `secrets.env`) พอร์ต 22 ถูกบล็อกจากวงลูกค้า | `image/stage-cafewifi/01-firstboot/00-run.sh`, `install.sh` บรรทัด ~172-225 |
| หน้าแอดมิน | `https://admin.cafe.wifi` (nginx → `cafe-admin` ที่ 127.0.0.1) | `install.sh` `configure_nginx` |

คำสั่งรัน tool ใน `tools/` ต้องโหลด `secrets.env` เสมอ (ต้องใช้ `DB_PASS`) — `sudo -E` เฉยๆ **ไม่พอ**
(env ของผู้ใช้ช่างไม่มี `DB_PASS`) ใช้รูปแบบนี้:

```bash
sudo bash -c 'set -a; . /etc/cafe-wifi/secrets.env; . /etc/cafe-wifi/db/ops.env; set +a; \
  cd /opt/cafe-wifi && PYTHONPATH=/opt/cafe-wifi venv/bin/python -m tools.<ชื่อ> <args>'
```
(รูปแบบนี้ตรงกับ docstring ของ `tools/reset_admin.py`; ถ้าใช้บ่อย ให้ทำเป็น alias/ฟังก์ชันในเชลล์ช่าง)

> หมายเหตุ: journal ของ systemd บน Pi **ไม่ถาวร** (หายตอนรีบูต — `image/firstboot/cafe-wifi-firstboot.sh` factory_reset()
> จึงเขียน `/var/log/cafe-wifi/factory-reset.log` เก็บไว้เอง) ถ้าจะสืบสาเหตุของเหตุการณ์ก่อนรีบูต
> ต้องดู `journalctl` **ก่อน** รีบูต หรือดูไฟล์ใน `/var/log/cafe-wifi/` แทน

---

## 2. Service และ timer

ชื่อ unit มาจาก `install.sh` (ฟังก์ชันสร้าง unit ~บรรทัด 1342-2125) และ `image/setup/`, `image/firstboot/`

### 2.1 Service ที่ต้องรันตลอด

| Unit | หน้าที่ | หมายเหตุ |
|---|---|---|
| `cafe-fas` | Captive portal (gunicorn 127.0.0.1:`FAS_PORT`, หน้าลงทะเบียน/login ลูกค้า) | `Restart=on-failure` |
| `cafe-admin` | หน้าแอดมิน (gunicorn) | `--workers 1` ตั้งใจ: ตัวนับ rate-limit อยู่ในหน่วยความจำ (ล้างได้ด้วย restart) |
| `cafe-logger` | เก็บ `conn_log` (conntrack) + `dns_log` (dnsmasq) ลง DB — หัวใจของการเก็บ log ตาม ม.26 | `Nice=-5`, รอ `time-sync.target` (ไม่เขียน log ก่อนนาฬิกา sync) |
| `opennds` | Captive-portal gateway (คุมว่าใครออกเน็ตได้) | มี drop-in หลายตัว (ด้านล่าง) |
| `dnsmasq` | DHCP + DNS ฝั่งลูกค้า (บน macvlan `cafe-wifi-cli0`) | ไฟล์ใน `/etc/dnsmasq.d/` **ทุกไฟล์** ถูกอ่านหมด — ห้ามวาง `.bak` ไว้ที่นั่น |
| `nginx` | reverse proxy: portal HTTP / admin HTTPS / ใบรับรอง `.crt` | |
| `mariadb` | ฐานข้อมูล `cafewifi` | |
| `nftables` | firewall + NAT + notrack | ไฟล์จริง `/etc/nftables.conf` (กฎที่แก้สดต้องเขียนลงไฟล์นี้ด้วย ไม่งั้นหายตอนบูต — ดู §11) |
| `cafe-wifi-netsetup` | oneshot ทุกบูต: ตั้ง IP ฝั่ง uplink + สร้าง macvlan `cafe-wifi-cli0` | รันก่อน dnsmasq/nftables/opennds |
| `cafe-wifi-conntrack-acct` | เปิด `nf_conntrack` byte accounting (ต้องรันหลัง nftables โหลด `nf_conntrack`) | `cafe-logger` พึ่งตัวนี้ |
| `chrony` / `chrony-wait` | นาฬิกา (Pi 4 ไม่มี RTC) — openNDS รอ chrony sync ก่อนเปิดให้ลูกค้าออกเน็ต (N23) | drop-in `cafe-wifi-time-sync.conf` |

drop-in ที่ install.sh วางให้ openNDS: `opennds.service.d/cafe-wifi-orphan-sweep.conf` (สั่ง `cafe-enforce` หลัง openNDS
เริ่ม 45 วิ), heartbeat cleanup (N18), time-sync (N23) — ตรวจด้วย `systemctl cat opennds`

### 2.2 Timer / งานเป็นรอบ

| Timer → Service | ความถี่ | ทำอะไร | ดูผล |
|---|---|---|---|
| `cafe-maintenance.timer` → `.service` | ทุกวัน 03:30 (`Persistent=true` — ถ้าเครื่องดับตอนนั้น จะรันชดเชยตอนบูต) | ตามลำดับ: `tools.purge_old_data` → `tools.backup_db` → `tools.check_disk` → `logger.integrity` → `check_time.sh` (ทุกบรรทัดเป็น `ExecStart=-` : ตัวหนึ่งล้มไม่ลากตัวอื่น ผลอยู่ใน journal) | §4-§6 |
| `cafe-enforce.timer` → `.service` | ทุก 5 นาที (เริ่มหลังบูต 2 นาที) | บังคับอายุ/เพิกถอน voucher, quota, ตัด orphan (`tools.enforce_voucher_expiry`) — รันเป็น root + `PrivateTmp=no` โดยเจตนา (ต้องคุยกับ `/tmp/ndsctl.sock`) | §7 |
| `cafe-reconcile.timer` → `.service` | ทุก 5 วินาที (`AccuracySec=1s`) | ยืนยัน session สถานะ `pending` กับ openNDS (`tools.reconcile_pending`) | §7 |
| `cafe-bypass-detect.timer` → `.service` | ทุก 1 นาที | `logger.bypass_detector` — เฝ้า `/proc/net/arp` หา IP/MAC แปลกปลอมในวง uplink (ลูกค้าตั้ง IP เองข้าม portal); มี cooldown ต่อคู่ (ip, mac) `BYPASS_ALERT_COOLDOWN_MIN` (ค่าเริ่ม 60 นาที) | หน้า Admin / `bypass_alert` |

### 2.3 Service ของโหมดตั้งค่า (image เท่านั้น)

| Unit | หน้าที่ |
|---|---|
| `cafe-wifi-firstboot.service` | ทำงาน**ครั้งเดียว**ตอนบูตแรก (ข้ามถ้ามี `/etc/cafe-wifi/.firstboot-done`): สร้างความลับประจำเครื่อง, DB, TLS |
| `cafe-wifi-setup.service` | setup wizard ที่ `http://cafewifi.local` |
| `cafe-wifi-apply.path` / `.service` | wizard สั่ง apply → รัน `install.sh --stage site` (ไม่ตั้ง dead-man switch เพราะไม่ได้มาจาก SSH) |
| `cafe-wifi-restore.path` / `.service` | wizard สั่ง "กู้คืนจากเครื่องเดิม" (กุญแจ + DB จาก USB) |
| `cafe-wifi-factory-reset.service` | ทำงานเฉพาะเมื่อมีไฟล์ `factory-reset` บน bootfs (§8.2) |

### 2.4 คำสั่งตรวจที่ใช้บ่อย

```bash
# ภาพรวม: อะไรล้ม?
systemctl --failed
systemctl is-active cafe-fas cafe-admin cafe-logger opennds dnsmasq nginx mariadb nftables

# timer ถัดไป / ครั้งล่าสุดที่รัน
systemctl list-timers 'cafe-*' --all

# log ของ unit (ย้อนหลัง 1 ชม. / ติดตามสด)
journalctl -u cafe-logger --since "1 hour ago" --no-pager
journalctl -u cafe-enforce -n 50 --no-pager
journalctl -u cafe-maintenance -n 100 --no-pager      # ผลงาน nightly ครบทั้ง 5 งาน
journalctl -fu opennds

# log แอป (gunicorn)
ls /var/log/cafe-wifi/            # cafe-fas-error.log, cafe-admin-error.log, *-access.log, install.log ฯลฯ
```

---

## 3. ตรวจสุขภาพระบบ

### 3.1 หน้า "สถานะระบบ" (`/status`)
แหล่งข้อมูลคือ `app/common/health.py` (`build_status()`) แสดง:
- **service**: `systemctl is-active` ของ `cafe-admin, cafe-fas, cafe-logger, mariadb, nginx, opennds` (ตั้งใจ**ไม่รวม** timer/oneshot
  เพราะ oneshot เป็น `inactive` เป็นปกติ — ดูผลงานจริงของมันจากแถว alert/manifest แทน)
- **ดิสก์**: % ใช้ของ `LOG_DIR` และ `/` (เกณฑ์ `DISK_WARN_PCT` ค่าเริ่ม 80, `DISK_CRIT_PCT` ค่าเริ่ม 90 — `tools/check_disk.py`)
- **นาฬิกา**: ค่า offset ล่าสุดจาก `/var/log/cafe-wifi/time-accuracy.log` (เกณฑ์ผ่านคือ < 10 ms ตาม `CHRONY_OK_MS`;
  `check_time.sh` เขียนทุกคืนพร้อม maintenance — ถ้าไฟล์ยังไม่มี หน้าจะบอกว่ายังไม่เคยตรวจ)
- **collector**: สถานะ `collector-*.json` ที่ `cafe-logger` เขียน (`app/logger/telemetry.py`)
- **ฐานข้อมูล**: จำนวน session ที่ active/pending, แถว `conn_log`/`dns_log` ของวันนี้, เวลาผนึก manifest ล่าสุด
  (ถ้า DB ล่ม หน้า status ไม่ล่มตาม — แสดง error แทน)
- **alert ล่าสุด**: บรรทัดสุดท้ายของ `/var/log/cafe-wifi/alert.log` (เขียนโดย `check_disk`)
- **สำรองข้อมูล**: จาก `/var/log/cafe-wifi/backup-status.json` (เวลา/ขนาด/คัดลอกลง USB ได้ไหม) — ดู [backup-usb.md](backup-usb.md)
- ลิงก์ + ลายนิ้วมือของใบรับรองร้าน `cafe-wifi.crt` (ใช้ตอนติดตั้งบนเครื่องพนักงาน)

> ข้อสังเกต: endpoint `/health` (JSON `{"status":"ok"}`) เก็บไว้ให้ monitoring ภายนอก และ `/status/live` กับ
> `/status/speedtest` มีอยู่ใน `app/admin/views/` — ดู [architecture.md](architecture.md)/[admin-guide.md](admin-guide.md)
> สำหรับรายละเอียดหน้าเว็บ

### 3.2 ตรวจจาก CLI

```bash
# ดิสก์ (รัน tool เดียวกับ nightly; ถ้าเกินเกณฑ์จะเขียน alert.log + audit_log)
sudo bash -c '...ชุดโหลด secrets.env ใน §1...  -m tools.check_disk'
tail -n 5 /var/log/cafe-wifi/alert.log
df -h / /var/log

# นาฬิกา (Pi ไม่มี RTC ต้อง sync chrony)
chronyc tracking
tail -n 3 /var/log/cafe-wifi/time-accuracy.log

# DB
sudo mysql -e "SELECT COUNT(*) FROM cafewifi.conn_log WHERE DATE(ts)=CURDATE();"

# เซสชันที่ openNDS มองเห็นจริง
sudo ndsctl status
sudo ndsctl json                      # ทั้งก้อน (ช้าเมื่อลูกค้าเยอะ — ดู §11)
```

### 3.3 ตรวจเราเตอร์ร้าน (`tools/check_router.py`)
ตรวจว่าเราเตอร์ปิด DHCP และไม่ประกาศ IPv6 RA ฝั่ง LAN แล้วจริง (ถ้ายังเปิด ลูกค้าจะข้าม portal และไม่มี log)
ต้องการ `CAP_NET_RAW` (root); ใช้ raw socket ไม่พึ่ง scapy:

```bash
sudo /opt/cafe-wifi/venv/bin/python /opt/cafe-wifi/tools/check_router.py --iface eth0 [--dhcp-timeout 20] [--ra-timeout 10] [--json]
```
ผ่าน = ไม่มี DHCP OFFER ตอบกลับ และไม่มี RA (ความหมายผลลัพธ์/exit code ดูหัวไฟล์ `tools/check_router.py`;
wizard ใช้ตัวเดียวกันในขั้นตรวจเราเตอร์) · วิธีตั้งเราเตอร์ที่ถูกต้องดู [isp-router-runbook.md](isp-router-runbook.md)

---

## 4. สำรองข้อมูลและกู้คืน

### 4.1 สำรอง DB รายวัน — `tools/backup_db.py`
- รันใน `cafe-maintenance` (03:30) หลัง purge เพื่อให้ไฟล์เล็กลง; dump ไป `BACKUP_DIR` (`/var/backups/cafe-wifi`, mode 0600)
  เก็บ `BACKUP_RETENTION_DAYS` (ค่าเริ่ม 14 วัน)
- แล้วคัดลอกไป `OFFSITE_BACKUP_DIR` = `/mnt/cafebackup/cafe-wifi` (USB label `CAFEBACKUP`) โดยตั้ง
  `OFFSITE_REQUIRE_SEPARATE_DEVICE=1` — **ไม่เสียบ USB = ไม่เขียนลง SD แทนเงียบๆ** แล้วหน้า status เตือน
  (รายละเอียดการเตรียม USB/กู้คืน: [backup-usb.md](backup-usb.md))
- ไฟล์ dump ไม่มี routines/triggers โดยตั้งใจ (schema อยู่ใน `sql/001_schema.sql`, และ `sql/003_partitions.sql` ถ้าเปิด partition) —
  เมื่อ restore เอง: รัน schema ก่อน แล้วค่อย restore dump ทับ (คำอธิบายเต็มใน docstring ของ `tools/backup_db.py`)
- สั่งสำรองทันที: `... -m tools.backup_db` (ใช้ชุดโหลด secrets.env ใน §1) แล้วดู `cat /var/log/cafe-wifi/backup-status.json`

### 4.2 กุญแจเข้ารหัส `.cwkey` — **สำคัญที่สุดอย่างหนึ่ง**
เลขบัตรลูกค้าใน DB (`natid_enc`) เข้ารหัสด้วย `NATID_DEK` และค้นหาด้วย `NATID_PEPPER` ซึ่งอยู่ใน `secrets.env`
**ไฟล์ dump จาก §4.1 ไม่มีกุญแจเหล่านี้** — การ์ดเสียโดยไม่มี `.cwkey` = ถอดเลขบัตรเดิมไม่ได้อีก

- สร้าง: หน้าแอดมิน → เมนู **สำรองกุญแจ** (`/keys`, แอดมินเท่านั้น; โค้ด `app/common/keybackup.py`, view `/keys/backup`)
  ยืนยันรหัสบัญชี + ตั้งรหัสผ่านล็อกไฟล์ (≥ 12 ตัว) → ได้ไฟล์ `cafe-wifi-keys-....cwkey`
- เก็บนอกเครื่อง ≥ 2 ที่ และ **อย่าเก็บในแฟลชไดรฟ์ `CAFEBACKUP` ใบเดียวกับไฟล์ dump**; จดรหัสผ่านไว้คนละที่
- ทำหลัง**ติดตั้งใหม่ทุกครั้ง** (image ใหม่ = กุญแจชุดใหม่ ไฟล์เก่าใช้กับเครื่องใหม่ไม่ได้ ยกเว้นตั้งใจกู้)

### 4.3 กู้คืนเมื่อการ์ดเสีย
ทางหลัก (ผ่านเว็บ): flash การ์ดใหม่ → เสียบ USB `CAFEBACKUP` เดิม → `http://cafewifi.local` → ใส่ setup code →
wizard ขั้น ② **"กู้คืนจากเครื่องเดิม"** → เลือก `.cwkey` + รหัสผ่านไฟล์ (unit `cafe-wifi-restore.service`;
โค้ด `app/setup/restore.py`) — ระบบตรวจว่ากุญแจถอดเลขบัตรใน dump ได้จริงก่อนใช้
ขั้นตอนเต็ม: [backup-usb.md](backup-usb.md) §กู้คืน และ [install-from-image.md](install-from-image.md) "แก้ปัญหา"

ทาง CLI (`tools/restore_keys.py`):
```bash
# ตรวจไฟล์ + รหัสผ่านก่อน (ไม่เขียนอะไร)
sudo /opt/cafe-wifi/venv/bin/python -m tools.restore_keys /path/to/xxx.cwkey --check
# กู้จริง
sudo /opt/cafe-wifi/venv/bin/python -m tools.restore_keys /path/to/xxx.cwkey
# แล้วคืน DB จากไฟล์สำรองล่าสุดบน USB
gunzip -c /mnt/cafebackup/cafe-wifi/cafewifi-<ล่าสุด>.sql.gz | sudo mysql cafewifi
```
พฤติกรรมของ `restore_keys` (จากโค้ด): เก็บ `secrets.env` เดิมเป็น `secrets.env.before-restore-<เวลา>` แล้วแทน
**เฉพาะ `NATID_DEK` และ `NATID_PEPPER`** (allowlist `RESTORE`) — ค่าอื่นเช่น `FAS_KEY`, `DB_PASS` ของเครื่องใหม่คงไว้
(1.0.1 เคยกู้ `FAS_KEY` ทับ ทำให้หน้าลงทะเบียนขึ้น "หน้านี้หมดอายุแล้ว" ทุกเครื่อง — แก้ใน 1.1.0)
ตั้งรหัสผ่านไฟล์ผ่าน env `CAFEWIFI_RESTORE_PASSPHRASE` ได้ถ้าไม่อยากพิมพ์ · ท้ายคำสั่งจะพิมพ์คำสั่ง restart service ให้

---

## 5. เก็บ/ลบข้อมูลตามอายุ (retention)

`tools/purge_old_data.py` (รันใน nightly maintenance):

| ข้อมูล | กติกา | ตัวแปร |
|---|---|---|
| `conn_log`, `dns_log` | ลบแถวที่เก่ากว่า N วัน — **ต่ำกว่า 90 ไม่ได้** (กฎหมาย ม.26; `compute_log_cutoff` ปฏิเสธ) | `LOG_RETENTION_DAYS` (ค่าเริ่ม **180**; ตั้งตอนติดตั้งด้วย `--retention-days`) |
| `customer` | **ไม่ลบแถว** — ล้างข้อมูลระบุตัวตน (anonymize) เฉพาะรายที่ไม่มี voucher active และ `last_seen` เก่ากว่าเกณฑ์ (แถวต้องอยู่เพื่อรักษา FK ของ voucher/device/session) | `CUSTOMER_RETENTION_DAYS` (ไม่ตั้ง = ใช้ค่าเดียวกับ log) |
| `audit_log`, `log_manifest` | **ไม่ลบอัตโนมัติ** (เป็นหลักฐาน) — ลบด้วยมือเท่านั้นถ้าจำเป็น | — |
| ไฟล์ raw log ใน `archive/` | `logger.integrity` ลบเมื่อพ้นอายุ **และ**ตรวจ hash แล้ว; ไฟล์ที่ chain มีปัญหา (เช่น `hash_mismatch`) จะถูก **hold ไม่ลบ** เป็นหลักฐาน | `LOG_RETENTION_DAYS` |
| สำรอง DB | ลบไฟล์เก่ากว่า N วัน ทั้งในเครื่องและบน USB | `BACKUP_RETENTION_DAYS` (14) |

ทุกครั้งที่ลบ จะสรุปจำนวนแถวเขียนลง `audit_log` เอง · การลบรายบุคคลตามคำขอ (PDPA) ทำที่หน้า Customers → erase
(`/customers/<id>/erase`) ดู [admin-guide.md](admin-guide.md)

---

## 6. ตรวจ log integrity และส่งออกหลักฐาน

### 6.1 Hash chain
- logrotate หมุนไฟล์ log เข้า `archive/` (ไฟล์ที่หมุนแล้วเป็น append-only `chattr +a`); `logger.integrity` ผนึกแต่ละไฟล์
  (SHA-256 ผูกกับไฟล์ก่อนหน้า `prev_sha256`) ลงตาราง `log_manifest` — รันทุกคืนใน maintenance
- เจอปัญหา → เขียน `audit_log` action `integrity_failed` (+ ไฟล์ log) และ **exit 1** (journal ของ `cafe-maintenance` จะมีบรรทัดผิดปกติ)
- ตรวจด้วยมือ: หน้าแอดมิน → **แดชบอร์ด** → ปุ่มตรวจ chain (admin, `POST /logs/verify`, `app/admin/views/logs.py`) หรือ CLI:
  ```bash
  sudo bash -c '...ชุดโหลด secrets.env ใน §1...  -m logger.integrity'
  sudo mysql cafewifi -e "SELECT ts, target, detail FROM audit_log WHERE action='integrity_failed' ORDER BY ts DESC LIMIT 20;"
  ```
  (คอลัมน์ `ts, target, detail` ตรงกับ `audit_log` ใน `sql/001_schema.sql`)
- ข้อควรรู้จากเหตุการณ์จริง: ไฟล์ `cafe-fas-access.log-2026-09-16` ในเครื่องแล็บจะฟ้อง `hash_mismatch` ทุกคืน — เป็นของจริง
  (หลักฐานบั๊ก N26 ก่อนแก้ ไม่แก้ย้อนหลัง) ที่เครื่องร้านจริงเจอ `hash_mismatch` = ต้องสืบ ห้ามเมินเฉย (`memory/pi-dhcp-and-portal-milestone.md`)

### 6.2 ส่งออกหลักฐานตามหมายศาล — `tools/export_evidence.py`
หน้าเว็บ: เมนู **Evidence** (`/evidence`); CLI (ต้องโหลด `secrets.env` เหมือน §1):
```bash
... -m tools.export_evidence --mac AA:BB:CC:DD:EE:FF --from 2026-08-01 --to 2026-08-22
... -m tools.export_evidence --natid <เลขบัตร13หลัก> --from 2026-08-01 --to 2026-08-22 [--out /var/log/cafe-wifi/exports]
```
- ผลลัพธ์: CSV แยก `conn_log` / `dns_log` (สิทธิ์ 0600, มีคอลัมน์ `voucher_username`, `natid_masked` — **ไม่มีเลขบัตรเต็ม**)
  + manifest `.json` ที่มี SHA-256 ของแต่ละไฟล์ + บันทึก `audit_log` ว่าใครส่งออกอะไรเมื่อไหร่
- `--natid` โยงเฉพาะแถวที่ผูกกลับหาลูกค้ารายนั้นได้แบบไม่กำกวม (mac + ip + ช่วงเวลา session); แถวที่เข้าได้หลาย session
  ไม่ถูกเดาใส่ให้ใคร — ใช้ `--mac` ค้นต่อเอง
- ก่อนส่งมอบไฟล์ให้เจ้าหน้าที่: เก็บ manifest ไว้คู่กัน และอย่าลืมว่าไฟล์เป็นข้อมูลส่วนบุคคลจำนวนมาก (PDPA) — ดู [privacy-policy-th.md](privacy-policy-th.md)

---

## 7. บังคับอายุ voucher

**`tools/enforce_voucher_expiry.py`** (`cafe-enforce`, ทุก 5 นาที) ทำ 4 อย่าง:
1. voucher หมดอายุ → ตั้ง `status='expired'` + `ndsctl deauth` + ปิด `portal_session`
2. quota (`quota_mb`) → รวมทราฟฟิกจาก `conn_log` (รวม session ที่ยังเปิด) ถ้าเกิน → `used_up` + ตัด (N29)
3. voucher ที่ถูกเพิกถอนที่หน้าแอดมิน → ตัดจริงที่ openNDS
4. **orphan sweep** (N44): MAC ที่ openNDS บอก `Authenticated` แต่ DB ไม่มี session ที่เปิดอยู่/pending → deauth + audit `orphan_deauth`
   (เพราะ openNDS จำและ auth ซ้ำ MAC เก่าเองหลัง restart โดยไม่ถาม DB; drop-in เรียกตัวนี้ 45 วิหลัง openNDS เริ่ม)

กฎสำคัญที่เรียนมาแล้ว: ถ้า `ndsctl deauth` **ล้มเหลว** จะไม่ปิด session ใน DB (รอบหน้าจะได้ลองตัดอีก); ผลลัพธ์
"Client ... not found" ถือว่าตัดสำเร็จ (N28); `ndsctl` ใช้ MAC ตัวพิมพ์เล็กเท่านั้น (N22)

**`tools/reconcile_pending.py`** (`cafe-reconcile`, ทุก 5 วิ): FAS สร้าง session เป็น `pending` ก่อน; ตัวนี้ถาม openNDS ทีละ MAC
(`ndsctl json <mac>`) แล้วยืนยันเป็น `authenticated` หรือปิด session ผีด้วยสาเหตุ `disconnected` (ผ่อนผัน 180 วิ; อ่าน ndsctl
ไม่ได้ = ข้ามรอบ ไม่ใช่ปิดทั้งร้าน)

ตรวจ/สั่งมือ:
```bash
sudo systemctl start cafe-enforce.service && journalctl -u cafe-enforce -n 30 --no-pager
sudo ndsctl status                         # รายชื่อ client + สถานะ
sudo ndsctl deauth aa:bb:cc:dd:ee:ff       # ตัวพิมพ์เล็กเท่านั้น
```
ความหน่วงที่คาดได้ (วัดบน Pi จริง): เพิกถอนจากหน้าแอดมิน → ตัดจริง **~6.7–8.3 วินาที** (ผ่าน reconcile หลังตั้ง `AccuracySec=1s`);
voucher **หมดอายุตามเวลา** ตัดช้ากว่าเวลาหมดอายุได้สูงสุด ~5 นาที (รอบ timer) — เป็นพฤติกรรมออกแบบ ไม่ใช่บั๊ก

---

## 8. รีเซ็ตรหัสแอดมิน / Factory reset

### 8.1 ลืมรหัสแอดมิน — `tools/reset_admin.py`
ต้อง root บนเครื่อง; จะถามรหัสใหม่สองครั้ง (ผ่านเกณฑ์ `crypto.check_admin_password`):
```bash
sudo bash -c 'set -a; . /etc/cafe-wifi/secrets.env; . /etc/cafe-wifi/db/ops.env; set +a; \
  cd /opt/cafe-wifi && PYTHONPATH=/opt/cafe-wifi venv/bin/python -m tools.reset_admin <username>'
```
- ถ้าโดนล็อกหลังใส่รหัสผิด (ตัวนับเก็บในหน่วยความจำ ~10 นาที): `sudo systemctl restart cafe-admin` ล้างได้
- *ข้อสังเกต:* docstring ของ `reset_admin.py` มีทั้งรูปแบบที่ใช้ได้ (โหลด `secrets.env`) — ใช้รูปแบบข้างบน ไม่ใช่ `sudo -E`
- พนักงานคนอื่นลืมรหัส → แอดมินกด reset-password ที่หน้า Staff ได้ (`/staff/<id>/reset-password`) ไม่ต้องใช้ CLI

### 8.2 Factory reset (ตั้งเครือข่ายผิด/ย้ายเราเตอร์แล้วเข้าไม่ได้)
**ไม่ลบข้อมูล** (ลูกค้า, log ตาม ม.26, กุญแจ, บัญชีพนักงาน คงอยู่) — แค่กลับเข้าโหมดตั้งค่า:
1. ถอดการ์ดเสียบคอมพิวเตอร์ Windows → `powershell -ExecutionPolicy Bypass -File image\prepare-sd.ps1 -FactoryReset`
   (วางไฟล์ `factory-reset` + setup code ใหม่ลง bootfs; ใส่ `-SshKey` ได้ถ้ามีช่างคนใหม่)
2. เปิด DHCP ของเราเตอร์กลับชั่วคราว → เสียบการ์ด → บูต
3. `cafe-wifi-factory-reset.service` (`cafe-wifi-firstboot --factory-reset`): ปิด unit ของร้าน (`opennds, dnsmasq, nginx, cafe-*`,
   timer ทั้งหมด), คืน `eth0` ให้ NetworkManager, สร้าง setup code ใหม่, เปิด wizard, ลบ `.site-done`, ลบไฟล์ `factory-reset` แล้ว **รีบูตเอง 1 รอบ (~2 นาที)**
4. เปิด `http://cafewifi.local` ใส่ code ใหม่ → wizard **ข้ามขั้นสร้างแอดมิน** ไปขั้นเครือข่าย
- ทุกขั้นรันซ้ำได้ — ไฟดับกลางทางแล้วบูตใหม่จะทำต่อ; บันทึกการรีเซ็ตอยู่ที่ `/var/log/cafe-wifi/factory-reset.log`
- ถ้ายังไม่เคยผ่านบูตแรก (`.firstboot-done` ไม่มี) จะไม่ทำอะไร (แค่ลบไฟล์ธง)
- ขั้นตอนเต็มและตารางอาการ: [install-from-image.md](install-from-image.md) "แก้ปัญหา"
- ไม่มี "ลบทุกอย่าง" ในตัว — ถ้าต้องล้างข้อมูลจริง ให้ flash image ใหม่ (และ**เก็บ `.cwkey` + dump ก่อน** ถ้ายังต้องใช้ข้อมูลเดิม)

---

## 9. ไฟดับ: ระบบทำอะไรตอนบูตกลับมา

สิ่งที่ออกแบบ/ทดสอบแล้ว (T15, `memory/pi-dhcp-and-portal-milestone.md`; 3 กรณีของนาฬิกาทดสอบรีบูตจริง):
- service ทั้งหมดถูก `enable` — กลับมาเองโดยไม่ต้องแตะ; `cafe-wifi-netsetup` สร้าง macvlan + IP uplink ใหม่ทุกบูต (idempotent)
- ถ้าสาย LAN ยังไม่ต่อ openNDS จะ restart วนเป็นระยะ (รอ macvlan `UP` ซึ่งต้องมี carrier บน eth0) แล้ว**ขึ้นเองภายในไม่กี่วินาทีหลังสายขึ้น** — ปกติ ไม่ใช่บั๊ก
- **นาฬิกา**: Pi 4 ไม่มี RTC จึงบูตมานาฬิกาผิดได้หลายวัน; `chrony-wait` + openNDS รอ sync ได้สูงสุด ~180 วินาทีแล้วเปิดให้ใช้
  (ร้านไม่ล่มแม้ NTP ไม่มา/chronyd พัง) แต่ในสองกรณีนั้น log ช่วงแรกอาจติดเวลาผิด — ทางแก้ถาวรคือ RTC (DS3231) [ข้อจำกัดที่บันทึกไว้]
- **openNDS จำลูกค้าเก่า**: หลังบูต openNDS auth MAC เก่าซ้ำเอง → `cafe-enforce` ตัด orphan ภายใน ~75 วินาที (วัดจริง)
- **maintenance**: `Persistent=true` — ถ้าดับตอน 03:30 จะรันชดเชยตอนบูต
- **firstboot**: ไฟดับระหว่างบูตแรก เสียบใหม่ได้เลย ทุกขั้นรันซ้ำได้ (ธง `.firstboot-done` ปักเป็นขั้นสุดท้าย)
- **หลังรีบูตทุกครั้งที่แก้อะไรสดๆ ให้ทดสอบการใช้งานจริง** (ขอ IP + portal เด้ง) ไม่ใช่แค่ `systemctl is-active` — ดูเคส N17 ใน §11
- ความเสี่ยงที่ยังมี: SD card เสียได้เมื่อไฟดับบ่อย → ต้องมี USB สำรอง + `.cwkey` (§4)

---

## 10. อัปเดต / รัน install.sh ซ้ำอย่างปลอดภัย

`install.sh` ออกแบบให้รันซ้ำได้ (idempotent; เคยรันทับบน Pi จริงหลายรอบ ข้อมูลครบ) แต่มีข้อควรระวัง:

**ก่อนรัน**
1. สำรอง: dump DB + `/etc/cafe-wifi` (เก็บ `secrets.env`!) ไปที่ปลอดภัย เช่น `sudo cp -a /etc/cafe-wifi /root/pre-reinstall-$(date +%Y%m%d)`
2. อย่าให้ NetworkManager คุม `eth0` (อาจแย่ง static IP) — สคริปต์เขียน `99-cafe-wifi-unmanage-eth0.conf` ให้ใน image
3. ห้ามมี `.bak` ใน `/etc/dnsmasq.d/`
4. ถ้า source ถูกส่งมาจาก Windows: ตัด CRLF ทุกไฟล์ข้อความ (`sed -i 's/\r$//'`) — ใช้ `git archive` บน Windows ก็ได้ CRLF; ตรวจ hash ไม่ตรงกับ repo
5. แก้โค้ดบนเครื่องจริง ต้องแก้ทั้ง `/opt/cafe-wifi/` (ตัวรันจริง) และ source ที่ install.sh คัดลอกจาก — ไม่งั้นหายตอนติดตั้งซ้ำ

**ตัวอย่างคำสั่ง** (ค่าเครือข่ายใส่ให้ตรงของร้านเสมอ — รันซ้ำด้วยค่าใหม่จะอัปเดตไฟร์วอลล์และ IP):
```bash
sudo ./install.sh -y --nic eth0 --uplink-cidr <pi-ip>/24 --uplink-gw <router-ip>
# ติดตั้งแบบ image แยกช่วง: --stage build | firstboot | site   (ดูหัวไฟล์ install.sh)
```

**ระหว่าง/หลังรัน**
- ถ้ารันผ่าน SSH จะตั้ง **dead-man switch** (`cafe-wifi-nft-failsafe`): ถ้าไม่ยกเลิกใน 5 นาที `nft flush ruleset` จะล้างไฟร์วอลล์เอง
  → ตรวจว่า SSH/ลูกค้ายังใช้ได้แล้วยกเลิกด้วยคำสั่งที่สคริปต์พิมพ์ (ปกติ `sudo systemctl stop cafe-wifi-nft-failsafe.timer`)
  (ไม่ตั้งเมื่อ wizard เรียก `--stage site` เอง)
- ย้ายเครื่องไปเครือข่ายใหม่: IP uplink เก่าอาจค้างบน eth0 (สคริปต์ใช้ `ip addr add` ไม่ลบเพื่อกันหลุดกลางทาง) → **รีบูต 1 ครั้ง**
- openNDS จะ restart → ลูกค้าถูกจำและ auth ซ้ำชั่วคราว แล้ว orphan sweep จัดการ (§7)
- หลังเสร็จ ทดสอบ: ลูกค้าขอ DHCP ได้ · portal เด้ง · login ด้วยรหัสได้ · `systemctl --failed` ว่าง · `journalctl -u cafe-logger` ไม่มี ERROR
- ถอนการติดตั้ง: `sudo ./install.sh --uninstall` · log การติดตั้ง `/var/log/cafe-wifi/install.log`

> ข้อสังเกต: เอกสารเก่า (`CLAUDE.md`, `PROJECT_PLAN.md`, `CODING_BRIEF.md`) บางส่วนล้าสมัย — ยึดโค้ดใน repo เป็นหลัก
> (`memory/cafe-wifi-source-of-truth.md` เตือนว่าโค้ดจริงบางช่วงอยู่ในทาร์บอล ไม่ใช่บนดิสก์ — ตรวจให้แน่ใจว่าใช้ branch/commit ที่ตั้งใจ)

---

## 11. ตารางแก้ปัญหา

ตารางขั้นต้นสำหรับช่างติดตั้งอยู่ที่ [install-from-image.md → แก้ปัญหา](install-from-image.md#แก้ปัญหา) (mDNS, การ์ดเสีย, LED, setup code,
factory reset, DHCP check) — ตารางนี้เสริมด้วยปัญหาตอนใช้งานจริง

### 11.1 ลูกค้าเชื่อมต่อ/ล็อกอิน

| อาการ | สาเหตุที่เป็นไปได้ | ตรวจ | แก้ |
|---|---|---|---|
| ลูกค้าเชื่อม Wi-Fi แล้วไม่ได้ IP (APIPA 169.254.x.x) | (1) nftables ทิ้ง DHCPDISCOVER จาก `0.0.0.0` — กฎ `udp sport 68 udp dport 67 accept` หายจาก `/etc/nftables.conf` (N17); (2) dnsmasq ไม่ขึ้น (ไฟล์ `.bak` ใน `/etc/dnsmasq.d/`); (3) macvlan ไม่ UP เพราะ eth0 ไม่มี carrier | `grep -n "sport 68" /etc/nftables.conf`; `sudo nft list ruleset \| grep -n "dport 67"`; `systemctl status dnsmasq`; `ip -br link show cafe-wifi-cli0`; **`sudo tcpdump -ni eth0 port 67 or port 68` คู่กันเสมอ** | (1) เพิ่มกฎลง**ไฟล์** แล้ว `sudo nft -f /etc/nftables.conf` (กฎที่ `nft insert` สดๆ หายตอนรีบูต) หรือรัน install.sh ซ้ำ; (2) ย้ายไฟล์ `.bak` ออก; (3) ตรวจสาย/สวิตช์ |
| ลูกค้าได้ IP จากเราเตอร์ร้าน (192.168.x.x) ไม่ใช่ `10.10.0.x` ออกเน็ตตรงข้าม portal | เราเตอร์ยังเปิด DHCP / หรือมี DHCP อื่นในวง (lab: DHCP ของสวิตช์) | `check_router.py` (§3.3); `tcpdump` ดู DHCP OFFER ว่ามาจาก MAC ใด | ปิด DHCP บนเราเตอร์/AP โหมด router ([isp-router-runbook.md](isp-router-runbook.md)); ที่แล็บ Aruba ใช้ `dhcpv4-snooping` + `trust` พอร์ต Pi ([memory/aruba-lab-switch.md]) |
| ผลทดสอบเครือข่ายเป็น "timeout/ไม่ได้รับ" แต่สงสัยว่าเป็นเพราะ kernel/NIC | เกือบทุกครั้งเป็น firewall ของเราเอง/ทดสอบผิดวิธี (เคยสรุปผิดว่า broadcast UDP ไม่ถึง socket — `pi-macvlan-bcmgenet-open-issue.md` ปิดเคสแล้ว) | **ผลลบต้องมี `tcpdump` คู่ขนานยืนยันเสมอ** ว่าแพ็กเก็ตมาถึงจริง; เช็ค `rp_filter` ถ้า source IP ไม่ routable | แก้ที่กฎ nftables ก่อนสงสัย kernel |
| มือถือไม่เด้งหน้า portal เอง | CPD ของ OS ถูกบล็อก/ได้ IPv6 ออกเน็ตข้าม; เราเตอร์ยังประกาศ RA | `check_router.py` (ผล IPv6); `sudo nft list ruleset \| grep -i ip6` | ปิด IPv6 RA บนเราเตอร์; เปิด `http://neverssl.com` หรือ `example.com` ทดสอบ (หมายเหตุ: บางเครือข่ายแล็บบล็อก neverssl ผ่าน eth0) |
| หลัง login ลูกค้าเห็น 404 | URL กลับถูก percent-encode ซ้ำ (N19 — แก้แล้ว) | ดู `cafe-fas-error.log` | อัปเดตเป็นรุ่นปัจจุบัน |
| หน้าลงทะเบียนขึ้น "หน้านี้หมดอายุแล้ว" ทุกเครื่อง | `FAS_KEY` ใน `secrets.env` ไม่ตรงกับที่ openNDS ใช้ (เคยเกิดจาก restore_keys รุ่น 1.0.1 กู้ `FAS_KEY` ทับ) | เทียบ `FAS_KEY` ใน `/etc/cafe-wifi/secrets.env` กับ `/etc/config/opennds` | รัน `install.sh --stage site` ซ้ำ/อัปเดตเป็น 1.1.0+ ([restore_keys.py](../tools/restore_keys.py)) |
| ลูกค้าแจ้งว่าขอสิทธิ์เครื่องใหม่ไม่ได้ ขึ้น "สิทธิ์นี้ใช้ครบ N เครื่องแล้ว" | ครบ `max_devices` ของสิทธิ์นั้น (ค่าเริ่มต้น 2, `sql/001_schema.sql`) — นับทั้งเครื่องที่อนุมัติแล้วและที่รออนุมัติ (`app/common/access.py`) | หน้าคำขอ/ลูกค้าในแอดมิน ดูจำนวนเครื่องของสิทธิ์ | ปกติ — แอดมินเพิ่มจำนวนเครื่อง (`POST /vouchers/<id>/devices`) หรือปิดสิทธิ์เครื่องเดิม |
| ลูกค้ากลับเข้าเน็ตได้ทั้งที่เพิกถอน/หมดอายุแล้ว | (1) `cafe-enforce` ยังไม่ถึงรอบ (≤ 5 นาที สำหรับหมดอายุตามเวลา); (2) openNDS restart แล้ว auth MAC เก่าซ้ำ (N44); (3) `ndsctl` ใช้งานไม่ได้จาก service (สิทธิ์/PrivateTmp) | `journalctl -u cafe-enforce -n 50`; `sudo ndsctl status`; `systemctl cat cafe-enforce \| grep -E "PrivateTmp\|User"` | (1) รอ/สั่ง `systemctl start cafe-enforce`; (2) orphan sweep ทำงาน ~45-75 วิหลัง restart; (3) unit ต้องเป็น root + `PrivateTmp=no` + `ReadWritePaths=/tmp` — รัน install.sh ซ้ำเพื่อคืนค่า |
| เพิกถอนแล้วตัดช้า (20+ วิ) | `AccuracySec` ของ timer ถูกปล่อยเป็นค่าปริยาย 1 นาที ทำให้ systemd รวมรอบ | `systemctl cat cafe-reconcile.timer \| grep Accuracy` ต้องเป็น `1s`; `systemctl list-timers cafe-reconcile.timer` | คืนค่า `AccuracySec=1s` (install.sh ใส่ให้); timer สั้นตัวใหม่ต้องตั้งเองเสมอ และวัดผลปลายทาง ไม่ใช่เรียก worker เอง |
| ลูกค้าค้างสถานะ pending/ออนไลน์ผี ในหน้า dashboard | openNDS ปฏิเสธ auth (หน้า login ค้างจน preauth idle timeout 10 นาที) หรือลูกค้าเดินออกจากร้านเฉยๆ | `systemctl status cafe-reconcile.timer`; `ndsctl json <mac>` | reconcile ปิดเองหลังผ่อนผัน 180 วิ; ถ้า `ndsctl` ช้า/ตอบ busy (ลูกค้าเยอะ) ตรวจ journal ของ `cafe-reconcile` |
| `ndsctl` ตอบ busy / ช้า | ใช้ `ndsctl json` ทั้งก้อนกับลูกค้าจำนวนมากนาน ~1.1 วิ/คน | `time sudo ndsctl json` | ใช้ `ndsctl json <mac>` ทีละเครื่อง (reconcile ทำแบบนี้อยู่แล้ว) |
| openNDS ไม่ขึ้น "already running" | ไฟล์ heartbeat `/tmp/ndscids/heartbeat` ค้างจากการหยุดไม่สะอาด (N18) | `journalctl -u opennds -n 30`; `ls -l /tmp/ndscids/heartbeat` | drop-in ลบให้อัตโนมัติเมื่อไม่มี process จริง; ถ้ายังค้าง ลบไฟล์แล้ว `systemctl restart opennds` |
| openNDS restart วนทุก ~25 วิ | eth0 ไม่มี carrier → macvlan ไม่ UP (รอแค่ 10 วิ) | `ip -br link`; ตรวจสาย/พอร์ตสวิตช์ | ต่อสายแล้วขึ้นเองใน ~3 วิ — ไม่ใช่บั๊ก |
| ใช้เน็ตได้แต่ออกเน็ตไม่ได้หลังรัน install.sh ผ่าน SSH ~5 นาที | dead-man switch ล้างไฟร์วอลล์เพราะไม่ได้ยกเลิก (เจอจริงกับการ์ด B) | `systemctl list-timers \| grep failsafe` ; `sudo nft list ruleset \| head` ว่างหรือไม่ | `sudo ./install.sh ...` ซ้ำ แล้วยกเลิก `systemctl stop cafe-wifi-nft-failsafe.timer` ภายใน 5 นาที |

### 11.2 หน้าแอดมิน / ใบรับรอง

| อาการ | สาเหตุที่เป็นไปได้ | ตรวจ | แก้ |
|---|---|---|---|
| `https://admin.cafe.wifi` บน Chrome Android ของเครื่องที่ยังไม่ได้รับอนุมัติ ขึ้นหน้า "Connect to Wi-Fi" ไม่มีปุ่มข้าม | Chrome ปฏิเสธใบรับรอง self-signed เมื่ออยู่ในสถานะ captive/preauth (Pi ปกติดี — ไม่ต้อง debug ฝั่ง Pi; `memory/admin-https-captive-chrome.md`) | หน้า Status แสดงลิงก์ + SHA-256 ของใบรับรอง | ติดตั้ง `http://<gateway-ip>:8080/cafe-wifi.crt` เป็น **CA certificate** บนเครื่องพนักงานครั้งเดียว (ใบจำกัดชื่อเฉพาะ cafe.wifi/IP ของ Pi ด้วย nameConstraints); ติดตั้ง Pi ใหม่ = ใบใหม่ ต้องติดตั้งซ้ำ |
| ล็อกอินแอดมินไม่ได้ / โดนล็อก | ใส่รหัสผิดเกินกำหนด (ตัวนับในหน่วยความจำ) | — | `sudo systemctl restart cafe-admin`; ลืมรหัส → §8.1 |
| เข้าหน้าแอดมินจากวงลูกค้าไม่ได้ | `openNDS users_to_router` ต้องมีพอร์ตแอดมิน (ค่านี้**แทนที่**ค่าปริยายทั้งหมด) | `grep -n users_to_router /etc/config/opennds` | รัน install.sh ซ้ำ (ออกแบบให้ผู้ใช้วงลูกค้าเข้าแอดมินได้ — `memory/admin-access-from-customer-lan.md`) |

### 11.3 Log, ฐานข้อมูล และหลักฐาน

| อาการ | สาเหตุที่เป็นไปได้ | ตรวจ | แก้ |
|---|---|---|---|
| `cafe-logger` log มี `ENOBUFS` / "losing events" / หลักฐานขาดเมื่อทราฟฟิกหนัก | socket event ของ conntrack-tools 1.4.8 ใช้ `net.core.rmem_default` (208 KB) — `--buffer-size` ไปตั้งผิดซ็อกเก็ต (N45) | `sysctl net.core.rmem_default` ต้อง = `16777216`; `journalctl -u cafe-logger \| grep -i -E "enobufs\|gap"`; `audit_log action=log_gap` | ตั้ง sysctl (install.sh ใส่ให้ใน `/etc/sysctl.d/99-cafe-wifi.conf`) แล้ว **restart `cafe-logger`** (socket ใหม่เท่านั้นที่รับค่าใหม่); ตรวจที่ผลลัพธ์ (เทียบกับ reference listener) ไม่ใช่แค่ syscall |
| `cafe-logger` ไม่ขึ้นหลังรีบูต | นาฬิกายังไม่ sync (`time-sync.target`) / `cafe-wifi-conntrack-acct` ล้ม | `systemctl status cafe-logger cafe-wifi-conntrack-acct chrony`; `chronyc tracking` | ตรวจ NTP ออกได้ (uplink); `chronyc -a makestep`; ถ้าแก้ `chrony.conf` ห้ามมี comment ท้ายบรรทัด (chronyd พัง) และตรวจ `chronyd -p -f <file>` ก่อนรีบูต |
| log ลูกค้าติดวันที่ผิด | บูตมานาฬิกาผิด (ไม่มี RTC) แล้วระบบเปิดให้ใช้ก่อน sync (NTP ไม่มา > 180 วิ) | `grep` ช่วงเวลาผิดใน `conn_log`; `time-accuracy.log` | ติดตั้ง RTC (DS3231) ถาวร; บันทึกเหตุไว้ ไม่แก้แถวย้อนหลังเงียบๆ |
| `integrity_failed` ใน `audit_log` | ไฟล์ archive ถูกแก้/ขาด หรือ (ข้อมูลเก่า) บั๊ก N25/N26 | แดชบอร์ด → ปุ่มตรวจ log (`/logs/verify`); §6.1 | เจอจริง = เก็บหลักฐานไว้ (ระบบ hold ไม่ลบไฟล์นั้น), สืบว่าใครเข้าเครื่อง; รายที่ตรงกับบั๊กเก่าเป็นข้อยกเว้นที่รู้แล้ว |
| ดิสก์ใกล้เต็ม / alert ใน `alert.log` | `dnsmasq.log` โตเร็ว (~5 MB/10 ชม. ตอนสตรีมหนัก), archive ยังไม่ครบอายุ | `df -h`; `du -sh /var/log/cafe-wifi/* \| sort -h \| tail`; `/status` | ลด retention ไม่ได้ต่ำกว่า 90 วัน; ย้าย `LOG_DIR` ไป SSD/พาร์ทิชันแยก; ล้าง backup เก่า; ดิสก์เต็ม = log หยุดเขียน = ผิด ม.26 ต้องแก้ทันที |
| หน้า status เตือน "ไม่ได้คัดลอกลง USB" | ไม่ได้เสียบ `CAFEBACKUP` / label ไม่ตรง / ระบบไฟล์เสีย | `lsblk -o NAME,LABEL,FSTYPE`; `ls /mnt/cafebackup/cafe-wifi`; `cat /var/log/cafe-wifi/backup-status.json` | เสียบ USB label ตรงตัวอักษร ([backup-usb.md](backup-usb.md)) แล้วรอบหน้า (หรือรัน `tools.backup_db` เอง) |
| `mysqldump`/backup ล้ม | สิทธิ์ `DB_USER` แคบโดยตั้งใจ (SELECT/INSERT/UPDATE/DELETE) — อย่าเติม `--routines/--triggers` | `journalctl -u cafe-maintenance` | ดูข้อความ error; อย่าขยายสิทธิ์ DB เพื่อแก้ |
| `cafe-maintenance` "ดูเหมือนผ่าน" แต่บางงานล้ม | `ExecStart=-` กลืน exit code | `journalctl -u cafe-maintenance -n 100` หาบรรทัด error แต่ละโมดูล | อ่าน journal เป็นประจำ (หรือดูหน้า Status) |
| `bypass_alert` ท่วม | อุปกรณ์เดิมในวง uplink โผล่ทุกนาที (เคยเจอ 12,960 แถว/วัน ก่อนมี cooldown) | `SELECT COUNT(*) FROM bypass_alert` | ตรวจว่าเป็นอุปกรณ์ที่รู้จัก (AP/เราเตอร์) ปรับ `BYPASS_ALERT_COOLDOWN_MIN`; ตั้งเราเตอร์ให้ออกเน็ตเฉพาะ IP ของ Pi |

### 11.4 เครือข่ายหน้างาน/แล็บ (กับดักที่เคยเสียเวลา)

| อาการ | สาเหตุที่เป็นไปได้ | ตรวจ | แก้ |
|---|---|---|---|
| ต่อ SSH ผ่าน Wi-Fi (`wlan0`) หลุดและกลับมาไม่ได้ | AP ร้านรบกวนช่องของ Wi-Fi ช่าง (5 GHz ช่องซ้อน); NetworkManager เลิกขอ secret ถาวรเพราะ headless | `nmcli device`; `journalctl -u NetworkManager` | ตั้งช่อง AP ให้ห่างกัน; ทางสำรองเข้า Pi ได้เสมอ: ตั้งการ์ด LAN ของโน้ตบุ๊กเป็น static ในวงเดียวกับ IP ฝั่งเราเตอร์ของ Pi (ไม่ใส่ gateway) แล้ว SSH เข้า IP นั้น (พอร์ต 22 ปิดเฉพาะวงลูกค้า); `nmcli connection up <ชื่อโปรไฟล์>` |
| SSID บน AP ทำให้ log เห็นทั้งร้านเป็นเครื่องเดียว | AP ตั้ง Client IP assignment เป็น Virtual Controller assigned (NAT) | Pi เห็น MAC เดียว/IP เดียวของ AP | ต้องเป็น **Network assigned (bridge)** เท่านั้น และปิด captive portal ของ AP (openNDS ทำหน้าที่นี้) — `memory/aruba-lab-switch.md` |
| ย้ายเครื่องไปที่ใหม่ (เราเตอร์คนละวง) แล้วออกเน็ตไม่ได้ | uplink IP/gw เป็น static ตามเราเตอร์เดิม | `ip -br addr show eth0`; `ip route` | รัน `install.sh -y --nic eth0 --uplink-cidr ... --uplink-gw ...` ใหม่ + รีบูต 1 ครั้ง (หรือใช้ factory reset §8.2 กับ image) |
| แก้สคริปต์แล้วไม่ทำงานบน Pi (`bad interpreter`/`^M`) | ไฟล์ CRLF จาก Windows | `file /opt/cafe-wifi/*.sh` | `sed -i 's/\r$//' <ไฟล์>` |

---

## 12. ก่อนส่งมอบร้าน (hardening checklist)

ทำที่หน้างานก่อนส่งมอบ (รวมกับ checklist ขั้น 7 ใน [install-from-image.md](install-from-image.md#ขั้น-7--ส่งมอบร้าน)):

**การเข้าถึงเครื่อง**
- [ ] รหัสผ่านบัญชีช่าง/SSH ที่ใช้ตอนทดสอบ — เปลี่ยนเป็นของที่ร้าน/ช่างเป็นผู้ตั้งเอง หรือใช้ **SSH key เท่านั้น** (image ปิด password อยู่แล้ว)
  — ผู้ช่วย AI/สคริปต์ **ไม่ควรตั้งรหัสผ่านแทนเจ้าของ**; ให้เจ้าของพิมพ์รหัสเอง (`passwd`)
- [ ] ลบโปรไฟล์ Wi-Fi ของแล็บ/บ้านที่ค้างบน Pi (`nmcli connection show` → `sudo nmcli connection delete <ชื่อ>`) และถอด `authorized_keys` ของผู้ที่ไม่เกี่ยวข้อง
- [ ] ตัดสินใจเรื่อง `wlan0`: ปิดถ้าไม่ใช้ หรือเก็บเป็นช่องทางช่างที่เชื่อม hotspot ของช่างเท่านั้น
  **ห้ามต่อ `wlan0` เข้า SSID ลูกค้าเดียวกับร้าน** (จะได้ IP จาก Pi เองซ้อนกับ `cafe-wifi-cli0` แล้ว routing พัง) —
  ฟีเจอร์ `--service-wifi` ถูกเสนอไว้แต่ **ยังไม่ได้สร้าง** (`memory/pending-service-wifi-reminder.md`)
- [ ] ยืนยันว่า SSH จากวงลูกค้าเข้าได้เฉพาะพอร์ตสำรองด้วย key (พอร์ต 22 ถูกบล็อกจาก `CLIENT_NET`)
- [ ] บัญชีแอดมินของร้านเปลี่ยนรหัสเป็นของร้านเอง · ปิดบัญชีพนักงานที่ไม่ใช้ (หน้า Staff)

**ข้อมูลและสำรอง**
- [ ] USB `CAFEBACKUP` เสียบอยู่ และหน้า Status แสดงสำรองลง USB สำเร็จ
- [ ] ดาวน์โหลด `.cwkey` เก็บนอกเครื่อง ≥ 2 ที่ + จดรหัสผ่านแยกที่ (§4.2)
- [ ] ทดสอบกู้คืนอย่างน้อยหนึ่งครั้ง (ในแล็บ) ว่ารู้ขั้นตอน

**เครือข่ายและการบังคับ**
- [ ] `check_router.py` ผ่าน (ไม่มี DHCP/IPv6 RA จากเราเตอร์) และตั้ง Access Control ให้ออกเน็ตได้เฉพาะ IP ของ Pi
- [ ] ทดสอบจริง 1 รอบด้วยมือถือ: เด้ง portal → ลงทะเบียน/อนุมัติ → ออกเน็ต → เพิกถอน → ถูกตัดภายในไม่กี่วินาที
- [ ] ติดตั้งใบรับรองร้าน (`cafe-wifi.crt`) บนเครื่องพนักงานทุกเครื่อง
- [ ] นาฬิกา sync (`chronyc tracking`) และ `systemctl --failed` ว่าง
- [ ] ชื่อ AP/SSID ตรงกับที่ตั้งใน wizard; AP ตั้ง Network-assigned และปิด captive portal ของ AP

**ส่งมอบความรู้**
- [ ] สอนพนักงาน: อนุมัติลูกค้า · เพิกถอน · ส่งออกหลักฐาน · ลืมรหัสติดต่อใคร
- [ ] ทิ้งช่องทางติดต่อช่างและวิธี factory reset (§8.2) ไว้ให้ร้าน (ไม่ต้องให้ร้านรู้ SSH)

---

*อ้างอิงหลักในคู่มือนี้:* `install.sh` (unit/timer/ค่าเริ่ม) · `app/common/health.py` · `app/common/keybackup.py` ·
`app/logger/integrity.py` · `tools/*.py` · `image/firstboot/cafe-wifi-firstboot.sh` · `image/prepare-sd.ps1` ·
`memory/` (บันทึกทดสอบฮาร์ดแวร์จริง)
