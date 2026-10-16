---
name: n2-ipv6-l2-bypass-pending
description: PENDING (user said "เก็บไว้ก่อน" 2026-10-16) — customers see the uplink router's IPv6 RA directly (same L2), so router-issued IPv6 bypasses the Pi entirely; not yet written into §3.19, RA-sim test + periodic RA monitor not done
metadata:
  type: project
---

2026-10-16 on the university VLAN: the lab laptop (customer side, 10.10.0.209 via Pi) showed IPv6 Default Gateway fe80::a2a4:7fff:fe29:8aa4 = the university router. That router's RA has no prefix and M=0, so nobody gets a global IPv6 and nothing leaks today.

Why it matters: the single-cable design puts customers and the router on one L2 ([[single-pi-single-cable-constraint]]). If the router ever advertises a prefix, customers get IPv6 straight from the router and the traffic never touches the Pi, so the Pi cannot block or log it. The only mitigation is disabling IPv6 on the router (book §5 limitation 6). check_router.py runs only at install.

**Why:** user deferred this ("เก็บข้อนี้ไว้ก่อน เดี๋ยวค่อยมาแก้").

**How to apply:** when the user returns to N2, the pending work is:
- add the screenshot evidence to docs/hardware-test-log.md §3.19;
- run tools/lab_ra_sim.py with a prefix and measure the leak with a phone;
- consider a periodic RA monitor that raises an audit event and a /status alert.

Also pending on the laptop: Ethernet 4 has a persistent stale gateway 10.4.1.254 (metric 256 < 10.10.0.1's 500). The user should remove it with Remove-NetRoute; Claude must not change it.
