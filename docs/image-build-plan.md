# แผนการทำ Image สำเร็จรูป (Cafe-WiFi OS)

> เป้าหมาย: ติดตั้งระบบแบบ "flash → เสียบสาย → เปิดเว็บ → ใช้งาน" ตาม
> [`install-from-image.md`](install-from-image.md) โดยไม่ต้องใช้ CLI และไม่ต้องต่อ GitHub/PyPI หน้างาน
>
> สถานะ: **แผน** (2026-10-03) — ยังไม่ได้เริ่มลงมือ

---

## 1. หลักการ

1. **ใช้ `install.sh` เดิมเป็นแกน** ไม่เขียนตัวติดตั้งใหม่ — สคริปต์นี้ผ่านการทดสอบบนฮาร์ดแวร์จริงมาแล้ว
   (แก้บั๊ก N17–N44, ผ่าน `lab_fulltest.sh` 49 ข้อ) แค่แบ่งให้รันเป็นช่วง (stage) ได้
2. **ไม่มีความลับใน image** — ทุกค่าสร้างบน Pi แต่ละเครื่องตอนบูตครั้งแรก (§2)
3. **ใน image ไม่มีค่าเฉพาะร้าน** — ค่าเครือข่ายตั้งผ่าน web wizard ที่ร้าน
4. **build ซ้ำได้ผลเหมือนเดิม** — pin เวอร์ชัน OS, openNDS (`v10.1.3`) และแพ็กเกจ Python (`app/requirements.txt`)
5. **ยังไม่เขียนโปรแกรม flash เอง** — ใช้ Raspberry Pi Imager + custom repository JSON ไปก่อน

## 2. ความลับที่ห้ามติดไปกับ image

ถ้าโคลนการ์ดจากเครื่องที่รัน `install.sh` แล้ว ทุกร้านจะได้ค่าเหล่านี้ชุดเดียวกัน

| # | ค่า | ที่อยู่ | สร้างโดย | ความรุนแรงถ้าซ้ำ |
|---|---|---|---|---|
| 1 | `NATID_DEK` | `/etc/cafe-wifi/secrets.env` | `gen_secrets` | 🔴 ถอดเลขบัตรของทุกร้านได้ |
| 2 | `NATID_PEPPER` | 〃 | `gen_secrets` | 🔴 brute-force เลขบัตร / เทียบข้ามร้าน |
| 3 | `SECRET_KEY` | 〃 | `gen_secrets` | 🔴 ปลอม session แอดมิน |
| 4 | `setup.token` | `/etc/cafe-wifi/setup.token` | `gen_secrets` | 🔴 ยึดเครื่องที่ยังไม่ได้ตั้งแอดมิน |
| 5 | `FAS_KEY` | `secrets.env`, `/etc/config/opennds` | `gen_secrets`, `build_opennds` | 🟠 ปลอมคำขอปลดล็อกเน็ต |
| 6 | TLS key | `/etc/cafe-wifi/tls/server.key` | `configure_nginx` | 🟠 MITM หน้าแอดมิน |
| 7 | `DB_PASS` | `secrets.env` + ผู้ใช้ใน MariaDB | `gen_secrets`, `setup_database` | 🟡 |
| 8 | `SSH_ALT_PORT` | `secrets.env`, `sshd_config.d` | `resolve_ssh_port` | 🟢 |
| 9 | SSH host keys | `/etc/ssh/ssh_host_*` | OS | 🟠 ปลอมตัวเป็น Pi |
| 10 | `machine-id` | `/etc/machine-id` | OS | 🟡 DHCP DUID ซ้ำ → IP ชน |
| 11 | random seed | `/var/lib/systemd/random-seed` | OS | 🟢 |
| 12 | user `ras`/`1234` | `/etc/shadow` | ติดตั้งมือ | 🔴 |

นอกจากนี้ ฐานข้อมูลใน image ต้องว่าง ไม่มีบัญชีแอดมิน ข้อมูลทดสอบ หรือ log

## 3. แบ่ง `install.sh` เป็น 3 stage

