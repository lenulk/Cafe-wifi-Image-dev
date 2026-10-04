#!/bin/bash
# tools/lab_fulltest.sh -- ทดสอบทั้งระบบบน Pi จริงรวดเดียว (regression) ใช้: sudo bash lab_fulltest.sh
# ต้องมี tools/lab_client.sh ที่ /root/cafe-client-test/client.sh (ดู lab_e2e_register.sh) · เลขบัตรทดสอบ 1101700000010
# ทดสอบทั้งระบบบน Pi จริง -- ทุกขั้นผ่านเครื่องลูกค้าจำลอง (network namespace "cte") บนวงลูกค้า
# ใช้บัญชีพนักงาน/SSH key ชั่วคราว ลบทิ้งตอนจบเสมอ (trap)
set -u
M=02:ca:fe:00:00:2a; MU=02:CA:FE:00:00:2A; NATID=1101700000010
X="ip netns exec cte"; CJ=/tmp/ft-cj; PASS=0; FAIL=0
cd /opt/cafe-wifi
ENVV="env $(grep -v '^#' /etc/cafe-wifi/secrets.env | xargs) PYTHONPATH=/opt/cafe-wifi"
SSHP=$(grep ^SSH_ALT_PORT= /etc/cafe-wifi/secrets.env | cut -d= -f2)
PW="Ft-$(openssl rand -hex 6)-x9"
ok()   { PASS=$((PASS+1)); printf "  \e[32mPASS\e[0m %s\n" "$1"; }
bad()  { FAIL=$((FAIL+1)); printf "  \e[31mFAIL\e[0m %s  [%s]\n" "$1" "$2"; }
chk()  { if [ "$2" = "$3" ]; then ok "$1"; else bad "$1" "got '$2' want '$3'"; fi; }
has()  { if grep -q -- "$3" <<<"$2"; then ok "$1"; else bad "$1" "missing '$3'"; fi; }
sq()   { mysql cafewifi -N -e "$1"; }
cleanup() {
  # ห้าม DELETE: ถ้าบัญชีนี้เคยกดอนุมัติ voucher จะอ้างถึง (fk_voucher_staff) ลบไม่ได้แล้วค้าง "เปิดใช้งาน" อยู่
  # (เกิดจริง 2026-10-03 -> ค้างเปิดอยู่ ~21 ชม.) -- ปิดใช้งาน + สุ่มรหัสใหม่ทิ้งแทน
  sq "UPDATE staff SET is_active=0, password_hash=SHA2(UUID(),256), password_changed_at=NOW() WHERE username='ft-staff'" 2>/dev/null
  sed -i '/cafe-fulltest-key/d' /home/ras/.ssh/authorized_keys 2>/dev/null; rm -f /tmp/ftkey /tmp/ftkey.pub $CJ /tmp/ft.*
  sq "DELETE FROM rate_attempt WHERE bucket IN ('login:10.10.0.177','login-user:ft-staff')" 2>/dev/null
  /root/cafe-client-test/client.sh down cte >/dev/null 2>&1; ndsctl deauth $M >/dev/null 2>&1
}
trap cleanup EXIT

echo "== 1. ระบบพื้นฐาน"
for s in cafe-admin cafe-fas cafe-logger opennds dnsmasq nginx mariadb chrony; do chk "service $s" "$(systemctl is-active $s)" active; done
chk "Pi resolve DNS ได้เอง (N40)" "$(getent hosts time1.nimt.or.th >/dev/null && echo y)" y
off=$(chronyc tracking | awk '/System time/{printf "%.3f", $4*1000}')
chk "นาฬิกาคลาด < 10ms (ม.26) [${off}ms]" "$(awk -v o="$off" 'BEGIN{print (o<10)?"y":"n"}')" y
chk "conntrack ไม่ติดตาม loopback (N43)" "$(conntrack -L 2>/dev/null | grep -c 'src=127\.')" 0

