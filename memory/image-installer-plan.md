---
name: image-installer-plan
description: 2026-10-03 plan to ship Cafe-WiFi as a prebuilt Pi image (no CLI) — docs/image-build-plan.md + docs/install-from-image.md; not started yet
metadata:
  node_type: memory
  type: project
  originSessionId: aeeefbbc-b458-4b43-8811-383e2f9573d2
  modified: 2026-10-04T15:11:49.696Z
---

User wants an installer "like Raspberry Pi Imager but locked to our OS/services, no CLI config". Agreed design (2026-10-03), written up in `docs/image-build-plan.md` (plan, milestones M1–M8, tests IMG-01..10) and `docs/install-from-image.md` (target on-site procedure):

- Keep `install.sh` as the core; add `--stage build|firstboot|site|all` (default all = old behaviour).
- Build with pi-gen/rpi-image-gen (WSL2+Docker on the laptop); stock Raspberry Pi Imager + custom os_list.json, no own flasher yet.
- **No secrets in the image** — 12 items (DEK, pepper, SECRET_KEY, setup.token, FAS_KEY, TLS key, DB_PASS, SSH alt port, SSH host keys, machine-id, random-seed, user ras/1234) must be generated at first boot.
- Site network values come from a web setup wizard at cafewifi.local, gated by a setup code; router DHCP must stay ON until the wizard, then wizard probes that DHCP/IPv6 are off before starting dnsmasq/openNDS.
- Imager can't add custom fields → `prepare-sd.ps1` writes cafewifi.conf + setup code to bootfs.

**Progress 2026-10-04:** M1 coded in install.sh (uncommitted at time of writing): `--stage`, `in_stage()`, `enable_offline_systemctl()` (exported systemctl wrapper used for *every* `--stage build`, even on live systemd), split `configure_opennds`/`make_tls_cert`/`start_nginx`, install.sh copied to /opt/cafe-wifi. Verified only by WSL dry-run (`--stage all` command list identical to old version except intended additions) — NOT yet run on the Pi. Gotcha: `sed s|..|$kv|` breaks on shop names with `&`/`|` → replaced with bash line rewrite. Docker Desktop installed via winget on the laptop (user must launch + accept license). User has 1 Pi + 2 SD cards: card A (working system, never flash), card B for image tests.

**Repo layout decided 2026-10-04:** user considers the main project complete and does not want it touched. `master` is frozen and tagged `v1.0`; M1 was removed from master's install.sh. M1 had been swept into the other chat's N45 commit 23fd46e by a blanket commit. All image work happens on branch **`image`** in the same repo, and M1 lives only there. Never commit image work to master. Only bring master into `image` with a merge; the M1 removal is already "reverted back" on `image`, so a merge will not drop M1. **Push target:** changed 2026-10-05, see "Two repos" below. The local `image` branch tracks `dev/main`. A plain `git push` sends work to the PRIVATE dev repo. Never push the `image` branch to `public`.

**M2 done in code 2026-10-04 (branch image):**
- New files: `image/firstboot/cafe-wifi-firstboot.{sh,service}`, plus `test_firstboot.sh`. The tests run in WSL as non-root via `CAFEWIFI_*` env overrides and pass 41/41. Run them from PowerShell: `wsl.exe -d kali-linux -- bash <script>`.
- `install.sh` changes:
  - `gen_secrets` now writes via `.new` + sync + mv, so the first write and every update are atomic. `secrets.env` existing is the "done" marker.
  - It now dies if an existing `secrets.env` lacks `NATID_DEK`.
  - `make_tls_cert` reissues the certificate if the key does not match it.
- `cafewifi.conf` keys: `GATEWAY_NAME`, `SETUP_CODE`, `SSH_PUBKEY`, `TECH_USER` (default `cafeadmin`, key-only, NOPASSWD sudo). The format is documented in plan §4.
- Not tested on the Pi yet (IMG-04).
- M3 todo found during M2:
  - disable `dnsmasq` in the image (the Debian package self-enables)
  - wipe the §2 files
  - lock the pi-gen first user

