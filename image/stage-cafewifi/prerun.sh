#!/bin/bash -e
# stage ของ pi-gen: ต่อจาก stage2 (Raspberry Pi OS Lite) -- ดู image/build.sh
if [ ! -d "${ROOTFS_DIR}" ]; then
	copy_previous
fi
