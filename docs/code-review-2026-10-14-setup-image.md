# รีวิวโค้ด — setup wizard + image/firstboot (14 ต.ค. 2026)

ขอบเขต: `app/setup/*`, `image/setup/*`, `image/firstboot/*`, `image/stage-cafewifi/*`, `image/pigen/config`,
`image/build.sh`, `image/check-image.sh`, `image/publish-public.sh`, `image/prepare-sd.ps1`
ทีม: Sonnet 1 ตัวตรวจ wizard → Opus ตรวจซ้ำกับโค้ด · ส่วน image Opus ตรวจเอง (Sonnet ชนลิมิตรายสัปดาห์)
**ยืนยัน** = เปิดโค้ดดูเส้นทางครบแล้ว · **น่าจะจริง** = เหตุผลถูก แต่ยังไม่ได้ลองรัน

**แก้แล้ว (14 ต.ค.):** S1, S2, S3 (ล็อกต่อ IP แทนทั้งเครื่อง), S5, S6 (ตัดที่ต้นเหตุด้วย: `parse_env`/`merge` แยกด้วย `\n` เท่านั้น
+ ตรวจชื่อร้านทั้ง wizard/install.sh/prepare-sd.ps1), S7, S8, S11, S12, S13 — มีเทสต์ทุกข้อยกเว้น S13 (bash ส่วน useradd รันนอก Pi ไม่ได้)
**เก็บไว้ก่อน (ผู้ใช้ตัดสิน):** S4 · **ต้องทำบน Pi:** S10 (import ด้วย user DB ที่ไม่ใช่ root + ปิด `\!` ของ mysql client +
จำกัดขนาด — ต้องลองกับ MariaDB จริง), ตรวจ S13 ด้วย `TECH_USER=www-data` ใน cafewifi.conf ต้องล้มพร้อมข้อความ ·
**ไม่แก้:** S9 (dump ไม่มีลูกค้า = ไม่มีอะไรให้ปกป้อง และผู้ถือ code สร้างแอดมินได้อยู่แล้ว)

**ภาพรวม:** ไม่พบทางยึดเครื่องจากวง LAN โดยไม่มี setup code, ไม่พบ command injection จากช่องกรอกของ wizard ไปถึง root,
wizard ปิดจริงหลังตั้งเสร็จ (410 + `ConditionPathExists=!.site-done` + ลบ code) และไม่มีความลับติดไปกับ image

## กลาง

| # | ที่ | ปัญหา | สถานะ |
|---|---|---|---|
| S1 | `app/setup/restore.py` `verify_keys` | ลูกค้าที่ถูกลบข้อมูล (PURGED: `natid_enc=''`) ถอดรหัสไม่ได้ → นับเป็น "กุญแจไม่ตรง" → **กู้คืนด้วยกุญแจที่ถูกต้องแล้วยังโดน DROP DATABASE** ทุกครั้งที่มีลูกค้า PURGED ใน 50 รายล่าสุด (ร้านที่ใช้ไปนานจนมี purge = กู้ผ่าน wizard ไม่ได้เลย) | ยืนยัน |
| S2 | `common/keybackup.py` `unpack` | พารามิเตอร์ scrypt อ่านจากหัวไฟล์ .cwkey ที่ผู้อัปโหลดกำหนดเอง เพดาน n≤2²⁰ r≤32 p≤16 = ใช้ RAM ~4 GiB ก่อนตรวจรหัสผ่าน → Pi OOM ฆ่า MariaDB/wizard (ต้องมี setup code) | ยืนยัน |
| S3 | `app/setup/app.py:68-77` | ผิด 5 ครั้งล็อกทั้งเครื่อง 15 นาที ไม่แยกต้นทาง → เครื่องไหนในวงก็กันช่างไม่ให้เข้าได้ตลอด (ไม่ใช่ช่องทาย code: ~39.6 บิต) | ยืนยัน · เชิงออกแบบ |
| S4 | wizard บน `:80` | setup code / รหัสแอดมินแรก / รหัส .cwkey ส่งแบบ HTTP ในวงที่ลูกค้าใช้ร่วม | ยืนยัน · ความเสี่ยงที่ยอมรับ (แนวเดียวกับเลขบัตรผ่าน HTTP) ควรเขียนไว้ในเอกสาร |

## ต่ำ

