"""สร้างเสียงพากย์ของวิดีโอ story (9:16) ด้วยเสียง Neural ภาษาไทย (edge-tts)

    python story_vo.py                      # เสียงชาย Niwat (ค่าเริ่มต้น)
    python story_vo.py --voice th-TH-PremwadeeNeural
    python story_vo.py --from vo/rec        # ใช้เสียงที่อัดเอง/ดาวน์โหลดมา: vo/rec/v01.m4a, v02.wav, ...
                                            # ประโยคที่ไม่มีไฟล์ใช้ TTS แทน · บทสำหรับอ่าน: vo/บทพากย์.md

ผลลัพธ์: vo/story-*.wav (44.1 kHz mono) + vo/story-vo.js (เวลา/คำบรรยาย ให้ story.html ใช้ทำซับ)
เวลาเริ่มแต่ละประโยคตามแผน (start) จะถูกเลื่อนออกเองถ้าประโยคก่อนหน้ายาวเกิน แล้วรายงานให้เห็น
"""
import argparse, asyncio, json, subprocess, wave
from pathlib import Path

import edge_tts
import imageio_ffmpeg

HERE = Path(__file__).resolve().parent
VO = HERE / "vo"

# (id, เวลาเริ่มตามแผน, ข้อความที่ให้อ่าน, ซับที่แสดงบนจอ หรือ None = ไม่ขึ้นซับเพราะบนจอมีข้อความนั้นอยู่แล้ว)
LINES = [
    ("v01", 3.0, "ทุกวัน… มีคนนับไม่ถ้วน ต่อไวไฟฟรี ในร้านกาแฟ", "ทุกวัน… มีคนนับไม่ถ้วน ต่อ Wi-Fi ฟรีในร้านกาแฟ"),
    ("v02", 14.6, "แต่ถ้าวันหนึ่ง… มีใครใช้มันทำผิดกฎหมาย", "แต่ถ้าวันหนึ่ง… มีใครใช้มันทำผิดกฎหมาย"),
    ("v03", 19.3, "ใครต้องตอบคำถาม?", None),
    ("v04", 23.6, "กฎหมายบอกว่า… ร้านต้องเก็บข้อมูลจราจร อย่างน้อยเก้าสิบวัน และต้องระบุตัวผู้ใช้ได้",
     "กฎหมายบอกว่า… ร้านต้องเก็บข้อมูลจราจรอย่างน้อย 90 วัน และต้องระบุตัวผู้ใช้ได้"),
    ("v05", 31.0, "แต่เราเตอร์ทั่วไป… ไม่ได้ถูกสร้างมาเพื่อสิ่งนี้", "แต่เราเตอร์ทั่วไป… ไม่ได้ถูกสร้างมาเพื่อสิ่งนี้"),
    ("v06", 37.0, "โจทย์ของเรา จึงเริ่มต้นขึ้น", "โจทย์ของเรา จึงเริ่มต้นขึ้น"),
    ("v07", 40.6, "ทำให้ร้านเล็กๆ ทำถูกกฎหมายได้… ด้วยคอมพิวเตอร์ ขนาดเท่าบัตรเครดิต",
     "ทำให้ร้านเล็กๆ ทำถูกกฎหมายได้… ด้วยคอมพิวเตอร์ขนาดเท่าบัตรเครดิต"),
    ("v08", 50.4, "เราสร้าง… ทดสอบ… พัง… แล้วแก้ไข… บนฮาร์ดแวร์จริง", "เราสร้าง… ทดสอบ… พัง… แล้วแก้ไข… บนฮาร์ดแวร์จริง"),
    ("v09", 68.0, "จนทุกตัวเลข… พิสูจน์ได้", "จนทุกตัวเลข… พิสูจน์ได้"),
    ("v10", 75.6, "นี่คือ… คาเฟ่ ไวไฟ โอเอส", None),
    ("v11", 84.6, "ลูกค้า… ใช้ไวไฟฟรีได้อย่างมั่นใจ", None),
    ("v12", 89.1, "ร้าน… ทำถูกกฎหมายได้ โดยไม่ต้องเป็นผู้เชี่ยวชาญ", None),
    ("v13", 93.6, "ส่วนเลขบัตรประชาชน ถูกเข้ารหัส เก็บอยู่ในร้าน และเปิดซอร์ส ให้ทุกคนตรวจสอบได้", None),
    ("v14", 100.4, "เพราะไวไฟฟรี… ไม่ควรมีราคา ที่ต้องจ่ายทีหลัง", None),
]
GAP = 0.3
# ต้องพูดจบก่อนเวลานี้ ไม่งั้นทับจังหวะภาพสำคัญ (เสียงกระแทกมาตรา 26, ความเงียบก่อนเปิดตัว, ฉากจบ ฯลฯ)
MUST_END = {"v01": 11.0, "v02": 19.1, "v03": 23.1, "v04": 30.8, "v05": 35.8, "v06": 40.4, "v07": 49.5,
            "v08": 57.0, "v09": 71.9, "v10": 83.5, "v11": 88.9, "v12": 93.5, "v13": 100.3, "v14": 105.5}
