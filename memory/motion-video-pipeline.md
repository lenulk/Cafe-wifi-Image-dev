---
name: motion-video-pipeline
description: Promo motion videos for Cafe-WiFi OS live in video/motion (branch image) — HTML+JS seek(t) scenes rendered to MP4 via Playwright(Chrome)+imageio-ffmpeg; font-preload trap
metadata:
  node_type: memory
  type: project
  originSessionId: fbeea19c-e6a2-4966-9996-4ef25adb3132
  modified: 2026-10-05T18:02:40.540Z
---

2026-10-05/06 made 3 promo videos, source on branch `image` in `video/motion/`:
- `index.html` — full 16:9, 86 s, 10 scenes (storyboard: hook → มาตรา 26 → dead end → launch → install → customer → staff → evidence → stats → CTA)
- `short.html` — 9:16, 18 s
- `compare.html` — 9:16, 28 s, ร้าน A (no system) vs ร้าน B (Cafe-WiFi OS), 5 scenarios, score x/5

Render: `PYTHONUTF8=1 python audio.py [short|compare]` then `python render.py [--short|--compare]` (also `--stills 3 9` for PNG checks). Music/SFX are synthesized with numpy (no copyright). MP4/WAV are gitignored, so copy them by hand to the desktop machine ([[two-machine-workflow]]).

No ffmpeg/node on the laptop. ffmpeg comes from the `imageio_ffmpeg` pip package. Playwright was pip-installed and uses `channel="chrome"`, so there is no browser download.

**Trap:** Google Fonts with `display=block` load lazily, so text using a not-yet-used weight/family was invisible in rendered frames. The fix: `document.fonts.load()` every weight and seek through the whole timeline once before setting `window.READY`.

**Claims rule:** same as the site ([[github-pages-site]]): only test-backed numbers (49/49, ~6 min, ~7–8 s, ≥90 days, 0 secrets/12 generated at first boot). The ฿500,000 fine was deliberately left out because the current Act text is unverified. No router/competitor brands.
