"""สังเคราะห์เพลงประกอบ lo-fi + เสียงเอฟเฟกต์ให้ตรงจังหวะฉากใน index.html -> audio.wav
ไม่ใช้ไฟล์เสียงภายนอก จึงไม่มีปัญหาลิขสิทธิ์

    python audio.py          # ฉบับเต็ม 86 วิ -> audio.wav
    python audio.py short    # ฉบับสั้น 18 วิ -> audio-short.wav
    python audio.py compare  # เปรียบเทียบ 28 วิ -> audio-compare.wav
"""
import sys
import wave
from pathlib import Path

import numpy as np

MODE = sys.argv[1] if len(sys.argv) > 1 else "full"
SHORT = MODE in ("short", "compare")  # คลิปแนวตั้ง: เพลงเริ่มทันที, เฟดท้ายสั้น
SR, DUR = 44100, {"short": 18.0, "compare": 28.0}.get(MODE, 86.0)
N = int(SR * DUR)
rng = np.random.default_rng(7)
mix = np.zeros(N)


def note(m):  # MIDI -> Hz
    return 440.0 * 2 ** ((m - 69) / 12)


def add(sig, at, gain=1.0):
    i = int(at * SR)
    if i >= N:
        return
    sig = sig[: N - i]
    mix[i : i + len(sig)] += sig * gain


def tt(d):
    return np.arange(int(d * SR)) / SR


def lowpass(x, fc):
    a = np.exp(-2 * np.pi * fc / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):  # one-pole; ยาวแต่ใช้ครั้งเดียว
        acc = (1 - a) * x[i] + a * acc
        y[i] = acc
    return y


# ---------- เพลง: 80 BPM, คอร์ดละ 1 ห้อง (3 วิ) ----------
BAR = 3.0
chords = [[48, 52, 55, 59], [45, 48, 52, 55], [41, 45, 48, 52], [43, 47, 50, 53]]  # Cmaj7 Am7 Fmaj7 G7
music = np.zeros(N)


def madd(sig, at, gain):
    i = int(at * SR)
    if i >= N:
        return
    sig = sig[: N - i]
    music[i : i + len(sig)] += sig * gain


nbars = int(DUR / BAR) + 1
for b in range(nbars):
    ch = chords[b % 4]
    t = tt(BAR + 0.8)
    env = np.minimum(1, t / 0.5) * np.minimum(1, np.maximum(0, (BAR + 0.8 - t) / 0.8))
    pad = np.zeros_like(t)
    for m in ch:
        f = note(m + 12)
        pad += np.sin(2 * np.pi * f * t) + 0.5 * np.sin(2 * np.pi * f * 1.004 * t) + 0.15 * np.sin(4 * np.pi * f * t)
    madd(pad * env, b * BAR, 0.018)
    # เบส
    for beat in (0, 2):
        tb = tt(1.4)
        f = note(ch[0] - 12)
        madd(np.sin(2 * np.pi * f * tb) * np.exp(-tb * 2.2) * np.minimum(1, tb / 0.01), b * BAR + beat * 0.75, 0.14)
    # อาร์เปจจิโอ electric piano (เริ่มหลังฮุก)
    if b * BAR >= (0 if SHORT else 6):
        seq = [0, 1, 2, 3, 2, 1, 3, 2]
        for k, s in enumerate(seq):
            if rng.random() < 0.18:
                continue
            te = tt(1.2)
            f = note(ch[s] + 24)
            ep = (np.sin(2 * np.pi * f * te) + 0.25 * np.sin(4 * np.pi * f * te)) * np.exp(-te * 3.5)
            ep *= 1 + 0.15 * np.sin(2 * np.pi * 5 * te)
            madd(ep * np.minimum(1, te / 0.004), b * BAR + k * 0.375 + rng.normal(0, 0.008), 0.05)

# กลอง: ฉาก 4 (22 วิ) ถึงก่อนจบ
beat = 0.75
DRUMS = {"short": (3.6, 17.2), "compare": (3.0, 26.5)}.get(MODE, (22, 84))
for k in range(int(DRUMS[0] / beat), int(DRUMS[1] / beat)):
    at = k * beat
    tk = tt(0.35)
    if k % 2 == 0:
        f = 110 * np.exp(-tk * 18) + 45
        madd(np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tk * 9), at, 0.32)
    else:
        nz = rng.normal(0, 1, len(tk)) * np.exp(-tk * 22)
        madd(nz, at, 0.05)
    for h in (0, 0.375):
        th = tt(0.06)
        hn = np.diff(rng.normal(0, 1, len(th) + 1)) * np.exp(-th * 70)
        madd(hn, at + h, 0.018)

# ฉุ่มฉ่ำแบบแผ่นเสียง
crack = np.zeros(N)
idx = rng.integers(0, N, 900)
crack[idx] = rng.normal(0, 1, len(idx))
music += np.convolve(crack, np.exp(-np.arange(60) / 8), "same") * 0.02
music = lowpass(music, 4200)
fade = np.minimum(1, np.arange(N) / (SR * 1.2)) * np.minimum(1, (N - np.arange(N)) / (SR * (1.0 if SHORT else 2.5)))
mix += music * fade


# ---------- เสียงเอฟเฟกต์ ----------
def pop():
    t = tt(0.18)
    f = 380 + 700 * np.minimum(1, t / 0.07)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 26)


def tick():
    t = tt(0.06)
    return np.sin(2 * np.pi * 2200 * t) * np.exp(-t * 90)


def click():
    t = tt(0.03)
    return rng.normal(0, 1, len(t)) * np.exp(-t * 200)


def thud():
    t = tt(0.6)
    f = 90 * np.exp(-t * 6) + 38
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7) + rng.normal(0, 1, len(t)) * np.exp(-t * 40) * 0.4


