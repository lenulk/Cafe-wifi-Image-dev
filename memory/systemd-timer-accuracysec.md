---
name: systemd-timer-accuracysec
description: systemd timers default AccuracySec=1min — a "every 5 sec" OnUnitInactiveSec timer actually fired 8–25 s apart; set AccuracySec=1s for latency-sensitive timers
metadata:
  type: project
---

`cafe-reconcile.timer` (`OnUnitInactiveSec=5sec`) drives revoke and extend sync. Measured on the real Pi on 2026-10-05, its runs were 8–25 s apart. Revoke → internet cut took 22–26 s, which is not the "immediate" claimed for 1.0.1.

The cause is systemd's default `AccuracySec=1min`, which lets it coalesce wakeups. The fix is `AccuracySec=1s` in install.sh. After the fix the cut takes 6.7–8.3 s across 6 runs.

**Why:** unit tests and the old lab_fulltest never caught this. The fulltest called enforce itself right after revoking, so it never measured real latency.

**How to apply:**
- Any new short-interval timer needs `AccuracySec=` set explicitly.
- When testing a "happens within N s" feature, measure it end to end without manually triggering the worker.
- lab_fulltest now measures revoke latency (≤ 15 s). Related: [[image-installer-plan]]