**M3–M6 status, 2026-10-04:**
- M3: the image built successfully (`image/deploy/`, gitignored, 644 MB) and passed IMG-02 on the real `.img`. Built from the pi-gen tag `2026-09-15-raspios-trixie-arm64` in Docker Desktop via `image/build.ps1` (`-Reuse` skips stage0-2 using the docker volume `cafewifi-pigen-work`).
- M4–M6 (`app/setup` wizard, `setup/apply.py`, `tools/check_router.py`, `prepare-sd.ps1`, `os_list.json`) pass unit tests only.
- Nothing has been booted on a Pi yet.
- M7 (factory reset + key backup) and the self-test were deferred.
- Gotchas found:
  - Docker CLI needs `C:\Program Files\Docker\Docker\resources\bin` on PATH (otherwise "docker-credential-desktop not found").
  - The kali WSL distro has no docker; drive Docker from PowerShell.
  - `docker pull` with `--platform arm64` retags the local `debian:trixie-slim`, so always pass `--platform linux/amd64`.
  - Docker Desktop binfmt registers `aarch64` with flags POCF, so pi-gen works without `dpkg-reconfigure`.
  - The Windows test suite has 10 pre-existing failures (backup_db / logger_restart / sysinfo), unrelated to this work.
  - `lab_fulltest.sh` assumes user `ras`, but the image's tech user is `cafeadmin` (SSH key only).

**First real boot on card B (2026-10-04):**
- The image boots and avahi is up.
- firstboot hung for 15 minutes in `configure_ssh`. Cause: `systemctl reload ssh` waited on ssh.service, which was itself ordered after firstboot (`Before=ssh.service`), so the two deadlocked.
  - Fixed in 6e84af1 (`--no-block try-reload-or-restart`, plus a TERM trap so the LED shows the error pattern instead of fast-blinking forever).
  - Applied by hand on the Pi, then firstboot was re-run. It took 16 s and the secret hashes were unchanged, which is good rerun evidence.
- The wizard is reachable at http://cafewifi.local (172.20.18.61). The Pi at that address runs card B and is reachable as `ssh cafeadmin@172.20.18.61` with the laptop key; known_hosts was kept in scratchpad.
- Lab gotcha: Aruba `dhcpv4-snooping` inserts option 82, and the lab router silently ignores those DISCOVERs (giaddr=0). Even trusting 1/1/24 did not help, so run `no dhcpv4-snooping` while testing the image.
- To simulate "router DHCP off" for IMG-06, re-enable snooping with trust on 1/1/6 only.
- Never use a Pi on card A as the test target.
- **The wizard passed end-to-end on card B at 16:48:**
  - The user ran steps ①–⑤ (router check passed with snooping re-enabled).
  - apply → `--stage site` finished.
  - All 10 services came up active (mariadb, nginx, dnsmasq, nftables, opennds, cafe-admin, cafe-fas, cafe-logger, netsetup, chrony).
  - Addresses: eth0 172.20.18.61/24, cafe-wifi-cli0 10.10.0.1/24.
  - `.site-done` is set, the setup code and SETUP-CODE.txt were removed, the wizard is disabled, and the LED is back to mmc0.
  - Next: phone portal flow, then `lab_fulltest` (adapt it for user `cafeadmin`).
- **IMG-08 passed 49/49 on card B (18:10).**
  - Before the fix it was 43/49. The nftables dead-man switch (`cafe-wifi-nft-failsafe`) flushed the entire firewall 5 minutes after apply, because no human was there to cancel it. That broke NAT, opened port 22 to customers, and dropped `lo` notrack.
  - Fixed in `install.sh`: skip the dead-man switch when `--stage site` runs without `SSH_CONNECTION`/`SUDO_USER`.
  - Manual recovery on a live Pi: `nft -f /etc/nftables.conf`, then `systemctl restart opennds` (the flush also removes the nds tables), then `conntrack -D -s 127.0.0.1` to clear stale lo entries.
  - `lab_fulltest` now picks `cafeadmin` automatically (`FT_SSH_USER` overrides).
  - A fresh install has no `backup-status.json` until `cafe-maintenance` runs (03:30), so for the test run `systemctl start cafe-maintenance` first.
  - Results are logged in `docs/hardware-test-log.md` §3.15.
