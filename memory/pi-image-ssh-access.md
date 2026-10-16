---
name: pi-image-ssh-access
description: "How to get into the lab Pi now that it runs the cafe-wifi image — user cafeadmin, key-only SSH on the customer side at a random port (39507); ras/1234 no longer exists"
metadata:
  node_type: memory
  type: reference
  originSessionId: 5d3fd741-97ba-4504-a0b7-ff3d7e36894a
  modified: 2026-10-16T03:41:22.186Z
---

As of 2026-10-16 the lab Pi 4B runs the **cafe-wifi image**, not the old manual install. hostname is `cafewifi`.

- **Login:** `cafeadmin`. The password is locked by design (`passwd -l`, `PasswordAuthentication no`), so the console login cannot work. `ras`/`1234` belongs to the old install and does not exist on the image.
- **SSH:** use the laptop key `~/.ssh/id_ed25519`. From the customer side the port is `ssh -p 39507 cafeadmin@10.10.0.1`; this is SSH_ALT_PORT, randomized at install and stored in /etc/cafe-wifi/secrets.env. Port 22 is only open on the router side.
- **Getting the laptop onto the customer side:** the laptop LAN (`Ethernet 4`) must get 10.10.0.x from the Pi, which needs the Aruba dhcpv4-snooping. It is lost whenever the switch reboots.
  - Set the Wi-Fi metric lower so the laptop's own internet goes via Wi-Fi: `Set-NetIPInterface -InterfaceMetric` (admin, done by the user).
- **wlan0 is disconnected** on the image, so there is no SSH over Wi-Fi.
- **Finding the port again:** if the port is unknown, scan 10.10.0.1:20000-60000 for an SSH banner (about 1 minute with 200 threads).
- **State found 2026-10-16:**
  - eth0 was `192.168.2.100/24` gw `192.168.2.1`, a setup from another place.
  - **192.168.20.1 is NOT the lab internet** — it is the switch's own VLAN20 SVI (LLDP: Aruba **JL725B 6200F**, hostname `6200`, ML.10.13; port 1/1/6 PVID 20 from leftover training config). Nothing else on VLAN 20; no internet. Old lab uplink was 172.20.18.0/24 gw .1 (no ARP reply on VLAN 20). Fix = put 1/1/6-8 into the same VLAN as 1/1/24.
  - 2026-10-16 ran `install.sh --stage site --uplink-cidr 192.168.20.250/24 --uplink-gw 192.168.20.1` (wrong gw) — must re-run site stage once real uplink is known, then `--stage all`.
  - Read LLDP from the Pi: `sudo tcpdump -vvni eth0 -c1 ether proto 0x88cc` shows switch model, port, PVID.
  - The installed code was old: sql only up to 013.

See [[real-pi-deployment]], [[aruba-lab-switch]], [[image-installer-plan]].

**2026-10-16 update done:** lab fixed the switch so 192.168.20.1 became the real lab router (MAC 44:c2:0c:aa:38:d1) → internet + NTP OK. Ran `install.sh --stage all` (same args, systemd-run, log /var/log/cafe-reinstall-all-1125.log) → success at 321b5be: all 12 units active incl. cafe-check-disk.timer, sql/017 applied, logger Restart=always, /setup = 410 (1 admin exists; stale setup.token from Oct 5 left on disk — harmless).
- install ends with a **dead-man switch: stop `cafe-wifi-nft-failsafe.timer` within 5 min** or nftables is flushed — must be done every run.
- `event_scheduler=OFF` + no events is EXPECTED here: partitions are opt-in (`--enable-partitions`), purge uses DELETE.
- nftables rate-limits new SSH from the customer side to 6/min — keep polling loops ≥ 10 s apart.
- **Clock-jump trap (2026-10-16):** after `chronyc makestep` moved the Pi +7 days, dnsmasq dropped every lease → openNDS logs `IP not allocated by dhcp [ip]` and serves the client **"Error 403 - Access Denied to this Client"**. Fix: client renews DHCP (`ipconfig /renew "Ethernet 4"`). Not a code bug; expect it after any big clock correction.
- Admin helper on Pi: `~/adm.sh login admin` (password on stdin, never argv) / `adm.sh approve RID LAST4` / `adm.sh get PATH` — curl to https://127.0.0.1:8443 with CSRF.
- **Pi test results 2026-10-16:** B2 confirmed (re-`ndsctl auth` on an online MAC = exit 1 → auth_timeout → kicked) → fixed in reconcile (deauth+auth) → re-verified on Pi. Also found + fixed: /opt/cafe-wifi files 664 root:cafewifi (git archive mode via `cp -a`) = web user could edit root-run tools. Re-test procedure for B2: open http://10.10.0.1 in 2 tabs, submit/approve one at a time (test ID 1111111111119, last4 1119).
