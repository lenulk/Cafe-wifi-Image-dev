# คู่มือนักพัฒนา (Developer Guide)

เอกสารนี้สำหรับคนที่จะแก้โค้ด/เพิ่มฟีเจอร์ของ Cafe-WiFi: โครงสร้างรีโป นโยบาย branch/remote วิธีตั้งสภาพแวดล้อม รันเทสต์
เพิ่ม migration เพิ่มหน้า Admin build image ออก release และกับดักที่เคยทำเสียเวลา ทุกข้อมาจากไฟล์ในรีโป (อ้าง path กำกับ)
ถ้า `PROJECT_PLAN.md` หรือ `CODING_BRIEF.md` ขัดกับเอกสารนี้ ให้เชื่อรีโปจริง — สองไฟล์นั้นบางส่วนล้าสมัยแล้ว

เอกสารพี่น้อง: `docs/architecture.md`, `docs/configuration.md`, `docs/database.md`, `docs/cli-tools.md`, `docs/operations.md`
(เขียนคู่ขนานกัน — เอกสารนี้ลิงก์ไปแทนการคัดลอกเนื้อหา)

## สารบัญ

1. [โครงสร้างรีโป](#1-โครงสร้างรีโป)
2. [Branch และ remote](#2-branch-และ-remote)
3. [ตั้งสภาพแวดล้อมพัฒนา](#3-ตั้งสภาพแวดล้อมพัฒนา)
4. [รันเทสต์](#4-รันเทสต์)
5. [ธรรมเนียมของโค้ด](#5-ธรรมเนียมของโค้ด)
6. [เพิ่ม DB migration](#6-เพิ่ม-db-migration)
7. [เพิ่มหน้า Admin](#7-เพิ่มหน้า-admin)
8. [Build image](#8-build-image)
9. [Git hook ซิงก์ความจำ](#9-git-hook-ซิงก์ความจำ)
10. [Release](#10-release)
11. [กับดักที่ควรรู้](#11-กับดักที่ควรรู้)

---

## 1. โครงสร้างรีโป

| path | หน้าที่ |
|---|---|
| `app/admin/` | Admin Panel (Flask): `app.py` (login/setup/health/gate/CSRF), `routes.py` (ตัวเก็บ route), `views/*.py` แยกตามหน้าที่, `templates/*.html` |
| `app/fas/` | Forwarding Authentication Service ของ openNDS (portal ลูกค้า): `app.py`, `opennds_proto.py`, `templates/` |
| `app/logger/` | daemon เก็บ log: `conn_collector.py`, `dns_collector.py`, `bypass_detector.py`, `integrity.py` (hash chain), `telemetry.py`, `run_all.py` |
| `app/setup/` | web wizard ตั้งค่าครั้งแรกบน image: `app.py`, `apply.py`, `restore.py`, `netinfo.py` |
| `app/common/` | โค้ดกลางที่ admin/fas/setup/logger ใช้ร่วมกัน: `db.py`, `crypto.py`, `audit.py`, `access.py`, `customer.py`, `ratelimit.py`, `traffic.py`, `health.py`, `sysinfo.py`, `device_info.py`, `keybackup.py`, `log_mapping.py` |
| `app/requirements.txt` | dependency ของแอป (Flask, gunicorn, PyMySQL, cryptography, argon2-cffi — ปักเวอร์ชันตรง) |
| `sql/` | schema + migration (`001`–`013`) |
| `tools/` | สคริปต์ CLI/timer: `backup_db`, `check_disk`, `check_router`, `enforce_voucher_expiry`, `export_evidence`, `purge_old_data`, `reconcile_pending`, `reset_admin`, `restore_keys` + สคริปต์แล็บ `lab_*` (ดู `docs/cli-tools.md`) |
| `tests/` | pytest + `_run_tests.py` (ดู [§4](#4-รันเทสต์)) |
| `install.sh` | ตัวติดตั้งทั้งระบบ มี `--stage all\|build\|firstboot\|site` |
| `image/` | ทุกอย่างเกี่ยวกับ image สำเร็จรูป: `build.sh`/`build.ps1` (pi-gen), `check-image.sh`, `pigen/config`, `stage-cafewifi/`, `firstboot/`, `setup/` (systemd unit ของ wizard), `public/` (README+เว็บ Pages ของรีโปสาธารณะ), `publish-public.sh`, `prepare-sd.ps1`, `VERSION`, `deploy/` (ผล build) |
| `Dockerfile`, `docker-compose.yaml`, `docker/` | สภาพแวดล้อมทดสอบในเครื่อง (ดู `docs/docker-test.md`) |
| `docs/` | เอกสารทางเทคนิค + `hardware-test-log.md` (หลักฐานจากฮาร์ดแวร์จริง) |
| `memory/` | ความจำสะสมของ Claude Code (ซิงก์อัตโนมัติ — [§9](#9-git-hook-ซิงก์ความจำ)) |
| `video/` | วิดีโอโปรโมต (HTML → render ด้วย Playwright) |
| `.githooks/` | `pre-commit` |
| `review/`, `รายงานเล่ม/` | เอกสารรีวิว/เล่มโครงการ (ไม่เกี่ยวกับโค้ดรัน) |
| `PROJECT_PLAN.md`, `CODING_BRIEF.md` | เอกสารแผนยุคแรก — บางส่วนล้าสมัย ใช้เป็นบริบทเท่านั้น |

หมายเหตุ: มี `cafe-wifi-project*.tar.gz` ที่รากรีโปด้วย เป็นของเก่า (ความจำ `memory/cafe-wifi-source-of-truth.md` เคยบอกว่าโค้ดจริงอยู่ในทาร์บอล —
ตอนนี้โค้ดอยู่ใน `app/` ตามปกติ) ไม่ต้องใช้

## 2. Branch และ remote

ตรวจจาก `git remote -v`, `git config` และ `git tag`:

| remote | ชี้ไป | ใช้ทำอะไร |
|---|---|---|
| `origin` | `lenulk/Cafe-wifi` | repo เดิม — `master` ตั้ง upstream ที่นี่; **`master` แช่แข็งที่ tag `v1.0`** |
| `dev` | `lenulk/Cafe-wifi-Image-dev` (private) | ที่ push งานจริง — branch `image` ตั้ง upstream เป็น `dev/main` |
| `public` | `lenulk/Cafe-wifi-Image` (สาธารณะ) | หน้าโชว์ผลิตภัณฑ์ — **ห้าม push ตรง** ใช้ `image/publish-public.sh` เท่านั้น |

กฎ:

- งานใหม่ทั้งหมดทำบน branch **`image`** แล้ว push ไป `dev`: `git push dev image:main`
  (ความจำ `memory/image-installer-plan.md`)
- **push เฉพาะรีโปของเจ้าของเอง** (`lenulk/*`) ห้าม push ไปรีโปคนอื่น เช่น fork ของผู้ร่วมงาน — ดู `memory/push-only-to-own-github.md`
  (อ่าน/fetch จากรีโปอื่นได้)
- รีโปสาธารณะได้เฉพาะไฟล์ใน allowlist `ALLOW=(...)` ของ `image/publish-public.sh` (app, sql, install.sh, tools ที่คัดแล้ว,
  `image/VERSION`, `image/setup`, firstboot บางไฟล์, เอกสารติดตั้ง/สำรอง/นโยบายความเป็นส่วนตัว + README/เว็บจาก `image/public/`)
  ไม่มี memory, เล่ม, แล็บ หรือตัว build ภายในหลุดไปเอง เพราะเป็น allowlist
- ขั้นตอนเผยแพร่ (จากหัวไฟล์สคริปต์):
  ```bash
  git commit ...                                   # ไฟล์ใน ALLOW ต้อง commit ให้เรียบร้อยก่อน ไม่งั้นสคริปต์ปฏิเสธ
  bash image/publish-public.sh "ข้อความ commit"    # สร้าง commit ด้วย index ชั่วคราว ชี้ branch `public` ไปที่มัน
  git ls-tree -r --name-only public                 # ตรวจรายชื่อไฟล์ก่อนปล่อย
  git push public refs/heads/public:refs/heads/main # ต้องใช้ ref เต็ม เพราะชื่อ branch ชนกับชื่อ remote
  ```
  สคริปต์ไม่แตะ working tree และต่อ commit จาก `public/main` ทำให้ประวัติฝั่งสาธารณะเป็นเส้นของตัวเอง
- เพิ่มไฟล์ที่ต้องเปิดเผย = แก้ `ALLOW` ใน `publish-public.sh` ที่เดียว
- เรื่อง token/credential ของ GitHub: ห้ามใส่ลง URL ของ remote หรือไฟล์ในรีโป ใช้ credential helper ของเครื่อง

> หมายเหตุสำหรับ Claude: ถ้าผู้ใช้พิมพ์ "pull" หลังเสนอ push แปลว่า push ไป origin/dev ของตน (ดู `memory/user-says-pull-means-push.md`)

## 3. ตั้งสภาพแวดล้อมพัฒนา

- **Python 3.12** — `Dockerfile` ใช้ `python:3.12-slim-bookworm`; เครื่องพัฒนาที่ตรวจใช้ 3.12.1 (Raspberry Pi OS บน image ใช้ Python ของ distro)
- ติดตั้ง dependency:
  ```bash
  python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
  pip install -r app/requirements.txt pytest
  ```
  ใน Dockerfile ใช้ `pytest==8.3.5`; เครื่องที่ตรวจใช้ pytest 9.1.1 และผ่านได้
- **ไม่ต้องมี secrets จริง** — `tests/conftest.py` ตั้ง env ปลอมให้เอง (`NATID_PEPPER`, `NATID_DEK`, `SECRET_KEY`, `GATEWAY_NAME`,
  `RATE_LIMIT_BACKEND=memory`) และเพิ่ม `app/` กับรากรีโปเข้า `sys.path` (จึง `import common...` และ `import tools...` ได้)
- เทสต์ส่วนใหญ่ใช้ DB จำลองในไฟล์เทสต์เอง จึง**ไม่ต้องมี MariaDB** ถ้าต้องการสแตกครบ (MariaDB + Caddy proxy + admin + fas) ใช้ Docker Compose —
  ดูคำสั่งทั้งหมดใน [`docs/docker-test.md`](docker-test.md) (ใช้ข้อมูล/กุญแจปลอมใน `docker/test.env` ห้ามใช้กับข้อมูลจริง)
- ตัวแปรสภาพแวดล้อมของแอป (`DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASS`, `DB_NAME`, ...) อ่านใน `app/common/db.py` ฯลฯ;
  บนเครื่องจริง `install.sh` เขียนค่าลง `/etc/cafe-wifi/secrets.env` และ systemd อ่านเป็น `EnvironmentFile` — รายการเต็มดู `docs/configuration.md`

## 4. รันเทสต์

```bash
python -m pytest tests -q                       # ทั้งชุด
python -m pytest tests/test_crypto.py -q        # ไฟล์เดียว
python -m pytest tests -q -k voucher -x         # กรองชื่อ + หยุดที่ตัวแรกที่ล้ม
```

- รันจากรากรีโป; `tests/conftest.py` จัดการ path และ env ให้
- DB-dependent: เทสต์ของ admin/fas/logger/tools ส่วนใหญ่ **monkeypatch ชั้น DB ด้วยของปลอม** ในไฟล์เทสต์นั้น ๆ ไม่ต่อ MariaDB จริง
  (conftest ระบุว่า DB จำลองของแต่ละไฟล์ไม่รู้จักตาราง `rate_attempt` จึงบังคับ `RATE_LIMIT_BACKEND=memory`; ตัวนับแบบ DB มีเทสต์แยก `tests/test_ratelimit.py`)
  สำหรับ migration จริงต้องทดสอบบน MariaDB ผ่าน Docker Compose หรือบน Pi
- เทสต์ที่ต้องมีเครื่องมือระบบจะถูก `skipif` เอง เช่น `tests/test_backup_db.py` ข้ามถ้าไม่มี `sh`/`gzip` ในระบบ
- `tests/_run_tests.py` เป็น mini runner สำหรับแซนด์บ็อกซ์ที่ไม่มี pytest จริง (ใช้คู่กับ shim `/tmp/stubs/pytest`)
  ไฟล์เองระบุว่าไม่ใช่ส่วนหนึ่งของการส่งมอบ — **เครื่องปกติใช้ `python -m pytest`** อย่าใช้ตัวนี้
- ใน Docker: `docker compose run --rm tests`
- แผนและตารางสถานะ T1–Tn ครบ: [`docs/test-plan.md`](test-plan.md); หลักฐานจากฮาร์ดแวร์จริง: [`docs/hardware-test-log.md`](hardware-test-log.md)
- สคริปต์ shell ของ firstboot มีเทสต์ของมันเอง: `image/firstboot/test_firstboot.sh`

ผลที่รันตอนเขียนเอกสาร (Windows, Python 3.12.1, pytest 9.1.1, ~2.5 นาที): **526 passed, 10 failed, 2 skipped** — ที่ล้มคือ `test_backup_db.py` (4), `test_logger.py` (1),
`test_logger_restart.py` (4), `test_sysinfo.py::test_speed_test_...` (1) ซึ่งพึ่ง `sh`/`gzip`/พฤติกรรมไฟล์และ path แบบ POSIX จริง ไม่ได้ตรวจสาเหตุรายตัว
(สันนิษฐานว่าเป็นความต่างของสภาพแวดล้อม Windows) เทสต์เหล่านี้ตั้งใจให้รันบน Linux/Docker

## 5. ธรรมเนียมของโค้ด

สังเกตจากโค้ดจริง:

- **โครงโมดูล**: ตรรกะที่ใช้ร่วมอยู่ใน `app/common/` — admin, fas, setup, logger เรียกใช้เหมือนกัน (เช่น `common.audit`, `common.db`, `common.crypto`)
  ห้ามให้ `common` import ย้อนกลับไปหา admin/fas
- **Admin แยกไฟล์ตามหน้าที่** ใต้ `admin/views/` แต่ละไฟล์มี `routes = Routes()` ของตัวเอง ไม่ใช้ Flask Blueprint (เหตุผลใน docstring ของ `admin/routes.py`:
  Blueprint เติมคำนำหน้า endpoint ทำให้ `url_for` ทุกจุดต้องแก้) endpoint จึงคือชื่อฟังก์ชันตรง ๆ
- **เรียกตัวช่วยกลางผ่าน `core.*` ตอนรันเสมอ** (`from admin import app as core` แล้ว `core.query_all(...)`) ไม่ import ตัวฟังก์ชันมาตรง ๆ —
  เพราะเทสต์ `importlib.reload(admin.app)` แล้วสลับ DB จำลอง ถ้า import ตรงจะค้างตัวเก่า (docstring ของ `admin/views/overview.py`)
- **ค่าตั้งผ่าน env**: อ่านด้วย `os.environ.get("NAME", default)` ที่จุดใช้งาน ความลับอยู่ใน `secrets.env` ไม่ฝังในโค้ด
- **ความลับ/ข้อมูลส่วนบุคคล**: เลขบัตรเข้ารหัสด้วย `common/crypto.py` (pepper + DEK); เปิดดูต้องบันทึก audit ผ่าน `audit.log_required(...)` (ค่าคงที่ action อยู่ใน `common/audit.py`)
- **คอมเมนต์/docstring เป็นภาษาไทย** อธิบาย "ทำไม" มากกว่า "ทำอะไร" และบอกบั๊กที่เป็นต้นเหตุ ศัพท์เทคนิค/ชื่อ identifier เป็นอังกฤษ
- **แท็ก ID บั๊กในคอมเมนต์** เช่น `N17`…`N45` (บั๊ก/งานจากแล็บและรีวิว), `T1`–`T17` (รายการทดสอบ/ความเสี่ยง), `R11` (risk),
  `IMG-xx` (เทสต์ของ image), `M2`/`M3` (milestone), และ "(CODING_BRIEF.md) Nxx" — ใส่แท็กเมื่อแก้บั๊กที่มีเลข เพื่อค้นย้อนหาที่มาได้ด้วย grep
  ตัวอย่าง: `N45` = ENOBUFS ของ conntrack, `N42` = `users_to_router`, `N44` = openNDS restore client
- **หน้าต่างอ่านผลจริงเสมอ**: เทสต์ที่วัดผลปลายทาง (end-to-end) ดีกว่าเทสต์ที่เรียกฟังก์ชันตรง ๆ — ดูบทเรียน `memory/systemd-timer-accuracysec.md`
- **ข้อความภาษา**: ตอบผู้ใช้/เขียนเอกสารเป็นไทยหรืออังกฤษเท่านั้น (ข้อกำหนดใน `CLAUDE.md`)
- บันทึกความจำเมื่อแก้บั๊กที่ใช้เวลาค้นนาน ลง memory directory ของ Claude Code (hook ซิงก์เข้า `memory/` ให้ — [§9](#9-git-hook-ซิงก์ความจำ))

## 6. เพิ่ม DB migration

ไฟล์ใน `sql/`: `001_schema.sql` (schema ตั้งต้น), `003_partitions.sql` (opt-in), `005`–`013` เป็น migration (หมายเลข 002 และ 004 ไม่มีในรีโป)
กฎในคอมเมนต์ของ `install.sh`: **schema ที่ apply ไปแล้วแก้ตรงไม่ได้** — ต้องเพิ่มผ่าน migration ใหม่เสมอ

ขั้นตอน:

1. สร้าง `sql/0NN_ชื่อสั้น.sql` โดย NN = เลขถัดจาก 013 (ปัจจุบันคือ `014`) ดูไฟล์เดิมเป็นตัวอย่างรูปแบบ
2. **เขียนให้รันซ้ำได้ (idempotent)** — `CREATE TABLE IF NOT EXISTS`, ตรวจคอลัมน์ก่อน `ALTER` — เพราะ `install.sh` ถูกรันซ้ำบนเครื่องที่ติดตั้งแล้ว
   (เช่น ตอนอัปเดต หรือ `--stage firstboot`/`site`)
3. **ลงทะเบียนใน `install.sh`** — ไม่มีการ glob โฟลเดอร์; แต่ละ migration มีบล็อกของตัวเองในฟังก์ชันตั้ง DB (ประมาณบรรทัด 930–1050) รูปแบบ:
   ```bash
   local foo="${SCRIPT_DIR}/sql/014_foo.sql"
   if [[ -f "$foo" ]]; then
     run_sh "mysql '${DB_NAME}' < '${foo}'"
   else
     die "ไม่พบ sql/014_foo.sql — <ใครต้องใช้ไฟล์นี้>"   # หรือ warn ถ้าไม่จำเป็นต่อการทำงาน
   fi
   ```
   ใช้ `die` ถ้าแอปพังเมื่อไม่มีคอลัมน์/ตาราง ใช้ `warn` ถ้าเป็นของเสริม (เช่น `005`, `006`) ลำดับในสคริปต์ตอนนี้ไม่ใช่ลำดับเลขเป๊ะ
   (เช่น `013` อยู่ก่อน `012` และ `011`) — ให้ตรวจว่า migration ใหม่ไม่ขึ้นกับตัวที่อยู่หลังมัน
4. **บน image**: `cafe-wifi-firstboot.sh` ไม่ apply SQL เอง แต่เรียก `install.sh --stage firstboot` จาก `/opt/cafe-wifi/` (ใช้ `/opt/cafe-wifi/sql` ข้างกัน)
   ดังนั้นลงทะเบียนใน `install.sh` ที่เดียวก็ครอบคลุมทั้งการติดตั้งตรงและ image (ไม่ได้ตรวจเส้นทางนี้ด้วยการรันจริง — อ่านจากโค้ด)
5. ถ้า `tools/` หรือแอปอ้างตัวตารางใหม่ ให้เพิ่มเทสต์ และตรวจ `tools/purge_old_data.py` / `export_evidence.py` ว่าต้องรู้จักตารางนี้ไหม (ข้อมูลส่วนบุคคล + ระยะเก็บตามกฎหมาย)
6. อัปเดต `docs/database.md` (เอกสารพี่น้อง) และลองบน MariaDB จริงผ่าน Docker Compose ก่อน
7. ถ้าไฟล์ต้องไปกับรีโปสาธารณะ: `sql` อยู่ใน allowlist ทั้งโฟลเดอร์แล้ว ไม่ต้องแก้

## 7. เพิ่มหน้า Admin

ตัวอย่างอ้างจาก `app/admin/views/staff.py` และ `app/admin/templates/requests.html`:

1. **View**: ใส่ฟังก์ชันใน `app/admin/views/<หน้าที่>.py` (หรือสร้างไฟล์ใหม่ที่มี `routes = Routes()` และ `from admin import app as core`)
   ```python
   @routes.get("/foo")
   @core.login_required
   @core.admin_required          # ใส่เมื่อให้เฉพาะ role admin; ไม่ใส่ = staff ทุกคนที่ login แล้วเข้าได้
   def foo_page():
       rows = core.query_all("SELECT ...")       # เรียกผ่าน core.* เสมอ (ดู §5)
       return render_template("foo.html", rows=rows)
   ```
   ฟอร์ม POST: ตรวจ `core.csrf_ok()` และใส่ `csrf_token()` ในฟอร์ม (ดูหน้า staff เป็นตัวอย่าง)
2. **ผูกไฟล์ใหม่เข้า app**: ท้าย `app/admin/app.py` (บรรทัด ~397–400) มี `from admin.views import access, customers, keys, logs, overview, staff` และลูป
   `for _views in (overview, staff, access, customers, logs, keys): _views.routes.register(app)` — ไฟล์ view ใหม่ต้องเพิ่มทั้งใน import และใน tuple นี้
3. **Template**: `app/admin/templates/foo.html` ขึ้นต้น `{% extends "base.html" %}` แล้วใส่ `{% block title %}` กับ `{% block body %}`
4. **เมนู**: เพิ่มลิงก์ใน `templates/base.html` ใช้ `url_for('foo_page')` (ชื่อ endpoint = ชื่อฟังก์ชัน) ลิงก์เฉพาะ admin ให้อยู่ในบล็อก
   `{% if current_role == 'admin' %}`
5. **Permission**: role มีสองระดับ — staff ทั่วไป กับ `admin` (ใช้ `core.admin_required`) การกระทำที่แตะข้อมูลส่วนบุคคลต้องเรียก `audit.log_required(audit.<ACTION>, staff_id=session["staff_id"], target=...)`
   และถ้าเป็น action ใหม่ ให้เพิ่มค่าคงที่ใน `common/audit.py`
6. ข้อมูลที่ไวต่อความลับ: ระวัง cache (`no_cache_sensitive` ใน `admin/app.py` ตั้ง header ให้) และ rate limit ของหน้า login ใช้ `core.rate_limited/record_attempt`
7. เพิ่มเทสต์ใน `tests/` (ดูแบบอย่าง `tests/test_staff_management.py`, `tests/test_status_page.py`)

## 8. Build image

รายละเอียดแผนและเหตุผล: [`docs/image-build-plan.md`](image-build-plan.md) (ความลับที่ห้ามติด image §2, การแบ่ง stage §3, ขั้นตอน §6, แผนทดสอบ §7)
คู่มือติดตั้งจาก image ฝั่งผู้ใช้: `docs/install-from-image.md`

- **Windows**: ต้องมี Docker Desktop
  ```powershell
  powershell -ExecutionPolicy Bypass -File image\build.ps1            # build เต็ม (ครั้งแรก ~1–2 ชม. ใต้ QEMU)
  powershell -ExecutionPolicy Bypass -File image\build.ps1 -Reuse     # ใช้ stage0–2 จากรอบก่อน
  powershell -ExecutionPolicy Bypass -File image\build.ps1 -Reuse -Fast   # ไม่บีบอัด ได้ .img (~15 นาที) ใช้ทดสอบเท่านั้น
  ```
- **สำคัญ**: `build.ps1` build จาก `git archive HEAD` — **ของที่ยังไม่ commit ไม่ติดไปกับ image** (สคริปต์เตือนถ้า working tree สกปรก)
- `build.sh` รันใน container Debian (amd64, `--privileged`) ล็อก pi-gen tag ผ่าน `PIGEN_TAG` (ค่าตั้งต้น `2026-09-15-raspios-trixie-arm64`),
  โครง stage ของเราอยู่ใน `image/stage-cafewifi/` (`00-install`, `01-firstboot`, `02-lockdown`) และค่า pi-gen ใน `image/pigen/config`
  ตัวแปรควบคุม: `CAFEWIFI_REUSE=1`, `CAFEWIFI_FAST=1` (**ห้ามใช้ทำ release**)
- ผลลัพธ์ในโฟลเดอร์ `image/deploy/`: `cafe-wifi-<VERSION>-<วันที่>-<hash>.img.xz` + `.sha256` + `.info` + `.check.txt` + `os_list.json`
  (โฟลเดอร์นี้ผลใหญ่ — ตรวจ `.gitignore` ก่อน commit)
- **ตรวจความลับ**: `image/check-image.sh [--clean] <rootfs>` ตรวจว่าไม่มี `secrets.env`, `setup.token`, `tls/server.key`, ฐานข้อมูล `cafewifi`,
  SSH host keys, พอร์ต SSH สำรอง ฯลฯ ติดไปกับ image ท้าย build (stage `02-lockdown`) เรียกด้วย `--clean` เฉพาะลบของที่ OS สร้างใหม่ได้
  (host keys, random-seed) ส่วนความลับของเราห้ามลบเงียบ ๆ — ถ้าเจอ build ต้องล้ม และใช้ตรวจซ้ำกับ `.img` ที่ mount ก่อนแจกได้
- เขียนการ์ด: `image/prepare-sd.ps1`
- ทดสอบ firstboot logic แยก: `bash image/firstboot/test_firstboot.sh`
- ผลทดสอบ image บน Pi จริง: `docs/hardware-test-log.md` §3.15–3.15.2

## 9. Git hook ซิงก์ความจำ

`.githooks/pre-commit` คัดลอกไฟล์ `*.md` จาก memory directory ของ Claude Code
(`~/.claude/projects/<slug ของ path โปรเจกต์>/memory/`) เข้า `memory/` ในรีโปแล้ว `git add memory/` ให้ทุกครั้งที่ commit
ถ้าเครื่องนั้นไม่มีความจำ (เช่นเครื่องทำเอกสาร) hook ข้ามเงียบ ๆ ถ้าไฟล์ใน `memory/` ไม่มีในความจำจริงแล้ว hook **เตือนแต่ไม่ลบ** — ต้อง `git rm` เอง

เปิดใช้ครั้งเดียวต่อเครื่อง (`core.hooksPath` ไม่ติดไปกับ git):

```bash
git config core.hooksPath .githooks
```

ข้ามชั่วคราว: `git commit --no-verify` (ไม่แนะนำ — จะทำให้เครื่องอื่นได้ความจำค้างเก่า)
เครื่องนี้ตั้งแล้ว (`core.hookspath .githooks`)

## 10. Release

- เวอร์ชันอยู่ที่ `image/VERSION` (ตอนนี้ `1.1.0`); `build.sh` ใช้เป็นส่วนของชื่อไฟล์ image
- tag ที่มีในรีโป: `v1.0`, `v1.0.0`, `v1.0.1`, `v1.1.0` (`v1.0` คือจุดแช่แข็งของ `master`)
- ลำดับที่ใช้จริงตามประวัติ commit (ไม่มีสคริปต์ release อัตโนมัติ — ไม่พบในรีโป):
  1. แก้ `image/VERSION` + อัปเดต `image/public/README.md`/เว็บ Pages ถ้าต้องบอกเวอร์ชัน
  2. commit บน `image` แล้ว build เต็ม (**ไม่ใส่ `-Fast`**) จาก HEAD ที่ commit แล้ว
  3. ตรวจ `*.check.txt` (ผลของ `check-image.sh`) ว่าผ่านทั้งหมด และทดสอบบน Pi จริง บันทึกผลลง `docs/hardware-test-log.md`
  4. สร้าง tag `vX.Y.Z` แล้ว push ไป `dev` (`git push dev vX.Y.Z`)
  5. ถ้าต้องอัปเดตหน้าสาธารณะ: `publish-public.sh` ตาม [§2](#2-branch-และ-remote)
  6. อัปเดต `image/deploy/os_list.json` ถ้าแจกผ่าน Raspberry Pi Imager (ไม่ได้ตรวจรูปแบบเต็ม)
- `.img.xz` ขนาดใหญ่ไม่ควรเข้า git — ส่งผ่านช่องทางอื่น (ดู `.gitignore`)

## 11. กับดักที่ควรรู้

สรุปจาก `memory/` (อ่านไฟล์เต็มเมื่อแตะส่วนนั้น) — ห้ามคัดลอกรหัสผ่าน/IP ของแล็บจาก `memory/real-pi-deployment.md` ลงเอกสารสาธารณะ

- **ENOBUFS / conntrack (N45)** — `conntrack-tools 1.4.8` ตั้ง `--buffer-size` กับ socket ผิดตัว ทำให้ event socket ยังใช้ `net.core.rmem_default` เดิม (208 KB)
  แล้วล้นตอน GC ลบ entry เป็นชุด; ทางแก้คือตั้ง `net.core.rmem_default=16MB` และต้อง**ตรวจที่ผลลัพธ์** ไม่ใช่แค่ syscall สำเร็จ →
  [`memory/enobufs-status.md`](../memory/enobufs-status.md)
- **systemd timer AccuracySec** — `cafe-reconcile.timer` ที่ตั้ง 5 วินาทีเคยยิงห่าง 8–25 วินาทีเพราะ `AccuracySec=1min` ตั้งต้น ทำให้ตัดสิทธิ์ช้า ~25 วินาที;
  แก้เป็น `AccuracySec=1s` (เหลือ 6.7–8.3 วินาที) บทเรียน: วัด latency แบบ end-to-end →
  [`memory/systemd-timer-accuracysec.md`](../memory/systemd-timer-accuracysec.md)
- **openNDS คืนสิทธิ์ client เองตอน restart (N44)** — openNDS อ่าน `/tmp/ndslog/authlog.log` แล้ว `ndsctl auth` ซ้ำโดยไม่ดู DB อุปกรณ์ที่ถูกเพิกถอนจึงกลับมาออนไลน์ได้
  (ปัญหา ม.26: log ไม่ผูกตัวตน); `enforce` ต้องกวาดอุปกรณ์ตกค้างและรันซ้ำหลัง openNDS เริ่ม ~45 วินาที →
  [`memory/opennds-restores-clients-on-restart.md`](../memory/opennds-restores-clients-on-restart.md)
- **Admin เข้าได้จากวงลูกค้า (N42)** — หลังปิด DHCP ของ router พนักงานได้ IP วงลูกค้า จึงเปิด Admin ให้วงนั้น; ต้องอนุญาตทั้ง nftables input chain **และ** `users_to_router`
  ของ openNDS (การตั้ง list นี้ *แทนที่* ค่าตั้งต้นทั้งหมด จึงต้องใส่ครบพร้อม `ADMIN_PORT`) →
  [`memory/admin-access-from-customer-lan.md`](../memory/admin-access-from-customer-lan.md)
- **R11 openNDS บน NIC เดียว (macvlan)** — ความเสี่ยงใหญ่สุดของโครงแบบ Pi เดียวสายเดียว ปิดแล้ว: ใช้ macvlan, ทดสอบด้วยการรัน `install.sh` จริง และพบว่า
  openNDS ไม่เคยอ่าน config แบบ flat-text เลย → [`memory/r11-opennds-macvlan-resolved.md`](../memory/r11-opennds-macvlan-resolved.md)
- **macvlan/bcmgenet (ปิดแล้ว)** — เคยสงสัยว่า broadcast UDP พังบน Pi จริง แต่สาเหตุคือ nftables input policy ของเราเองทิ้ง DHCPDISCOVER จาก `0.0.0.0`;
  เก็บทฤษฎีที่ตัดทิ้งแล้วและบทเรียนการจับคู่ tcpdump ไว้ → [`memory/pi-macvlan-bcmgenet-open-issue.md`](../memory/pi-macvlan-bcmgenet-open-issue.md)
- **Chrome บน Android กับ Admin HTTPS** — ใบรับรอง self-signed ของ `admin.cafe.wifi` ถูกบล็อก (1.1.0 แก้ด้วยใบรับรองร้านแบบ name-constrained ที่ติดตั้งเป็น CA
  จาก `http://<gw>:8080/cafe-wifi.crt`) → [`memory/admin-https-captive-chrome.md`](../memory/admin-https-captive-chrome.md)
- **ฮาร์ดแวร์จริง** — อ่าน [`memory/real-pi-deployment.md`](../memory/real-pi-deployment.md) และ
  [`memory/pi-dhcp-and-portal-milestone.md`](../memory/pi-dhcp-and-portal-milestone.md) ก่อนแตะ Pi (มีกับดัก 6 ข้อที่เสียเวลาไปหลายชั่วโมง; ไฟล์ใน `memory/` มีข้อมูลแล็บ ไม่ควรเผยแพร่)
- **ข้อจำกัดเชิงออกแบบ: Pi เดียว สายเดียว** — ห้ามเสนอ interface/VLAN สำหรับจัดการแยก; ป้องกัน SSH/Admin ด้วยการยืนยันตัวตน, ปิด IPv6, WireGuard →
  [`memory/single-pi-single-cable-constraint.md`](../memory/single-pi-single-cable-constraint.md)
- **ก่อนส่งมอบร้าน** — ต้องเปลี่ยนรหัสผ่านบัญชีแล็บและถอด Wi-Fi แล็บออก (`memory/pending-service-wifi-reminder.md`)
- **เครื่องพัฒนา Windows** — เทสต์บางตัวพึ่ง `sh`/`gzip`/path แบบ POSIX จึงล้มบน Windows; ใช้ WSL/Docker (`docker compose run --rm tests`) ถ้าต้องการผลเขียวทั้งชุด
