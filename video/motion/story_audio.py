"""เพลงประกอบแนว cinematic + เสียงเอฟเฟกต์ + เสียงพากย์ ของวิดีโอ story.html -> audio-story.wav

ต้องรัน story_vo.py ก่อน (ใช้ vo/story-*.wav และ vo/story-vo.json)
เวลาเหตุการณ์ทั้งหมดตรงกับ story.html — ถ้าแก้จังหวะภาพ ให้แก้ตัวเลขในไฟล์นี้ด้วย
"""
import json, wave
from pathlib import Path

import numpy as np
from scipy.signal import butter, lfilter

HERE = Path(__file__).resolve().parent
SR, DUR = 44100, 113.0
N = int(SR * DUR)
rng = np.random.default_rng(11)
music = np.zeros(N)
sfx = np.zeros(N)


def tt(d):
    return np.arange(int(d * SR)) / SR


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def put(buf, sig, at, gain=1.0):
    i = int(at * SR)
    if i >= N or i + len(sig) <= 0:
        return
    if i < 0:
        sig, i = sig[-i:], 0
    sig = sig[: N - i]
    buf[i : i + len(sig)] += sig * gain


def lp(x, fc, order=2):
    b, a = butter(order, fc / (SR / 2), "low")
    return lfilter(b, a, x)


def hp(x, fc, order=2):
    b, a = butter(order, fc / (SR / 2), "high")
    return lfilter(b, a, x)


def env(n, a, r):
    t = np.arange(n) / SR
    d = n / SR
    return np.minimum(1, t / max(a, 1e-3)) * np.minimum(1, np.maximum(0, (d - t) / max(r, 1e-3)))


# ---------- เครื่องดนตรี ----------
def pad(notes, d, a=1.5, r=1.5, bright=0.2):
    t = tt(d)
    s = np.zeros_like(t)
    for m in notes:
        f = hz(m)
        s += np.sin(2 * np.pi * f * t) + 0.6 * np.sin(2 * np.pi * f * 1.005 * t + 1) + bright * np.sin(4 * np.pi * f * t)
    return s * env(len(t), a, r) / len(notes)


def drone(f, d, a=2.0, r=2.0):
    t = tt(d)
    lfo = 0.75 + 0.25 * np.sin(2 * np.pi * 0.13 * t)
    s = np.sin(2 * np.pi * f * t) + 0.5 * np.sin(2 * np.pi * 2 * f * t + .3) + 0.25 * np.sin(2 * np.pi * 3.01 * f * t)
    return s * lfo * env(len(t), a, r)


def pluck(m, d=1.6, decay=3.0):
    t = tt(d)
    f = hz(m)
    s = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(4 * np.pi * f * t) + 0.12 * np.sin(6 * np.pi * f * t)
    return s * np.exp(-t * decay) * np.minimum(1, t / 0.004)


def thump(f0=60, d=0.45, decay=9):
    t = tt(d)
    f = f0 * (1 + 1.5 * np.exp(-t * 40))
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * decay)


def boom(d=3.0, f0=48):
    t = tt(d)
    f = f0 * np.exp(-t * 0.6) + 22
    sub = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 1.3)
    nz = lp(rng.normal(0, 1, len(t)), 900) * np.exp(-t * 3.5) * 0.9
    return sub + nz


def riser(d, f0=180, f1=2200):
    t = tt(d)
    k = t / d
    f = f0 * (f1 / f0) ** (k ** 2)
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.3
    nz = hp(rng.normal(0, 1, len(t)), 1500) * 0.5
    return (tone + nz) * k ** 2.2


def whoosh(d=0.8, fc=1800):
    t = tt(d)
    return lp(rng.normal(0, 1, len(t)), fc) * np.sin(np.pi * t / d) ** 2


def hit(d=1.2):
    return thump(70, d, 5) * 0.9 + lp(rng.normal(0, 1, int(d * SR)), 3000) * np.exp(-tt(d) * 14) * 0.6


def tick(f=2600, d=0.05):
    t = tt(d)
    return np.sin(2 * np.pi * f * t) * np.exp(-t * 90)


def glitch_burst(d=0.12):
    t = tt(d)
    n = rng.normal(0, 1, len(t))
    step = rng.integers(20, 120)
    n = np.repeat(n[::step], step)[: len(t)]          # bitcrush
    sq = np.sign(np.sin(2 * np.pi * rng.uniform(200, 900) * t))
    return (n * 0.6 + sq * 0.4) * env(len(t), .003, .02)


def chime(m=84, d=2.5):
    return pluck(m, d, 2.2) + 0.5 * pluck(m + 7, d, 2.6)


def powerdown(d=1.1):
    t = tt(d)
    f = 420 * np.exp(-t * 2.6) + 40
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * env(len(t), .01, .3) * 0.6


