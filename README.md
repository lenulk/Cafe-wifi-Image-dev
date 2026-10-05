# Cafe-WiFi OS — image สำเร็จรูปสำหรับ Raspberry Pi

ระบบ Wi-Fi สำหรับร้านกาแฟ: หน้าลงทะเบียนลูกค้าด้วยเลขประจำตัวประชาชน (captive portal) + พนักงานอนุมัติ
+ บันทึกข้อมูลจราจรทางคอมพิวเตอร์ตาม **พ.ร.บ.คอมพิวเตอร์ฯ มาตรา 26** — แบบ **flash การ์ดแล้วตั้งค่าผ่านเว็บ
ไม่ต้องใช้ command line**

> repo นี้ = ตัวสร้าง image + first-boot + setup wizard ต่อยอดจากโปรเจกต์หลัก
> [lenulk/Cafe-wifi](https://github.com/lenulk/Cafe-wifi) (`v1.0` — ติดตั้งด้วย `install.sh` บนเครื่องที่มีอยู่แล้ว)
>
> 🌐 เว็บไซต์ผลิตภัณฑ์: <https://lenulk.github.io/Cafe-wifi-Image/> · 🎬 วิดีโอโปรโมต: [ด้านล่าง](#วิดีโอโปรโมต-motion)

## ดาวน์โหลด

**[Release v1.1.0](https://github.com/lenulk/Cafe-wifi-Image/releases/tag/v1.1.0)** —
`cafe-wifi-1.1.0-20261004-061c6bc.img.xz` (642 MB)

| | |
|---|---|
| ฮาร์ดแวร์ | Raspberry Pi 4B (64-bit) + SD card ≥ 8 GB + สาย LAN 1 เส้นไปเราเตอร์ร้าน + (แนะนำ) USB สำรองข้อมูล |
| ระบบฐาน | Raspberry Pi OS Lite 64-bit (Debian 13 trixie) — สร้างด้วย [pi-gen](https://github.com/RPi-Distro/pi-gen) |
| SHA-256 | `ea553cb0f61406de016d7db482aab70dd8aa02d21452e79509dd5b471222c74d` |

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
5. **ส่งมอบ** — ดาวน์โหลด**ไฟล์สำรองกุญแจ** (`.cwkey`) เก็บนอกเครื่อง, เสียบ USB สำรองข้อมูล,
   ติดตั้งใบรับรองของร้านบนเครื่องพนักงาน (ลิงก์ในหน้าสถานะระบบ) — รายการตรวจครบใน
   [`docs/install-from-image.md`](docs/install-from-image.md) ขั้น 7

## ความปลอดภัยของ image

- **ไม่มีความลับใน image** — กุญแจเข้ารหัสเลขบัตร, pepper, session key, FAS key, รหัส DB, ใบรับรอง TLS,
  SSH host key, machine-id สร้างใหม่บน Pi แต่ละเครื่องตอนบูตครั้งแรก
  (ตรวจอัตโนมัติท้าย build ด้วย [`image/check-image.sh`](image/check-image.sh) กับไฟล์ .img จริง — ไม่ผ่าน = build ล้ม)
- **ไม่มีบัญชีที่มีรหัสผ่าน** — เข้าเครื่องได้ทาง SSH key ของช่าง (`cafeadmin`, จาก `prepare-sd.ps1`) เท่านั้น
- ช่วงตั้งค่า wizard เปิดได้เฉพาะคนที่มี setup code (ผิด 5 ครั้งล็อก 15 นาที) และปิดตัวเองถาวรเมื่อตั้งเสร็จ
- ไฟดับระหว่างบูตครั้งแรก → เสียบใหม่ได้ ทำต่อจากเดิมโดยไม่สร้างกุญแจทับ
- **สำรองกุญแจ** — แอดมินดาวน์โหลดไฟล์ `.cwkey` (scrypt + AES-256-GCM ด้วยรหัสผ่านที่ตั้งเอง) เก็บนอกเครื่อง
  การ์ดเสีย: flash ใหม่แล้ว**กู้คืนผ่านหน้าเว็บ** (ขั้น ① ของ wizard → "กู้คืนจากเครื่องเดิม" ด้วย `.cwkey` + USB สำรอง)
  ข้อมูลลูกค้า, log และบัญชีพนักงานกลับมาครบ — ไม่มีไฟล์ `.cwkey` = ถอดเลขบัตรที่เก็บไว้ไม่ได้อีก
- **Factory reset** — ตั้งเครือข่ายผิด/เปลี่ยนเราเตอร์: `prepare-sd.ps1 -FactoryReset` แล้วตั้งใหม่ผ่าน wizard โดยข้อมูลไม่หาย

## ผลทดสอบบนฮาร์ดแวร์จริง (Raspberry Pi 4B — v1.0.1 แล็บ 4 ต.ค. 2026, v1.1.0 แล็บ 5 ต.ค. 2026)

| รหัส | ทดสอบ | ผล |
|---|---|---|
| IMG-01 | flash image เดิมซ้ำ → ความลับใหม่ทุกเครื่อง | ✅ 8/8 ต่างกัน |
| IMG-02 | ไม่มีความลับในไฟล์ image | ✅ 26/26 รายการ |
| IMG-03 | ติดตั้งโดยไม่มีอินเทอร์เน็ต | ✅ |
| IMG-04 | ถูกตัดกลาง first boot แล้วรันใหม่ | ✅ กุญแจไม่เปลี่ยน |
| IMG-05 | setup code ผิด 5 ครั้ง | ✅ ล็อก 15 นาที |
| IMG-06 | ตรวจ DHCP ของเราเตอร์ (เปิด / ปิด) | ✅ จับได้ทั้งสองฝั่ง |
| IMG-07 | ตรวจ IPv6 RA (เปิด / ปิด) | ✅ จับได้ทั้งสองฝั่ง |
| IMG-08 | ทดสอบทั้งระบบ `tools/lab_fulltest.sh` (v1.1.0) | ✅ 49/49 |
| IMG-09 | factory reset → กลับเข้า wizard | ✅ 85 วิ ข้อมูลเท่าเดิม |
| IMG-10 | เวลาติดตั้ง | ✅ ~6 นาที ตั้งแต่เสียบไฟ |
| — | ปิดสิทธิ์ลูกค้า → เน็ตถูกตัด (v1.1.0, 6 รอบ) | ✅ 6.7–8.3 วิ (1.0.1 ช้าได้ถึง 26 วิ) |
| — | การ์ดเสีย → flash ใหม่ → กู้คืนผ่านหน้าเว็บ (.cwkey + USB) | ✅ เลขบัตร/พนักงาน/log กลับมาครบ |
| — | Android 10 ที่ยังไม่อนุมัติ + ติดตั้งใบรับรองร้าน → เปิดหน้าแอดมิน | ✅ ไม่มีหน้าเตือน |

รายละเอียด บั๊กที่เจอระหว่างทดสอบ และกับดักของแล็บ: [`docs/hardware-test-log.md`](docs/hardware-test-log.md) §3.15–3.15.2

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

- ต้องใช้เราเตอร์ที่**ปิด DHCP และ IPv6 ฝั่ง LAN ได้** (wizard ตรวจให้ก่อนเปิดใช้)
- ใบรับรองหน้าแอดมินเป็นของร้านเอง (ไม่ใช่ CA สาธารณะ) — เครื่องพนักงานต้องติดตั้งใบรับรองครั้งเดียว
  (`http://<ip ของ Pi>:8080/cafe-wifi.crt`) ทดสอบแล้วบน Android 10

## วิดีโอโปรโมต (motion)

วิดีโอ 3 ตัวสร้างจากโค้ดใน [`video/motion/`](video/motion/) — ทุกฉากเป็น HTML/JS ที่ขับด้วย `seek(t)`
ใช้ภาพหน้าจอจริงจาก [`image/public/img/`](image/public/img/) และตัวเลขที่มีผลทดสอบรองรับเท่านั้น
เพลงและเสียงเอฟเฟกต์สังเคราะห์ด้วยโค้ด (ไม่มีไฟล์เสียงภายนอก ไม่ติดลิขสิทธิ์)

| วิดีโอ | สัดส่วน · ความยาว | ต้นฉบับ | เนื้อหา |
|---|---|---|---|
| ฉบับเต็ม | 16:9 · 1:26 | [`index.html`](video/motion/index.html) | 10 ฉาก: มาตรา 26 → ติดตั้ง → ลูกค้าลงทะเบียน → พนักงานอนุมัติ/ปิดสิทธิ์ → หลักฐาน → ผลทดสอบ |
| ฉบับสั้น | 9:16 · 0:18 | [`short.html`](video/motion/short.html) | Reels/TikTok/Shorts — 90 วัน → ติดตั้ง 3 ขั้น → ลงทะเบียน+อนุมัติ → ดาวน์โหลด |
| เปรียบเทียบ | 9:16 · 0:28 | [`compare.html`](video/motion/compare.html) | ร้าน A (ไม่มีระบบ) vs ร้าน B (มี Cafe-WiFi OS) 5 สถานการณ์ |

ไฟล์ `.mp4` ไม่อยู่ใน git (ไบนารีใหญ่) — เรนเดอร์เองได้ ต้องมี Python + Google Chrome:

```bash
pip install playwright imageio-ffmpeg numpy
cd video/motion
python audio.py && python render.py                      # ฉบับเต็ม  -> cafe-wifi-os.mp4
python audio.py short && python render.py --short        # ฉบับสั้น  -> cafe-wifi-os-short.mp4
python audio.py compare && python render.py --compare    # เปรียบเทียบ -> cafe-wifi-os-compare.mp4
```

พรีวิว/แก้จังหวะ: เปิดไฟล์ `.html` ในเบราว์เซอร์ (มีแถบเลื่อนเวลา) · ตรวจเฟรม: `python render.py --stills 3 9 30`
· บน Windows ตั้ง `PYTHONUTF8=1` ก่อนรัน

## รันเทสต์

```bash
pip install pytest
PYTHONPATH=app pytest tests/ -v
bash image/firstboot/test_firstboot.sh      # first boot (Linux/WSL ไม่ต้อง root)
```