| # | ที่ | ปัญหา | สถานะ |
|---|---|---|---|
| S5 | `app/setup/netinfo.py:18`, `install.sh:2516` | ชื่อร้านมี NUL → `apply.py` (root) ล้มด้วย ValueError ที่ไม่ถูกจับ: wizard ถูก stop ไปแล้ว + status ค้าง "running" จนรีบูต | ยืนยัน |
| S6 | เดียวกับ S5 + `cafewifi.conf`, `prepare-sd.ps1` | ตัวควบคุม/ตัวแบ่งบรรทัด Unicode (`\x0b \x0c \x1c-\x1e \x85 U+2028/2029`) ผ่านการตรวจ → `splitlines()` ใน `keybackup.parse_env`/`restore_keys.merge` แยกเป็นบรรทัดใหม่ = แทรก `NATID_DEK=` ปลอมลงไฟล์สำรองกุญแจได้ | ยืนยัน (ฝั่ง Python) |
| S7 | `app/setup/app.py:117` | `secrets.compare_digest(str, str)` กับ csrf ที่ไม่ใช่ ASCII → TypeError 500 (ไม่ต้องมี code) | ยืนยัน |
| S8 | `app/setup/restore.py:189-211` | ล้มกลางทางหลัง import (migrations/partition/write_keys หรือ exception นอกรายการที่จับ) ไม่ DROP ฐาน → staff>0 กู้ซ้ำไม่ได้ แต่ secrets.env ยังเป็นกุญแจใหม่ = ถอดเลขบัตรไม่ได้ · exception นอกรายการ = status ค้าง running | ยืนยัน |
| S9 | `restore.py:198` | dump ไม่มีลูกค้าเลย = ไม่ตรวจกุญแจ รับ .cwkey อะไรก็ได้ (ต้องมี code อยู่แล้ว) | ยืนยัน |
| S10 | `restore.py` `import_dump` | ไฟล์ .sql.gz บน USB รันด้วย mysql root ไม่จำกัดขนาด (ต้องเข้าถึง USB) | น่าจะจริง |
| S11 | `app/setup/app.py:283`, `tools/check_router.py` | เก็บผลตรวจเราเตอร์ทั้งก้อนใน cookie · RA จำนวนมากดัน cookie เกิน 4 KB | น่าจะจริง |
| S12 | `netinfo.py` | `nic` รับ `wlan0`/`lo` ได้ · `client_cidr` รับ 127/8, 169.254/16 · `/apply` ไม่กันระหว่าง restore กำลังรัน | ยืนยัน |
| S13 | `image/firstboot/cafe-wifi-firstboot.sh:181-202` | `TECH_USER` เป็นบัญชีระบบที่มีอยู่ได้ (`www-data`, `mysql`) → บัญชีนั้นได้ `NOPASSWD:ALL` (ต้องถือการ์ด) | ยืนยัน |

## ส่วนที่ตรวจแล้วแน่น

- wizard: ปิดหลังตั้งเสร็จ, code เทียบเป็น bytes ค่าว่างไม่ผ่าน, ไม่อยู่ใน URL/log/Referer, session ผูกกับ code ปัจจุบัน,
  CSRF ทุก POST + SameSite=Strict, ไม่มี `|safe`, ฝั่ง root ย้ายไฟล์คำขอก่อนอ่าน + `O_NOFOLLOW` + จำกัดขนาด + validate ซ้ำ,
  argv list ไม่ผ่าน shell, สร้างแอดมินแรกด้วย `FOR UPDATE`
- image: `check-image.sh` ตรวจ secrets/host keys/machine-id/random-seed/รหัสผ่านใน shadow ทั้งท้าย build และกับไฟล์ .img จริง,
  SSH key เท่านั้น (`PasswordAuthentication no`, `PermitRootLogin no`, ล็อก root + cafeadmin), setup code สุ่มจาก
  `/dev/urandom` แบบ rejection sampling (ทั้ง bash และ PowerShell), firstboot รันซ้ำได้ (ปักธงท้ายสุด, ไม่สร้างกุญแจทับ,
  ซ่อม host key ที่เสียจากไฟดับ), `cafewifi.conf` อ่านแบบไม่ source และลบหลังใช้, factory reset ต้องวางไฟล์บน bootfs
  (เข้าถึงทางกายภาพเท่านั้น) และไม่ลบข้อมูล ม.26, `publish-public.sh` เป็น allowlist + ปฏิเสธถ้ามีไฟล์ยังไม่ commit