def snare(d=0.25):
    t = tt(d)
    return hp(rng.normal(0, 1, len(t)), 1200) * np.exp(-t * 18) * 0.7 + np.sin(2 * np.pi * 190 * t) * np.exp(-t * 25) * 0.4


def hat(d=0.06):
    t = tt(d)
    return hp(rng.normal(0, 1, len(t)), 6000) * np.exp(-t * 70)


# ---------- องก์ 1 (0–14): หัวใจเต้น + เครือข่ายเกิด ----------
for base in (0.0, 1.2, 2.4):
    for off, g in ((0.1, 1.0), (0.38, 0.7)):
        at = base + off
        if 0.4 <= at <= 3.4:
            put(music, thump(52, 0.5, 8), at, 0.55 * g)
put(music, drone(55, 14.5, 2.5, 2.5), 0.0, 0.10)
put(music, pad([57, 64, 67, 71, 72], 11.5, 3.0, 2.5, 0.15), 2.6, 0.22)       # Am9
for k in range(18):                                                         # ประกายตอนจุดเชื่อมกัน
    put(music, pluck([81, 84, 88, 91, 93][k % 5], 1.2, 4), 2.8 + k * 0.32 + rng.uniform(-.04, .04), 0.05)
put(sfx, riser(2.6, 120, 1400), 11.6, 0.35)
put(sfx, whoosh(1.1, 2500), 13.3, 0.4)

# ---------- องก์ 2 (14–36): ความตึงเครียด ----------
put(music, drone(41.2, 9.5, 2, 1), 14.0, 0.14)                              # E1
put(music, pad([52, 53, 59], 9.0, 2.5, 0.6, 0.35), 14.2, 0.12)                # คลัสเตอร์ตึง
for k in range(40):                                                         # สายข้อมูลวิ่งออก
    put(sfx, tick(rng.uniform(1800, 4200), 0.04), 14.4 + k * 0.11, 0.05)
for at in np.arange(16.8, 19.0, 0.17):
    if rng.random() < 0.7:
        put(sfx, glitch_burst(rng.uniform(.05, .14)), at, 0.18)
for at in np.arange(19.3, 23.1, 0.21):
    if rng.random() < 0.45 + 0.4 * (at > 22.3):
        put(sfx, glitch_burst(rng.uniform(.04, .1)), at, 0.16)
put(sfx, riser(1.6, 100, 900), 21.6, 0.3)
put(sfx, boom(4.0, 50), 23.2, 1.0)                                          # มาตรา 26
put(music, drone(36.7, 7.5, 0.05, 2.5), 23.2, 0.16)
for k in range(15):
    put(sfx, tick(2200, .04), 25.7 + k * 0.1, 0.12)                           # ตัวนับ 90
put(sfx, hit(0.8), 28.0, 0.35)
put(sfx, whoosh(0.9, 1200), 30.3, 0.3)
put(music, pad([45, 52, 55], 6.0, 1.0, 2.0, 0.1), 30.4, 0.14)
put(sfx, powerdown(1.4), 34.2, 0.5)

