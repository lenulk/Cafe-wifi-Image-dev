---
name: enobufs-status
description: ENOBUFS root cause SOLVED 2026-10-04 (N45) — conntrack-tools 1.4.8 applies --buffer-size to the wrong netlink socket; fix is net.core.rmem_default=16MB
metadata:
  type: project
---

**Root cause (N45, confirmed 2026-10-04):** conntrack-tools 1.4.8 opens two netlink sockets.
- fd 3 has groups 0 and fd 4 has groups 0x5 (it receives NEW/DESTROY).
- `--buffer-size` calls SO_RCVBUFFORCE on **fd 3**, so the event socket keeps `net.core.rmem_default` (208 KB, about 150–200 events).
- conntrack's GC destroys expired entries in batches (thousands within milliseconds), which overflows that socket.
- Every buffer increase from N31 onward never touched the event socket.
- Proof command: `strace -f -e trace=socket,bind,setsockopt conntrack -E ... --buffer-size N`.

**Fix:**
- install.sh sysctl `net.core.rmem_default = 16777216`. New sockets take this value at creation, so restart cafe-logger after changing it.
- `conn_collector.check_event_buffer()` logs an error at start if the value is below 8 MB.

**Measured on the Pi (load from the lab client to 10.10.0.1:8080/health, compared against a reference listener):**

| Burst | Before | After |
|---|---|---|
| ~6,300 DESTROY/s | lost 473 (7.9%) | 6,021/6,021 |
| ~12,160/s | not run | 12,030/12,030, 0 drops |

**Earlier mistakes, kept here as lessons:**
- On 2026-10-03 I claimed "buffer verified 64 MB via strace". strace only showed the call succeeding on fd 3.
- Rmem sampled at 0.5 s showed ~0 because the 208 KB fills and drains in microseconds.

**How to apply:** verify settings at the outcome (drops on the actual event socket plus a reference listener), not at the syscall. Earlier mitigations (N41 ping notrack, N43 lo notrack and the `-s` kernel filter) remain useful because they reduce volume.

Related: [[opennds-restores-clients-on-restart]]
