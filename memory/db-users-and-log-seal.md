---
name: db-users-and-log-seal
description: A8/H2 done 2026-10-16 — per-service MariaDB users, evidence triggers, daily DB-row seal chain; where creds live and how to run CLI tools now
metadata:
  type: project
---

Owner chose option 3 (2026-10-16). Shipped in b144bba..7b577db (pushed to dev), verified on the lab Pi (docs/hardware-test-log.md §3.17).

- **Users:** cafe_fas / cafe_admin / cafe_logger get table-level grants (matrix in install.sh `db_grant_matrix`); none can UPDATE/DELETE conn_log/dns_log or DELETE audit_log. cafe_ops (root units: maintenance, enforce, reconcile, check-disk) = full DML on the db. Legacy `DB_USER` in secrets.env keeps only setup-wizard rights (staff S/I, audit_log I) — restricted in start_services AFTER restart (doing it earlier dropped 19 log events).
- **Creds:** /etc/cafe-wifi/db/{fas,admin,logger,ops}.env root 0600, loaded by units after secrets.env; grants.sql there is re-applied by setup/restore.py after a DB restore.
- **CLI tools now need:** `set -a; . /etc/cafe-wifi/secrets.env; . /etc/cafe-wifi/db/ops.env; set +a` (docs updated). Ad-hoc runs: `systemd-run --wait --pipe -p EnvironmentFile=/etc/cafe-wifi/secrets.env -p EnvironmentFile=/etc/cafe-wifi/db/ops.env ...`.
- **sql/018:** log_seal (append-only) + triggers. backup_db uses --skip-triggers (triggers come back from sql/018).
- **Seal:** logger/db_seal.py in cafe-maintenance after purge, before backup; seals day D at D+2; nightly verify last 9 days + 14-night rotation; ~10k rows/s on Pi. Head → USB log-seal-anchor.txt + /status card with "check a recorded code".
- **Test residue on lab Pi:** one audit row `integrity_failed dns_log:2026-10-12` from the planted-row test (expected).
- Remaining limits for thesis ch.5: unsealed (≤2 days) inserts, read access, root rebuilding the chain (caught only by offsite head), same-unix-user services can read each other's env.

Related: [[core-review-2026-10-14]], [[pi-image-ssh-access]], [[windows-crlf-edit-trap]]
