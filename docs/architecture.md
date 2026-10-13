# สถาปัตยกรรมระบบ Cafe-WiFi

> เอกสารนี้อธิบาย "ระบบประกอบกันอย่างไร และทำไมจึงออกแบบแบบนี้" — Raspberry Pi 4B ตัวเดียวต่อสาย LAN เส้นเดียวเข้ากับเราเตอร์ร้าน
> ทำหน้าที่เป็น gateway + captive portal + ตัวเก็บ log ตาม พ.ร.บ.คอมพิวเตอร์ ม.26 โดยลูกค้าต้องลงทะเบียนด้วยเลขบัตรประชาชนและพนักงานอนุมัติก่อนออกเน็ต
> ข้อมูลทุกอย่างในเอกสารนี้อ้างอิงจากโค้ดจริง (`app/`, `install.sh`, `image/`, `sql/`, `tools/`) — ถ้าโค้ดกับ `PROJECT_PLAN.md` ขัดกัน ให้เชื่อโค้ด

## สารบัญ

1. [ภาพรวมและเหตุผลของการออกแบบ](#1-ภาพรวมและเหตุผลของการออกแบบ)
2. [โทโพโลยีเครือข่าย](#2-โทโพโลยีเครือข่าย)
3. [องค์ประกอบของระบบ](#3-องค์ประกอบของระบบ)
4. [โฟลว์ลูกค้าตั้งแต่ต่อ Wi-Fi จนหมดสิทธิ์](#4-โฟลว์ลูกค้าตั้งแต่ต่อ-wi-fi-จนหมดสิทธิ์)
5. [การไหลของข้อมูล log](#5-การไหลของข้อมูล-log)
6. [โมเดลความปลอดภัย](#6-โมเดลความปลอดภัย)
7. [Service, timer และพอร์ต](#7-service-timer-และพอร์ต)
8. [วงจรชีวิตของเครื่อง (image / install.sh)](#8-วงจรชีวิตของเครื่อง-image--installsh)
9. [ข้อจำกัดที่ตั้งใจและข้อควรรู้](#9-ข้อจำกัดที่ตั้งใจและข้อควรรู้)
10. [เอกสารที่เกี่ยวข้อง](#10-เอกสารที่เกี่ยวข้อง)

---

## 1. ภาพรวมและเหตุผลของการออกแบบ

**หลักการข้อแรก — Pi ตัวเดียว สายเดียว** (`install.sh` หัวไฟล์, โหมด "one-armed router"):
ร้านกาแฟทั่วไปมีเราเตอร์ตัวเดียวที่ปล่อย Wi-Fi ให้ลูกค้า ระบบนี้จึงไม่ต้องการ switch/VLAN/พอร์ตแยกเพิ่ม
ช่างเสียบสาย LAN จากเราเตอร์เข้า Pi หนึ่งเส้น แล้ว **ปิด DHCP (และ IPv6 RA) ที่เราเตอร์** เพื่อให้ Pi เป็นผู้แจก IP, เป็น DNS และเป็น default gateway ของลูกค้าทุกคน
(เราเตอร์ยังคงเป็นเพียง AP/ทางออก ISP — Wizard ตรวจให้ก่อนบันทึกด้วย `tools/check_router.py` ว่า DHCP/IPv6 ของเราเตอร์ปิดจริง ดู `app/setup/apply.py`)

เมื่อลูกค้าทุกคนต้องผ่าน Pi เป็น gateway ระบบจึง:

- บังคับ **captive portal** ผ่าน openNDS (ลูกค้ายังไม่ได้รับอนุมัติ = ออกเน็ตไม่ได้)
- เห็นทุก connection (ผ่าน conntrack) และทุก DNS query (ผ่าน dnsmasq) → เก็บเป็น `conn_log` / `dns_log` โยงกลับถึงตัวบุคคลได้
- ไม่ต้องพึ่งอุปกรณ์เครือข่ายอื่นของร้าน

**หลักการข้อสอง — macvlan แทนการใส่ 2 IP บน NIC เดียว**:
Pi ต้องมี 2 IP (ฝั่งเราเตอร์/uplink และฝั่งลูกค้า/gateway) แต่ openNDS ปฏิเสธ interface ที่มีมากกว่า 1 IP
("IP address aliasing forbidden" — บันทึกไว้ใน `install.sh` ฟังก์ชัน `configure_network()`)
ทางออกคือสร้าง **macvlan** ชื่อ `cafe-wifi-cli0` (`CLI_IFACE`) ซ้อนบน NIC จริง (เช่น `eth0`):

- `eth0` ถือ IP uplink (ค่าตั้งต้นในสคริปต์ `192.168.1.2/24`, เปลี่ยนได้ผ่าน wizard/flag) ใช้ออกเน็ตและให้ช่างเข้า SSH
- `cafe-wifi-cli0` ถือ IP ฝั่งลูกค้า (ค่าตั้งต้น `10.10.0.1/24`) — dnsmasq, openNDS ผูกกับ interface นี้
- ทั้งสองอยู่บนสายกายภาพเส้นเดียวกัน

macvlan + IP ถูกสร้างซ้ำทุกบูตโดย `cafe-wifi-netsetup.service` (oneshot, เรียก `/opt/cafe-wifi/netsetup.sh`) —
ไม่พึ่ง NetworkManager/systemd-networkd/ifupdown ตัวใดตัวหนึ่ง (เหตุผลและบั๊กที่เจอระบุในคอมเมนต์ของ `configure_network()`)

**หลักการข้อสาม — เก็บหลักฐานครบ ปกป้องข้อมูลส่วนบุคคล**:
เลขบัตรประชาชนไม่เคยเก็บเป็น plaintext, log ถูกผนึกด้วย hash chain, ทุกการเข้าถึงข้อมูลสำคัญเขียน `audit_log`
(รายละเอียดในหัวข้อ 5–6 และ [`privacy-policy-th.md`](privacy-policy-th.md))

---

## 2. โทโพโลยีเครือข่าย

```
                     Internet
                         |
                  +--------------+
                  |  ISP modem / |   DHCP server = ปิด   IPv6 RA = ปิด
                  |  café router |   (เหลือแค่ Wi-Fi AP + ทางออก ISP)
                  +------+-------+
                         | LAN port
                         |            <-- สาย LAN "เส้นเดียว" ของระบบ
                  +------+---------------------------------------------+
                  |  Raspberry Pi 4B   (eth0 = NIC เดียว)              |
                  |                                                    |
                  |   eth0              uplink IP   (เช่น 192.168.1.2) |
                  |     |  default route -> เราเตอร์, SSH ของช่าง      |
                  |     |                                              |
                  |   cafe-wifi-cli0    macvlan บน eth0                |
                  |     |  IP ลูกค้า 10.10.0.1/24 (ค่าตั้งต้น)         |
                  |     |  = gateway + DHCP + DNS ของลูกค้า            |
                  |                                                    |
                  |   nftables: NAT (masquerade) + DNS redirect +      |
                  |             forward/input policy drop              |
                  |   openNDS  (gatewayinterface = cafe-wifi-cli0)     |
                  +----------------------------------------------------+
                         ^
                         | (L2 เดียวกันผ่านเราเตอร์/AP)
        +----------------+-----------------+
        |                |                 |
   มือถือลูกค้า      เครื่องพนักงาน      อุปกรณ์อื่น ๆ
   10.10.0.100-250   (ได้ IP วงเดียวกับลูกค้า → เข้า Admin ผ่าน https://admin.cafe.wifi)
```

ข้อสังเกตจากโค้ด:

| เรื่อง | พฤติกรรมจริง | ที่มา |
|---|---|---|
| ช่วง DHCP | `10.10.0.100`–`10.10.0.250` ค่าตั้งต้น, lease `4h`, `dhcp-authoritative` | `configure_network()` ใน `install.sh` |
| DNS | dnsmasq upstream `1.1.1.1`/`8.8.8.8`; nftables **dnat ทุก DNS query ของลูกค้า** (udp/tcp 53) เข้า dnsmasq ของ Pi เพื่อกัน DNS bypass | `table ip nat` ใน `/etc/nftables.conf` ที่ install.sh สร้าง |
| ชื่อที่ลูกค้าพิมพ์ได้ | `cafe.wifi` และ `admin.cafe.wifi` ชี้ไป IP ฝั่งลูกค้าของ Pi | `address=/cafe.wifi/...` ใน dnsmasq conf |
| NAT | `masquerade` ตาม source subnet (ไม่ใช้ชื่อ interface เพราะมี NIC เดียว) | nftables `postrouting` |
| Isolation ลูกค้า↔ลูกค้า | forward chain drop `CLIENT_NET → CLIENT_NET` (เฉพาะทราฟฟิกที่ผ่าน Pi — การคุยกันตรงบน L2 ต้องเปิด client isolation ที่ AP) | nftables `forward` |
| กันเข้าวงส่วนตัวของร้าน | forward drop `CLIENT_NET → 10/8, 172.16/12, 192.168/16` | nftables `forward` |
| DoT | drop tcp/udp 853 จากลูกค้า | nftables `forward` |

---

## 3. องค์ประกอบของระบบ

### 3.1 ภาพรวมการสื่อสารระหว่างองค์ประกอบ

```
 มือถือลูกค้า
     | (1) HTTP ใด ๆ -> openNDS ดัก
     v
 +-----------+  (2) redirect + query ?fas=<AES>&iv=<16>   +-----------------------+
 |  openNDS  | -----------------------------------------> | nginx :8080 / :80     |
 | (:2050)   |                                            |  -> cafe-fas (gunicorn|
 |           | <---- (6) ndsctl auth <mac> <นาที> ------- |     127.0.0.1:18080)  |
 +-----+-----+                                            +-----------+-----------+
       ^                                                              | (3) INSERT access_request
       | ndsctl (unix socket /tmp/ndsctl.sock)                        v
 +-----+------------------+      (5) อ่านคำขอที่อนุมัติ     +---------------------+
 | cafe-reconcile.timer   | <------------------------------ |   MariaDB           |
 |  tools/reconcile_pending|  (7) ยืนยัน session กับ openNDS |   127.0.0.1:3306    |
 | cafe-enforce.timer     | ------------------------------> |   (cafewifi)        |
 |  tools/enforce_voucher_ |                                +----------+----------+
 |  expiry                |                                           ^  ^
 +------------------------+                                           |  |
                                                  (4) พนักงานอนุมัติ  |  | เขียน conn_log / dns_log
 เครื่องพนักงาน --https--> nginx :443/:8443 --> cafe-admin (18443) ---+  |
                                                                         |
 conntrack -E ---------> cafe-logger (conn_collector) -------------------+
 dnsmasq.log ----------> cafe-logger (dns_collector)  -------------------+
```

### 3.2 ตารางองค์ประกอบ

| องค์ประกอบ | ตำแหน่งในรีโป | หน้าที่ | รันเป็น |
|---|---|---|---|
| **Customer portal (FAS)** | `app/fas/app.py`, `app/fas/opennds_proto.py`, `app/fas/templates/` | รับ redirect จาก openNDS (ถอดรหัส AES-256-CBC ด้วย `FAS_KEY`), แสดงฟอร์มลงทะเบียน (เลขบัตร + ยินยอม), สร้าง `access_request`, หน้า `/request` แสดงสถานะ/เวลาที่เหลือ, `/policy`, `/health` | `cafe-fas.service` (gunicorn 1 worker + 4 threads, `127.0.0.1:18080`) ผู้ใช้ `cafewifi` |
| **Admin UI** | `app/admin/app.py`, `app/admin/views/*.py`, `app/admin/templates/` | login พนักงาน, `/requests` (อนุมัติ/ปฏิเสธ), แดชบอร์ด, `/customers` (reveal/block/erase), `/logs` (ค้นหา, ส่งออก CSV, ตรวจ hash chain), `/evidence` (ส่งออกหลักฐาน), `/staff`, `/keys` (สำรองกุญแจ), `/status`, `/reports` | `cafe-admin.service` (gunicorn, `127.0.0.1:18443`) ผู้ใช้ `cafewifi` |
| **Setup wizard** | `app/setup/app.py`, `apply.py`, `restore.py`, `netinfo.py`; units ใน `image/setup/` | เฉพาะ image: ตั้งค่าครั้งแรกที่ `http://cafewifi.local` (ตรวจ setup code → สร้างแอดมินคนแรก → ตั้งเครือข่าย/ชื่อร้าน/อายุ log → ตรวจเราเตอร์ → บันทึก) และกู้คืนจากไฟล์สำรอง `.cwkey` + USB; หลังบันทึกสำเร็จจะปิดตัวเองถาวร (`.site-done`) | `cafe-wifi-setup.service` (ผู้ใช้ `cafewifi`) + `cafe-wifi-apply.service` / `cafe-wifi-restore.service` (root, ปลุกด้วย `.path`) |
| **Logger** | `app/logger/run_all.py` | entrypoint: รัน `conn_collector` + `dns_collector` เป็น thread, จับ SIGTERM แล้ว flush ก่อนออก | `cafe-logger.service` (`Nice=-5`, ได้เฉพาะ `CAP_NET_ADMIN CAP_NET_RAW`) |
| ↳ conn collector | `app/logger/conn_collector.py` | อ่าน `conntrack -E` บันทึกเฉพาะเหตุการณ์ DESTROY (มี bytes ปลายทาง) ลง `conn_log` พร้อม MAC (จาก ARP ผ่าน `netutil.MacCache`), `started_at`; ตรวจ ENOBUFS แล้วเขียน `log_gap` ลง `audit_log` | thread ใน cafe-logger |
| ↳ dns collector | `app/logger/dns_collector.py` | tail `/var/log/cafe-wifi/dnsmasq.log` แปลง `query`/`reply`/`cached` เป็นแถว `dns_log` (จำตำแหน่งที่อ่านถึงข้าม restart) | thread ใน cafe-logger |
| ↳ bypass detector | `app/logger/bypass_detector.py` | เฝ้าวง uplink หาอุปกรณ์ที่ตั้ง IP วง uplink เองเพื่อเลี่ยง Pi (ping ทั้งวงให้เกิด ARP แล้วอ่าน `/proc/net/arp`) เขียน `bypass_alert` + `audit_log` มี cooldown ต่อคู่ (ip, mac) — เป็นการ **ตรวจจับ ไม่ใช่ป้องกัน** | `cafe-bypass-detect.timer` ทุก 1 นาที |
| ↳ integrity | `app/logger/integrity.py` | ผนึก/ตรวจ hash chain ของไฟล์ log ที่หมุนแล้ว + ลบไฟล์ครบอายุ | เรียกใน `cafe-maintenance.service` และจากปุ่มบนแดชบอร์ด (`POST /logs/verify`) |
| ↳ telemetry | `app/logger/telemetry.py` | เขียนสถานะ collector (`collector-conn.json`, `collector-dns.json`) ให้หน้า Admin อ่านได้แม้ DB ล่ม | ภายใน collector |
| **Common modules** | `app/common/` | `crypto.py` (HMAC/AES-GCM/Argon2id/นโยบายรหัสผ่าน), `db.py`, `access.py` (คำขอ + จอง session), `audit.py`, `ratelimit.py`, `customer.py`, `device_info.py`, `keybackup.py` (ไฟล์สำรองกุญแจ), `log_mapping.py` (SQL JOIN log → ตัวบุคคล), `health.py`/`sysinfo.py` (หน้า `/status`), `traffic.py` | ใช้ร่วมโดย fas / admin / setup / tools |
| **Tools (CLI + timer)** | `tools/` | `reconcile_pending` (เปิดสิทธิ์/ยืนยัน session), `enforce_voucher_expiry` (ตัดสิทธิ์หมดอายุ), `purge_old_data`, `backup_db`, `check_disk`, `export_evidence`, `check_router`, `reset_admin`, `restore_keys`, สคริปต์ `lab_*` สำหรับทดสอบ | `cafe-reconcile`, `cafe-enforce`, `cafe-maintenance` (ดูหัวข้อ 7) |
| **openNDS** | build จาก source (`OPENNDS_REF` ใน `install.sh`, ค่าตั้งต้น `v10.1.3`); config `/etc/config/opennds` (รูปแบบ UCI) | captive portal engine: ดัก HTTP, redirect ไป FAS, คุม nftables ของลูกค้า (`ndsctl auth/deauth/json`) | `opennds.service` |
| **dnsmasq** | `/etc/dnsmasq.d/cafe-wifi.conf` | DHCP + DNS + `log-queries` (เป็นแหล่งของ `dns_log`) | `dnsmasq.service` |
| **nginx** | `/etc/nginx/.../cafe-wifi.conf` | reverse proxy: HTTP (`80`, `8080`) → FAS; HTTPS (`443`, `8443`) → Admin; เสิร์ฟใบรับรองร้านที่ `/cafe-wifi.crt` | `nginx.service` |
| **MariaDB** | `sql/*.sql` | ฐานข้อมูล `cafewifi` ฟังที่ `127.0.0.1:3306` เท่านั้น (`bind-address = 127.0.0.1`) | `mariadb.service` |

> รายละเอียดตาราง/คอลัมน์ ดู [`database.md`](database.md) · การ import ข้ามโมดูลและการเขียนโค้ดเพิ่ม ดู [`developer-guide.md`](developer-guide.md)

### 3.3 ทำไม gunicorn ใช้ 1 worker + 4 threads

`install.sh` (`install_services()`) อธิบายว่า rate-limit และ `SECRET_KEY` fallback เดิมเก็บในหน่วยความจำต่อโปรเซส
จึงใช้ `--workers 1 --threads 4` แทนหลาย worker ข้อแลกเปลี่ยนคือถ้า request หนึ่งค้าง worker เดียวจะไม่ตอบอย่างอื่นจนกว่า gunicorn จะฆ่า-เกิดใหม่หลัง `--timeout 60`
(ปัจจุบัน rate-limit ย้ายไปเก็บในตาราง `rate_attempt` แล้ว — `app/common/ratelimit.py` — แต่ unit ยังคงเป็น 1 worker ตามโค้ดใน install.sh)

---

## 4. โฟลว์ลูกค้าตั้งแต่ต่อ Wi-Fi จนหมดสิทธิ์

```
 ลูกค้า                openNDS            cafe-fas             staff (Admin)       reconcile / enforce
   |                      |                  |                      |                      |
   |-- ต่อ Wi-Fi, DHCP -->|                  |                      |                      |
   |   (ได้ IP 10.10.0.x จาก dnsmasq)        |                      |                      |
   |-- เปิดเว็บใดก็ได้ -->|                  |                      |                      |
   |<-- redirect ---------|                  |                      |                      |
   |   /login?fas=..&iv=..                   |                      |                      |
   |------------------------------------->   |                      |                      |
   |                      |   ถอดรหัส AES-256-CBC (FAS_KEY)         |                      |
   |                      |   เช็ค clientip == IP จริงของ request   |                      |
   |<---------------- ฟอร์ม: เลขบัตร 13 หลัก + ยินยอม PDPA          |                      |
   |-- POST ------------------------------>  |                      |                      |
   |                      |   เช็ค MAC จาก ARP == MAC ใน payload    |                      |
   |                      |   ตรวจ checksum บัตร, rate limit, is_blocked                  |
   |                      |   INSERT access_request (status=pending, หมดอายุ 15 นาที)       |
   |<-- redirect /request (แสดงรหัสคำขอ 4 ตัว) -|                     |                      |
   |                      |                  |   ลูกค้าส่งบัตรจริง + รหัสให้พนักงาน           |
   |                      |                  |      <-- เปิด /requests, กรอก "4 ตัวท้ายบัตร" -|
   |                      |                  |   เทียบกับเลขที่ถอดรหัสจาก natid_enc         |
   |                      |                  |   สร้าง/ใช้ voucher เดิม + portal_session(pending)
   |                      |                  |   access_request.status = approved          |
   |                      |                  |                      |   (ทุก 5 วินาที)       |
   |                      |<-------- ndsctl auth <mac> <นาทีที่เหลือ> ---|                      |
   |                      |   ยืนยัน session จาก ndsctl json <mac> -> portal_session = authenticated
   |<== ออกอินเทอร์เน็ตได้; หน้า /request แสดงเวลา/โควตาที่เหลือ ==>     |                      |
   |                      |   conn_log / dns_log ถูกเก็บตลอด (หัวข้อ 5)  |                      |
   |                      |                  |                      |   (ทุก 5 นาที)        |
   |                      |<---------- ndsctl deauth เมื่อ voucher หมดอายุ/ถูกยกเลิก/โควตาหมด --|
```

ลำดับขั้นอธิบายด้วยโค้ดจริง:

1. **ต่อ Wi-Fi** — dnsmasq แจก IP; rule `udp sport 68 dport 67` ใน nftables input ยอมรับ DHCPDISCOVER จาก `0.0.0.0`
   (บั๊กที่เคยทำให้ลูกค้าจริงเชื่อมต่อไม่ได้เลย — บันทึกไว้ในคอมเมนต์ nftables ของ install.sh)
   openNDS นับลูกค้าเป็น "ยังไม่ login" และ walled garden เปิดเฉพาะโดเมนที่ OS ใช้ตรวจ captive portal (Apple, Google, Microsoft, Firefox, GNOME)
2. **Redirect** — openNDS (`fas_secure_enabled = 2`) ส่งลูกค้าไป `faspath /login` พร้อมพารามิเตอร์ `fas` (base64 ที่เข้ารหัส) และ `iv`
   `app/fas/opennds_proto.py::decrypt_fas_payload` ถอดรหัสแล้วได้ `clientip`, `clientmac`, `gatewayname`, `originurl` ฯลฯ;
   `_valid_gateway()` และการเทียบ `clientip` กับ IP จริงของ request กัน payload ปลอม
   บริบทที่ถอดแล้วเก็บในตาราง `fas_context` โดยอ้างด้วย nonce (เก็บเป็น hash) ผูกกับ IP ใช้ครั้งเดียว
3. **ลงทะเบียน** — ฟอร์มรับเลขบัตร 13 หลักล้วน + checkbox ยินยอม; FAS ตรวจ `valid_thai_id`, ตรวจ MAC จากตาราง ARP ของเคอร์เนล (ไม่เชื่อค่าจากฟอร์ม),
   นับความพยายามผิดต่อ MAC (5 ครั้ง/10 นาที), ตรวจว่าลูกค้าไม่ถูกบล็อก, จำกัดคำขอที่รออยู่ไม่เกิน `MAX_PENDING_REQUESTS = 50`
   แล้ว INSERT `access_request` พร้อม `natid_hash`, `natid_enc`, `natid_masked`, ชื่อเครื่อง (จาก DHCP lease) และ OS (จาก User-Agent) ช่วยพนักงานระบุเครื่อง
   คำขออายุ `REQUEST_TTL_MIN = 15` นาที (`app/common/access.py`)
4. **พนักงานอนุมัติ** — `POST /requests/<id>/approve` (`app/admin/views/access.py`): พนักงานตรวจบัตรจริงแล้วพิมพ์ **4 ตัวท้าย** ระบบเทียบกับเลขที่ถอดรหัส
   (ผิด → บันทึก `REQUEST_MISMATCH` ใน audit) ถ้าถูก: สร้าง/ผูก `customer` (ใช้ `natid_hash` กันซ้ำ), ออก `voucher` (1–24 ชม., 1–5 เครื่อง, โควตา MB หรือไม่จำกัด) หรือ **ใช้ voucher เดิมที่ยัง active อยู่**,
   `reserve_pending_session()` จอง MAC + ตรวจโควตาจำนวนเครื่อง แล้วล้าง `natid_hash/natid_enc` ออกจากแถวคำขอทันที (เลขบัตรไปอยู่ในตาราง `customer` อย่างเดียว)
5. **เปิดสิทธิ์ที่ openNDS** — `cafe-reconcile.timer` (ทุก 5 วินาที, `AccuracySec=1s`) รัน `tools/reconcile_pending.py`:
   `authorize_approved()` สั่ง `ndsctl auth <mac> <นาทีที่เหลือ>` (ต้อง root เพราะ `ndsctl` ใช้ socket/ไฟล์ config ที่ root เท่านั้น),
   จากนั้นถาม `ndsctl json <mac>` ยืนยันว่า openNDS อนุญาตจริง (IP เดิม + `session_start` หลังเริ่ม pending) แล้วเลื่อน `portal_session` เป็น `authenticated`
   ถ้าเกิน `PENDING_SECONDS = 180` โดยไม่ได้รับการยืนยัน → ปิดเป็น `auth_timeout`
6. **ระหว่างใช้งาน** — `/request` (และ `http://cafe.wifi:8080/`) แสดงเวลา/โควตาที่เหลือ (รวมทุกเครื่องที่ใช้สิทธิ์เดียวกัน)
   พนักงานต่อเวลา (30/60/120 นาที), เพิ่มจำนวนเครื่อง หรือ "ปิดสิทธิ์" จากแดชบอร์ด → ตั้งธง `voucher.auth_sync_needed` ให้ reconcile ทำต่อใน ≤ 5 วินาที (`sync_extended()`: deauth แล้ว auth ใหม่ด้วยนาทีที่เหลือ)
7. **หมดสิทธิ์** — `cafe-enforce.timer` (ทุก 5 นาที) รัน `tools/enforce_voucher_expiry.py` ตั้ง `voucher.status` = `expired`/`used_up`,
   รวมยอด bytes จาก `conn_log` เข้า `portal_session`/`voucher.used_mb`, `ndsctl deauth` เครื่องที่หมดสิทธิ์, ปิด `portal_session` และกวาดเครื่องกำพร้าที่ openNDS ยังจำไว้
   (openNDS ถูกตั้ง `sessiontimeout 1440` เป็นเพดานกันตัดเร็วเกินไป เวลาที่แท้จริงถูกบังคับโดย enforce และโดยนาทีที่ส่งให้ `ndsctl auth`)
   หลัง openNDS สตาร์ท drop-in `cafe-wifi-orphan-sweep.conf` จะสั่ง `cafe-enforce.service` อีกครั้งที่ ~45 วินาที เพราะ openNDS คืนสิทธิ์ MAC ที่จำไว้โดยไม่ดู DB

> ตัวเลขเวลาเปิด/ปิดสิทธิ์ที่วัดจากเครื่องจริง ดู [`hardware-test-log.md`](hardware-test-log.md) · ขั้นตอนของพนักงาน ดู [`admin-guide.md`](admin-guide.md)

---

## 5. การไหลของข้อมูล log

```
 [ลูกค้า] --ทราฟฟิก--> Pi (conntrack, dnsmasq)
                            |                        |
                conntrack -E (DESTROY)         dnsmasq.log (log-queries)
                            |                        |
                      conn_collector            dns_collector
                            |  (+ MAC จาก ARP)       |
                            v                        v
                      +---------------- MariaDB ----------------+
                      |  conn_log     dns_log     audit_log      |
                      |  portal_session -> voucher -> customer   |
                      +---+----------------------+---------------+
                          |                      |
   MAPPING_JOIN (mac+ip+ช่วงเวลา session)        |
                          v                      |
        หน้า /logs  &  tools/export_evidence ----+--> CSV + manifest (SHA-256) + audit_log

 ไฟล์ดิบใน /var/log/cafe-wifi/*.log ──logrotate (daily, dateext)──> archive/*.log-YYYY-MM-DD[.gz]
        └─ chattr +a (append-only) ─> integrity.seal_directory ─> log_manifest (hash chain)
                                          └─> verify_chain (ทุกคืน 03:30 + ปุ่ม /logs/verify)

 purge_old_data ทุกคืน: ลบ conn_log/dns_log เก่ากว่า LOG_RETENTION_DAYS (≥ 90 วัน)
```

### 5.1 การเก็บ

- **`conn_log`**: `conntrack -E` ผ่าน `cafe-logger` — บันทึกเฉพาะ **DESTROY** เพราะเป็นเหตุการณ์เดียวที่มีตัวเลข bytes สุดท้าย
  ต้องเปิด `nf_conntrack_acct=1` (และ `nf_conntrack_timestamp=1` เพื่อให้รู้เวลาเริ่ม connection) — `cafe-wifi-conntrack-acct.service` ตั้งซ้ำทุกบูตหลัง nftables โหลดโมดูล
  เก็บ metadata เท่านั้น (ไม่เก็บเนื้อหา): `ts`, `started_at`, `mac`, `src_ip/port`, `dst_ip/port`, `proto`, `bytes_out/in`
- **`dns_log`**: จาก `dnsmasq.log` (`query` และ `answer`) ข้อจำกัด: DNS-over-HTTPS ในเบราว์เซอร์ไม่ผ่าน dnsmasq จึงไม่ถูกบันทึก (DoT ถูก drop ที่ nftables)
- **ป้องกัน log หาย**: sysctl `net.core.rmem_default = 16 MB` (แก้ ENOBUFS — ต้นเหตุคือ conntrack 1.4.8 ตั้ง buffer ผิด socket), notrack ให้ loopback และ ICMP ของ bypass detector
  (ลดเหตุการณ์ DESTROY ที่ไม่ใช่ทราฟฟิกลูกค้า), `Nice=-5` ให้ตัวอ่านก่อนงานอื่น, `cafe-logger` รอ `time-sync.target` ก่อนเขียน (Pi ไม่มี RTC)
  ถ้า collector ตรวจพบการทิ้งเหตุการณ์ จะเขียน `log_gap` ลง `audit_log` และสถานะลงไฟล์ telemetry
- **โยงถึงตัวบุคคล**: `app/common/log_mapping.py` JOIN `conn_log`/`dns_log` → `portal_session` (ด้วย mac + ip + ช่วงเวลา session) → `voucher` → `customer`
  ถ้า MAC/ช่วงเวลาตรงกับหลาย session จะ **ไม่เดา** (ไม่ผูกให้ใคร) — ทั้งหน้า `/logs` และ `export_evidence` ใช้ JOIN ชุดเดียวกันเพื่อให้ผลตรงกัน

### 5.2 Integrity: hash chain

สิ่งที่ถูกผนึกคือ **ไฟล์ log ดิบที่ logrotate หมุนแล้ว** ใน `/var/log/cafe-wifi/archive/` (เช่น `dnsmasq.log-2026-10-01.gz`, log ของ nginx/gunicorn) — ไม่ใช่แถวในตาราง `conn_log`
(ตรวจจากโค้ด `app/logger/integrity.py::seal_directory` และ pattern ใน `configure_logrotate()`)

- logrotate หมุนรายวัน (`rotate -1` = ไม่ให้ logrotate ลบเอง) แล้วตั้ง `chattr +a` ให้ไฟล์ใน archive (เขียนทับ/ลบไม่ได้แม้ root จนกว่าจะ `chattr -a` ซึ่งเป็นร่องรอย)
- `cafe-maintenance.service` (03:30) เรียก `logger.integrity`: `seal_directory` คำนวณ SHA-256 (ของเนื้อหาหลัง decompress) ผูก `prev_sha256` ของไฟล์ก่อนหน้าลงตาราง `log_manifest`
  → `verify_chain` ตรวจ hash, ลำดับ chain, ไฟล์หาย → ถ้าพบปัญหาเขียน `INTEGRITY_FAILED` ลง `audit_log` (คนละที่กับสิ่งที่ถูกแก้) และ exit code 1
- Admin ที่เป็น role `admin` กดตรวจเองได้ที่ `POST /logs/verify`
- `prune_archives` ลบไฟล์ครบอายุเมื่อ hash ยังตรงและไม่มีปัญหาค้าง (ไฟล์ที่มีปัญหา integrity ถูกเก็บไว้เป็นหลักฐาน) บันทึกการลบเป็น `raw_log_delete` และปฏิเสธถ้า retention < 90 วัน

### 5.3 การส่งออกหลักฐาน

`tools/export_evidence.py` (และหน้า `/evidence` ของ Admin): ระบุ MAC หรือเลขบัตร + ช่วงวันที่ → เขียน CSV แยก `conn_log` / `dns_log` (สิทธิ์ไฟล์ 0600, มี `voucher_username` และ `natid_masked` ไม่มีเลขบัตรเต็ม)
พร้อม manifest `.json` ที่มี SHA-256 ของแต่ละไฟล์ และบันทึก `audit_log` ว่าใครส่งออกอะไร — ขั้นตอนใช้งานจริงดู [`admin-guide.md`](admin-guide.md) และ [`cli-tools.md`](cli-tools.md)

### 5.4 Retention / purge

`tools/purge_old_data.py` (ใน `cafe-maintenance.service`):

- ลบ `conn_log`/`dns_log` ที่เก่ากว่า `LOG_RETENTION_DAYS` (ค่าตั้งต้น 180; โค้ดปฏิเสธต่ำกว่า 90 ตามขั้นต่ำของ ม.26)
- **ล้างข้อมูลระบุตัวตน** ของ `customer` ที่ไม่มี voucher active และ `last_seen` เก่ากว่า `CUSTOMER_RETENTION_DAYS` (ถ้าไม่ตั้ง ใช้เท่า log) — เก็บแถวไว้เพื่อรักษา foreign key
- ลบ `access_request` เก่า, `voucher_reveal` หมดอายุ, `rate_attempt` เก่ากว่า 1 วัน
- `audit_log` และ `log_manifest` **ไม่ถูกลบอัตโนมัติ**
- งานอื่นใน maintenance: `backup_db` (dump DB รายวัน เก็บ `BACKUP_RETENTION_DAYS` = 14 วัน + คัดลอกไป USB label `CAFEBACKUP` ถ้าเสียบอยู่ — ดู [`backup-usb.md`](backup-usb.md)), `check_disk`, `check_time.sh`

---

## 6. โมเดลความปลอดภัย

### 6.1 การเข้ารหัสเลขบัตรประชาชน (`app/common/crypto.py`)

เลขบัตรไม่ถูกเก็บเป็น plaintext แต่เก็บ 3 รูปแบบพร้อมกัน:

| คอลัมน์ | วิธี | ใช้ทำอะไร |
|---|---|---|
| `natid_hash` | HMAC-SHA256(เลขบัตร, `NATID_PEPPER`) | ค้นหา/กันซ้ำ (deterministic) |
| `natid_enc` | AES-256-GCM(เลขบัตร, `NATID_DEK`) เก็บเป็น `nonce(12) ‖ ciphertext ‖ tag(16)` | ถอดกลับได้เมื่อมีหมายศาล / ใช้เทียบ 4 ตัวท้ายตอนอนุมัติ |
| `natid_masked` | `1-2345-XXXXX-XX-3` (เปิดเฉพาะหลักแรกกับหลักสุดท้าย) | แสดงผลบนหน้าจอ/CSV |

- `NATID_DEK` และ `NATID_PEPPER` เป็นค่าสุ่ม 32 ไบต์ (hex 64 ตัว) อยู่ใน `/etc/cafe-wifi/secrets.env` (โหมด `0640 root:cafewifi`) เท่านั้น
- การถอดรหัสเลขเต็มทำได้ **เฉพาะ role `admin`**, ต้องระบุเหตุผล ≥ 10 ตัวอักษร และเขียน `audit_log` แบบ "required" (ถ้าเขียน audit ไม่ได้ ต้องไม่เปิดเผย) — `app/admin/views/customers.py::reveal`
- ขอลบข้อมูล (DSR/erase) ล้าง `natid_hash/enc/masked` แต่คงแถวไว้
- รหัสผ่านพนักงาน: Argon2id (`time_cost=3, memory_cost=64 MiB, parallelism=2`) นโยบาย ≥ 12 ตัว มีพิมพ์เล็ก/ใหญ่/ตัวเลข; รหัสชั่วคราวที่ระบบออกให้ใช้ได้ครั้งเดียวแล้วบังคับเปลี่ยน
- ข้อยอมรับที่เจ้าของโครงงานตัดสินใจ: เลขบัตรเต็มเดินทางจากมือถือลูกค้าถึง Pi บน **HTTP** (portal ไม่ใช่ HTTPS) — โค้ด FAS จึงไม่บันทึกเลขเต็มลง log/audit/หน้า error

### 6.2 ความลับประจำเครื่องและการสำรองกุญแจ

- `gen_secrets()` ใน `install.sh` สร้าง `DB_PASS`, `NATID_PEPPER`, `NATID_DEK`, `SECRET_KEY` (Flask), `FAS_KEY` (`openssl rand -hex 16` = 32 ตัวอักษร ใช้เป็นคีย์ AES ของ openNDS) และ `setup.token` ด้วย `openssl rand`
  - ใน image การสร้างทำที่ **บูตแรก** (`--stage firstboot`) ไม่ใช่ตอน build เพื่อไม่ให้ทุกเครื่องจาก image เดียวกันมีกุญแจเดียวกัน (เช่นเดียวกับ machine-id, SSH host keys และใบรับรอง TLS — ดู `image/firstboot/cafe-wifi-firstboot.sh` และ `make_tls_cert`)
  - ถ้า `secrets.env` มีอยู่แล้ว `install.sh` ใช้ของเดิมและอัปเดตเฉพาะค่าเครือข่าย (สร้างใหม่ = ข้อมูลที่เข้ารหัสไว้ถอดไม่ได้)
- **กุญแจอยู่บน SD card ใบเดียวกับข้อมูล** การ์ดเสีย = ถอดเลขบัตรไม่ได้ จึงมี `app/common/keybackup.py` + หน้า Admin `/keys`:
  สร้างไฟล์ `cafe-wifi-keys-<host>-<วันที่>.cwkey` เข้ารหัสด้วยรหัสผ่านของเจ้าของร้าน (scrypt N=2^15 → AES-256-GCM, หัวไฟล์เป็น AAD, รหัสผ่านอย่างน้อย 12 ตัว) ครอบคลุมคีย์ `NATID_DEK, NATID_PEPPER, SECRET_KEY, FAS_KEY, DB_PASS`
  ให้เก็บนอกเครื่อง; กู้คืนผ่าน Setup wizard (`app/setup/restore.py`) หรือ `tools/restore_keys.py` ร่วมกับไฟล์ dump ใน USB

### 6.3 Admin: HTTPS, session, rate limit

- **HTTPS ด้วยใบรับรองร้าน**: `make_tls_cert()` สร้างใบรับรอง self-signed 825 วัน (RSA 2048) ที่มี SAN `admin.cafe.wifi`, `cafe.wifi`, `localhost`, IP ฝั่งลูกค้า และ `basicConstraints CA:TRUE, pathlen:0` + **nameConstraints** จำกัดให้ใช้กับชื่อ/IP ของร้านเท่านั้น
  จึงให้เครื่องพนักงานติดตั้งเป็น CA ได้อย่างจำกัดขอบเขต โดยดาวน์โหลดจาก `http://<gateway>:8080/cafe-wifi.crt` (nginx เสิร์ฟจาก `/var/lib/cafe-wifi-ca/`); nginx ตั้ง TLS 1.2/1.3, HSTS, `X-Frame-Options: DENY`, `nosniff`
- **Session/CSRF**: cookie `HttpOnly`, `SameSite=Lax`, `Secure`; อายุ 8 ชั่วโมง; CSRF token ตรวจทุก POST (รวม `/login`); ทุก request ตรวจ role/สถานะ active ของพนักงานจาก DB ซ้ำ (เปลี่ยนสิทธิ์/ปิดบัญชีมีผลทันที)
- **Role**: `admin` และ `staff` (`ENUM` ใน `sql/001_schema.sql`) — เฉพาะ admin เข้า reveal/block/erase, ตรวจ hash chain, จัดการพนักงาน ฯลฯ (`@core.admin_required`)
- **Rate limit** (`app/common/ratelimit.py`): เก็บใน DB ตาราง `rate_attempt` (รอด restart service; ถ้า DB ล่มถอยไปใช้หน่วยความจำ) —
  Admin login: 5 ครั้ง/10 นาทีต่อ IP และ 10 ครั้ง/10 นาทีต่อชื่อผู้ใช้; FAS: 5 ครั้ง/10 นาทีต่อ MAC; Setup wizard: ผิด 5 ครั้งล็อกทั้งเครื่อง 15 นาที
- Admin ถูกเปิดให้วงลูกค้าเข้าถึงได้ **ตามที่เจ้าของโครงงานเลือก** เพราะร้านมีแค่เราเตอร์+Pi (พนักงานได้ IP วงเดียวกับลูกค้า) — ป้องกันด้วย HTTPS + รหัสผ่านรายคน + rate limit + audit ทุก login ที่ล้มเหลว

### 6.4 nftables และเครือข่าย

ไฟล์ `/etc/nftables.conf` (สร้างโดย `configure_network()`) วางหลักการ default-deny:

| chain | policy | กฎสำคัญ |
|---|---|---|
| `input` | **drop** | accept established/related; **`meta nfproto ipv6 drop`** (ระบบใช้ IPv4 อย่างเดียว กันเข้า sshd ผ่าน link-local); icmp จำกัดอัตรา; DHCP (`udp 68→67`); จากวงลูกค้าอนุญาตเฉพาะ DNS (53), DHCP (67), openNDS (`2050`), FAS (`8080`), `80`, Admin (`8443`, `443`) และ SSH เฉพาะพอร์ตสุ่มพร้อม rate limit; **พอร์ต 22 จากวงลูกค้าถูก drop**; จากวง uplink อนุญาต SSH/Admin |
| `forward` | **drop** | drop DoT (853), drop ลูกค้า→ลูกค้า, drop ลูกค้า→ช่วง IP ส่วนตัว (RFC1918), แล้วจึง accept `CLIENT_NET` (การคุมว่าใครออกเน็ตได้จริงทำโดยกฎของ openNDS) |
| `table ip raw` | accept | `notrack` สำหรับ loopback และ ICMP ของ bypass detector (กัน conntrack DESTROY ถล่มจน ENOBUFS) |
| `table ip nat` | accept | dnat DNS ของลูกค้าเข้า dnsmasq, masquerade วงลูกค้า |

- ผู้ติดตั้งที่รัน `install.sh` ผ่าน SSH จะมี **dead-man switch** (`systemd-run --on-active=300 nft flush ruleset`) กันล็อกตัวเองออก; ไม่ตั้งเมื่อรันผ่าน Setup wizard
- SSH: `configure_ssh()` เพิ่มพอร์ตสุ่ม (`SSH_ALT_PORT`) ที่ **บังคับ public key เท่านั้น** (`Match LocalPort`) เพื่อให้ช่างเข้าจากวงลูกค้าได้ — ใน image ผู้ใช้ช่าง (ค่าตั้งต้น `cafeadmin`) ได้ key จาก `cafewifi.conf` บน boot partition
- `/etc/config/opennds` โหมด `0640 root:root` (มี `faskey`); `users_to_router` ของ openNDS ต้องใส่พอร์ตทั้งชุดเอง (กำหนดแล้ว **แทนที่ค่าปริยายทั้งหมด**) รวมพอร์ต Admin ด้วย
- Hardening ของ systemd units: `NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome`, `RestrictAddressFamilies`; `cafe-logger` ได้เฉพาะ `CAP_NET_ADMIN CAP_NET_RAW`;
  `cafe-enforce` / `cafe-reconcile` รันเป็น root + `PrivateTmp=no` เพราะต้องคุยกับ `/tmp/ndsctl.sock` (เมื่อรันเป็น `cafewifi` เคยทำให้ `ndsctl deauth` ล้มเหลวเงียบ ๆ — ดูคอมเมนต์ใน `install_services()`)

### 6.5 Audit log

`app/common/audit.py` เขียน `audit_log` สำหรับ: login ล้มเหลว, CSRF reject, อนุมัติ/ปฏิเสธ/เลขไม่ตรง, reveal เลขบัตร, ส่งออกหลักฐาน, ตรวจ integrity, `log_gap`, bypass, purge, ลบ raw log, restore ฯลฯ
ฟังก์ชัน `log_required` ใช้กับการกระทำที่ต้องมีร่องรอยก่อนจึงจะทำได้ (ผูกกับ transaction เดียวกัน)

---

## 7. Service, timer และพอร์ต

### 7.1 Service และ timer

| Unit | ชนิด | ความถี่/เงื่อนไข | ทำอะไร |
|---|---|---|---|
| `cafe-wifi-netsetup.service` | oneshot | ทุกบูต (ก่อน dnsmasq/nftables/opennds) | ตั้ง IP uplink, สร้าง macvlan `cafe-wifi-cli0` + IP ลูกค้า, default route |
| `nftables.service` | — | ทุกบูต | โหลด `/etc/nftables.conf` |
| `cafe-wifi-conntrack-acct.service` | oneshot | หลัง nftables | เปิด `nf_conntrack_acct`/`timestamp`, ลด TCP established timeout เป็น 7440 วินาที |
| `dnsmasq.service` | daemon | — | DHCP + DNS + query log |
| `opennds.service` | daemon | + drop-ins (heartbeat, orphan-sweep, time-sync) | captive portal |
| `nginx.service` | daemon | — | reverse proxy |
| `mariadb.service` | daemon | — | ฐานข้อมูล |
| `cafe-fas.service` | daemon (gunicorn) | — | หน้าลูกค้า |
| `cafe-admin.service` | daemon (gunicorn) | — | หน้าพนักงาน |
| `cafe-logger.service` | daemon | หลัง `time-sync.target` | conn + dns collector |
| `cafe-reconcile.timer` → `.service` | timer | ทุก **5 วินาที** (`OnUnitInactiveSec=5sec`, `AccuracySec=1s`) | เปิดสิทธิ์ที่อนุมัติ, ยืนยัน/หมดเวลา pending, ซิงก์การต่อเวลา/ปิดสิทธิ์ |
| `cafe-enforce.timer` → `.service` | timer | ทุก **5 นาที** (+ 45 วินาทีหลัง openNDS สตาร์ท) | ตัดสิทธิ์หมดอายุ/โควตา, ปิด session ค้าง |
| `cafe-bypass-detect.timer` → `.service` | timer | ทุก **1 นาที** | ตรวจอุปกรณ์ที่เลี่ยง Pi |
| `cafe-maintenance.timer` → `.service` | timer | ทุกวัน **03:30** (`Persistent=true`) | purge → backup_db → check_disk → integrity → check_time |
| `cafe-wifi-setup.service`, `cafe-wifi-apply.path/.service`, `cafe-wifi-restore.path/.service` | image เท่านั้น | ทำงานจนกว่า `/etc/cafe-wifi/.site-done` จะถูกสร้าง | Setup wizard / ใช้ค่า / กู้คืน |
| `cafe-wifi-firstboot.service`, `cafe-wifi-factory-reset.service` | image เท่านั้น | บูตแรก / รีเซ็ตโรงงาน | สร้างความลับประจำเครื่อง + DB; ล้างเครื่องกลับสู่โหมดตั้งค่า |

หน้า `/status` ของ Admin ตรวจ "service ที่ควรรันตลอด" (`app/common/health.py`) — ตั้งใจ **ไม่รวม** unit แบบ oneshot ที่ผูกกับ timer เพราะปกติเป็น `inactive`

### 7.2 พอร์ต

| พอร์ต | ผู้ฟัง | เข้าถึงจาก | หมายเหตุ |
|---|---|---|---|
| 53 (udp/tcp), 67 (udp) | dnsmasq | วงลูกค้า | DNS/DHCP |
| 80 | nginx | วงลูกค้า | → FAS (openNDS มีกฎ redirect พอร์ต 80 ที่ gateway ไปหน้าของตัวเอง จึงให้ลูกค้าดูสถานะที่ `http://cafe.wifi:8080`) |
| 8080 (`FAS_PORT`) | nginx | วงลูกค้า | → FAS; เสิร์ฟ `/cafe-wifi.crt` |
| 2050 (`NDS_PORT`) | openNDS | วงลูกค้า | gateway port |
| 443, 8443 (`ADMIN_PORT`) | nginx (TLS) | วงลูกค้า + uplink | → Admin |
| 18080 / 18443 | gunicorn FAS / Admin | `127.0.0.1` เท่านั้น | backend ภายใน |
| 3306 | MariaDB | `127.0.0.1` เท่านั้น | |
| 22 | sshd | **เฉพาะ uplink** (วงลูกค้าถูก drop) | |
| `SSH_ALT_PORT` (สุ่ม) | sshd | วงลูกค้า + uplink | public key เท่านั้น, จำกัด 6 การเชื่อมต่อใหม่/นาทีจากวงลูกค้า |
| 80 (`[::]:80`) | Setup wizard | ช่วงตั้งค่าครั้งแรกเท่านั้น | `http://cafewifi.local`; ปิดหลัง `.site-done` |

---

## 8. วงจรชีวิตของเครื่อง (image / install.sh)

`install.sh --stage` แบ่งงานเป็นสามช่วง (ตารางใน `main()` ของ `install.sh` และ [`image-build-plan.md`](image-build-plan.md)):

| ช่วง | รันเมื่อ | ทำอะไร |
|---|---|---|
| `build` | ตอนสร้าง image (chroot, pi-gen ใน `image/stage-cafewifi/`) | ติดตั้งแพ็กเกจ, สร้าง venv + dependencies, วางโค้ดที่ `/opt/cafe-wifi`, build openNDS, สร้าง unit/nginx/logrotate, ตั้ง chrony, fstab ของ USB |
| `firstboot` | บูตแรกบน Pi (`cafe-wifi-firstboot.service`) | machine-id, SSH host keys, ผู้ใช้ช่าง/SSH key, setup code (เขียน `SETUP-CODE.txt` ลง boot partition), **สร้าง `secrets.env`**, ตั้งค่า MariaDB + import `sql/`, ตั้ง sshd พอร์ตสุ่ม, ออกใบรับรองเบื้องต้น |
| `site` | หลังช่างกรอก wizard (`setup.apply` รันเป็น root) | ตั้งเครือข่ายตามร้าน (macvlan, dnsmasq, nftables), เขียน `/etc/config/opennds`, ออกใบรับรองใหม่ตามวงลูกค้า, เปิด nginx และ service/timer ทั้งหมด |
| `all` (ค่าปริยาย) | ติดตั้งบน Debian/Ubuntu/RPi OS ที่มีอยู่รวดเดียว | ทำทุกช่วงต่อกัน |

ก่อน `site` เครื่องยังไม่มี portal และลูกค้ายังใช้ Wi-Fi ร้านตามปกติ (DHCP ของเราเตอร์ยังเปิดอยู่) — wizard จึงป้องกันด้วย setup code + ล็อกเมื่อผิดซ้ำ
ขั้นตอนฝั่งช่างทั้งหมดอยู่ใน [`install-from-image.md`](install-from-image.md); เรื่องการเตรียมเราเตอร์ ISP ดู [`isp-router-runbook.md`](isp-router-runbook.md)

---

## 9. ข้อจำกัดที่ตั้งใจและข้อควรรู้

- **Bypass ตรวจจับได้ ป้องกันไม่ได้**: อุปกรณ์ที่ตั้ง IP วง uplink เองจะคุยกับเราเตอร์ตรง ๆ ไม่ผ่าน Pi และไม่ถูกบันทึก `conn_log`/`dns_log`; `bypass_detector` เพียงบันทึกร่องรอย (และเป็น polling จึงอาจพลาดอุปกรณ์ที่ต่อสั้นมาก)
  การป้องกันจริงต้องทำที่เราเตอร์/AP (client isolation, access control)
- **ลูกค้า↔ลูกค้าบน L2 เดียวกัน**: nftables ของ Pi กันได้เฉพาะทราฟฟิกที่ผ่าน Pi — ต้องเปิด client isolation ที่ AP
- **DNS-over-HTTPS**: บันทึกไม่ได้ (ไม่ผ่าน dnsmasq)
- **เลขบัตรเต็มบน HTTP** ระหว่างมือถือกับ portal (ความเสี่ยงที่ยอมรับ)
- **Single point of failure**: Pi ตัวเดียว ไฟดับ/การ์ดเสียหมายถึงลูกค้าออกเน็ตไม่ได้ (ทดสอบการกู้คืนหลังไฟดับแล้วใน [`hardware-test-log.md`](hardware-test-log.md)); การ์ดเสียต้องมีไฟล์ `.cwkey` + USB สำรองจึงจะกู้เลขบัตรได้
- **gunicorn 1 worker**: ดูหัวข้อ 3.3
- **IPv6**: ถูกปิดทั้งที่เราเตอร์ (wizard ตรวจ) และ drop ที่ nftables ของ Pi

---

## 10. เอกสารที่เกี่ยวข้อง

| เรื่อง | เอกสาร |
|---|---|
| ติดตั้งจาก image | [`install-from-image.md`](install-from-image.md) |
| ผลทดสอบบนฮาร์ดแวร์จริง | [`hardware-test-log.md`](hardware-test-log.md) |
| แผนทดสอบ | [`test-plan.md`](test-plan.md) |
| เตรียมเราเตอร์ ISP | [`isp-router-runbook.md`](isp-router-runbook.md) |
| สำรองข้อมูลลง USB | [`backup-usb.md`](backup-usb.md) |
| นโยบายความเป็นส่วนตัว | [`privacy-policy-th.md`](privacy-policy-th.md) |
| แผนสร้าง image | [`image-build-plan.md`](image-build-plan.md) |
| คู่มือผู้ดูแล / นักพัฒนา / ปฏิบัติการ | `admin-guide.md`, `developer-guide.md`, `operations.md` |
| ค่าตั้งค่า / ฐานข้อมูล / เครื่องมือ CLI | `configuration.md`, `database.md`, `cli-tools.md` |
