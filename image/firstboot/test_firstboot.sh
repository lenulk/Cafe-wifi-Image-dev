#!/usr/bin/env bash
# ทดสอบ M2 นอก Pi (WSL/Linux ใดก็ได้ ไม่ต้องเป็น root) -- ไม่แตะ /etc จริง ใช้โฟลเดอร์ชั่วคราวทั้งหมด
#   bash image/firstboot/test_firstboot.sh
# ส่วน A: cafe-wifi-firstboot.sh กับ install.sh จำลอง (ล้มได้ตามสั่ง) -- รันซ้ำ / ไฟดับกลางทาง / conf แปลก ๆ
# ส่วน B: gen_secrets + make_tls_cert ของ install.sh ตัวจริง -- ไม่สร้างกุญแจทับ, เขียน atomic, ซ่อม key เสีย
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${HERE}/../.." && pwd)"
FB="${HERE}/cafe-wifi-firstboot.sh"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
pass=0; failn=0
check() {  # check "ชื่อ" <คำสั่ง...>
  local name="$1"; shift
  if "$@"; then pass=$((pass+1)); printf '  ok   %s\n' "$name"
  else failn=$((failn+1)); printf '  FAIL %s\n' "$name"; fi
}

# ---------------- ส่วน A ----------------
echo "A. firstboot script"
STUB="${T}/stub-install.sh"
cat > "$STUB" <<'EOF'
#!/usr/bin/env bash
echo "$*" >> "${STUB_LOG}"
[[ -f "${STUB_FAIL}" ]] && exit 7
exit 0
EOF
newenv() {  # สภาพการ์ดใหม่ 1 ใบ
  rm -rf "${T}/etc" "${T}/boot" "${T}/stub.log" "${T}/stub.fail"
  mkdir -p "${T}/etc" "${T}/boot"; touch "${T}/boot/config.txt"
}
fb() {
  CAFEWIFI_ETC_DIR="${T}/etc" CAFEWIFI_BOOT_DIR="${T}/boot" CAFEWIFI_INSTALL_SH="$STUB" \
  CAFEWIFI_LED_DIR="${T}/noled" CAFEWIFI_SKIP_OS_IDENTITY=1 CAFEWIFI_APP_USER="$(id -un)" \
  STUB_LOG="${T}/stub.log" STUB_FAIL="${T}/stub.fail" bash "$FB" >/dev/null 2>&1
}

# A1: conf จาก Notepad (BOM + CRLF + คำพูดครอบ + code ตัวเล็กมีขีด)
newenv
printf '\xef\xbb\xbf# comment\r\nGATEWAY_NAME="Baan Cafe & Co"\r\nSETUP_CODE = k7qm-29xd\r\nFOO=bar\r\n' > "${T}/boot/cafewifi.conf"
fb; rc=$?
check "A1 exit 0" test "$rc" -eq 0
check "A1 code จาก conf ถูก normalize" test "$(cat "${T}/etc/setup-code" 2>/dev/null)" = "K7QM29XD"
check "A1 ส่งชื่อร้านให้ install.sh" grep -qxF -- "--stage firstboot --ssid Baan Cafe & Co" "${T}/stub.log"
check "A1 ลบ conf ออกจาก bootfs" test ! -e "${T}/boot/cafewifi.conf"
check "A1 ไม่เขียน SETUP-CODE.txt (code มาจากช่าง)" test ! -e "${T}/boot/SETUP-CODE.txt"
check "A1 ปักธงเสร็จ" test -e "${T}/etc/.firstboot-done"
check "A1 code file mode 640" test "$(stat -c %a "${T}/etc/setup-code")" = "640"

# A2: รันซ้ำหลังเสร็จแล้ว ต้องไม่เรียก install.sh อีก
lines_before=$(wc -l < "${T}/stub.log")
fb; rc=$?
check "A2 รันซ้ำ exit 0" test "$rc" -eq 0
check "A2 รันซ้ำไม่เรียก install.sh" test "$(wc -l < "${T}/stub.log")" -eq "$lines_before"

# A3: ไม่มี conf -> สุ่ม code + เขียน SETUP-CODE.txt
newenv
fb; rc=$?
code="$(cat "${T}/etc/setup-code" 2>/dev/null)"
check "A3 exit 0" test "$rc" -eq 0
check "A3 code สุ่ม 8 ตัวจากชุดตัวอักษรที่ไม่สับสน" bash -c '[[ "$1" =~ ^[ABCDEFGHJKMNPQRSTUVWXYZ23456789]{8}$ ]]' _ "$code"
check "A3 SETUP-CODE.txt บน bootfs" grep -q "${code:0:4}-${code:4}" "${T}/boot/SETUP-CODE.txt"
check "A3 ไม่ส่ง --ssid เมื่อไม่มีชื่อร้าน" grep -qx -- "--stage firstboot" "${T}/stub.log"

