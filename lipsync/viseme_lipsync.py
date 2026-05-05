#!/usr/bin/env python3
"""
Viseme Compositor — Fast Lip-Sync for Miko (Attempt 9)

Usage:
    python3 viseme_lipsync.py --text "Hello, I am Miko!"
    python3 viseme_lipsync.py --batch
    python3 viseme_lipsync.py --rebuild
"""

import os, time, wave, argparse, subprocess, tempfile
import numpy as np
from PIL import Image, ImageFilter

MIKO_DIR = "/Users/sahaj/Desktop/termux/miko_character"
OUTPUT_DIR = "/Users/sahaj/Desktop/termux/lipsync/output"
CACHE_DIR = "/Users/sahaj/Desktop/termux/lipsync/.vcache"

WORK_W, WORK_H = 544, 960
FPS = 30
NUM_STATES = 15
EMA_ALPHA = 0.35

# Mouth region at 544x960 — lower face centered on the actual lips
# Verified: lips are at rows ~280-305, centered at x~270
MOUTH_X, MOUTH_Y = 220, 272
MOUTH_W, MOUTH_H = 115, 45


class VisemeCache:
    def __init__(self, force_rebuild=False):
        os.makedirs(CACHE_DIR, exist_ok=True)
        self.speaking_video = os.path.join(MIKO_DIR, "speaking1.mp4")
        self.base_frame = None
        self.mouth_states = []
        self.mouth_rect = (MOUTH_X, MOUTH_Y, MOUTH_W, MOUTH_H)
        self.alpha_mask = None

        if force_rebuild or not self._cache_ok():
            print("⚙️  Building viseme cache...")
            t0 = time.time()
            self._build()
            self._save()
            print(f"   ✓ Built in {(time.time()-t0)*1000:.0f}ms")
        else:
            self._load()
        print(f"✓ Cache: {len(self.mouth_states)} states, rect=({MOUTH_X},{MOUTH_Y},{MOUTH_W}x{MOUTH_H})")

    def _cache_ok(self):
        return all(os.path.exists(os.path.join(CACHE_DIR, n))
                   for n in ("base.npy", "states.npy", "mask.npy"))

    def _save(self):
        np.save(os.path.join(CACHE_DIR, "base.npy"), self.base_frame)
        np.save(os.path.join(CACHE_DIR, "states.npy"), np.array(self.mouth_states))
        np.save(os.path.join(CACHE_DIR, "mask.npy"), self.alpha_mask)

    def _load(self):
        self.base_frame = np.load(os.path.join(CACHE_DIR, "base.npy"))
        self.mouth_states = list(np.load(os.path.join(CACHE_DIR, "states.npy")))
        self.alpha_mask = np.load(os.path.join(CACHE_DIR, "mask.npy"))

    def _xframe(self, ts):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            tmp = f.name
        subprocess.run(["ffmpeg", "-y", "-ss", str(ts), "-i", self.speaking_video,
                        "-vframes", "1", "-s", f"{WORK_W}x{WORK_H}", tmp],
                       capture_output=True)
        img = np.array(Image.open(tmp).convert("RGB"))
        os.remove(tmp)
        return img

    def _build(self):
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "default=noprint_wrappers=1:nokey=1", self.speaking_video],
                           capture_output=True, text=True)
        dur = float(r.stdout.strip())

        print("   Base frame...")
        self.base_frame = self._xframe(0.05)

        # Extract many candidates
        n_cand = NUM_STATES * 4
        timestamps = np.linspace(0.05, dur - 0.05, n_cand)
        print(f"   Extracting {n_cand} candidates...")
        frames = [self._xframe(ts) for ts in timestamps]

        mx, my, mw, mh = self.mouth_rect
        base_crop = self.base_frame[my:my+mh, mx:mx+mw].astype(np.float32)

        # Crop mouth from each frame, score by DIFFERENCE from closed-mouth base
        # More difference = more open mouth
        crops = []
        diffs = []
        for f in frames:
            crop = f[my:my+mh, mx:mx+mw].copy()
            crops.append(crop)
            # Pixel difference from base = how much the mouth changed
            d = np.abs(crop.astype(np.float32) - base_crop).mean()
            diffs.append(d)

        # Sort by difference ascending (0 = closed, max = wide open)
        order = np.argsort(diffs)

        # Pick evenly spaced states across the full range
        picks = np.linspace(0, len(order) - 1, NUM_STATES, dtype=int)
        self.mouth_states = [crops[order[i]] for i in picks]

        # Print diff range for debugging
        print(f"   Diff range: {diffs[order[0]]:.1f} → {diffs[order[-1]]:.1f}")

        # Alpha mask
        print("   Alpha mask...")
        self.alpha_mask = self._make_mask(mw, mh)

    def _make_mask(self, w, h):
        yy = np.linspace(-1, 1, h).reshape(-1, 1)
        xx = np.linspace(-1, 1, w).reshape(1, -1)
        dist = np.sqrt(xx**2 + yy**2)
        mask = np.clip(1.0 - dist, 0, 1) ** 1.5
        mi = Image.fromarray((mask * 255).astype(np.uint8))
        mi = mi.filter(ImageFilter.GaussianBlur(radius=10))
        return np.array(mi).astype(np.float32) / 255.0