echo "== 2. ลูกค้าขอใช้งาน (เครื่องจำลองบนวงลูกค้า)"
/root/cafe-client-test/client.sh down cte >/dev/null 2>&1; ndsctl deauth $M >/dev/null 2>&1
sq "UPDATE portal_session SET state='closed', ended_at=NOW(), terminate_cause='disconnected' WHERE mac='$MU' AND state='authenticated'"
sq "UPDATE access_request SET status='expired' WHERE mac='$MU' AND status='pending'"
/root/cafe-client-test/client.sh up cte $M >/dev/null
chk "ยังไม่ขอใช้งาน = ออกเน็ตไม่ได้" "$($X curl -s -m 8 -o /dev/null -w '%{http_code}' http://example.com/)" 307
loc=$($X curl -s -m 8 -o /dev/null -w '%{redirect_url}' http://example.com/)
base=$(echo "$loc" | sed 's#\(http://[^/]*\)/.*#\1#')
page=$($X curl -s -m 8 -b $CJ -c $CJ -L "$loc")
has "หน้า portal มีช่องเลขบัตร 13 หลัก" "$page" 'pattern="\[0-9\]{13}"'
chk "หน้า portal ไม่มีช่องทางไปหน้าแอดมิน" "$(grep -c 'แอดมิน\|admin.cafe\|8443' <<<"$page")" 0
nonce=$(grep -o 'name="nonce" value="[^"]*"' <<<"$page" | sed 's/.*value="//;s/"//')
chk "เลขบัตรมีขีด ถูกปฏิเสธ" "$($X curl -s -m 8 -b $CJ -c $CJ -o /dev/null -w '%{http_code}' --data-urlencode "nonce=$nonce" --data-urlencode natid=1-1017-00000-01-0 -d consent=on "$base/login")" 400
chk "ส่งคำขอด้วยเลขบัตรถูกต้อง" "$($X curl -s -m 8 -b $CJ -c $CJ -A 'Mozilla/5.0 (Linux; Android 14; SM-A546E)' -o /dev/null -w '%{http_code}' --data-urlencode "nonce=$nonce" --data-urlencode natid=$NATID -d consent=on "$base/login")" 303
code=$($X curl -s -m 8 http://cafe.wifi:8080/request | grep -oE '>[A-Z0-9]{4}</div>' | head -1 | tr -d '<>/div')
chk "หน้ารอแสดงรหัสคำขอ 4 ตัว [$code]" "${#code}" 4
chk "คำขอเก็บชื่อเครื่อง/OS" "$(sq "SELECT CONCAT(hostname,'|',os_label) FROM access_request WHERE code='$code'")" "Lab-cte-Phone|Android 14 · SM-A546E"

echo "== 3. พนักงานเข้า https://admin.cafe.wifi จากวงลูกค้า แล้วอนุมัติ"
$ENVV ./venv/bin/python - "$PW" >/tmp/ft.py.err 2>&1 <<'PY'
import sys
from common import crypto
from common.db import execute
# สร้างครั้งแรก หรือใช้บัญชีเดิม (ลบไม่ได้ถ้าเคยอนุมัติ) -- ตั้งรหัสใหม่ + เปิดใช้งานเฉพาะระหว่างทดสอบ
execute("INSERT INTO staff (username, password_hash, display_name, role, is_active, must_change_password) "
        "VALUES ('ft-staff', %s, 'ทดสอบรวม', 'admin', 1, 0) "
        "ON DUPLICATE KEY UPDATE password_hash=VALUES(password_hash), is_active=1, must_change_password=0, "
        "role='admin', password_changed_at=NOW()", (crypto.hash_password(sys.argv[1]),))
PY
[ "$(sq "SELECT is_active FROM staff WHERE username='ft-staff'")" = 1 ] || { bad "สร้างบัญชีทดสอบ" "$(tail -1 /tmp/ft.py.err)"; exit 1; }
rm -f $CJ; A="$X curl -s -m 10 --cacert /etc/cafe-wifi/tls/server.crt -b $CJ -c $CJ"
tok() { $A "$1" | grep -o 'name="csrf_token" value="[^"]*"' | head -1 | sed 's/.*value="//;s/"//'; }
t=$(tok https://admin.cafe.wifi/login)
chk "login ผ่าน https://admin.cafe.wifi (cert ตรงชื่อ)" "$($A -o /dev/null -w '%{http_code}' --data-urlencode "csrf_token=$t" -d username=ft-staff --data-urlencode "password=$PW" https://admin.cafe.wifi/login)" 302
for p in / /requests /customers "/logs?range=today" /reports /status /evidence /staff; do
  chk "หน้า $p" "$($A -o /dev/null -w '%{http_code}' "https://admin.cafe.wifi$p")" 200
done
req=$($A https://admin.cafe.wifi/requests)
has "หน้าคำขอเห็นรหัส $code + ชื่อเครื่อง" "$req" "Lab-cte-Phone"
chk "หน้าคำขอไม่มีเลขบัตรเต็ม" "$(grep -c "$NATID" <<<"$req")" 0
rid=$(grep -o "/requests/[0-9]*/approve" <<<"$req" | tail -1 | grep -o '[0-9]*')
t=$(tok https://admin.cafe.wifi/requests)
chk "4 ตัวท้ายผิด อนุมัติไม่ได้" "$($A -o /dev/null -w '%{http_code}' --data-urlencode "csrf_token=$t" -d last4=9999 -d hours=1 -d devices=1 https://admin.cafe.wifi/requests/$rid/approve; sq "SELECT status FROM access_request WHERE id=$rid")" "302pending"
t=$(tok https://admin.cafe.wifi/requests)
$A -o /dev/null --data-urlencode "csrf_token=$t" -d last4=${NATID: -4} -d hours=1 -d devices=1 https://admin.cafe.wifi/requests/$rid/approve
chk "อนุมัติสำเร็จ" "$(sq "SELECT status FROM access_request WHERE id=$rid")" approved
for i in $(seq 1 30); do st=$(sq "SELECT state FROM portal_session WHERE mac='$MU' ORDER BY id DESC LIMIT 1"); [ "$st" = authenticated ] && break; sleep 1; done
chk "เครื่องได้รับสิทธิ์ใน ${i} วิ" "$st" authenticated
chk "ออกเน็ตได้หลังอนุมัติ" "$($X curl -s -m 8 -o /dev/null -w '%{http_code}' http://example.com/)" 200
sp=$($X curl -s -m 8 http://cafe.wifi:8080/request)
has "ลูกค้าเห็นเวลาที่เหลือที่ cafe.wifi:8080" "$sp" "เวลาที่เหลือ"

echo "== 4. ต่อเวลา / ปิดสิทธิ์"
VID=$(sq "SELECT voucher_id FROM portal_session WHERE mac='$MU' ORDER BY id DESC LIMIT 1")
end1=$(ndsctl json $M 2>/dev/null | python3 -c 'import json,sys;print(json.load(sys.stdin)["session_end"])')
t=$(tok https://admin.cafe.wifi/)
$A -o /dev/null --data-urlencode "csrf_token=$t" -d minutes=30 https://admin.cafe.wifi/vouchers/$VID/extend
for i in $(seq 1 15); do [ "$(sq "SELECT auth_sync_needed FROM voucher WHERE id=$VID")" = 0 ] && break; sleep 2; done
end2=$(ndsctl json $M 2>/dev/null | python3 -c 'import json,sys;print(json.load(sys.stdin)["session_end"])')
d=$(( (end2-end1)/60 ))
chk "ต่อเวลา +30 น. เลื่อนเวลาตัดของ openNDS [+${d} นาที]" "$([ $d -ge 29 ] && [ $d -le 31 ] && echo y)" y
chk "เน็ตยังใช้ได้หลังต่อเวลา" "$($X curl -s -m 8 -o /dev/null -w '%{http_code}' http://example.com/)" 200
t=$(tok https://admin.cafe.wifi/)
$A -o /dev/null --data-urlencode "csrf_token=$t" https://admin.cafe.wifi/vouchers/$VID/revoke
$ENVV ./venv/bin/python -m tools.enforce_voucher_expiry >/dev/null 2>&1
chk "ปิดสิทธิ์แล้วเน็ตถูกตัด" "$($X curl -s -m 8 -o /dev/null -w '%{http_code}' http://example.com/)" 307
has "ลูกค้าเห็นว่าถูกปิดสิทธิ์" "$($X curl -s -m 8 http://cafe.wifi:8080/request)" "ถูกปิดโดยพนักงาน"

echo "== 5. openNDS คืนสิทธิ์เองแต่ไม่มีสิทธิ์ในฐานข้อมูล (N44)"
ndsctl auth $M 30 >/dev/null 2>&1
chk "จำลอง: openNDS ปล่อยเครื่องไม่มีสิทธิ์ออนไลน์" "$(ndsctl json $M 2>/dev/null | grep -o '"state":"[A-Za-z]*"')" '"state":"Authenticated"'
$ENVV ./venv/bin/python -m tools.enforce_voucher_expiry >/dev/null 2>&1
# หลัง deauth openNDS ลบเครื่องออกจากรายการไปเลย (ndsctl json ว่าง) -- วัดจากสิ่งที่สำคัญจริง: ออกเน็ตได้ไหม
chk "ตัวตรวจย้อนทางตัดเครื่องนั้น (ออกเน็ตไม่ได้แล้ว)" "$($X curl -s -m 8 -o /dev/null -w '%{http_code}' http://example.com/)" 307
chk "ลง audit orphan_deauth" "$(sq "SELECT COUNT(*)>0 FROM audit_log WHERE action='orphan_deauth' AND target='$MU' AND ts > NOW() - INTERVAL 2 MINUTE")" 1

echo "== 6. SSH จากวงลูกค้า (พอร์ต $SSHP)"
O="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=6 -o LogLevel=ERROR -o BatchMode=yes"
chk "พอร์ต 22 จากวงลูกค้าถูกบล็อก" "$($X timeout 5 bash -c '</dev/tcp/10.10.0.1/22' 2>/dev/null && echo open || echo blocked)" blocked
has "รหัสผ่านถูกปฏิเสธ (key เท่านั้น)" "$($X ssh $O -o PreferredAuthentications=password -o PubkeyAuthentication=no -p $SSHP ras@10.10.0.1 true 2>&1)" "publickey"
ssh-keygen -q -t ed25519 -N '' -C cafe-fulltest-key -f /tmp/ftkey; cat /tmp/ftkey.pub >> /home/ras/.ssh/authorized_keys
chk "SSH key เข้าได้" "$($X ssh $O -i /tmp/ftkey -p $SSHP ras@10.10.0.1 'echo ok' 2>&1)" ok

echo "== 7. log / หลักฐาน / ความปลอดภัย"
lq=$($A "https://admin.cafe.wifi/logs?range=1h&q=Lab-cte-Phone")
has "ค้น log ด้วยชื่อเครื่องเจอ" "$lq" "Lab-cte-Phone"
t=$(tok https://admin.cafe.wifi/evidence)
$A -o /tmp/ft.zip -D /tmp/ft.hdr --data-urlencode "csrf_token=$t" -d who=natid --data-urlencode natid=$NATID -d start=$(date +%F) -d end=$(date +%F) --data-urlencode "reason=ทดสอบระบบรวม (แลป)" https://admin.cafe.wifi/evidence
python3 - <<'PY' > /tmp/ft.ev
import zipfile, json, hashlib
z = zipfile.ZipFile("/tmp/ft.zip"); m = json.loads(z.read("manifest.json"))
ok = all(hashlib.sha256(z.read(f["filename"]).decode().lstrip("﻿").encode()).hexdigest() == f["sha256"] for f in m["files"])
print("y" if ok and m["files"][0]["row_count"] > 0 else "n")
PY
chk "ส่งออกหลักฐาน: ZIP + SHA-256 ตรวจผ่าน" "$(cat /tmp/ft.ev)" y
t=$(tok https://admin.cafe.wifi/login); rm -f $CJ
codes=""; for i in 1 2 3 4 5 6; do rm -f $CJ; t=$(tok https://admin.cafe.wifi/login); codes="$codes$($A -o /dev/null -w '%{http_code}' --data-urlencode "csrf_token=$t" -d username=ft-staff -d password=wrong https://admin.cafe.wifi/login) "; done
chk "เดารหัสผิด 5 ครั้งแล้วถูกบล็อก" "$codes" "401 401 401 401 401 429 "
systemctl restart cafe-admin; sleep 3; rm -f $CJ; t=$(tok https://admin.cafe.wifi/login)
chk "รีสตาร์ทแล้วยังบล็อก (ตัวนับใน DB)" "$($A -o /dev/null -w '%{http_code}' --data-urlencode "csrf_token=$t" -d username=ft-staff --data-urlencode "password=$PW" https://admin.cafe.wifi/login)" 429

echo "== 8. สำรองข้อมูล / log ตกหล่น"
st=$(python3 -c 'import json;d=json.load(open("/var/log/cafe-wifi/backup-status.json"));print(d["ok"], d.get("offsite_ok"))' 2>/dev/null)
chk "สำรองล่าสุดสำเร็จ (USB ยังไม่เสียบ = False ถูกต้อง)" "$st" "True False"
echo "  INFO ENOBUFS ตั้งแต่ติดตั้งล่าสุด (15:24): $(sq "SELECT COUNT(*) FROM audit_log WHERE action='log_gap' AND detail LIKE '%ENOBUFS%' AND ts > '2026-10-03 15:24'") ครั้ง"

echo; echo "== สรุป: PASS $PASS  FAIL $FAIL"
