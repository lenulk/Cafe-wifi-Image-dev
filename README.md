# Cafe-WiFi OS — image สำเร็จรูปสำหรับ Raspberry Pi

ระบบ Wi-Fi สำหรับร้านกาแฟ: หน้าลงทะเบียนลูกค้าด้วยเลขประจำตัวประชาชน (captive portal) + พนักงานอนุมัติ
+ บันทึกข้อมูลจราจรทางคอมพิวเตอร์ตาม **พ.ร.บ.คอมพิวเตอร์ฯ มาตรา 26** — แบบ **flash การ์ดแล้วตั้งค่าผ่านเว็บ
ไม่ต้องใช้ command line**

> repo นี้ = ตัวสร้าง image + first-boot + setup wizard ต่อยอดจากโปรเจกต์หลัก
> [lenulk/Cafe-wifi](https://github.com/lenulk/Cafe-wifi) (`v1.0` — ติดตั้งด้วย `install.sh` บนเครื่องที่มีอยู่แล้ว)

## ดาวน์โหลด

**[Release v1.0.0](https://github.com/lenulk/Cafe-wifi-Image/releases/tag/v1.0.0)** —
`cafe-wifi-1.0.0-20261004-ec1e0dc.img.xz` (644 MB, แตกแล้ว 3.4 GB)

| | |
|---|---|
| ฮาร์ดแวร์ | Raspberry Pi 4B (64-bit) + SD card ≥ 8 GB + สาย LAN 1 เส้นไปเราเตอร์ร้าน |
| ระบบฐาน | Raspberry Pi OS Lite 64-bit (Debian 13 trixie) — สร้างด้วย [pi-gen](https://github.com/RPi-Distro/pi-gen) |
| SHA-256 | `ce967c32fa29114973a58cf9ea49e3b695a57b758fbef499f047feef5fed66bb` |

## ติดตั้ง (สรุป — ฉบับเต็ม: [`docs/install-from-image.md`](docs/install-from-image.md))

1. **เขียนการ์ด** — Raspberry Pi Imager → Device: Raspberry Pi 4 → OS: *Use custom* → เลือกไฟล์ `.img.xz`
   (Imager ถามเรื่อง OS customisation ให้ตอบ **No**)
2. **เตรียมการ์ด** — เปิด PowerShell แล้วรัน [`image/prepare-sd.ps1`](image/prepare-sd.ps1)
   (ใส่ชื่อร้าน + SSH key ของช่าง ไม่บังคับ) → **จด setup code** ที่ได้
3. **บูต** — ต่อสาย LAN จากเราเตอร์ร้าน (DHCP ของเราเตอร์**ต้องยังเปิดอยู่**ในขั้นนี้) แล้วเสียบไฟ
   รอไฟ LED เขียวกะพริบแบบ heartbeat (~1 นาที)
4. **ตั้งค่าผ่านเว็บ** — มือถือ/โน้ตบุ๊กที่ต่อ Wi-Fi ร้าน เปิด **`http://cafewifi.local`**
   ① setup code ② สร้างแอดมิน ③ เครือข่าย (ระบบเสนอให้เอง) ④ **ปิด DHCP และ IPv6 ที่เราเตอร์** แล้วกด "ตรวจสอบ"
   ⑤ บันทึก — ระบบไม่ยอมบันทึกจนกว่าจะตรวจได้ว่าเราเตอร์ปิด DHCP แล้วจริง (กันลูกค้าข้าม portal)
5. **ส่งมอบ** — เครื่องพนักงานแต่ละเครื่อง: อนุมัติก่อน → เปิด `https://admin.cafe.wifi` → กด
   "ขั้นสูง → ดำเนินการต่อ" ครั้งเดียว (ใบรับรอง self-signed) — รายการตรวจครบใน
   [`docs/install-from-image.md`](docs/install-from-image.md) ขั้น 7

## ความปลอดภัยของ image

- **ไม่มีความลับใน image** — กุญแจเข้ารหัสเลขบัตร, pepper, session key, FAS key, รหัส DB, ใบรับรอง TLS,
  SSH host key, machine-id สร้างใหม่บน Pi แต่ละเครื่องตอนบูตครั้งแรก
  (ตรวจอัตโนมัติท้าย build ด้วย [`image/check-image.sh`](image/check-image.sh) กับไฟล์ .img จริง — ไม่ผ่าน = build ล้ม)
- **ไม่มีบัญชีที่มีรหัสผ่าน** — เข้าเครื่องได้ทาง SSH key ของช่าง (`cafeadmin`, จาก `prepare-sd.ps1`) เท่านั้น
- ช่วงตั้งค่า wizard เปิดได้เฉพาะคนที่มี setup code (ผิด 5 ครั้งล็อก 15 นาที) และปิดตัวเองถาวรเมื่อตั้งเสร็จ
- ไฟดับระหว่างบูตครั้งแรก → เสียบใหม่ได้ ทำต่อจากเดิมโดยไม่สร้างกุญแจทับ

## ผลทดสอบบนฮาร์ดแวร์จริง (Raspberry Pi 4B, แล็บ 4 ต.ค. 2026)

| รหัส | ทดสอบ | ผล |
|---|---|---|
| IMG-02 | ไม่มีความลับในไฟล์ image | ✅ 26/26 รายการ |
| IMG-04 | ถูกตัดกลาง first boot แล้วรันใหม่ | ✅ กุญแจไม่เปลี่ยน |
| IMG-06 | ตรวจ DHCP ของเราเตอร์ (เปิด / ปิด) | ✅ จับได้ทั้งสองฝั่ง |
| IMG-07 | ตรวจ IPv6 RA | ⚠️ ทดสอบได้เฉพาะฝั่ง "ไม่มี RA" |
| IMG-08 | ทดสอบทั้งระบบ `tools/lab_fulltest.sh` | ✅ 49/49 |

รายละเอียด บั๊กที่เจอระหว่างทดสอบ และกับดักของแล็บ: [`docs/hardware-test-log.md`](docs/hardware-test-log.md) §3.15

## สร้าง image เอง

ต้องมี Windows + Docker Desktop (ใช้ QEMU ของ Docker Desktop สร้าง arm64):

```powershell
powershell -ExecutionPolicy Bypass -File image\build.ps1          # ครั้งแรก ~75 นาที
powershell -ExecutionPolicy Bypass -File image\build.ps1 -Reuse   # แก้แค่ stage ของเรา ~30 นาที
```

build จาก commit ปัจจุบัน (`git archive HEAD`) → `image\deploy\` ได้ `.img.xz` + `.sha256` + `os_list.json`
(สำหรับ Raspberry Pi Imager) + ผลตรวจความลับ · แผนและการออกแบบ: [`docs/image-build-plan.md`](docs/image-build-plan.md)

| ส่วน | ไฟล์ |
|---|---|
| stage ของ pi-gen | [`image/stage-cafewifi/`](image/stage-cafewifi/) |
| first boot | [`image/firstboot/`](image/firstboot/) |
| setup wizard | [`app/setup/`](app/setup/) + [`image/setup/`](image/setup/) (systemd units) |
| ตรวจเราเตอร์ | [`tools/check_router.py`](tools/check_router.py) |
| ตัวติดตั้งหลัก | [`install.sh`](install.sh) `--stage build \| firstboot \| site \| all` |

## ข้อจำกัดที่รู้แล้ว

- Chrome Android ที่**ยังไม่ได้รับอนุมัติ**และไม่เคยยอมรับใบรับรองของเครื่อง เปิด `https://admin.cafe.wifi` ไม่ได้
  (ขึ้น "Connect to Wi-Fi" ไม่มีปุ่มข้าม) — ให้อนุมัติเครื่องพนักงานก่อนแล้วยอมรับใบรับรองครั้งเดียว
- กด "ปิดสิทธิ์" ในหน้าแอดมิน มีผลภายในรอบตรวจถัดไป (≤ 5 นาที)
- ยังไม่มี factory reset / ไฟล์สำรองกุญแจแบบเข้ารหัส (แผน M7)

## รันเทสต์

```bash
pip install pytest
PYTHONPATH=app pytest tests/ -v
bash image/firstboot/test_firstboot.sh      # first boot (Linux/WSL ไม่ต้อง root)
```