# A4: "ไฟดับ" ระหว่าง install.sh (ล้ม) -> ไม่ปักธง, conf ยังอยู่ · บูตใหม่ทำต่อ code เดิม
newenv
printf 'GATEWAY_NAME=Shop\n' > "${T}/boot/cafewifi.conf"
touch "${T}/stub.fail"
fb; rc=$?
code1="$(cat "${T}/etc/setup-code" 2>/dev/null)"
check "A4 ล้มแล้ว exit != 0" test "$rc" -ne 0
check "A4 ล้มแล้วไม่ปักธง" test ! -e "${T}/etc/.firstboot-done"
check "A4 ล้มแล้ว conf ยังอยู่" test -e "${T}/boot/cafewifi.conf"
rm -f "${T}/stub.fail" "${T}/boot/SETUP-CODE.txt"   # จำลอง: ไฟดับก่อนเขียน SETUP-CODE.txt ทัน
fb; rc=$?
check "A4 บูตใหม่สำเร็จ" test "$rc" -eq 0
check "A4 code ไม่เปลี่ยนข้ามการบูต" test "$(cat "${T}/etc/setup-code")" = "$code1"
check "A4 SETUP-CODE.txt ถูกเขียนกลับมา" grep -q "${code1:0:4}-${code1:4}" "${T}/boot/SETUP-CODE.txt"
check "A4 ปักธงแล้ว" test -e "${T}/etc/.firstboot-done"

# A5: code ผิดรูปแบบ -> ไม่ทำต่อ (ไม่เรียก install.sh)
newenv
printf 'SETUP_CODE=abc\n' > "${T}/boot/cafewifi.conf"
fb; rc=$?
check "A5 code สั้นเกิน -> ล้ม" test "$rc" -ne 0
check "A5 ไม่เรียก install.sh" test ! -s "${T}/stub.log"

# A6: ไม่มี bootfs เลย -> ยังผ่าน (code สุ่ม, ไม่มีที่เขียน txt)
rm -rf "${T}/etc" "${T}/stub.log"; mkdir -p "${T}/etc"
CAFEWIFI_ETC_DIR="${T}/etc" CAFEWIFI_BOOT_DIR="${T}/nonexistent" CAFEWIFI_INSTALL_SH="$STUB" \
  CAFEWIFI_LED_DIR="${T}/noled" CAFEWIFI_SKIP_OS_IDENTITY=1 CAFEWIFI_APP_USER="$(id -un)" \
  STUB_LOG="${T}/stub.log" STUB_FAIL="${T}/stub.fail" bash "$FB" >/dev/null 2>&1; rc=$?
check "A6 bootfs หาย ยังผ่าน" test "$rc" -eq 0


# ---------------- ส่วน R: factory reset (IMG-09) ----------------
echo "R. factory reset"
SCTL="${T}/systemctl"
cat > "$SCTL" <<'EOF2'
#!/usr/bin/env bash
echo "$*" >> "${SCTL_LOG}"
EOF2
chmod +x "$SCTL"
fr() {
  CAFEWIFI_ETC_DIR="${T}/etc" CAFEWIFI_BOOT_DIR="${T}/boot" CAFEWIFI_INSTALL_SH="$STUB"   CAFEWIFI_LED_DIR="${T}/noled" CAFEWIFI_SKIP_OS_IDENTITY=1 CAFEWIFI_APP_USER="$(id -un)"   CAFEWIFI_NM_CONF_DIR="${T}/nm" CAFEWIFI_SYSTEMCTL="$SCTL" SCTL_LOG="${T}/sctl.log"   STUB_LOG="${T}/stub.log" STUB_FAIL="${T}/stub.fail" bash "$FB" --factory-reset >/dev/null 2>&1
}
site_done_env() {  # เครื่องที่ตั้งค่าเสร็จแล้ว: ผ่านบูตแรก + .site-done + eth0 ถูกปลดจาก NM + มีข้อมูล
  newenv; rm -rf "${T}/nm" "${T}/sctl.log"; mkdir -p "${T}/nm"
  touch "${T}/etc/.firstboot-done" "${T}/etc/.site-done" "${T}/nm/99-cafe-wifi-unmanage-eth0.conf" "${T}/nm/30-cafe-wifi-linklocal.conf"
  printf 'NATID_DEK=keep
' > "${T}/etc/secrets.env"
}