def buzz():
    t = tt(0.32)
    sq = np.sign(np.sin(2 * np.pi * 120 * t)) * 0.5 + np.sin(2 * np.pi * 240 * t) * 0.5
    gate = ((t < 0.13) | (t > 0.17)).astype(float)
    return lowpass(sq * gate * np.exp(-t * 4), 1800)


def whoosh():
    t = tt(0.7)
    nz = rng.normal(0, 1, len(t))
    return lowpass(nz, 2500) * np.sin(np.pi * t / 0.7) ** 2


def chime():
    out = np.zeros(int(0.9 * SR))
    for k, m in enumerate((76, 83)):
        t = tt(0.9 - k * 0.12)
        s = (np.sin(2 * np.pi * note(m) * t) + 0.3 * np.sin(4 * np.pi * note(m) * t)) * np.exp(-t * 5)
        i = int(k * 0.12 * SR)
        out[i : i + len(s)] += s
    return out


def shimmer():
    out = np.zeros(int(1.6 * SR))
    for k, m in enumerate((72, 76, 79, 83, 88)):
        t = tt(1.6 - k * 0.07)
        s = np.sin(2 * np.pi * note(m) * t) * np.exp(-t * 3)
        i = int(k * 0.07 * SR)
        out[i : i + len(s)] += s
    return out


cues = [
    (0.15, pop, .35), (1.95, whoosh, .18), (2.75, tick, .25), (2.95, tick, .25), (3.17, tick, .25), (3.39, tick, .25),
    (6.15, whoosh, .2), (7.3, thud, .55), (11.4, pop, .25),
    (16.2, pop, .3), (17.0, buzz, .22),
    (22.1, whoosh, .22), (22.3, shimmer, .16), (24.9, pop, .25), (25.0, pop, .25), (26.4, click, .3),
    (28.8, whoosh, .15), (30.0, click, .45), (30.05, tick, .3), (33.8, click, .35),
    (42.9, click, .35), (43.8, chime, .14), (43.95, pop, .2), (44.4, whoosh, .15), (46.4, tick, .3), (47.0, click, .4), (47.6, pop, .25),
    (53.9, click, .45), (54.0, chime, .16), (58.3, click, .45), (60.4, buzz, .2),
    (68.0, whoosh, .2), (69.3, thud, .5), (69.9, pop, .22),
    (72.8, pop, .25), (73.2, pop, .25), (73.6, pop, .25), (74.0, pop, .25),
    (80.25, shimmer, .2), (81.5, pop, .25),
]
for at in (37.2, 37.6, 38.0, 39.1, 39.9):
    cues.append((at, tick, .3))
cues.append((40.3, chime, .16))
for k in range(13):
    cues.append((45.1 + k * 0.085, click, .1))
for k in range(8):
    cues.append((63.4 + k * 0.5, tick, .2))
for k in range(18):
    cues.append((17.7 + k * 0.13, click, .07))
for k in range(8):
    cues.append((58.4 + k * 0.25, tick, .12))
if MODE == "compare":
    cues = [(0.1, pop, .35), (0.6, tick, .25), (0.8, tick, .25), (1.3, thud, .4), (2.7, whoosh, .25)]
    for k in range(5):
        a = 3.0 + k * 4.2
        cues += [(a, whoosh, .14), (a + 2.6, buzz, .16), (a + 2.9, chime, .17), (a + 2.95, pop, .2)]
    cues += [(3.0 + 0.5 + k * 0.05, click, .07) for k in range(13)] + [(4.25, tick, .25), (4.45, click, .35)]  # 1: กรอกบัตร
    cues += [(7.2 + 0.7 + k * 0.35, tick, .2) for k in range(4)] + [(8.6, thud, .3)]                       # 2: log / โฟลเดอร์ว่าง
    cues += [(11.4 + 1.4, click, .4), (11.4 + 1.8, pop, .25)]                                              # 3: ส่งออก
    cues += [(15.6 + 0.9, click, .4)] + [(15.6 + 1.0 + k * 0.2, tick, .12) for k in range(6)]              # 4: ปิดสิทธิ์
    cues += [(19.8 + 0.5 + k * 0.2, click, .1) for k in range(7)] + [(19.8 + 1.5, pop, .25)]               # 5: ติดตั้ง
    cues += [(24.0, whoosh, .22), (24.3, shimmer, .2), (24.5, pop, .3), (25.8, pop, .3)]
elif SHORT:
    cues = [(0.05, pop, .35), (0.35, tick, .25), (0.47, tick, .25), (0.59, tick, .25), (0.71, tick, .25), (0.55, pop, .3),
            (1.15, pop, .3), (2.0, thud, .45), (2.1, pop, .2),
            (3.6, whoosh, .2), (4.7, click, .4), (4.75, tick, .3), (6.3, click, .35), (6.3, tick, .3), (6.7, whoosh, .15), (7.6, tick, .3),
            (8.2, whoosh, .2), (9.7, tick, .3), (10.1, click, .4), (10.35, pop, .25), (10.8, whoosh, .15), (11.6, click, .45), (11.8, chime, .2),
            (13.6, whoosh, .2), (13.75, shimmer, .2), (15.0, pop, .3)]
    for k in range(13):
        cues.append((8.7 + k * 0.07, click, .1))
for at, fn, g in cues:
    add(fn(), at, g)

mix /= max(1e-9, np.max(np.abs(mix))) / 0.89
pcm = (np.clip(mix, -1, 1) * 32767).astype(np.int16)
out = Path(__file__).resolve().parent / {"short": "audio-short.wav", "compare": "audio-compare.wav"}.get(MODE, "audio.wav")
with wave.open(str(out), "wb") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(pcm.tobytes())
print("wrote", out)