- Image todo:
  - add an IPv4 link-local fallback and make the wizard listen on [::] (it was unreachable while there was no DHCP)
  - rebuild with 6e84af1

**Clean first boot of image 9009677 on card B (2026-10-04 ~19:00):**
- No manual fixes were needed.
- firstboot completes in seconds. The log timestamps jump from the fake-hwclock build time to NTP time; that is not a hang.
- The wizard comes up by itself on `*:80`.
- The firewall survives after apply.
- `lab_fulltest`: 49/49. On a fresh install the first run's evidence check can fail once; it looks like collector timing. The test now prints a reason when that check fails.

**`check_router` had a false-negative bug** (it reported router DHCP as off while it was on). Fixed in 3144660, IMG-06 now 10/10:
- the DISCOVER must be padded to ≥300 bytes (RFC 1542)
- the probe socket needs PACKET_MR_PROMISC, because the router unicasts the OFFER to the random MAC
- the probe must listen continuously for 12 s with the same xid, because the OFFER arrives after more than 2 s

**The image must be rebuilt** to include this fix; 9009677 predates it.

**Image 10335a3, full wizard through the browser (2026-10-04 ~20:30–21:00):**
- The first router check after a long idle **missed again**. The lab router ignores the first 3 DISCOVERs after idle and only answers the 4th, at ~12.2 s.
  - Fix: listen 20 s and resend every ~3 s.
  - Fixed in commit ec1e0dc (after 10335a3), so **10335a3 still has the 12 s window**. Rebuild before release.
- After the fix:
  - DHCP on → ❌ and the save button is hidden.
  - Snooping on → ✅.
  - Apply works.
  - After more than 5 minutes, the firewall is intact.
  - `lab_fulltest` 49/49 on the first run.
- The console session on COM5 times out when idle. aruba.ps1 now stops if it sees a login prompt.
- The .ps1 must be saved with a UTF-8 BOM (PowerShell 5.1).

**Aruba console:**
- COM5, 115200 baud. The user logs in through PuTTY and then closes the window, leaving the session open.
- Claude then drives the console with `scratchpad/aruba.ps1` (System.IO.Ports, no pyserial).
- **Claude must never log in or enter a password itself.**
- Never `write memory`.

**Release candidate ec1e0dc passed on card B (2026-10-04 21:55):**
- The first wizard router check returned ❌ with lab DHCP on, which is correct.
- Snooping on → ✅, apply works, the firewall is still intact at +339 s.
- `lab_fulltest` 49/49.
- The evidence check was a test bug, not a product bug. `conn_log` rows are written only when a connection ends (conntrack DESTROY), so a fresh install has 0 rows. The test now sums rows across all files.

