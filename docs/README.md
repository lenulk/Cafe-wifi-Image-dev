# เอกสาร Cafe-WiFi — สารบัญ

เลือกอ่านตามบทบาท: **เจ้าของร้าน/พนักงาน** → คู่มือผู้ดูแลร้าน · **ช่างติดตั้ง/ดูแลเครื่อง** → คู่มือติดตั้ง + Operations
· **นักพัฒนา** → สถาปัตยกรรม + คู่มือนักพัฒนา + เอกสารอ้างอิง

## เริ่มที่นี่

| ฉันคือ… | อ่าน |
|---|---|
| เจ้าของร้าน / พนักงาน | [admin-guide.md](admin-guide.md) — อนุมัติลูกค้า, จัดการพนักงาน, ค้น log, ส่งออกหลักฐาน, สำรองกุญแจ |
| ช่างที่จะติดตั้งร้านใหม่ | [install-from-image.md](install-from-image.md) → [isp-router-runbook.md](isp-router-runbook.md) → [backup-usb.md](backup-usb.md) |
| ช่างที่ดูแลเครื่องที่ใช้งานอยู่ | [operations.md](operations.md) — service/timer, health check, backup/restore, ตารางแก้ปัญหา |
| นักพัฒนาคนใหม่ | [architecture.md](architecture.md) → [developer-guide.md](developer-guide.md) |

## ภาพรวมและการออกแบบ

| เอกสาร | เนื้อหา |
|---|---|
| [architecture.md](architecture.md) | สถาปัตยกรรมระบบ: Pi เครื่องเดียวสายเดียว, macvlan, openNDS/FAS, flow ลูกค้า, flow ของ log, โมเดลความปลอดภัย |
| [image-build-plan.md](image-build-plan.md) | การออกแบบ image สำเร็จรูป + first boot + setup wizard |
| [privacy-policy-th.md](privacy-policy-th.md) | นโยบายความเป็นส่วนตัว (ติดประกาศหน้าร้าน) |

## คู่มือใช้งาน

| เอกสาร | เนื้อหา |
|---|---|
| [admin-guide.md](admin-guide.md) | คู่มือผู้ดูแลร้านและพนักงาน (หน้าเว็บแอดมิน) |
| [install-from-image.md](install-from-image.md) | ติดตั้งจาก image ทีละขั้น จนส่งมอบร้าน |
| [isp-router-runbook.md](isp-router-runbook.md) | ตั้งค่าเราเตอร์ ISP (ปิด DHCP/IPv6 ฯลฯ) |
| [backup-usb.md](backup-usb.md) | เตรียมและใช้ USB สำรองข้อมูล |
| [operations.md](operations.md) | ดูแลระบบและแก้ปัญหา (สำหรับช่างที่มี SSH) |

## เอกสารอ้างอิง

| เอกสาร | เนื้อหา |
|---|---|
| [configuration.md](configuration.md) | ตัวแปรใน `secrets.env`, ไฟล์/พาธบน Pi, พอร์ต, systemd unit/timer, ค่าปรับแต่ง |
| [database.md](database.md) | schema สุดท้ายหลัง migration ทุกไฟล์ + ER diagram + retention |
| [cli-tools.md](cli-tools.md) | สคริปต์ใน `tools/` และ `image/` — วิธีรัน, flag, รันอัตโนมัติหรือไม่ |

## พัฒนาและทดสอบ

| เอกสาร | เนื้อหา |
|---|---|
| [developer-guide.md](developer-guide.md) | โครงสร้างรีโป, branch/remote, รันเทสต์, เพิ่ม migration/หน้าแอดมิน, build image, กับดัก |
| [docker-test.md](docker-test.md) | สภาพแวดล้อมทดสอบด้วย Docker |
| [test-plan.md](test-plan.md) | แผนการทดสอบ |
| [hardware-test-log.md](hardware-test-log.md) | บันทึกผลทดสอบบนฮาร์ดแวร์จริง (หลักฐานหลัก) |

## รวมเล่มเป็น Word / PDF

```bash
python docs/build_word.py
```

ได้ `รายงานเล่ม/เอกสารระบบ-Cafe-WiFi.docx` และ `.pdf` (ปก + สารบัญ + เลขหน้า) — ต้องมี Microsoft Word บนเครื่อง
ลำดับบทกำหนดใน `PARTS` ในสคริปต์ · ไฟล์ผลลัพธ์ไม่เข้า git ต้องส่งข้ามเครื่องเอง
