"""เรนเดอร์ index.html เป็น MP4 ทีละเฟรม (Chrome headless + ffmpeg จาก imageio-ffmpeg)

    python render.py                 # วิดีโอเต็ม -> cafe-wifi-os.mp4
    python render.py --stills 3 9 30 # ภาพนิ่งตามวินาที -> stills/
    python render.py --short         # ฉบับสั้น 9:16 (short.html) -> cafe-wifi-os-short.mp4
    python render.py --compare       # เปรียบเทียบ 9:16 (compare.html) -> cafe-wifi-os-compare.mp4
"""
import argparse, base64, subprocess, sys, time
from pathlib import Path

import imageio_ffmpeg
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
DUR, W, H, PAGE, AUDIO = 86, 1920, 1080, "index.html", "audio.wav"


def open_page(p):
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
    page.goto((HERE / PAGE).as_uri() + "?render=1")
    page.wait_for_function("window.READY === true", timeout=60000)
    return browser, page, page.context.new_cdp_session(page)


def shot(page, cdp, t, fmt="jpeg"):
    page.evaluate(f"seek({t})")
    opts = {"format": fmt}
    if fmt == "jpeg":
        opts["quality"] = 94
    return base64.b64decode(cdp.send("Page.captureScreenshot", opts)["data"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stills", nargs="*", type=float)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--out")
    ap.add_argument("--short", action="store_true")
    ap.add_argument("--compare", action="store_true")
    a = ap.parse_args()
    global DUR, W, H, PAGE, AUDIO
    if a.short:
        DUR, W, H, PAGE, AUDIO = 18, 1080, 1920, "short.html", "audio-short.wav"
    elif a.compare:
        DUR, W, H, PAGE, AUDIO = 28, 1080, 1920, "compare.html", "audio-compare.wav"
    a.out = a.out or {"short.html": "cafe-wifi-os-short.mp4", "compare.html": "cafe-wifi-os-compare.mp4"}.get(PAGE, "cafe-wifi-os.mp4")
    with sync_playwright() as p:
        browser, page, cdp = open_page(p)
        if a.stills is not None:
            (HERE / "stills").mkdir(exist_ok=True)
            for t in a.stills:
                (HERE / "stills" / f"{PAGE[:-5]}-t{t:05.1f}.png").write_bytes(shot(page, cdp, t, "png"))
            return
        ff = imageio_ffmpeg.get_ffmpeg_exe()
        audio = HERE / AUDIO
        cmd = [ff, "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(a.fps), "-c:v", "mjpeg", "-i", "-"]
        if audio.exists():
            cmd += ["-i", str(audio), "-c:a", "aac", "-b:a", "192k", "-shortest"]
        cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", str(HERE / a.out)]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        n = DUR * a.fps
        t0 = time.time()
        for i in range(n):
            proc.stdin.write(shot(page, cdp, i / a.fps))
            if i % 150 == 0:
                print(f"{i}/{n} frames  {time.time() - t0:.0f}s", flush=True)
        proc.stdin.close()
        proc.wait()
        browser.close()
        print("done", HERE / a.out)
        sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
