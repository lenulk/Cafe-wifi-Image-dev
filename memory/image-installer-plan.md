---
name: image-installer-plan
description: 2026-10-03 plan to ship Cafe-WiFi as a prebuilt Pi image (no CLI) — docs/image-build-plan.md + docs/install-from-image.md; not started yet
metadata:
  node_type: memory
  type: project
  originSessionId: aeeefbbc-b458-4b43-8811-383e2f9573d2
  modified: 2026-10-03T09:37:34.460Z
---

User wants an installer "like Raspberry Pi Imager but locked to our OS/services, no CLI config". Agreed design (2026-10-03), written up in `docs/image-build-plan.md` (plan, milestones M1–M8, tests IMG-01..10) and `docs/install-from-image.md` (target on-site procedure):

- Keep `install.sh` as the core; add `--stage build|firstboot|site|all` (default all = old behaviour).
- Build with pi-gen/rpi-image-gen (WSL2+Docker on the laptop); stock Raspberry Pi Imager + custom os_list.json, no own flasher yet.
- **No secrets in the image** — 12 items (DEK, pepper, SECRET_KEY, setup.token, FAS_KEY, TLS key, DB_PASS, SSH alt port, SSH host keys, machine-id, random-seed, user ras/1234) must be generated at first boot.
- Site network values come from a web setup wizard at cafewifi.local, gated by a setup code; router DHCP must stay ON until the wizard, then wizard probes that DHCP/IPv6 are off before starting dnsmasq/openNDS.
- Imager can't add custom fields → `prepare-sd.ps1` writes cafewifi.conf + setup code to bootfs.

**Why:** single-Pi plug-and-play goal ([[single-pi-single-cable-constraint]]); avoid on-site GitHub/PyPI dependency (openNDS v10.1.3 is the only thing compiled from source).
**How to apply:** start at M1 when user says go; any change to install.sh must keep `--stage all` passing lab_fulltest.sh 49/49.