class LipSyncGenerator:
    def __init__(self, cache: VisemeCache):
        self.c = cache
        os.makedirs(OUTPUT_DIR, exist_ok=True)

    def _analyze(self, wav_path):
        with wave.open(wav_path, "rb") as wf:
            sw, sr = wf.getsampwidth(), wf.getframerate()
            raw = wf.readframes(wf.getnframes())
            nch = wf.getnchannels()
        if sw == 2:
            s = np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0
        elif sw == 4:
            s = np.frombuffer(raw, np.int32).astype(np.float32) / 2147483648.0
        else:
            s = np.frombuffer(raw, np.uint8).astype(np.float32) / 128.0 - 1.0
        if nch > 1:
            s = s.reshape(-1, nch).mean(axis=1)
        spf = int(sr / FPS)
        nf = max(1, int(len(s) / spf))
        dur = len(s) / sr
        v = np.zeros(nf)
        for i in range(nf):
            chunk = s[i*spf:min((i+1)*spf, len(s))]
            v[i] = np.sqrt(np.mean(chunk**2)) if len(chunk) > 0 else 0
        mx = v.max()
        if mx > 0:
            v /= mx
        # EMA
        sm = np.zeros_like(v)
        sm[0] = v[0]
        for i in range(1, len(v)):
            sm[i] = EMA_ALPHA * v[i] + (1 - EMA_ALPHA) * sm[i-1]
        return sm, dur

    def _vol2idx(self, vol):
        n = len(self.c.mouth_states) - 1
        # More aggressive mapping — use the full range of states
        if vol < 0.03:
            return 0
        elif vol < 0.10:
            return max(1, int(((vol - 0.03) / 0.07) * n * 0.15))
        elif vol < 0.30:
            return int(n * 0.15 + ((vol - 0.10) / 0.20) * n * 0.35)
        elif vol < 0.60:
            return int(n * 0.50 + ((vol - 0.30) / 0.30) * n * 0.30)
        else:
            return min(n, int(n * 0.80 + min((vol - 0.60) / 0.40, 1.0) * n * 0.20))

    def _composite(self, base, idx):
        frame = base.copy()
        mx, my, mw, mh = self.c.mouth_rect
        m3 = self.c.alpha_mask[:, :, np.newaxis]
        region = frame[my:my+mh, mx:mx+mw].astype(np.float32)
        mouth = self.c.mouth_states[idx].astype(np.float32)
        frame[my:my+mh, mx:mx+mw] = (mouth * m3 + region * (1 - m3)).astype(np.uint8)
        return frame

    def generate(self, text, output_path=None, voice="Samantha", play=False):
        if output_path is None:
            safe = "".join(c if c.isalnum() else "_" for c in text[:25])
            output_path = os.path.join(OUTPUT_DIR, f"ls_{safe}_{int(time.time())}.mp4")
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        print(f'🎤 "{text}"')

        # TTS
        t0 = time.time()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav = f.name
        aiff = wav.replace(".wav", ".aiff")
        subprocess.run(["say", "-v", voice, "-o", aiff, text], check=True, capture_output=True)
        subprocess.run(["ffmpeg", "-y", "-i", aiff, "-acodec", "pcm_s16le",
                       "-ar", "16000", "-ac", "1", wav], capture_output=True)
        os.remove(aiff)
        t1 = time.time()

        vols, dur = self._analyze(wav)
        t2 = time.time()

        n = len(vols)
        proc = subprocess.Popen([
            "ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-s", f"{WORK_W}x{WORK_H}", "-r", str(FPS),
            "-i", "pipe:0", "-i", wav,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
            "-shortest", "-movflags", "+faststart", output_path
        ], stdin=subprocess.PIPE, stderr=subprocess.PIPE)

        base = self.c.base_frame
        for i in range(n):
            proc.stdin.write(self._composite(base, self._vol2idx(vols[i])).tobytes())
        proc.stdin.close()
        proc.wait()
        t3 = time.time()
        os.remove(wav)

        tts = (t1-t0)*1000; vid = (t3-t2)*1000; tot = (t3-t0)*1000
        print(f"   ⚡ TTS:{tts:.0f}ms Video:{vid:.0f}ms Total:{tot:.0f}ms")
        print(f"   📁 {output_path}")
        if play:
            subprocess.run(["open", output_path])
        return output_path, {"tts_ms": tts, "video_ms": vid, "total_ms": tot,
                             "duration": dur, "frames": n}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", type=str)
    ap.add_argument("--voice", type=str, default="Samantha")
    ap.add_argument("--output", type=str)
    ap.add_argument("--play", action="store_true")
    ap.add_argument("--batch", action="store_true")
    ap.add_argument("--rebuild", action="store_true")
    args = ap.parse_args()

    cache = VisemeCache(force_rebuild=args.rebuild)
    gen = LipSyncGenerator(cache)

    if args.batch:
        demos = [
            "Hello, I am Miko! Nice to meet you.",
            "The weather is beautiful today, isn't it?",
            "I love technology and artificial intelligence.",
            "Can you help me with something important?",
            "Wow, that's really amazing! Tell me more about it.",
        ]
        results = []
        for i, t in enumerate(demos):
            print(f"\n{'='*50}\n[{i+1}/{len(demos)}]")
            p, s = gen.generate(t, voice=args.voice)
            results.append((t, p, s))
        print(f"\n{'='*50}\n📊 {len(results)} videos")
        avg_v = sum(r[2]['video_ms'] for r in results) / len(results)
        avg_t = sum(r[2]['total_ms'] for r in results) / len(results)
        print(f"   Avg video: {avg_v:.0f}ms | Avg total: {avg_t:.0f}ms")
        for _, p, _ in results:
            print(f"   • {p}")
    elif args.text:
        gen.generate(args.text, args.output, args.voice, args.play)
    else:
        print("\n🎭 Interactive (type 'q' to quit)\n")
        while True:
            try:
                t = input("> ").strip()
                if t.lower() in ("q", "quit", "exit"): break
                if t: gen.generate(t, voice=args.voice, play=True); print()
            except (KeyboardInterrupt, EOFError): break
        print("Bye!")

if __name__ == "__main__":
    main()
