#!/usr/bin/env bash
# ตรวจว่า rootfs ของ image ไม่มีความลับประจำเครื่องติดไป (docs/image-build-plan.md §2, IMG-02)
#
#   check-image.sh [--clean] <rootfs>
#     --clean  ลบของที่ OS สร้างใหม่เองได้ (SSH host keys, random-seed) ก่อนตรวจ -- ใช้ตอน build
#              ส่วนความลับของเรา (secrets.env ฯลฯ) ห้ามลบเงียบ ๆ: ถ้าเจอแปลว่า build ผิด ต้องล้มให้เห็น
#
# ใช้ได้ทั้งท้าย build (02-lockdown) และกับไฟล์ .img ที่ mount แล้ว (ตรวจซ้ำก่อนแจก)
set -euo pipefail

clean=0
if [[ "${1:-}" == "--clean" ]]; then clean=1; shift; fi
R="${1:?ระบุ rootfs เช่น /mnt/img-root}"
[[ -d "${R}/etc" ]] || { echo "ไม่ใช่ rootfs: ${R}" >&2; exit 2; }

fail=0
bad()  { printf '  ✗ %s\n' "$*"; fail=1; }
good() { printf '  ✓ %s\n' "$*"; }

echo "ตรวจความลับใน image: ${R}"

if (( clean )); then
  rm -f "${R}"/etc/ssh/ssh_host_*
  rm -f "${R}/var/lib/systemd/random-seed"
fi

# 1-7: ความลับของ Cafe-WiFi -- ต้องไม่มีเลย (สร้างตอน firstboot เท่านั้น)
for f in etc/cafe-wifi/secrets.env etc/cafe-wifi/secrets.env.new etc/cafe-wifi/setup.token \
         etc/cafe-wifi/setup-code etc/cafe-wifi/.firstboot-done etc/cafe-wifi/tls/server.key \
         etc/config/opennds; do
  if [[ -e "${R}/${f}" ]]; then bad "/${f} ไม่ควรอยู่ใน image"; else good "/${f} ไม่มี"; fi
done
# ฐานข้อมูลของแอป (สร้างตอน firstboot พร้อม DB_PASS)
if [[ -d "${R}/var/lib/mysql/cafewifi" ]]; then bad "มีฐานข้อมูล cafewifi ใน image"; else good "ไม่มีฐานข้อมูล cafewifi"; fi
# 8: พอร์ต SSH สำรอง
if [[ -e "${R}/etc/ssh/sshd_config.d/40-cafe-wifi.conf" ]]; then bad "มี sshd 40-cafe-wifi.conf (พอร์ตสำรอง) ใน image"; else good "ไม่มีพอร์ต SSH สำรอง"; fi
# 9: SSH host keys
if compgen -G "${R}/etc/ssh/ssh_host_*" >/dev/null; then bad "มี SSH host keys"; else good "ไม่มี SSH host keys"; fi
# 10: machine-id (export-image ของ pi-gen ใส่ "uninitialized" ภายหลัง -- ว่างหรือ uninitialized = ผ่าน)
mid="$(cat "${R}/etc/machine-id" 2>/dev/null || true)"
if [[ -z "$mid" || "$mid" == uninitialized ]]; then good "machine-id ว่าง/uninitialized"
elif (( clean )); then good "machine-id จะถูกล้างโดย export-image (ตอนนี้: ${mid:0:8}…)"
else bad "machine-id ถูกตั้งไว้แล้ว (${mid:0:8}…)"; fi
if [[ -s "${R}/var/lib/dbus/machine-id" && ! -L "${R}/var/lib/dbus/machine-id" ]] && (( ! clean )); then bad "มี /var/lib/dbus/machine-id"; fi
# 11: random seed
if [[ -e "${R}/var/lib/systemd/random-seed" ]]; then bad "มี /var/lib/systemd/random-seed"; else good "ไม่มี random-seed"; fi
# 12: ไม่มีบัญชีไหนมีรหัสผ่านใช้ได้ (ช่องที่ 2 ของ shadow ต้องเป็น ! * หรือ !…)
pw="$(awk -F: '$2 != "" && $2 !~ /^[!*]/ {print $1}' "${R}/etc/shadow")"
empty="$(awk -F: '$2 == "" {print $1}' "${R}/etc/shadow")"
if [[ -n "$pw" ]]; then bad "บัญชีที่มีรหัสผ่าน: ${pw//$'\n'/, }"; else good "ไม่มีบัญชีที่ login ด้วยรหัสผ่านได้"; fi
if [[ -n "$empty" ]]; then bad "บัญชีรหัสผ่านว่าง: ${empty//$'\n'/, }"; fi
# ของที่ต้องมี (ไม่งั้น firstboot ไม่ทำงาน)
for f in usr/local/sbin/cafe-wifi-firstboot etc/systemd/system/cafe-wifi-firstboot.service \
         etc/systemd/system/multi-user.target.wants/cafe-wifi-firstboot.service \
         opt/cafe-wifi/install.sh opt/cafe-wifi/venv/bin/python; do
  if [[ -e "${R}/${f}" || -L "${R}/${f}" ]]; then good "มี /${f}"; else bad "ขาด /${f}"; fi
done
if [[ -x "${R}/usr/bin/opennds" || -x "${R}/usr/local/bin/opennds" ]]; then good "มี opennds (คอมไพล์แล้ว)"; else bad "ขาด opennds"; fi
# dnsmasq/opennds ต้องไม่เปิดเองตอนบูตแรก (DHCP ของเราเตอร์ยังเปิดอยู่)
for s in dnsmasq opennds; do
  # -L ด้วย: ลิงก์ enable ชี้ /lib/systemd/... ซึ่ง dangling เมื่อมองจากนอก rootfs
  w="${R}/etc/systemd/system/multi-user.target.wants/${s}.service"
  if [[ -e "$w" || -L "$w" ]]; then bad "${s} ถูก enable ไว้"; else good "${s} ไม่ได้ enable"; fi
done

echo
if (( fail )); then echo "ไม่ผ่าน -- ห้ามแจก image นี้"; exit 1; fi
echo "ผ่าน"
