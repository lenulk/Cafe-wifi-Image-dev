#!/usr/bin/env bash
# ============================================================================
#  สร้าง Cafe-WiFi OS (.img.xz) ด้วย pi-gen -- รันใน container Debian (amd64, --privileged)
#  ปกติเรียกผ่าน image/build.ps1 บน Windows ซึ่งเตรียม /out/src.tar (git archive) ให้
#
#  /out           ผลลัพธ์ (.img.xz, .sha256, build.log)  -- bind mount จาก image/deploy/
#  /work          work dir ของ pi-gen (docker volume, เก็บข้ามรอบได้)
#  CAFEWIFI_REUSE=1  ใช้ rootfs ของ stage0-2 จากรอบก่อน (build แค่ stage ของเรา ~เร็วกว่ามาก)
# ============================================================================
set -euo pipefail
PIGEN_TAG="${PIGEN_TAG:-2026-09-15-raspios-trixie-arm64}"
SRC="${CAFEWIFI_SRC:-/cafewifi/src}"
export CAFEWIFI_SRC="$SRC"
OUT=/out
WORK=/work/pi-gen

echo "==> เครื่องมือ build"
export DEBIAN_FRONTEND=noninteractive
apt-get -qq update
# รายการเดียวกับ Dockerfile ของ pi-gen tag ที่ปักไว้
apt-get -qq install -y --no-install-recommends \
  git vim parted quilt coreutils qemu-user-static debootstrap zerofree zip dosfstools e2fsprogs \
  libarchive-tools libcap2-bin rsync grep udev xz-utils curl xxd file kmod bc \
  binfmt-support ca-certificates fdisk gpg pigz arch-test >/dev/null
grep -q /proc/sys/fs/binfmt_misc /proc/mounts || mount -t binfmt_misc binfmt_misc /proc/sys/fs/binfmt_misc

echo "==> pi-gen ${PIGEN_TAG}"
rm -rf /pi-gen
git clone -q --depth 1 -b "$PIGEN_TAG" https://github.com/RPi-Distro/pi-gen /pi-gen
touch /pi-gen/stage2/SKIP_IMAGES     # ไม่ต้อง export Lite เปล่า ๆ (เสียเวลา + ที่)
cp -a "${SRC}/image/stage-cafewifi" /pi-gen/stage-cafewifi
find /pi-gen/stage-cafewifi -name '*.sh' -exec chmod +x {} +

if [[ "${CAFEWIFI_REUSE:-0}" == 1 && -d "${WORK}/stage2/rootfs" ]]; then
  echo "==> ใช้ stage0-2 จากรอบก่อน (CAFEWIFI_REUSE=1)"
  touch /pi-gen/stage0/SKIP /pi-gen/stage1/SKIP /pi-gen/stage2/SKIP
fi

ver="$(cd "$SRC" && cat image/VERSION 2>/dev/null || echo dev)"
{
  cat "${SRC}/image/pigen/config"
  # รหัสผ่านทิ้งได้: pi-gen ต้องมีถ้าปิด user rename -- 01-firstboot ล็อกบัญชีนี้ทันที ไม่มีใครรู้ค่า
  echo "FIRST_USER_PASS='$(head -c 48 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 32)'"
  echo "IMG_FILENAME='cafe-wifi-${ver}-$(date +%Y%m%d)${CAFEWIFI_GIT:+-${CAFEWIFI_GIT}}'"
  echo "WORK_DIR='${WORK}'"
  echo "DEPLOY_DIR='${OUT}'"
  echo "STAGE_LIST='stage0 stage1 stage2 /pi-gen/stage-cafewifi'"
} > /pi-gen/config

echo "==> build (ครั้งแรก ~1-2 ชม. ใต้ QEMU)"
cd /pi-gen
set +e
./build.sh 2>&1 | tee "${OUT}/build.log"
rc=${PIPESTATUS[0]}
set -e
(( rc == 0 )) || { echo "pi-gen ล้มเหลว (rc=${rc}) -- ดู ${OUT}/build.log และ ${WORK}/build.log"; exit "$rc"; }

cd "$OUT"
# URL ที่จะอัปโหลดไฟล์ไปไว้ (GitHub Release ของ repo image) -- Imager ดาวน์โหลดจากตรงนี้
URL_BASE="${CAFEWIFI_URL_BASE:-https://github.com/lenulk/Cafe-wifi-Image/releases/download/v${ver}}"
for f in *.img.xz; do
  [[ -e "$f" ]] || continue
  sha256sum "$f" > "${f}.sha256"
  echo "==> ได้ ${f} ($(du -h "$f" | cut -f1)) sha256 $(cut -c1-16 "${f}.sha256")…"
  # os_list.json ของ Raspberry Pi Imager (M6): ไม่ใส่ init_format = Imager ไม่เสนอ OS customisation
  # (ค่าทั้งหมดตั้งผ่าน cafewifi.conf + wizard แทน)
  ext_sha=$(xz -dc "$f" | sha256sum | cut -d' ' -f1)
  ext_size=$(xz --robot --list "$f" | awk '$1 == "totals" {print $5}')
  cat > os_list.json <<JSON
{
  "os_list": [
    {
      "name": "Cafe-WiFi OS ${ver}",
      "description": "Captive portal + บันทึก log ตาม พ.ร.บ.คอมฯ ม.26 สำหรับร้านกาแฟ (Raspberry Pi OS Lite 64-bit ${RELEASE:-trixie})",
      "url": "${URL_BASE}/${f}",
      "release_date": "$(date +%Y-%m-%d)",
      "extract_size": ${ext_size},
      "extract_sha256": "${ext_sha}",
      "image_download_size": $(stat -c %s "$f"),
      "image_download_sha256": "$(cut -d' ' -f1 "${f}.sha256")",
      "devices": ["pi4-64bit"]
    }
  ]
}
JSON
  echo "==> os_list.json (url: ${URL_BASE}/${f})"
done
