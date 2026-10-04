"""tools/check_router.py -- สร้าง/แยกแพ็กเก็ต DHCP และ IPv6 RA (ไม่ต้องมี root หรือเครือข่ายจริง)"""
import socket
import struct

from tools import check_router as cr

PI_MAC = bytes.fromhex("dca632000001")
ROUTER_MAC = bytes.fromhex("50c7bf112233")


def _offer(xid: int, msg_type: int = 2, server="192.168.1.1", yiaddr="192.168.1.57") -> bytes:
    bootp = struct.pack("!BBBBIHH4s4s4s4s16s64s128s", 2, 1, 6, 0, xid, 0, 0x8000,
                        b"\0" * 4, socket.inet_aton(yiaddr), b"\0" * 4, b"\0" * 4,
                        b"\0" * 16, b"\0" * 64, b"\0" * 128)
    opts = b"\x63\x82\x53\x63" + bytes([53, 1, msg_type]) + b"\x36\x04" + socket.inet_aton(server) + b"\xff"
    payload = bootp + opts
    udp = struct.pack("!HHHH", 67, 68, 8 + len(payload), 0) + payload
    ip = struct.pack("!BBHHHBBH4s4s", 0x45, 0, 20 + len(udp), 0, 0, 64, 17, 0,
                     socket.inet_aton(server), b"\xff" * 4)
    return b"\xff" * 6 + ROUTER_MAC + b"\x08\x00" + ip + udp


def _ra(lifetime=1800, prefix="2001:db8:1::", a_flag=True, managed=False, valid=86400) -> bytes:
    pio = struct.pack("!BBBBIII16s", 3, 4, 64, 0x40 if a_flag else 0, valid, 3600, 0,
                      socket.inet_pton(socket.AF_INET6, prefix))
    icmp = struct.pack("!BBHBBHII", 134, 0, 0, 64, 0x80 if managed else 0, lifetime, 0, 0) + pio
    src = socket.inet_pton(socket.AF_INET6, "fe80::1")
    dst = socket.inet_pton(socket.AF_INET6, "ff02::1")
    ip6 = struct.pack("!IHBB", 0x60000000, len(icmp), 58, 255) + src + dst
    return b"\x33\x33\x00\x00\x00\x01" + ROUTER_MAC + b"\x86\xdd" + ip6 + icmp


def test_discover_is_valid_broadcast_ipv4():
    mac = cr.random_mac()
    f = cr.build_dhcp_discover(mac, 0x12345678)
    assert f[:6] == b"\xff" * 6 and f[6:12] == mac and f[12:14] == b"\x08\x00"
    ip = f[14:34]
    assert cr._csum(ip) == 0                       # checksum ของ IP header ถูก
    assert ip[16:20] == b"\xff" * 4
    bootp = f[42:]
    assert bootp[0] == 1 and struct.unpack("!I", bootp[4:8])[0] == 0x12345678
    assert bootp[28:34] == mac
    assert b"\x35\x01\x01" in bootp[240:]          # DHCPDISCOVER
    # RFC 1542 ขั้นต่ำ 300 ไบต์ -- สั้นกว่านี้เราเตอร์จริงบางตัวทิ้งเงียบ (เจอกับเราเตอร์แล็บ)
    assert len(bootp) >= 300
    assert b"\x3d\x07\x01" + mac in bootp[240:]    # client-id
    udp_len = struct.unpack("!H", f[38:40])[0]
    ip_len = struct.unpack("!H", f[16:18])[0]
    assert udp_len == 8 + len(bootp) and ip_len == 20 + udp_len


def test_random_mac_is_local_unicast():
    for _ in range(50):
        m = cr.random_mac()
        assert m[0] & 0x02 and not m[0] & 0x01


def test_offer_with_matching_xid_detected():
    hit = cr.parse_dhcp_reply(_offer(0xABCD), 0xABCD)
    assert hit == {"server_ip": "192.168.1.1", "server_mac": "50:c7:bf:11:22:33", "offered_ip": "192.168.1.57"}


def test_ack_also_counts():
    assert cr.parse_dhcp_reply(_offer(7, msg_type=5), 7)


def test_offer_for_other_xid_ignored():
    # คำตอบของเครื่องอื่นในวงที่บังเอิญได้ยิน ไม่ใช่หลักฐานว่าเราเตอร์ตอบ probe ของเรา
    assert cr.parse_dhcp_reply(_offer(1), 2) is None


def test_nak_ignored():
    assert cr.parse_dhcp_reply(_offer(9, msg_type=6), 9) is None


def test_garbage_frames_ignored():
    for f in (b"", b"\0" * 60, _ra()):
        assert cr.parse_dhcp_reply(f, 1) is None
        assert cr.parse_ra(_offer(1)) is None


def test_router_solicit_checksum():
    f = cr.build_router_solicit(PI_MAC)
    assert f[:6] == b"\x33\x33\x00\x00\x00\x02" and f[12:14] == b"\x86\xdd"
    ip6, icmp = f[14:54], f[54:]
    assert icmp[0] == 133
    pseudo = ip6[8:24] + ip6[24:40] + struct.pack("!I3xB", len(icmp), 58)
    assert cr._csum(pseudo + icmp) == 0


def test_ra_with_slaac_prefix_detected():
    hit = cr.parse_ra(_ra())
    assert hit["router_ip"] == "fe80::1" and hit["prefixes"] == ["2001:db8:1::/64"]


def test_ra_default_router_only_detected():
    # ไม่มี prefix แต่ประกาศตัวเป็น default router (lifetime > 0) -- ยังนับว่าเปิด
    assert cr.parse_ra(_ra(a_flag=False))


def test_ra_dhcpv6_managed_detected():
    assert cr.parse_ra(_ra(lifetime=0, a_flag=False, managed=True))["dhcpv6_managed"]


def test_ra_withdrawn_not_counted():
    # เราเตอร์ที่เพิ่งปิด IPv6 ส่ง RA lifetime 0 + prefix valid 0 -- มือถือเลิกใช้ IPv6 แล้ว ถือว่าผ่าน
    assert cr.parse_ra(_ra(lifetime=0, valid=0)) is None


def test_check_reports_raw_socket_errors(monkeypatch):
    def boom(*a, **k):
        raise PermissionError("Operation not permitted")
    monkeypatch.setattr(cr, "probe_dhcp", boom)
    monkeypatch.setattr(cr, "probe_ipv6_ra", lambda *a, **k: [])
    r = cr.check("eth0")
    # ตรวจไม่ได้ต้องไม่ถือว่าผ่าน (ไม่งั้นเปิด portal ทั้งที่ DHCP ของเราเตอร์ยังเปิด)
    assert r["ok"] is False and r["dhcp"]["ok"] is False and "error" in r["dhcp"]
