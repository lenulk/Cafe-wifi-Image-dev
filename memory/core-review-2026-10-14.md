---
name: core-review-2026-10-14
description: "Local team review of fas/common/logger/sql on 2026-10-14 — what got fixed off-Pi, what still must be checked on the real Pi first (M1, M2, H2)"
metadata:
  node_type: memory
  type: project
  originSessionId: 5d3fd741-97ba-4504-a0b7-ff3d7e36894a
  modified: 2026-10-13T20:07:29.513Z
---

Report: `docs/code-review-2026-10-14-core.md` (branch `image`, commits 691bbe6..e251076).

- Fixed off-Pi: H1 ICMP ct_id, H3 partition memory, M3–M12, Low items (SESSION_MATCH now `t < ended_at` everywhere except `common/traffic.py` quota — left on purpose).
- DB timeouts: connect 5s / read 600s / write 60s. 30s was rejected because purge/export/backup run long on the Pi; web is capped by gunicorn `--timeout 60` anyway.
- **Not fixed and needs the Pi:** M1 (whether dnsmasq prints `query[type=65]`), M2 (lines lost during logrotate), H2 (split DB users + external hash anchor, a design discussion). Commands are listed in the report's "⏳ ต้องตรวจบน Pi" section.
- After deploying, verify on the Pi:
  - re-run install.sh without the flag; `@@event_scheduler` must be ON
  - `EXPLAIN` must use idx_ip_auth
  - stop MariaDB for 60s, then look for a `log_gap` row with `dropped=`
- Watch out: integrity `unexpected_file` compares dates across every archive file in the directory. If several log streams rotate on different schedules, it could raise a false INTEGRITY_FAILED.
- Windows test failures are down to 6 known ones; the 4 in test_logger_restart passed after the CRLF fix.

**Why:** the user said to fix whatever can be fixed now and to record anything that needs the Pi in a file first.
**How to apply:** when taking the Pi out to test, start from the report's Pi table. Do not fix M1 or M2 by guessing. See [[log-search-upgrade-2026-10-12]], [[real-pi-deployment]].

**Setup wizard + image review (same day, commit 5dfece5, report `docs/code-review-2026-10-14-setup-image.md`):**
- Fixed S1–S3, S5–S8, S11–S13.
- User decisions: S3 means a wrong setup code locks only that IP, not the whole box. S4 (setup code sent over HTTP) is kept as is for now; don't raise it again.
- **Needs the Pi:**
  - S10: run restore import as a non-root DB user and disable `\!` in the mysql client.
  - Test S13 with `TECH_USER=www-data` in cafewifi.conf; firstboot must fail with an error.

**Network layer review (commit 497c67a, report `docs/code-review-2026-10-14-network.md`):**
- **Highest priority on the Pi: N1.** Our own nftables forward chain ends with `ip saddr $CLIENT_NET accept`, so the gate relies only on openNDS's rules. Customers get free internet when:
  - the Pi is booting and openNDS is still waiting on time-sync (up to 180s)
  - openNDS has crashed
  - install.sh is re-run, or nftables is reloaded (`flush ruleset` wipes openNDS's tables)
- N1 fix direction: forward only packets carrying the openNDS authenticated mark. Check the real mark values on the Pi first; a wrong guess cuts off every customer.
- `tests/test_install_sh.py` + `CAFEWIFI_SOURCE_ONLY=1` let tests source install.sh functions on this machine. Use this pattern to test install.sh changes from now on.
- server.key is now 0600 root:root. After re-running install.sh on the Pi, verify that nginx still starts.

**Admin review + small leftovers (same day, report `docs/code-review-2026-10-14-admin.md`):**
- Small leftovers fixed:
  - consent_version is stored (sql/017 + common/policy.py; bump PRIVACY_POLICY_VERSION whenever the policy text changes)
  - a register deadlock (1213/1205) now redirects to /request instead of a 500
  - /request still shows an approved, still-valid multi-day voucher after 1 day
- **The 017 migration must run before restarting cafe-fas**, or the register INSERT fails. Re-run install.sh; the new code alone isn't enough.
- Biggest admin finding: B1, a manifest hash mismatch on the evidence zip. Fixable locally.
- Pi-only: B2 (approving a MAC that is already authed), B3, B4 (export memory), B7, A7, A8, B12.
- Local admin fixes landed: B1, A1–A6, B5, B6, B8, B9, B11.
  - Session cap: absolute 12h, from `session["login_at"]`. tests/conftest.py autouse adds login_at to session_transaction.
  - Known-device cookie `cw_kd` skips the per-username login bucket.
  - Temp passwords expire after 24h.
  - Evidence hash is over the exact zip bytes, BOM included.
  - Blocking a customer sets voucher.auth_sync_needed, and sync_extended now cuts blocked customers instead of re-authing them.
- Still Pi-only: B2, B3, B4, B7, A7, A8, B12.

**tools/ review (same day, report `docs/code-review-2026-10-14-tools.md`), the last section of the 14 Oct review:**
- Fixed locally: T3, T6, T7, T9, U1–U8, U10–U12.
- T8 is the user's decision: **no automatic deletion of audit_log**. An admin presses `/audit/scrub` instead, which replaces MAC and national-ID text with `[ลบแล้ว]` in rows older than ≥180 days and keeps the rows themselves.
- New timer `cafe-check-disk.timer` runs every 15 minutes. It is in install.sh start_services and firstboot SITE_UNITS. The audit for the same level is written at most once every 6 h.
- restore_keys refuses when secrets.env is empty (it used to restore the whole bundle).
- Export CLI: use `--natid-stdin` instead of putting the national ID in argv.
- T10 won't fix.
- **Pi needed:**
  - T1: right after openNDS restarts, ndsctl json may list only some clients. Sessions get marked gone, then cut as orphans. This is the top priority on the Pi.
  - T2, T4, T5 (quota counted only on conntrack DESTROY), T11, U9.
  - The partition DROP event uses CURDATE() and has no clock check.

**Pi results 2026-10-16** (docs/hardware-test-log.md §3.16): B2 confirmed→fixed→re-verified; B3 display fixed; B5/U8/M12 OK; M1 closed (dnsmasq 2.91 prints `query[HTTPS]`); M2 not reproduced (399/399 across logrotate); M6 OK (DB down 68 s, 500/500, no log_gap needed); U9/B4 streaming export (iter_rows + write_csv_stream, web cap 300k rows). Still open: A8/H2 (DB grants — owner decision, proposed audit_log triggers), T1/T2/T4/T5/T11 (need AP + several phones), N1, N2.

**Phones via AP 2026-10-16 (hardware-test-log §3.18):** T1 ok at 3 phones (openNDS restores all in ~32 s < 45 s enforce sweep), T2 ok, T4 ok (new 8.9 s, revoked ~1 s). **N1 confirmed + fixed**: forward now accepts only openNDS mark bit 0x20000 + own `cafe_walledgarden` set (dnsmasq nftset); nftables reload/start drop-in try-restarts openNDS. Fail-closed: openNDS down = nobody online (intended). Still open: N2 (router IPv6 RA), T1/T4 at 10+ devices, T5 quota overshoot, openNDS appends duplicate nftset lines to /etc/dnsmasq.conf each start (low).