**Released 2026-10-04:** https://github.com/lenulk/Cafe-wifi-Image/releases/tag/v1.0.0
- The tag points at ec1e0dc. Assets: `.img.xz`, `.sha256` and `os_list.json`.
- GitHub's digest matches the local sha256, and an anonymous download works.
- Both repos are public (the user's choice).
- The README was rewritten for the image repo in ed50f36.
- `gh` 2.102 is installed at `C:\Program Files\GitHub CLI\gh.exe`, logged in as lenulk by the user. Claude never handles the token.

**v1.0.1 (7bac6b3) built and tested on card B (2026-10-04 23:00–23:59). All IMG tests pass except IMG-09** (results in hardware-test-log §3.15.1).
- New in v1.0.1:
  - `.cwkey` key backup (admin `/keys`) + `tools/restore_keys.py`.
  - Revoke takes effect immediately.
  - The wizard prefills the shop name.
- Full disaster recovery was proven: reflash → wizard → `restore_keys` (the user types the passphrase in their own terminal) → import DB dump → the old national IDs decrypt 1/1.
- IMG-07, RA side: a namespace on the same Pi does NOT work, because a packet socket bound to ETH_P_IPV6 never receives outgoing frames. Use the laptop instead:
  - `netsh interface ipv6 set route 2001:db8:cafe::/64 "Ethernet 4" publish=yes` + `set interface advertise=enabled` (UAC). The script is `scratchpad/ra-laptop.ps1`.
  - Use `set route`, not just `add`: the route may already exist.
- `lab_fulltest.sh` broke on shop names with spaces (it used `env $(xargs)`). Fixed with a `penv` line reader.
- The wizard needs port 24 up for the IMG-06 ❌ side, because the router sits behind 1/1/24. So for IMG-03, cut the port before first boot finishes and again just before Save.

**Released 2026-10-05:** https://github.com/lenulk/Cafe-wifi-Image/releases/tag/v1.0.1
- The tag is the full SHA 7bac6b35. `gh --target` rejects a short SHA with 422.
- The GitHub digest matches the local sha256, and an anonymous download works.
- The README (ae0c87e) points to v1.0.1.
- The auto-mode classifier blocks `gh release create` until the user explicitly grants permission in chat.

Remaining work:
- IMG-09 factory reset is deferred to a later version. The workaround is reflash + `restore_keys` + DB restore.

**Why:** single-Pi plug-and-play goal ([[single-pi-single-cable-constraint]]); avoid on-site GitHub/PyPI dependency (openNDS v10.1.3 is the only thing compiled from source).
**How to apply:** start at M1 when user says go; any change to install.sh must keep `--stage all` passing lab_fulltest.sh 49/49.

**Two repos (2026-10-05, user decision): public = product showcase, private = workspace.**
- Remote `dev` → https://github.com/lenulk/Cafe-wifi-Image-dev (PRIVATE).
  - This is the old public repo, renamed and made private. It holds the full history, the v1.0.0/v1.0.1 releases, memory/, the thesis, lab tools and the build.
  - Local branch `image` tracks `dev/main`.
- Remote `public` → https://github.com/lenulk/Cafe-wifi-Image (PUBLIC, recreated fresh).
  - Its history is its own; the first commit 1d154f6 has 106 files.
  - Release v1.0.1 was re-uploaded there and the digest matches.
  - Old commit SHAs from the dev history return 404 publicly.
- Publish with `bash image/publish-public.sh "<msg>"`, then `git push public public:main`.
  - The script builds the branch `public` from an ALLOWLIST at HEAD: app, sql, install.sh, the runtime tools/*.py, image/{VERSION,prepare-sd.ps1,setup,firstboot/*.sh|.service}, and docs/{install-from-image,backup-usb,privacy-policy-th}.md.
  - It also copies `image/public/README.md` and `image/public/gitignore`.
  - There is no build how-to (the user asked for that).
  - A new public file means editing ALLOW.
  - Release notes and gh releases go on `lenulk/Cafe-wifi-Image`.
- The desktop machine must run `git remote set-url` to point at the -dev repo. The repo is now private, so it needs a GitHub login.
- Known bug for v1.0.2: `app/admin/templates/status.html` hardcodes `ssh -p … ras@10.10.0.1`. Image installs use the user `cafeadmin`, and the client IP is configurable.

**v1.1.0 (2026-10-05, one combined round):**
- Fixes: revoke timer (`AccuracySec`), and `restore_keys` now restores only `NATID_DEK`/`NATID_PEPPER`. Before that, the old `FAS_KEY` broke the portal with "หน้านี้หมดอายุแล้ว".
- New:
  - factory reset: `prepare-sd.ps1 -FactoryReset` → `cafe-wifi-factory-reset.service`; keeps data and skips the wizard admin step.
  - web restore: wizard step ② "กู้คืนจากเครื่องเดิม" → `setup/restore.py`, which takes the newest USB backup, runs migrations, verifies decryption, then writes keys.
  - status page SSH user from the sudo group; shop CA cert link.
  - MIT LICENSE; `build.ps1 -Fast` (.img, 21 min).
- Card B passed: 49/49, IMG-05/06/09, and web restore through a simulated USB (loop FAT labelled CAFEBACKUP), with real phone screenshots in `image/public/img`.
- Dev workflow that worked well: hot-deploy files (app/X → /opt/cafe-wifi/X) and test on the Pi, then do a single build at the end.
- The scratchpad flash.py verify now skips bootfs, because Windows writes to it after mounting.