EXTS = (".wav", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".webm", ".flac")
# เสียงอัดเอง: ตัดหัวท้ายเงียบ, ตัดเสียงลมต่ำ, ลดเสียงรบกวนเบา ๆ, คุมความดังให้เท่ากันทุกประโยค
CLEAN = ("highpass=f=80,afftdn=nf=-25,"
         "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,areverse,"
         "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.15,areverse,"
         "acompressor=threshold=-20dB:ratio=3:attack=5:release=80,loudnorm=I=-16:TP=-1.5")


async def synth(text, voice, out):
    for attempt in range(4):  # บริการตอบ NoAudioReceived เป็นครั้งคราว ลองใหม่ก็ผ่าน
        try:
            await edge_tts.Communicate(text, voice, rate="-6%", pitch="-2Hz").save(str(out))
            if out.stat().st_size > 0:
                return
        except edge_tts.exceptions.NoAudioReceived:
            pass
        await asyncio.sleep(1.5)
    raise SystemExit(f"TTS failed: {text}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", default="th-TH-NiwatNeural")
    ap.add_argument("--from", dest="src", help="โฟลเดอร์ไฟล์เสียงรายประโยค (v01.*, v02.*, ...)")
    a = ap.parse_args()
    src = (HERE / a.src) if a.src else None
    VO.mkdir(exist_ok=True)
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    out, prev_end = [], 0.0
    for vid, start, say, sub in LINES:
        mp3, wav = VO / f"story-{vid}.mp3", VO / f"story-{vid}.wav"
        rec = next((f for e in EXTS if (f := src / f"{vid}{e}").exists()), None) if src else None
        if rec:
            subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(rec), "-af", CLEAN, "-ac", "1", "-ar", "44100", str(wav)], check=True)
        else:
            asyncio.run(synth(say, a.voice, mp3))
            subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(mp3), "-ac", "1", "-ar", "44100", str(wav)], check=True)
        with wave.open(str(wav)) as w:
            dur = w.getnframes() / w.getframerate()
        real = max(start, prev_end + GAP)
        note = f"  (เลื่อน +{real - start:.2f}s)" if real > start + 1e-6 else ""
        if real + dur > MUST_END[vid]:
            note += f"  ⚠ ยาวเกิน {real + dur - MUST_END[vid]:.1f}s — ควรพูดให้จบภายใน {MUST_END[vid] - start:.1f}s"
        print(f"{vid}  {'อัดเอง' if rec else 'TTS  '}  {real:6.2f} → {real + dur:6.2f}  ({dur:4.2f}s){note}")
        out.append({"id": vid, "start": round(real, 3), "dur": round(dur, 3), "sub": sub})
        prev_end = real + dur
    (VO / "story-vo.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    (VO / "story-vo.js").write_text("window.VO = " + json.dumps(out, ensure_ascii=False) + ";\n", encoding="utf-8")
    print("voice:", a.voice, "| recordings:", src or "-")


if __name__ == "__main__":
    main()
