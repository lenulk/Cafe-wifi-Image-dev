"""teaser 9:16 ตัดจากวิดีโอ story -- เลือกช่วงที่ประโยคพากย์จบครบ แล้วมิกซ์เสียงใหม่ให้รอยต่อเนียน

    python story_teaser.py            # -> audio-teaser.wav (ต้องรัน story_vo.py + story_audio.py ก่อน)
    python render.py --teaser         # ภาพ: seek story.html ตามช่วงใน SEGS -> cafe-wifi-os-teaser.mp4
"""
import json, wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SR = 44100

# (เริ่ม, จบ) เป็นเวลาใน story.html
SEGS = [
    (2.5, 9.8),      # ปัญหา: ทุกวันมีคนต่อ Wi-Fi ฟรี                                  (v01)
    (14.4, 30.4),    # ถ้ามีใครทำผิด… ใครต้องตอบ? → มาตรา 26 · 90 วัน · ระบุตัวผู้ใช้  (v02, v03, v04)
    (30.8, 34.9),    # แต่เราเตอร์ทั่วไปทำไม่ได้                                       (v05)
    (72.0, 78.6),    # เงียบ → แถบเปิดเต็มจอ → "นี่คือ Cafe-WiFi OS" + บรรทัดอธิบาย     (v10)
    (84.3, 104.5),   # ประโยชน์: ลูกค้า · ร้าน · ข้อมูล → "Wi-Fi ฟรี ไม่ควรมีราคา…"    (v11–v14)
    (106.3, 110.4),  # โลโก้ + URL
]
DUR = sum(b - a for a, b in SEGS)


def src_time(t):
    """เวลาใน teaser -> เวลาใน story.html"""
    for a, b in SEGS:
        if t < b - a:
            return a + t
        t -= b - a
    return SEGS[-1][1] - 1e-3


def read(p):
    with wave.open(str(p)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float64) / 32768


def lp1(x, fc):
    a = np.exp(-2 * np.pi * fc / SR)
    y = np.empty_like(x); acc = 0.0
    for i in range(len(x)):
        acc = (1 - a) * x[i] + a * acc; y[i] = acc
    return y


def main():
    bed_src = read(HERE / "vo" / "stem-bed.wav")
    vo = json.loads((HERE / "vo" / "story-vo.json").read_text(encoding="utf-8"))
    n = int(DUR * SR)
    bed, voice, active = np.zeros(n), np.zeros(n), np.zeros(n)
    xf = int(0.03 * SR)
    pos = 0.0
    for a, b in SEGS:
        seg = bed_src[int(a * SR):int(b * SR)].copy()
        seg[:xf] *= np.linspace(0, 1, xf); seg[-xf:] *= np.linspace(1, 0, xf)   # กันเสียงแตกตรงรอยตัด
        i = int(pos * SR)
        bed[i:i + len(seg)] += seg[: n - i]
        for v in vo:                                   # ใส่เฉพาะประโยคที่อยู่ในช่วงนี้ครบทั้งประโยค
            if v["start"] >= a and v["start"] + v["dur"] <= b + 0.05:
                x = read(HERE / "vo" / f"story-{v['id']}.wav")
                j = int((pos + v["start"] - a) * SR)
                voice[j:j + len(x)] += x[: n - j]
                active[max(0, j - int(.15 * SR)):j + len(x) + int(.1 * SR)] = 1
        if pos > 0:                                    # รอยต่อ: เสียงวูบสั้น ๆ ช่วยให้การตัดฟังตั้งใจ
            k = int(0.35 * SR); t = np.arange(k) / SR
            sw = np.random.default_rng(int(pos * 10)).normal(0, 1, k) * np.sin(np.pi * t / 0.35) ** 2
            j = max(0, i - k // 2)
            bed[j:j + k] += lp1(sw, 2500)[: n - j] * 0.12
        pos += b - a
    duck = 1 - 0.5 * lp1(active, 6)
    voice /= np.max(np.abs(voice)) / 0.85
    mix = bed * duck + voice
    tt = np.arange(n) / SR
    mix *= np.minimum(1, tt / 0.25) * np.minimum(1, (DUR - tt) / 0.9)
    mix = np.tanh(mix * 1.1) / np.tanh(1.1)
    mix /= np.max(np.abs(mix)) / 0.95
    with wave.open(str(HERE / "audio-teaser.wav"), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((mix * 32767).astype(np.int16).tobytes())
    used = [v["id"] for v in vo if any(v["start"] >= a and v["start"] + v["dur"] <= b + .05 for a, b in SEGS)]
    print(f"audio-teaser.wav  {DUR:.1f}s  เสียงพากย์: {', '.join(used)}")


if __name__ == "__main__":
    main()