เพิ่มตัวเลือก `--stage build|firstboot|site|all` โดยค่า default = `all`
ซึ่งทำงานเหมือนเดิมทุกอย่าง (การติดตั้งแบบเก่าบน Pi และใน VM lab จึงไม่พัง)

| ฟังก์ชันใน `main()` | build (ที่บ้าน ใน chroot) | firstboot (บน Pi ไม่ต้องรู้เครือข่าย) | site (หลัง wizard) |
|---|:-:|:-:|:-:|
| `create_user_and_dirs` | ✅ | | |
| `ensure_uplink_before_packages` | | | ✅ ¹ |
| `install_packages` (+ fake-hwclock, avahi-daemon) | ✅ | | |
| `resolve_ssh_port` + `configure_ssh` | | ✅ | |
| `gen_secrets` — ส่วนความลับ | | ✅ | |
| `gen_secrets` — ส่วนค่าเครือข่าย | | | ✅ |
| `setup_python` | ✅ | | |
| `install_app_files` | ✅ | | |
| `setup_database` | | ✅ ² | |
| `configure_time` | ✅ | | |
| `configure_backup_usb` | ✅ | | |
| `configure_host_dns` / `configure_network` | | | ✅ |
| `build_opennds` — คอมไพล์ + `make install` | ✅ | | |
| `build_opennds` — เขียน `/etc/config/opennds` | | | ✅ |
| `install_services` (unit files + `enable`) | ✅ ³ | | |
| `configure_nginx` — ไฟล์ config | ✅ | | |
| `configure_nginx` — ออก TLS cert (SAN มี IP ลูกค้า) | | | ✅ |
| `configure_logrotate` | ✅ | | |
| `start_services` | | | ✅ |
| `write_state` | ✅ | ✅ | ✅ |

1. ไม่จำเป็นใน stage site (ไม่ต้องลงแพ็กเกจแล้ว) — ข้ามไปเลย
2. MariaDB ต้องรันอยู่ถึงสร้างผู้ใช้/schema ได้ ซึ่งทำใน chroot ไม่ได้ จึงย้ายมาทำตอนบูตแรก (schema ไม่กี่วินาที)
3. ใน chroot ใช้ `systemctl enable` ได้ แต่ `start`/`reload`/`daemon-reload` ไม่ได้
   → ต้องให้ `svc()` และ `run_sh "systemctl ..."` ข้ามคำสั่งพวกนั้นเมื่อ `--stage build`
   (ตรวจด้วย `systemd-detect-virt --chroot`)

**จุดที่ต้องแก้เพิ่ม**
- `preflight` ตรวจเน็ตและ NIC — ข้ามใน stage build
- `wizard()` แบบ CLI — ไม่ใช้ใน image (ใช้ web wizard แทน)
- `final_summary` — แสดงเฉพาะ stage site / all

## 4. ส่วนประกอบใหม่

| ส่วน | ไฟล์ (เสนอ) | หน้าที่ |
|---|---|---|
| Build script | `image/build.sh` | เรียก rpi-image-gen/pi-gen + stage ของเรา → `cafe-wifi-<ver>.img.xz` + `.sha256` |
| Stage ของ pi-gen | `image/stage-cafewifi/` | copy โปรเจกต์เข้า chroot แล้วรัน `install.sh --stage build -y`, ลบ user default, ล้าง machine-id / host keys |
| First-boot | `image/firstboot/cafe-wifi-firstboot.service` + `.sh` | `ConditionPathExists=!/etc/cafe-wifi/.firstboot-done` → `install.sh --stage firstboot` → อ่าน `cafewifi.conf` → เข้า setup mode |
| Setup mode | `cafe-wifi-setup.target` | ขอ DHCP บน eth0, เปิด avahi (`cafewifi.local`) + wizard; ยังไม่เปิด dnsmasq/openNDS |
| Web wizard | `app/setup/` (Flask แยกจาก admin) | หน้า ①–⑤ ตามคู่มือ → เรียก `install.sh --stage site -y --uplink-cidr … --uplink-gw … --client-cidr …` |
| ตรวจเราเตอร์ | `tools/check_router.py` | DHCPDISCOVER probe + ฟัง IPv6 RA (ต่อยอดจาก `bypass_detector.py`) |
| Self-test | `tools/selftest.sh` | ข้อที่ไม่ต้องใช้มือถือจาก `lab_fulltest.sh` → JSON ให้ wizard แสดง |
| LED | ใน firstboot/wizard | เขียน `/sys/class/leds/ACT/trigger` (timer/heartbeat) |
| ตัวช่วยเตรียมการ์ด | `image/prepare-sd.ps1` (+ `.sh`) | เขียน `cafewifi.conf` ลง `bootfs` และสุ่ม setup code |
| Repo JSON ของ Imager | `image/os_list.json` | รายการ OS ตัวเดียว + URL, ขนาด, SHA-256 |
| Factory reset | ใน firstboot | ถ้ามี `bootfs/factory-reset` → ล้างค่า site + บัญชีแอดมิน (เก็บ secrets/log/DB ไว้) → กลับ setup mode |

