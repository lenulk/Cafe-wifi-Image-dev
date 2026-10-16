# รีวิวโค้ด — ชั้นเครือข่าย install.sh (14 ต.ค. 2026)

ขอบเขต: `install.sh` — `configure_network` (nftables/dnsmasq/sysctl/macvlan), `configure_ssh`, `build_opennds`,
`configure_opennds`, `install_services`, `make_tls_cert`, `configure_nginx`, `start_services`
ทีม: Sonnet 2 ตัว (แยกส่วน อ่านอย่างเดียว) → Opus ตรวจซ้ำกับโค้ด · ยกเว้นตามการออกแบบ: Pi ตัวเดียวสายเดียว
(ตั้ง IP เองในวงเราเตอร์ = ตรวจจับได้อย่างเดียว), Admin เปิดให้วงลูกค้า, เลขบัตรผ่าน HTTP

**แก้แล้ว (14 ต.ค., ทดสอบในเครื่องด้วย `tests/test_install_sh.py` ที่ source ฟังก์ชันของ install.sh มาเรียกตรง):**
N5 (กุญแจ CA 0600 root:root + ลดสิทธิ์เครื่องเดิมทุกรอบ + ลบกุญแจเก่า), N10 (clone tag ไม่ได้ = หยุด ไม่ fallback),
N12, N13, N14, N15, N16, N20 · ยังต้องยืนยันบน Pi ตอนรัน install.sh ซ้ำ: nginx ยังเปิดได้หลังกุญแจเป็น 0600 root:root
**ยังเปิด (ต้องทำบน Pi):** N2, N3, N4, N6, N7, N8, N9 (meter ของ nft ตรวจไวยากรณ์ในเครื่องไม่ได้), N11, N17 · N18, N19 = ข้อจำกัดของการออกแบบ

**ข้อจำกัดสำคัญ:** ไม่มีชุดทดสอบของ install.sh ในเครื่อง (ตรวจได้แค่ `bash -n`) — ทุกข้อในรายงานนี้ต้องพิสูจน์/แก้บน Pi

## สูง

| # | ที่ | ปัญหา | สถานะ |
|---|---|---|---|
| N1 | `install.sh:1552` forward chain, `:1472` `flush ruleset`, `:2366` | **ด่านกันเน็ตมีแค่กฎของ openNDS เอง** — chain forward ของเราจบด้วย `ip saddr $CLIENT_NET accept` + masquerade ถ้ากฎของ openNDS ไม่อยู่ ลูกค้าที่ยังไม่อนุมัติออกเน็ตได้ทันที กรณีที่เกิดได้จริง: (a) **บูต/ไฟดับ**: nftables + dnsmasq ขึ้นก่อน openNDS ที่รอ `time-sync.target` (chrony-wait ได้ถึง 180 วิ) (b) openNDS ล่ม/ติด start-limit (c) **รัน install.sh ซ้ำ** หรือ `systemctl reload/restart nftables` → `flush ruleset` ลบตารางของ openNDS และ start_services ตั้งใจไม่ restart openNDS | ✅ **ยืนยันบน Pi 16 ต.ค. แล้วแก้** — ลูกค้าจำลองที่ยังไม่อนุมัติ: หยุด openNDS = ping ออกได้, `nft -f` = เปิด HTTPS ภายนอกได้ · แก้: forward ปล่อยเฉพาะ mark ของ openNDS (bit 0x20000 = trusted/auth) + ชุด `cafe_walledgarden` (dnsmasq nftset) · โหลดกฎใหม่ (install.sh, drop-in reload/start ของ nftables) = try-restart openNDS · ทดสอบซ้ำ: ทุกกรณีออกไม่ได้, `systemctl reload nftables` แล้ว openNDS สร้างตารางคืนใน 40 วิ ลูกค้าเดิมไม่หลุด, เครื่องใหม่ยังเด้งหน้าลงทะเบียน · กรณีบูต (a) ไม่ได้ลองรีบูต แต่ไม่มี mark ก่อน openNDS ขึ้น = ปิดไว้ก่อนโดยโครงสร้าง |
| N2 | ทั้งระบบ | เราเตอร์กลับมาเปิด IPv6 RA ภายหลัง (อัปเดต firmware/รีเซ็ต/ISP) → ลูกค้าทุกคนออก IPv6 ตรงที่เราเตอร์ ไม่ผ่าน portal ไม่มี log — ตรวจแค่ตอนติดตั้ง (`check_router`) และ bypass_detector ดูแค่ ARP IPv4 | ยืนยันจากโค้ด · ตรวจจับได้อย่างเดียว (ต้องเพิ่มตัวฟัง RA เป็นระยะ) |