# R1: ไม่มีไฟล์ factory-reset -> ไม่แตะอะไร
site_done_env
fr; rc=$?
check "R1 ไม่มีธง exit 0" test "$rc" -eq 0
check "R1 ไม่มีธง .site-done ยังอยู่" test -e "${T}/etc/.site-done"
check "R1 ไม่มีธง ไม่เรียก systemctl" test ! -e "${T}/sctl.log"

# R2: มีธง + conf จาก prepare-sd -FactoryReset (code ของช่าง)
site_done_env
touch "${T}/boot/factory-reset"
printf 'SETUP_CODE=QXRR-YTR6
TECH_USER=cafeadmin
' > "${T}/boot/cafewifi.conf"
fr; rc=$?
check "R2 exit 0" test "$rc" -eq 0
check "R2 ลบ .site-done (wizard เปิดได้)" test ! -e "${T}/etc/.site-done"
check "R2 setup code ใหม่จาก conf" test "$(cat "${T}/etc/setup-code" 2>/dev/null)" = "QXRRYTR6"
check "R2 ปิด service ของร้าน" grep -q '^disable opennds.service dnsmasq.service nginx.service' "${T}/sctl.log"
check "R2 เปิด wizard" grep -qx 'enable cafe-wifi-setup.service cafe-wifi-apply.path' "${T}/sctl.log"
check "R2 รีบูตเป็นขั้นสุดท้าย" test "$(tail -1 "${T}/sctl.log")" = "reboot"
check "R2 คืน eth0 ให้ NetworkManager" test ! -e "${T}/nm/99-cafe-wifi-unmanage-eth0.conf"
check "R2 ไม่แตะ conf อื่นของ NM" test -e "${T}/nm/30-cafe-wifi-linklocal.conf"
check "R2 ลบธง + conf ออกจาก bootfs" test ! -e "${T}/boot/factory-reset" -a ! -e "${T}/boot/cafewifi.conf"
check "R2 ข้อมูล/กุญแจไม่ถูกแตะ" test "$(cat "${T}/etc/secrets.env")" = "NATID_DEK=keep"
check "R2 ไม่เรียก install.sh" test ! -e "${T}/stub.log"

# R3: มีธงแต่ไม่มี conf -> สุ่ม code แล้วเขียน SETUP-CODE.txt ให้ช่างอ่าน
site_done_env; touch "${T}/boot/factory-reset"
fr
code="$(cat "${T}/etc/setup-code" 2>/dev/null)"
check "R3 สุ่ม code 8 ตัว" bash -c '[[ "$1" =~ ^[ABCDEFGHJKMNPQRSTUVWXYZ23456789]{8}$ ]]' _ "$code"
check "R3 SETUP-CODE.txt บน bootfs" grep -q "${code:0:4}-${code:4}" "${T}/boot/SETUP-CODE.txt"

# R4: การ์ดที่ยังไม่ผ่านบูตแรก -> ลบธงทิ้งเฉย ๆ (บูตแรกเข้าโหมดตั้งค่าเองอยู่แล้ว)
newenv; rm -f "${T}/sctl.log"; touch "${T}/boot/factory-reset"
fr; rc=$?
check "R4 ยังไม่บูตแรก exit 0 + ลบธง" test "$rc" -eq 0 -a ! -e "${T}/boot/factory-reset"
check "R4 ยังไม่บูตแรก ไม่รีบูต" test ! -e "${T}/sctl.log"

