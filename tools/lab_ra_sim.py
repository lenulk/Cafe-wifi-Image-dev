#!/usr/bin/env python3
"""
tools/lab_ra_sim.py -- "เราเตอร์ที่ยังเปิด IPv6" จำลอง สำหรับทดสอบ IMG-07 ในแล็บที่ไม่มี IPv6 (ใช้ในแล็บเท่านั้น)

ส่ง ICMPv6 Router Advertisement (prefix 2001:db8:cafe::/64 แบบ SLAAC, router lifetime 1800) ทุก 1 วินาที
ออกทางอินเทอร์เฟซที่กำหนด -- ใช้คู่กับ lab_client.sh (namespace ลูกค้าจำลองบน eth0 ของ Pi):
  sudo ip netns exec ctr python3 lab_ra_sim.py --iface eth0 --seconds 40 &
  sudo python3 /opt/cafe-wifi/tools/check_router.py --iface eth0      # ต้องได้ ❌ IPv6 ยังเปิดอยู่
--withdraw ส่ง RA แบบถอนตัว (lifetime 0, prefix valid 0) = เราเตอร์ที่เพิ่งปิด IPv6 -> ตัวตรวจต้องไม่นับ

ข้อจำกัด: RA จาก namespace บน Pi เครื่องเดียวกัน วิ่งออก eth0 ตัวเดียวกับที่ตัวตรวจฟัง (ตัวตรวจเห็นสำเนาขาออก)
ไม่ได้ผ่านสวิตช์จริง -- พิสูจน์การจับ/แยก RA ของตัวตรวจ แต่ไม่ได้พิสูจน์เส้นทางเครือข่าย
"""
from __future__ import annotations

import argparse
import os
import socket
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.check_router import ETH_P_IPV6, _csum, _iface_mac  # noqa: E402


def link_local(mac: bytes) -> bytes:
    eui = bytearray(mac[:3] + b"\xff\xfe" + mac[3:])
    eui[0] ^= 0x02
    return b"\xfe\x80" + b"\0" * 6 + bytes(eui)


def build_ra(mac: bytes, withdraw: bool = False) -> bytes:
    src = link_local(mac)
    dst = socket.inet_pton(socket.AF_INET6, "ff02::1")
    lifetime, valid, pref = (0, 0, 0) if withdraw else (1800, 86400, 14400)
    pio = struct.pack("!BBBBIII16s", 3, 4, 64, 0xC0, valid, pref, 0,
                      socket.inet_pton(socket.AF_INET6, "2001:db8:cafe::"))
    slla = struct.pack("!BB6s", 1, 1, mac)
    icmp = struct.pack("!BBHBBHII", 134, 0, 0, 64, 0, lifetime, 0, 0) + pio + slla
    pseudo = src + dst + struct.pack("!I3xB", len(icmp), 58)
    icmp = icmp[:2] + struct.pack("!H", _csum(pseudo + icmp)) + icmp[4:]
    ip6 = struct.pack("!IHBB", 0x60000000, len(icmp), 58, 255) + src + dst
    return b"\x33\x33\x00\x00\x00\x01" + mac + struct.pack("!H", ETH_P_IPV6) + ip6 + icmp


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iface", default="eth0")
    ap.add_argument("--seconds", type=float, default=40)
    ap.add_argument("--withdraw", action="store_true")
    a = ap.parse_args()
    mac = _iface_mac(a.iface)
    s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETH_P_IPV6))
    s.bind((a.iface, 0))
    frame = build_ra(mac, a.withdraw)
    end = time.monotonic() + a.seconds
    n = 0
    while time.monotonic() < end:
        s.send(frame)
        n += 1
        time.sleep(1)
    print(f"sent {n} RA ({'withdraw' if a.withdraw else 'active'}) from {mac.hex(':')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