**รูปแบบ `cafewifi.conf`** (บน bootfs, `KEY=VALUE` ทีละบรรทัด, `#` = คอมเมนต์, แก้ด้วย Notepad ได้ —
ตัวอ่านตัด BOM/CRLF/เครื่องหมายคำพูดให้เอง และ**ไม่ source** ไฟล์นี้)

| คีย์ | ใช้ทำอะไร | ไม่ใส่ |
|---|---|---|
| `GATEWAY_NAME` | ชื่อร้านบนหน้า portal (ห้ามมี `'` `"` `\` `` ` `` `$`) | `Cafe-Guest` |
| `SETUP_CODE` | รหัสเข้า wizard 8–32 ตัว (`K7QM-29XD` = `k7qm29xd`) | Pi สุ่มเอง → `bootfs/SETUP-CODE.txt` |
| `SSH_PUBKEY` | public key ของช่าง → สร้างบัญชี `cafeadmin` (key เท่านั้น ไม่มีรหัสผ่าน, sudo ได้) | ไม่มีบัญชี SSH เลย |
| `TECH_USER` | เปลี่ยนชื่อบัญชีช่าง | `cafeadmin` |

firstboot ลบไฟล์นี้ทิ้งเมื่อสำเร็จ (มี code + key ที่ใครถือการ์ดก็อ่านได้)

**เรื่อง setup code:** Raspberry Pi Imager เพิ่มช่องกรอกของเราเองในหน้า OS customisation ไม่ได้
ระยะแรกจึงใช้ตัวช่วยเตรียมการ์ด (`prepare-sd.ps1`) ซึ่งสุ่ม code แล้วเขียนลงไฟล์
ถ้าไม่มีไฟล์ conf ตอนบูตแรก Pi จะสุ่ม code เองแล้วเขียนกลับลง `bootfs/SETUP-CODE.txt`
(ช่างถอดการ์ดมาเปิดดูได้) — เมื่อทำแอป flash ของเราเองค่อยรวมสองขั้นนี้เป็นขั้นเดียว

## 5. เครื่องมือ build

| ทางเลือก | ข้อดี | ข้อเสีย | ใช้เมื่อ |
|---|---|---|---|
| **A. rpi-image-gen / pi-gen** (แนะนำ) | สร้างจากศูนย์ทุกครั้ง ไม่มีของค้าง, build ซ้ำได้, รันใน Docker/WSL2 หรือ GitHub Actions ได้ | ตั้งค่าครั้งแรกนาน, คอมไพล์ openNDS ใต้ QEMU ช้า (~10–20 นาที) | ตัวจริงที่ส่งมอบ |
| B. Golden master (รัน `--stage build` บน Pi จริง → ล้างเครื่อง → PiShrink) | เร็ว ไม่ต้องตั้ง toolchain | ล้างไม่หมดเสี่ยงความลับรั่ว, build ซ้ำยาก | เดโม/ต้นแบบเร็ว ๆ เท่านั้น |

