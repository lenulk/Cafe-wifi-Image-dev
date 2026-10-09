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
- `story.html` — 9:16 cinematic story, 1:53, 7 acts, letterbox band opens to full frame at 73 s. It has a Thai voiceover. Order: `story_vo.py` (edge-tts, default voice th-TH-NiwatNeural; Premwadee via `--voice`) → `story_audio.py` (scipy) → `render.py --story`. The film grain makes the file ~108 MB, so also make a crf-27 copy (~17 MB). The user wants a 16:9 version of it later (2026-10-07).
  - Credits: the user wants NO credits at all. On 2026-10-08 they said to remove both the team names and the advisor name. Don't add names back.
  - Teaser: `story_teaser.py` holds SEGS (time ranges in story.html) and remixes audio from `vo/stem-bed.wav`. Then run `render.py --teaser`. Only include ranges where voiceover lines finish completely.
  - Lesson (user feedback 2026-10-08): the first teaser was picked for 'exciting' moments and the user could not understand it. A cutdown must keep the story spine: problem → law → why existing routers fail → reveal → benefits → closing line. A montage without context is confusing. Check that the cut start doesn't carry over a subtitle or chapter label from the dropped part.
  - TTS: the only local Thai voice is Windows OneCore Pattara, and it sounds robotic. The user chose online neural edge-tts. It sometimes throws NoAudioReceived, so the script retries.

Render: `PYTHONUTF8=1 python audio.py [short|compare]` then `python render.py [--short|--compare]` (also `--stills 3 9` for PNG checks). Music/SFX are synthesized with numpy (no copyright). MP4/WAV are gitignored, so copy them by hand to the desktop machine ([[two-machine-workflow]]).

No ffmpeg/node on the laptop. ffmpeg comes from the `imageio_ffmpeg` pip package. Playwright was pip-installed and uses `channel="chrome"`, so there is no browser download.

**Trap:** Google Fonts with `display=block` load lazily, so text using a not-yet-used weight/family was invisible in rendered frames. The fix: `document.fonts.load()` every weight and seek through the whole timeline once before setting `window.READY`.

- `explain.html` (16:9) and `explain-v.html` (9:16) cover the same content with identical timing (59 s) and share `audio-explain.wav`. The user zooms through 6 levels: shop → network → inside Pi → one customer → log → national ID. If you change the timeline, change both files plus the `explain` cues in audio.py.

**User review feedback (2026-10-07):**
- When moving elements to a new layout, also retime anything drawn in sync with them. A connector line once appeared before its target block did.
- A progress dot paired with step cards must step card-by-card and arrive exactly when each card activates. One global easing looks out of sync.
- Don't leave idle time after all labels have appeared. The user found an 8 s scene too long.

Verify timing numerically with a Playwright script that seeks and reads positions; spotting it in stills is unreliable.

**Claims rule:** same as the site ([[github-pages-site]]): only test-backed numbers (49/49, ~6 min, ~7–8 s, ≥90 days, 0 secrets/12 generated at first boot). The ฿500,000 fine was deliberately left out because the current Act text is unverified. No router/competitor brands.
