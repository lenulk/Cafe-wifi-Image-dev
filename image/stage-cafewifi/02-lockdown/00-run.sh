#!/bin/bash -e
# เก็บกวาดแล้วตรวจว่าไม่มีความลับติดไปกับ image (IMG-02) -- ไม่ผ่าน = build ล้ม ไม่ได้ไฟล์ .img
rm -f "${ROOTFS_DIR}/usr/sbin/policy-rc.d"
rm -rf "${ROOTFS_DIR}/usr/local/src/cafe-wifi"
rm -rf "${ROOTFS_DIR}/root/.cache"
on_chroot <<'CHROOT'
apt-get clean
CHROOT
bash "${CAFEWIFI_SRC}/image/check-image.sh" --clean "${ROOTFS_DIR}"