- OS ฐาน: **Raspberry Pi OS Lite 64-bit** (ล็อกเวอร์ชันตาม release ที่ทดสอบผ่าน)
- บนโน้ตบุ๊ก Windows: ใช้ WSL2 + Docker (`build-docker.sh` ของ pi-gen)
- **build ต้องทำบนโน้ตบุ๊ก** (เครื่องที่แตะโค้ด) — ไฟล์ `.img.xz` ห้าม commit (เพิ่ม `*.img*` ใน `.gitignore`)

## 6. ขั้นตอนดำเนินงาน (milestones)

| # | งาน | ผลลัพธ์ / เกณฑ์ผ่าน |
|---|---|---|
| **M1** | เพิ่ม `--stage` ใน `install.sh` | `--stage all` บน Pi จริงผ่าน `lab_fulltest.sh` 49/49 เหมือนเดิม; รัน `build` → `firstboot` → `site` ต่อกันบน Pi เปล่าแล้วได้ผลเท่ากัน |
| **M2** | first-boot service | ถอดไฟระหว่าง firstboot แล้วบูตใหม่ได้ (idempotent); รันซ้ำไม่สร้างกุญแจทับ — **โค้ดเสร็จ** `image/firstboot/` ทดสอบนอก Pi 41/41 (`test_firstboot.sh`) รอทดสอบไฟดับจริง (IMG-04) |
| **M3** | build image ด้วย pi-gen | ได้ `.img.xz` + `.sha256`; ไม่มีไฟล์ใน §2 อยู่ใน image (สคริปต์ตรวจอัตโนมัติท้าย build) |
| **M4** | setup mode + web wizard ①–⑤ | ตั้งค่าเครือข่ายจากมือถือได้โดยไม่ใช้ SSH |
| **M5** | ตรวจเราเตอร์ + self-test + LED | ตรวจจับได้ทั้งตอน DHCP/IPv6 เปิดและปิด (ทดสอบทั้งสองด้าน) |
| **M6** | `prepare-sd.ps1` + `os_list.json` | flash ด้วย Imager → ติดตั้งครบตามคู่มือโดยไม่แตะ CLI |
| **M7** | factory reset + ไฟล์สำรองกุญแจที่เข้ารหัส | reset แล้วข้อมูลเดิมยังถอดรหัสได้ |
| **M8** | ทดสอบรวม + เก็บหลักฐานลงเล่ม | ผลตาม §7 บันทึกใน `docs/hardware-test-log.md` |

ลำดับความสำคัญ: M1–M3 คือแกน (ได้ image ที่ปลอดภัย) · M4–M6 คือ "ไม่ต้องใช้ CLI" · M7 เป็นของเสริม

**ข้อควรทำใน M3 ที่พบตอนทำ M2**
- แพ็กเกจ Debian `dnsmasq` และ `nginx` enable ตัวเองตอน `apt install` → stage ของ pi-gen ต้อง
  `systemctl disable dnsmasq` (และ opennds) ไว้จนถึง `--stage site` ไม่งั้นบูตแรกจะเปิด DNS/DHCP บนวงเราเตอร์
  ขณะที่ DHCP ของเราเตอร์ยังเปิดอยู่
- copy `image/firstboot/cafe-wifi-firstboot.sh` → `/usr/local/sbin/cafe-wifi-firstboot` (0755) และ `.service`
  → `/etc/systemd/system/` แล้ว enable · ล้าง `/etc/machine-id` (ให้ว่าง), `/etc/ssh/ssh_host_*`,
  `/var/lib/systemd/random-seed`, `/etc/cafe-wifi/{secrets.env,setup.token,setup-code,.firstboot-done,tls/}`
- ผู้ใช้แรกของ pi-gen: ล็อกรหัสผ่าน (`passwd -l`) — เข้าเครื่องได้ทางบัญชีช่าง (SSH key) เท่านั้น

## 7. แผนทดสอบ