## กลาง

| # | ที่ | ปัญหา | สถานะ |
|---|---|---|---|
| N3 | `install.sh:1531-1534` | พอร์ต 22 รับจากทุก source ที่ไม่ใช่วงลูกค้า → คนที่ตั้ง IP เองในวงเราเตอร์ (bypass ที่ยอมรับ) ได้ SSH พอร์ต 22 ที่ยังใช้รหัสผ่านได้ (เครื่องแล็บ `ras`) · image ปิดรหัสผ่านแล้ว (`30-cafe-wifi-image.conf`) | ยืนยัน · ผูกกับเรื่องเตือน SSH hardening ก่อนส่งมอบ |
| N4 | `install.sh:1619-1625` | dead-man switch = `nft flush ruleset` ทั้งหมด (ล้างทั้งของเราและของ openNDS) ไม่ใช่คืนกฎเดิม · ลืมยกเลิก = ไม่มี firewall เลย | ยืนยัน |
| N5 | `install.sh:2198` | กุญแจ CA ของร้าน (`server.key`, ใช้เป็นทั้ง CA และ TLS) เป็น `0640 root:cafewifi` — ผู้ใช้ที่รัน FAS (หน้าลูกค้า) อ่านได้ ทั้งที่ไม่มีโค้ดแอปตัวไหนใช้ (nginx อ่านด้วย root) → FAS ถูกเจาะ = ออกใบรับรอง admin.cafe.wifi ปลอมได้ · `server.key.old` ค้างตลอด | ยืนยัน (grep ไม่พบโค้ดแอปอ่านไฟล์นี้) |
| N6 | `install.sh:1824-1836` | `--trusted-mac`: ใครโคลน MAC นั้น (เช่น AP) ได้เน็ตไม่ต้องลงทะเบียน และ log โทษ MAC ของ AP | ยืนยันตรรกะ · ใช้เฉพาะร้านที่ตั้ง trusted MAC |
| N7 | `install.sh:1296-1305` | sysctl ตั้งแค่ `all.*` — `default.rp_filter`/`send_redirects` ของอินเทอร์เฟซ macvlan อาจไม่เป็นอย่างที่คอมเมนต์เข้าใจ | น่าจะจริง · ต้องดู `sysctl -a` บน Pi |
| N8 | `install.sh:1456-1461` | แก้ `--local-service` ด้วย `sed` ในไฟล์ของแพ็กเกจ dnsmasq → `apt upgrade` คืนค่าเดิม = DHCP ฝั่งลูกค้าพังเงียบ | ยืนยัน · ควรใช้ `dpkg-divert` หรือ drop-in |

## ต่ำ

