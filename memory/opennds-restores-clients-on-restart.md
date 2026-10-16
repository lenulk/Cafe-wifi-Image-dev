---
name: opennds-restores-clients-on-restart
description: openNDS 10.1.3 re-authenticates every client it remembers when it restarts, ignoring our DB; cafe-enforce must sweep openNDS→DB orphans (N44)
metadata:
  type: project
---

openNDS keeps `/tmp/ndslog/authlog.log` (base64 MAC + session_end). After any restart (install.sh re-run, reboot, crash) it runs `ndsctl auth` for each of those clients. binauthlog shows `shutdown_deauth` immediately followed by `ndsctl_auth`.

It does not consult our database. A device whose voucher was revoked or expired can therefore come back online for free, with unattributed logs, which is a Section 26 problem. Found 2026-10-03: a revoked ASUS laptop was online with session_end the next day.

**Fix (N44):**
- `tools/enforce_voucher_expiry.find_orphan_macs()` deauths any openNDS Authenticated MAC that has no DB session in state authenticated (open) or pending (not yet expired), and audits it as `orphan_deauth`.
- Drop-in `opennds.service.d/cafe-wifi-orphan-sweep.conf` uses systemd-run to start cafe-enforce 45 s after openNDS starts.
- Measured on the Pi: orphans were cut about 75 s after the restart.

**How to apply:**
- Every reachability check must go both ways (DB→openNDS and openNDS→DB).
- Never treat "openNDS says Authenticated" as entitlement.
- Pending sessions must not be cut: openNDS opens a device before reconcile confirms it.

Related: [[admin-access-from-customer-lan]]

**2026-10-16 follow-ups (commits e33a0a4, 1d1d28c + session_end fix):**
- openNDS restore only covers clients with traffic at that moment; a sleeping phone gets dropped → enforce closes it `disconnected` → it hit the register page with 80 min left. Fix: `reconcile_pending.resume_returning()` (every 5 s) re-auths any MAC in `device` bound to an active voucher (customer not blocked, no open/pending session) when it is REACHABLE/DELAY/PROBE in `ip neigh`; `ndsctl auth` works even when openNDS doesn't know the MAC (pre-emptive auth). Audit `device_resume`. Verified: Redmi 14 + Samsung came back with no re-registration.
- `GONE_GRACE_SECONDS` 180 → 30, measured from `authenticated_at` (authenticated now always means openNDS-confirmed).
- openNDS restore also sets a WRONG, shorter session_end (laptop: voucher 16:13 → restored 16:09, then 16:08 after 2nd restart → cut early). Fix: `enforce.flag_short_gateway_sessions()` sets `voucher.auth_sync_needed=1` when openNDS session_end < valid_until − 120 s → sync_extended deauth+auth with real minutes. Verified on Pi: Redmi 12 17:01:29 → 17:06:15.
