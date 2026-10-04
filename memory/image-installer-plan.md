---
name: image-installer-plan
description: 2026-10-03 plan to ship Cafe-WiFi as a prebuilt Pi image (no CLI) — docs/image-build-plan.md + docs/install-from-image.md; not started yet
metadata:
  node_type: memory
  type: project
  originSessionId: aeeefbbc-b458-4b43-8811-383e2f9573d2
  modified: 2026-10-04T11:11:34.774Z
---

User wants an installer "like Raspberry Pi Imager but locked to our OS/services, no CLI config". Agreed design (2026-10-03), written up in `docs/image-build-plan.md` (plan, milestones M1–M8, tests IMG-01..10) and `docs/install-from-image.md` (target on-site procedure):

- Keep `install.sh` as the core; add `--stage build|firstboot|site|all` (default all = old behaviour).
- Build with pi-gen/rpi-image-gen (WSL2+Docker on the laptop); stock Raspberry Pi Imager + custom os_list.json, no own flasher yet.
- **No secrets in the image** — 12 items (DEK, pepper, SECRET_KEY, setup.token, FAS_KEY, TLS key, DB_PASS, SSH alt port, SSH host keys, machine-id, random-seed, user ras/1234) must be generated at first boot.
- Site network values come from a web setup wizard at cafewifi.local, gated by a setup code; router DHCP must stay ON until the wizard, then wizard probes that DHCP/IPv6 are off before starting dnsmasq/openNDS.
- Imager can't add custom fields → `prepare-sd.ps1` writes cafewifi.conf + setup code to bootfs.

**Progress 2026-10-04:** M1 coded in install.sh (uncommitted at time of writing): `--stage`, `in_stage()`, `enable_offline_systemctl()` (exported systemctl wrapper used for *every* `--stage build`, even on live systemd), split `configure_opennds`/`make_tls_cert`/`start_nginx`, install.sh copied to /opt/cafe-wifi. Verified only by WSL dry-run (`--stage all` command list identical to old version except intended additions) — NOT yet run on the Pi. Gotcha: `sed s|..|$kv|` breaks on shop names with `&`/`|` → replaced with bash line rewrite. Docker Desktop installed via winget on the laptop (user must launch + accept license). User has 1 Pi + 2 SD cards: card A (working system, never flash), card B for image tests.

**Repo layout decided 2026-10-04:** user considers the main project complete and does not want it touched. `master` is frozen and tagged `v1.0`; M1 was removed from master's install.sh. M1 had been swept into the other chat's N45 commit 23fd46e by a blanket commit. All image work happens on branch **`image`** in the same repo, and M1 lives only there. Never commit image work to master. Only bring master into `image` with a merge; the M1 removal is already "reverted back" on `image`, so a merge will not drop M1. **Push target:** the local `image` branch tracks remote `imagerepo` (https://github.com/lenulk/Cafe-wifi-Image.git, the user's own repo created 2026-10-04) as its `main` branch. Image work is pushed there, not to origin Cafe-wifi. Push it with `git push imagerepo image:main`, or a plain `git push` since `image` tracks it.

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

**Why:** single-Pi plug-and-play goal ([[single-pi-single-cable-constraint]]); avoid on-site GitHub/PyPI dependency (openNDS v10.1.3 is the only thing compiled from source).
**How to apply:** start at M1 when user says go; any change to install.sh must keep `--stage all` passing lab_fulltest.sh 49/49.
