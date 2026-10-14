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