- N9 `:1526` rate limit SSH alt port เป็นค่ารวมทั้งเครื่อง ไม่ใช่ต่อ IP — ลูกค้ายิงขยะจนช่างเข้าไม่ได้ (ควรใช้ `meter` ตาม `ip saddr`)
- N10 openNDS: clone ด้วย tag ไม่ปัก commit/checksum และถ้า clone tag ล้มจะ fallback ไป HEAD (อาจเป็น v11 ที่ config เปลี่ยน) แค่เตือน
- N11 `configure_opennds` เขียน config ใหม่แต่ไม่ restart openNDS ตอนรันซ้ำ — ลบ trusted MAC/เปลี่ยนพอร์ตไม่มีผลจนกว่า restart (ไม่มีคำเตือน)
- N12 `cafe-maintenance.service` ไม่มี `After=mariadb.service` + `Persistent=true` → บูตแล้วรันทันทีก่อน DB พร้อม และ `-` ซ่อนความล้มเหลว (purge/backup/integrity ข้ามไป 1 วัน)
- N13 `cafe-logger` ใช้ `Restart=on-failure` — ออกด้วย code 0 (SIGTERM หลง) ไม่ถูกเปิดใหม่ · ตัวเก็บหลักฐานควรเป็น `Restart=always`
- N14 `cafe-enforce.timer`/`cafe-bypass-detect.timer` ไม่ตั้ง `AccuracySec` (ค่าปริยาย 1 นาที — บทเรียนเดียวกับ systemd-timer-accuracysec)
- N15 `start_nginx`: `nginx -t` ไม่ผ่านแค่เตือนและทิ้ง output · `make_tls_cert`: openssl ล้มแล้ว `set -e` ตายเงียบ
- N16 `write_file` เขียนก่อน chmod — `/etc/config/opennds` (มี faskey) มีช่วงสั้น ๆ ที่สิทธิ์ตาม umask
- N17 macvlan ได้ MAC สุ่มใหม่ทุกบูต → ลูกค้า ARP cache ค้าง หลุดช่วงสั้น ๆ หลังไฟดับ
- N18 walled garden เป็น IP ของ CDN ใหญ่ + DNS ก่อน login = tunnel ได้ (แก้ไม่ได้เต็มที่ในการออกแบบนี้ — บันทึกเป็นข้อจำกัด)
- N19 DoH (443 ไปยัง resolver สาธารณะ) ไม่ผ่าน dnsmasq → conntrack เห็นปลายทาง แต่ไม่มีชื่อโดเมนใน dns_log (ข้อจำกัด ห้ามเคลมในเล่มว่าเก็บชื่อโดเมนครบ)
- N20 CLI `--client-cidr`/`--dhcp-range` ไม่ถูก validate ใน install.sh (wizard ตรวจแล้ว — เฉพาะ root ที่รันเอง)

## ส่วนที่ตรวจแล้วแน่น

ปลอมการอนุมัติไม่ได้ (FAS ไม่เคยให้ URL auth กับลูกค้า, auth ผ่าน `ndsctl auth` จาก root หลังพนักงานอนุมัติเท่านั้น, faskey 128 บิต) ·
FAS ล่ม = ลูกค้าติดหน้า portal ไม่ได้เน็ต (ปิดแบบปลอดภัย) · ไม่มี click-to-continue · DNS ทุก query (UDP/TCP 53) ถูก DNAT เข้า dnsmasq ·
DoT 853 ถูกปิด · ไม่มี flowtable/fastpath (ทุก flow ผ่าน conntrack) · IPv6 ขาเข้า Pi ถูก drop และไม่ forward v6 ·
dnsmasq ฟังเฉพาะฝั่งลูกค้า · gunicorn bind 127.0.0.1 · nginx เขียนทับ `X-Forwarded-For` (ปลอม IP หลบ rate limit ไม่ได้) ·
admin ใช้ TLS อย่างเดียว · ชื่อร้าน/MAC ถูก validate ก่อนเขียนลง config · `users_to_router` ครบ · `configure_ssh` ตรวจ `sshd -t` และย้อนกลับเมื่อพัง

## ⏳ ลำดับทดสอบบน Pi

| ข้อ | ทดสอบ | ผลที่ต้องได้ / แนวแก้ |
|---|---|---|
| ~~N1~~ | ✅ 16 ต.ค. — ยืนยันแล้วแก้ (ดูตารางบน) | — |
| N2 | เปิด IPv6 ที่เราเตอร์ แล้วดูว่ามือถือได้ IPv6 + ออกเน็ตได้ไหม | ได้ = ต้องมีตัวฟัง RA เป็นระยะ + แจ้งเตือนใน audit |
| N7 | `sysctl -a \| grep -E 'rp_filter\|send_redirects'` | ดูค่าจริงของ macvlan ก่อนตัดสินใจ |
| N8 | `apt-get install --reinstall dnsmasq` แล้วดูว่า DHCP ฝั่งลูกค้ายังทำงาน | ไม่ทำงาน = เปลี่ยนเป็น drop-in/dpkg-divert |
| N3–N6, N9–N17 | แก้ใน install.sh แล้วรัน install.sh ซ้ำบน Pi + ตรวจ service ทุกตัว | ไม่มีชุดทดสอบในเครื่อง |