| รหัส | ทดสอบ | วิธี | ผ่านเมื่อ |
|---|---|---|---|
| IMG-01 | ความลับไม่ซ้ำ | flash image เดียวลง 2 การ์ด บูตทั้งคู่ เทียบ `sha256sum` ของ 12 รายการใน §2 | ไม่ซ้ำเลยทุกรายการ |
| IMG-02 | ไม่มีความลับใน image | mount ไฟล์ `.img` แล้วค้นหาไฟล์ใน §2 | ไม่พบ |
| IMG-03 | ติดตั้งหน้างานไม่ต้องใช้ GitHub/PyPI | บล็อก github.com/pypi.org ที่เราเตอร์ แล้วติดตั้งตามคู่มือ | ผ่านครบ |
| IMG-04 | ไฟดับระหว่าง firstboot | ถอดไฟตอน LED กะพริบถี่ แล้วเสียบใหม่ | บูตต่อจนพร้อมใช้ และ DEK ไม่ถูกสร้างทับ |
| IMG-05 | กันการ wizard จากลูกค้า | เปิด wizard โดยไม่มี code / ใส่ผิด 5 ครั้ง | เข้าไม่ได้ / ถูกล็อก |
| IMG-06 | ตรวจ DHCP เราเตอร์ | กดตรวจตอน DHCP เราเตอร์เปิดและปิด | ❌ ตอนเปิด, ✅ ตอนปิด |
| IMG-07 | ตรวจ IPv6 | กดตรวจตอน IPv6 เปิดและปิด | ❌ ตอนเปิด, ✅ ตอนปิด |
| IMG-08 | ระบบทำงานครบ | รัน `lab_fulltest.sh` บน Pi ที่ติดตั้งจาก image | 49/49 |
| IMG-09 | factory reset | reset แล้วตั้งค่าใหม่ | ข้อมูลเก่ายังถอดเลขบัตรได้ |
| IMG-10 | เวลาติดตั้งหน้างาน | จับเวลาตั้งแต่ขั้น 2–6 | ≤ 30 นาที |

ทดสอบบนแล็บ ER706W ตามผังใน `memory/pi-dhcp-and-portal-milestone.md`
(เราเตอร์ปิด DHCP/IPv6 ได้ เหมาะกับ IMG-06/07)

## 8. ความเสี่ยง

| ความเสี่ยง | ผลกระทบ | ทางลด |
|---|---|---|
| คำสั่งใน `install.sh` ที่ต้องมี systemd ทำงาน หลุดไปรันใน chroot | build พัง | ห่อทุก `systemctl` ด้วยการตรวจ chroot; ทดสอบ `--stage build` ใน Docker ก่อน |
| คอมไพล์ openNDS ใต้ QEMU ช้าหรือพัง | build นาน | cache ไฟล์ `.deb`/binary ที่คอมไพล์แล้ว หรือคอมไพล์บน Pi แล้วเอาผลมาใส่ stage |
| mDNS ใช้ไม่ได้บน Android บางรุ่น | ช่างเปิด wizard ไม่ได้ | คู่มือบอกให้ใช้ IP จากหน้าเราเตอร์; wizard รับทั้งสองทาง |
| setup mode เปิดอยู่ในวงเดียวกับลูกค้า | คนอื่นแย่งตั้งค่า | ต้องมี setup code + rate limit; ปิด wizard ถาวรเมื่อตั้งเสร็จ |
| เราเตอร์ร้านปิด DHCP ไม่ได้ | ข้าม portal | wizard ไม่ยอมไปต่อ + แนะนำทางสำรองตาม runbook |
| Raspberry Pi OS ออกเวอร์ชันใหม่แล้ว macvlan/openNDS เปลี่ยนพฤติกรรม | ระบบพัง | ล็อกเวอร์ชัน OS ฐาน และ `apt-mark hold` kernel/openNDS; อัปเดตเฉพาะหลังทดสอบ IMG-08 |

## 9. ยังไม่อยู่ในขอบเขตรอบนี้

- โปรแกรม flash ของเราเอง (fork Imager หรือเขียนใหม่)
- อัปเดตผ่านเว็บแบบมีลายเซ็น / A/B partition (RAUC, Mender)
- root filesystem แบบอ่านอย่างเดียว (overlayfs) + partition `/data`
- รองรับ Pi 5 (ใช้ NIC คนละตัวกับ Pi 4B ยังไม่ได้ทดสอบ macvlan)