# ---------------- ส่วน B ----------------
echo "B. install.sh gen_secrets / make_tls_cert (ตัวจริง)"
LIB="${T}/install-lib.sh"
# ตัด main "$@" บรรทัดสุดท้ายออก แล้วย้าย ETC_DIR ไปโฟลเดอร์ชั่วคราว
sed -e '$d' -e "s#^readonly ETC_DIR=.*#ETC_DIR='${T}/betc'#" "${ROOT}/install.sh" > "$LIB"
run_lib() {  # run_lib "<คำสั่ง bash หลัง source>"
  bash -c "
    set -Eeuo pipefail
    source '$LIB'
    chown() { :; }            # ไม่ใช่ root -- owner ไม่ใช่สิ่งที่ทดสอบ
    trap - ERR
    UPLINK_CIDR=192.168.1.2/24 UPLINK_GW=192.168.1.1 CLIENT_CIDR=10.10.0.1/24 SSH_ALT_PORT=22222
    $1
  " >/dev/null 2>&1
}
mkdir -p "${T}/betc"
S="${T}/betc/secrets.env"
run_lib "gen_secrets"; rc=$?
check "B1 สร้าง secrets ครั้งแรก" test "$rc" -eq 0 -a -s "$S"
dek1="$(grep '^NATID_DEK=' "$S")"
check "B1 มี DEK 64 hex" bash -c '[[ "$1" =~ ^NATID_DEK=[0-9a-f]{64}$ ]]' _ "$dek1"
check "B1 setup.token มี" test -s "${T}/betc/setup.token"
check "B1 ไม่มี .new ค้าง" bash -c '! ls "$1"/*.new >/dev/null 2>&1' _ "${T}/betc"
check "B1 mode 640" test "$(stat -c %a "$S")" = "640"

run_lib "GATEWAY_NAME='A&B|C'; CLIENT_CIDR=10.20.0.1/24; gen_secrets"; rc=$?
check "B2 รันซ้ำ exit 0" test "$rc" -eq 0
check "B2 DEK ไม่ถูกสร้างทับ" test "$(grep '^NATID_DEK=' "$S")" = "$dek1"
check "B2 ชื่อร้านที่มี & | อัปเดตถูก" grep -qxF 'GATEWAY_NAME=A&B|C' "$S"
check "B2 ค่าเครือข่ายอัปเดต" grep -qx 'CLIENT_CIDR=10.20.0.1/24' "$S"
check "B2 mode ยัง 640 หลังเขียนทับ" test "$(stat -c %a "$S")" = "640"
check "B2 ไม่มี .new ค้าง" bash -c '! ls "$1"/*.new >/dev/null 2>&1' _ "${T}/betc"

# B3: ไฟดับระหว่างสร้างครั้งแรก -> มีแค่ .new ขาดครึ่ง ไม่มี secrets.env -> รอบหน้าสร้างใหม่ครบ
rm -f "${T}/betc/"*; printf 'DB_HOST=127.0.0.1\nNATID_PEP' > "${S}.new"
run_lib "gen_secrets"; rc=$?
check "B3 .new ขาดครึ่งค้าง -> สร้างใหม่ครบ" bash -c '[[ $1 -eq 0 ]] && grep -q "^SSH_ALT_PORT=" "$2" && grep -q "^NATID_DEK=" "$2"' _ "$rc" "$S"

# B4: secrets.env เสีย (ไม่มี DEK) -> ต้องหยุด ไม่สร้างทับ ไม่ "ซ่อม" เอง
printf 'DB_HOST=127.0.0.1\n' > "$S"
run_lib "gen_secrets"; rc=$?
check "B4 ไฟล์เสีย -> หยุด" test "$rc" -ne 0
check "B4 ไฟล์เสียไม่ถูกแตะ" test "$(cat "$S")" = "DB_HOST=127.0.0.1"

# B5: ใบรับรอง -- ออกครั้งแรก, รันซ้ำไม่ออกใหม่, key ว่าง (ไฟดับ) -> ออกใหม่
rm -rf "${T}/betc/tls"
run_lib "install() { mkdir -p \"\${@: -1}\"; }; make_tls_cert"; rc=$?
check "B5 ออกใบรับรอง" test "$rc" -eq 0 -a -s "${T}/betc/tls/server.crt" -a -s "${T}/betc/tls/server.key"
fp1="$(openssl x509 -in "${T}/betc/tls/server.crt" -noout -fingerprint 2>/dev/null)"
run_lib "install() { mkdir -p \"\${@: -1}\"; }; make_tls_cert"
check "B5 รันซ้ำไม่ออกใหม่" test "$(openssl x509 -in "${T}/betc/tls/server.crt" -noout -fingerprint)" = "$fp1"
: > "${T}/betc/tls/server.key"
run_lib "install() { mkdir -p \"\${@: -1}\"; }; make_tls_cert"
check "B5 key ว่าง -> ออกใหม่" test "$(openssl x509 -in "${T}/betc/tls/server.crt" -noout -fingerprint)" != "$fp1"
check "B5 key ใหม่คู่กับ crt" test "$(openssl x509 -in "${T}/betc/tls/server.crt" -noout -pubkey)" = "$(openssl pkey -in "${T}/betc/tls/server.key" -pubout)"

echo
echo "ผ่าน ${pass} / $((pass+failn))"
(( failn == 0 ))
