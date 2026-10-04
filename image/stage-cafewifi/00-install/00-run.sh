#!/bin/bash -e
# คัดลอกโปรเจกต์ (จาก git archive ของ commit ที่ build -- ไม่ใช่ working tree) เข้า rootfs
dst="${ROOTFS_DIR}/usr/local/src/cafe-wifi"
rm -rf "$dst"
mkdir -p "$dst"
cp -a "${CAFEWIFI_SRC}/." "$dst/"

# ห้าม postinst ของแพ็กเกจ start service ใน chroot (ไม่มี systemd -> invoke-rc.d ตกไปใช้ init.d
# แล้ว mariadb ใต้ QEMU รันค้างอยู่ ทำให้ unmount rootfs ไม่ได้) -- ลบทิ้งใน 02-lockdown
cat > "${ROOTFS_DIR}/usr/sbin/policy-rc.d" <<'POLICY'
#!/bin/sh
exit 101
POLICY
chmod 755 "${ROOTFS_DIR}/usr/sbin/policy-rc.d"
