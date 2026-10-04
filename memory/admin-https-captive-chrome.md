---
name: admin-https-captive-chrome
description: "Unapproved Android Chrome can't open self-signed admin.cafe.wifi (\"Connect to Wi-Fi\", no Proceed) -- SOLVED in 1.1.0 by installing the name-constrained shop cert as a user CA (tested Android 10, 2026-10-05)"
metadata:
  node_type: memory
  type: project
  originSessionId: aeeefbbc-b458-4b43-8811-383e2f9573d2
  modified: 2026-10-04T11:03:46.473Z
---

On an Android tablet that is still **Preauthenticated** in openNDS, Chrome shows a "Connect to Wi-Fi / may require you to visit its login page" page for https://admin.cafe.wifi instead of the normal certificate warning. That page has no Proceed button. Chrome never even sends a SYN to 10.10.0.1:443; tcpdump confirmed DNS answered 10.10.0.1 and then nothing.

The Pi side is fine. A simulated netns customer gets 200, and DNS, nginx :443, nftables and openNDS `users_to_router` 443 are all correct.

Proven on 2026-10-04 with card B:
1. Approve the tablet.
2. Open admin.cafe.wifi and press Advanced → Proceed once.
3. Revoke the tablet and wait for cafe-enforce (it runs about every 5 minutes, so a revoke is not instant).
4. With the tablet back in Preauthenticated, admin.cafe.wifi **still opens**. Chrome remembers the cert-bypass decision for that host+cert.

The user's belief that "it worked before from the customer side on every device" comes from exactly this, plus earlier tests that used curl/netns rather than a real unapproved phone. A new image means a new per-device TLS key, so every staff device must accept once **while approved**.

**Why:** the user insists that the whole customer subnet must reach admin.cafe.wifi ([[admin-access-from-customer-lan]]). A self-signed cert cannot satisfy "first visit from any unapproved Chrome device".

**How to apply:** don't re-debug the Pi when this shows up. The fixes are:
- doc/wizard step: approve the staff device first, then accept the cert once
- or a cert-install link
- or HTTP on :8080
- or a real domain with a trusted certificate (user was asked; undecided)

See [[image-installer-plan]].

**SOLVED 2026-10-05 (v1.1.0):** use the cert-install link.
- Install `http://<GATEWAY_IP>:8080/cafe-wifi.crt` on the staff device as a **CA certificate**. The port is FAS 8080, which is open to unapproved devices.
- After that, https://admin.cafe.wifi opens with no warning even while the device is Preauthenticated. Verified on a real Android 10 phone using the portal-access and admin-access logs plus `ndsctl`.
- `make_tls_cert` adds `nameConstraints=critical,permitted;DNS:cafe.wifi,DNS:localhost,IP:<gw>/32` and `pathlen:0`. A leaked Pi key therefore can't impersonate other sites to staff phones.
- The status page shows the link and the SHA-256 fingerprint.
- A new install means a new cert, so staff must reinstall it.