# ---------- องก์ 3 (36–50): โจทย์ / พิมพ์เขียว ----------
put(music, pad([57, 60, 64, 67], 14.5, 1.5, 0.3, 0.2), 36.0, 0.16)
prog = [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]]
at, k = 36.4, 0
while at < 49.9:
    ch = prog[int((at - 36.4) // 2.4) % 4]
    step = 0.3 if at < 44 else 0.15
    put(music, pluck(ch[k % 3] + 12 + 12 * (k % 6 >= 3), 0.9, 4.5), at, 0.07 + 0.05 * (at > 44))
    at += step
    k += 1
for k in range(16):
    put(sfx, tick(rng.uniform(3000, 5000), .03), 38.2 + k * 0.15, 0.05)        # เส้นถูกวาด
for i in range(4):
    put(sfx, hit(0.4), 42.6 + i * 0.35, 0.18)                               # ชิ้นส่วนประกอบ
put(sfx, chime(84, 2.5), 45.0, 0.12)
put(sfx, riser(3.0, 150, 2600), 47.0, 0.55)
put(sfx, boom(2.0, 60), 50.0, 0.7)

# ---------- องก์ 4 (50–72): มอนทาจ 120 BPM ----------
roots = [45, 41, 48, 43]
for b in range(int((68.4 - 50.5) / 0.5)):
    at = 50.5 + b * 0.5
    put(music, thump(58, 0.4, 10), at, 0.45)
    if b % 2 == 1:
        put(music, snare(), at, 0.22)
    for h in (0, 0.25):
        put(music, hat(), at + h, 0.06)
    if b % 4 == 0:
        r = roots[(b // 4) % 4]
        t = tt(2.0)
        put(music, (np.sign(np.sin(2 * np.pi * hz(r - 12) * t)) * 0.3 + np.sin(2 * np.pi * hz(r - 12) * t)) * np.exp(-t * 1.2), at, 0.13)
for at in (50.8, 51.5, 52.2, 52.9):
    put(sfx, hit(0.6), at, 0.4)
put(sfx, glitch_burst(0.3), 52.2, 0.3)
for at in (53.8, 56.3, 58.8, 61.3, 63.8, 66.3):
    put(sfx, whoosh(0.5, 3000), at - 0.35, 0.25)
    put(sfx, hit(0.9), at, 0.45)
for k in range(13):
    put(sfx, tick(1900, .04), 53.9 + k * 0.17, 0.08)                          # บรรทัด terminal
put(sfx, boom(1.4, 70), 67.0, 0.45)                                         # ตราประทับ แก้ได้
put(music, pad([57, 64, 69, 72], 3.6, 0.3, 0.4, 0.3), 68.4, 0.14)
put(sfx, riser(3.4, 200, 3200), 68.4, 0.6)
for base in (72.0, 72.0 + 1.2):                                             # เงียบ… เหลือแต่หัวใจ
    for off, g in ((0.1, 1.0), (0.38, 0.7)):
        if base + off < 73.0:
            put(sfx, thump(50, 0.45, 9), base + off, 0.5 * g)

# ---------- องก์ 5 (73–84): เปิดตัว ----------
put(sfx, boom(5.0, 44), 73.0, 1.0)
put(sfx, whoosh(1.4, 4000), 72.9, 0.3)
put(music, pad([48, 55, 60, 64, 67, 72], 11.5, 0.05, 3.0, 0.35), 73.0, 0.32)  # C major กว้าง
for k in range(26):
    put(music, pluck([72, 76, 79, 84, 88][k % 5], 1.5, 3.5), 74.6 + k * 0.33, 0.05)
for i, at in enumerate((77.9, 78.3, 78.8)):
    put(sfx, whoosh(0.7, 2500), at, 0.18)

# ---------- องก์ 6 (84–100): ความสำคัญ ----------
warm = [[53, 57, 60, 64], [48, 52, 55, 59], [55, 59, 62, 65], [57, 60, 64, 67]]   # Fmaj7 Cmaj7 G7 Am7
for i in range(4):
    put(music, pad(warm[i], 4.6, 1.0, 1.2, 0.2), 84.0 + i * 4.0, 0.22)
    for k in range(8):
        put(music, pluck(warm[i][k % 4] + 12, 1.4, 3.2), 84.2 + i * 4.0 + k * 0.5, 0.045)

vo = json.loads((HERE / "vo" / "story-vo.json").read_text(encoding="utf-8"))
starts = {v["id"]: v["start"] for v in vo}
for vid in ("v11", "v12", "v13"):
    put(sfx, chime(88, 2.0), starts[vid] - 0.3, 0.1)

# ---------- องก์ 7 (100–113): ปิดท้าย ----------
put(music, pad([45, 52, 57, 60], 6.5, 1.5, 2.0, 0.1), 100.0, 0.16)
for k, m in enumerate((69, 72, 76, 74, 72)):
    put(music, pluck(m, 2.5, 1.8), starts["v14"] + k * 1.0, 0.09)
put(music, pad([48, 55, 62, 64, 71], 7.0, 0.3, 4.0, 0.25), 106.4, 0.28)         # Cmaj9
put(music, chime(84, 4.0), 106.5, 0.12)
put(music, pluck(96, 3.0, 1.5), 108.2, 0.04)

# ---------- เสียงพากย์ + ducking ----------
voice = np.zeros(N)
for v in vo:
    with wave.open(str(HERE / "vo" / f"story-{v['id']}.wav")) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float64) / 32768
    put(voice, x, v["start"], 1.0)
active = np.zeros(N)
for v in vo:
    a, b = int((v["start"] - 0.15) * SR), int((v["start"] + v["dur"] + 0.1) * SR)
    active[max(0, a):min(N, b)] = 1
duck = 1 - 0.5 * lp(active, 6, 1)

bed = lp(music, 7000) + sfx
bed /= np.max(np.abs(bed)) / 0.6
with wave.open(str(HERE / "vo" / "stem-bed.wav"), "wb") as w:      # เพลง+เอฟเฟกต์ (ไม่มีเสียงพากย์) ให้ story_teaser.py ใช้
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((np.clip(bed, -1, 1) * 32767).astype(np.int16).tobytes())
voice /= np.max(np.abs(voice)) / 0.85
voice = hp(voice, 90)
mix = bed * duck + voice
fade = np.minimum(1, np.arange(N) / (SR * 0.3)) * np.minimum(1, (N - np.arange(N)) / (SR * 1.5))
mix = np.tanh(mix * fade * 1.1) / np.tanh(1.1)
mix /= np.max(np.abs(mix)) / 0.95
pcm = (mix * 32767).astype(np.int16)
out = HERE / "audio-story.wav"
with wave.open(str(out), "wb") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(pcm.tobytes())
print("wrote", out)
