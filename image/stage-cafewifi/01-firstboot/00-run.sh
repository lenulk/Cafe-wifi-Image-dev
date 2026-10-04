#!/bin/bash -e
# first-boot service (M2) + ล็อกบัญชี + ปิด service ที่ต้องรอ wizard (--stage site)
src="${CAFEWIFI_SRC}/image/firstboot"
install -m 755 "${src}/cafe-wifi-firstboot.sh"      "${ROOTFS_DIR}/usr/local/sbin/cafe-wifi-firstboot"
install -m 644 "${src}/cafe-wifi-firstboot.service" "${ROOTFS_DIR}/etc/systemd/system/cafe-wifi-firstboot.service"
# factory reset (IMG-09): ทำงานเฉพาะเมื่อมีไฟล์ factory-reset บน bootfs
install -m 644 "${src}/cafe-wifi-factory-reset.service" "${ROOTFS_DIR}/etc/systemd/system/cafe-wifi-factory-reset.service"
# โหมดตั้งค่า + web wizard (M4)
for u in cafe-wifi-setup.service cafe-wifi-apply.path cafe-wifi-apply.service; do
	install -m 644 "${CAFEWIFI_SRC}/image/setup/${u}" "${ROOTFS_DIR}/etc/systemd/system/${u}"
done

# SSH ด้วย key เท่านั้น (บัญชีช่างสร้างจาก SSH_PUBKEY ใน cafewifi.conf) -- 30 = อ่านก่อน 40-cafe-wifi.conf
install -d -m 755 "${ROOTFS_DIR}/etc/ssh/sshd_config.d"
cat > "${ROOTFS_DIR}/etc/ssh/sshd_config.d/30-cafe-wifi-image.conf" <<'SSHD'
# managed by Cafe-WiFi image -- ห้ามใช้รหัสผ่านทาง SSH (image ไม่มีบัญชีที่มีรหัสผ่านอยู่แล้ว)
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
SSHD

# ไม่ได้ DHCP จากเราเตอร์ (ปิดไว้ / สวิตช์ทิ้ง) -> ตั้ง 169.254.x.x เองแทนการไม่มี IPv4 เลย
# avahi ประกาศ cafewifi.local ด้วย IP นั้น ช่างที่ต่อสายเดียวกันจึงยังเปิด wizard ได้ (เจอบนการ์ด B 2026-10-04)
# หลัง --stage site eth0 ถูกปลดจาก NetworkManager แล้ว ค่านี้จึงไม่มีผลกับระบบที่ใช้งานจริง
install -d -m 755 "${ROOTFS_DIR}/etc/NetworkManager/conf.d"
cat > "${ROOTFS_DIR}/etc/NetworkManager/conf.d/30-cafe-wifi-linklocal.conf" <<'NM'
# managed by Cafe-WiFi image -- โหมดตั้งค่า: DHCP ไม่มา = ใช้ IPv4 link-local
[connection]
ipv4.link-local=fallback
NM

on_chroot <<CHROOT
systemctl enable cafe-wifi-firstboot.service cafe-wifi-factory-reset.service cafe-wifi-setup.service cafe-wifi-apply.path avahi-daemon.service
# แพ็กเกจ Debian enable ตัวเองตอนติดตั้ง -- บูตแรก DHCP ของเราเตอร์ยังเปิดอยู่ ห้ามมี dnsmasq/portal
# ขึ้นมาบนวงเราเตอร์ก่อน wizard ตรวจ · --stage site เป็นคน enable กลับ (configure_network/start_services)
for s in dnsmasq.service nginx.service opennds.service nftables.service; do
	systemctl disable "\$s" 2>/dev/null || true
done
# ไม่มีรหัสผ่านใน image (§2 ข้อ 12) -- เข้าเครื่องได้ทาง SSH key ของช่างเท่านั้น
passwd -l root
passwd -l ${FIRST_USER_NAME}
CHROOT
