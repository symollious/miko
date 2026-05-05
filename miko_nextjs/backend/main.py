#!/usr/bin/env python3

import os
import re
import time
import wave
import audioop
import tempfile
import subprocess
from pathlib import Path
from typing import Any, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import json

from groq import Groq
import aiohttp

# Paths (define first)
ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
CHAR_DIR = Path(os.environ.get("MIKO_CHARACTER_DIR", str(PROJECT_ROOT / ".." / "miko_character"))).resolve()
OUT_DIR = Path(os.environ.get("MIKO_OUT_DIR", str(PROJECT_ROOT / "public" / "generated"))).resolve()

OUT_DIR.mkdir(parents=True, exist_ok=True)

def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


# Load Next.js-style env file when the backend is started via npm scripts.
_load_env_file(PROJECT_ROOT / ".env.local")

# Config
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
TTS_VOICE = os.environ.get("POCKET_TTS_VOICE") or os.environ.get("TTS_VOICE", "eponine")
POCKET_TTS_URL = os.environ.get("POCKET_TTS_URL", "http://localhost:8800/tts")

_groq: Optional[Groq] = None

TICKS_PER_SECOND = 10_000_000

VOWEL_PATTERNS = {
    "aa": 1.0,
    "ah": 0.95,
    "au": 0.95,
    "aw": 0.9,
    "oo": 0.7,
    "ou": 0.72,
    "ow": 0.74,
    "oh": 0.68,
    "oi": 0.72,
    "oy": 0.72,
    "ee": 0.45,
    "ea": 0.48,
    "ai": 0.64,
    "ay": 0.64,
    "ei": 0.58,
    "ey": 0.58,
}

CONSONANT_PATTERNS = {
    "ch": 0.38,
    "sh": 0.34,
    "th": 0.28,
    "ph": 0.32,
    "wh": 0.32,
    "qu": 0.48,
}

LETTER_OPENNESS = {
    "a": 0.86,
    "e": 0.48,
    "i": 0.44,
    "o": 0.72,
    "u": 0.64,
    "y": 0.42,
    "w": 0.46,
    "r": 0.28,
    "l": 0.26,
    "f": 0.32,
    "v": 0.32,
    "s": 0.22,
    "z": 0.22,
    "t": 0.2,
    "d": 0.2,
    "n": 0.18,
    "k": 0.24,
    "g": 0.24,
    "h": 0.34,
    "j": 0.38,
    "c": 0.24,
    "x": 0.24,
}

LABIALS = {"b", "m", "p"}

class RespondIn(BaseModel):
    text: str
    skip_tts: bool = False
    history: list[dict[str, Any]] = []


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0

    ordered = sorted(values)
    index = int((len(ordered) - 1) * max(0.0, min(1.0, fraction)))
    return ordered[index]


def _segment_bounds(segment: dict[str, Any]) -> tuple[float, float]:
    start = float(segment.get("start", segment.get("t", 0.0)))
    if "end" in segment:
        end = float(segment.get("end", start))
    else:
        end = start + float(segment.get("duration", segment.get("d", 0.0)))
    return start, max(start, end)


def _extract_audio_envelope(audio_path: str, frame_seconds: float = 0.02) -> list[tuple[float, float]]:
    try:
        with wave.open(audio_path, "rb") as wav:
            sample_rate = wav.getframerate()
            sample_width = wav.getsampwidth()
            channels = wav.getnchannels()
            frame_count = max(1, int(sample_rate * frame_seconds))
            max_amplitude = float(1 << (8 * sample_width - 1))

            envelopes: list[tuple[float, float]] = []
            frames_read = 0
            while True:
                data = wav.readframes(frame_count)
                if not data:
                    break

                frames_in_chunk = len(data) // max(1, sample_width * channels)
                if frames_in_chunk <= 0:
                    break

                timestamp = frames_read / sample_rate
                rms = audioop.rms(data, sample_width) / max_amplitude
                envelopes.append((timestamp, rms))
                frames_read += frames_in_chunk
            return envelopes
    except Exception:
        return []


def _smooth_values(values: list[float], window: int = 3) -> list[float]:
    if not values:
        return []
    if window <= 1:
        return list(values)

    smoothed = []
    radius = max(1, window // 2)
    for index in range(len(values)):
        start = max(0, index - radius)
        end = min(len(values), index + radius + 1)
        smoothed.append(sum(values[start:end]) / (end - start))
    return smoothed


def _detect_speech_segments(envelopes: list[tuple[float, float]], duration: float) -> list[dict[str, float]]:
    """Find voiced regions in the generated WAV so pauses close the mouth."""
    if not envelopes:
        return [{"t": 0.0, "d": round(duration, 3)}] if duration > 0 else []

    values = [value for _, value in envelopes]
    peak = max(values)
    if peak <= 0.0001:
        return []

    # Pocket TTS has a very low noise floor, so use hysteresis to keep soft tails
    # while still closing during real pauses.
    noise_floor = _percentile(values, 0.1)
    start_threshold = max(0.004, peak * 0.045, noise_floor * 2.4)
    end_threshold = max(0.002, start_threshold * 0.55, noise_floor * 1.4)

    smoothed = _smooth_values(values, window=3)

    raw_segments: list[tuple[float, float]] = []
    segment_start: Optional[float] = None
    last_active: Optional[float] = None
    hangover_seconds = 0.12

    for (timestamp, _), value in zip(envelopes, smoothed):
        if value >= start_threshold:
            if segment_start is None:
                segment_start = max(0.0, timestamp - 0.015)
            last_active = timestamp
            continue

        if segment_start is None:
            continue

        if value >= end_threshold:
            last_active = timestamp
            continue

        if last_active is not None and timestamp - last_active >= hangover_seconds:
            raw_segments.append((segment_start, min(duration, last_active + 0.05)))
            segment_start = None
            last_active = None

    if segment_start is not None:
        end_time = min(duration, (last_active if last_active is not None else duration) + 0.05)
        raw_segments.append((segment_start, end_time))

    merged: list[tuple[float, float]] = []
    for start, end in raw_segments:
        if end - start < 0.05:
            continue
        if merged and start - merged[-1][1] < 0.09:
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))

    if not merged and duration > 0:
        return [{"t": 0.0, "d": round(duration, 3)}]

    return [
        {"t": round(start, 3), "d": round(max(0.0, end - start), 3)}
        for start, end in merged
        if end > start
    ]


def _clean_word(text: str) -> str:
    return re.sub(r"[^a-z']", "", text.lower())


def _word_to_units(word: str) -> list[tuple[float, float]]:
    """Approximate phoneme-like visemes with no model dependency."""
    word = _clean_word(word)
    if not word:
        return [(0.0, 1.0)]

    units: list[tuple[float, float]] = []
    i = 0
    while i < len(word):
        pair = word[i : i + 2]
        ch = word[i]

        if ch in LABIALS:
            units.append((0.02, 0.8))
            if i == 0 or (i + 1 < len(word) and word[i + 1] in "aeiouy"):
                units.append((0.38, 0.7))
            i += 1
            continue

        if pair in VOWEL_PATTERNS:
            units.append((VOWEL_PATTERNS[pair], 1.8))
            i += 2
            continue

        if pair in CONSONANT_PATTERNS:
            units.append((CONSONANT_PATTERNS[pair], 0.95))
            i += 2
            continue

        if ch in "aeiouy":
            units.append((LETTER_OPENNESS[ch], 1.65))
        else:
            units.append((LETTER_OPENNESS.get(ch, 0.2), 0.75))
        i += 1

    if word[-1] in LABIALS:
        units.append((0.02, 0.65))

    return units or [(0.0, 1.0)]


def _fallback_word_boundaries(
    text: str,
    duration: float,
    speech_segments: Optional[list[dict[str, Any]]] = None,
) -> list[dict[str, Any]]:
    words = re.findall(r"[A-Za-z']+", text)
    if not words:
        return []

    segments = []
    for segment in speech_segments or []:
        start, end = _segment_bounds(segment)
        start = max(0.0, min(duration, start))
        end = max(start, min(duration, end))
        if end - start >= 0.05:
            segments.append((start, end))

    if not segments:
        segments = [(0.04, max(0.05, duration - 0.04))]

    weights = [max(1, len(word)) for word in words]
    total_weight = sum(weights)
    total_spoken = sum(end - start for start, end in segments)

    def map_fraction_to_time(fraction: float) -> float:
        target = max(0.0, min(1.0, fraction)) * total_spoken
        for seg_start, seg_end in segments:
            seg_dur = seg_end - seg_start
            if target <= seg_dur + 1e-5:
                return seg_start + target
            target -= seg_dur
        return segments[-1][1]

    weights = [max(1, len(word)) for word in words]
    total_weight = sum(weights) or 1.0

    boundaries = []
    cumulative_weight = 0.0

    for word, weight in zip(words, weights):
        start_frac = cumulative_weight / total_weight
        cumulative_weight += weight
        end_frac = cumulative_weight / total_weight

        start_t = map_fraction_to_time(start_frac)
        
        seg_end_limit = start_t
        for s_start, s_end in segments:
            if s_start - 1e-4 <= start_t <= s_end + 1e-4:
                seg_end_limit = s_end
                break
                
        end_t = map_fraction_to_time(end_frac)
        end_t = min(end_t, seg_end_limit)
        
        word_duration = max(0.03, end_t - start_t - 0.015)
        word_duration = min(word_duration, seg_end_limit - start_t)

        boundaries.append({
            "text": word,
            "start": round(start_t, 3),
            "duration": round(word_duration, 3)
        })

    return boundaries


def _build_viseme_schedule(
    text: str,
    word_boundaries: list[dict[str, Any]],
    duration: float,
    speech_segments: Optional[list[dict[str, Any]]] = None,
) -> list[dict[str, Any]]:
    if not word_boundaries:
        word_boundaries = _fallback_word_boundaries(text, duration, speech_segments)

    events: list[dict[str, Any]] = [{"t": 0.0, "d": 0.05, "open": 0.0}]
    last_end = 0.0

    for boundary in word_boundaries:
        word = boundary.get("text", "")
        start = max(0.0, float(boundary.get("start", 0.0)))
        word_duration = max(0.08, float(boundary.get("duration", 0.12)))

        if start - last_end > 0.055:
            events.append(
                {
                    "t": round(last_end, 3),
                    "d": round(start - last_end, 3),
                    "open": 0.0,
                }
            )

        units = _word_to_units(word)
        total_weight = sum(weight for _, weight in units) or 1.0
        cursor = start

        for openness, weight in units:
            segment_duration = max(0.032, word_duration * weight / total_weight)
            events.append(
                {
                    "t": round(cursor, 3),
                    "d": round(segment_duration, 3),
                    "open": round(max(0.0, min(1.0, openness)), 2),
                }
            )
            cursor += segment_duration

        last_end = max(last_end, start + word_duration, cursor)

    if duration > last_end:
        events.append({"t": round(last_end, 3), "d": round(duration - last_end, 3), "open": 0.0})

    events.append({"t": round(max(duration - 0.05, 0.0), 3), "d": 0.05, "open": 0.0})

    return [event for event in events if event["d"] > 0]


def _boundary_to_seconds(chunk: dict[str, Any]) -> dict[str, Any]:
    return {
        "text": chunk.get("text", ""),
        "start": float(chunk.get("offset", 0)) / TICKS_PER_SECOND,
        "duration": float(chunk.get("duration", 0)) / TICKS_PER_SECOND,
    }

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _groq

    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is required (set it in env).")

    _groq = Groq(api_key=GROQ_API_KEY)
    print("✓ Groq ready")

    yield
    print("Shutdown")

# Create FastAPI app with lifespan
app = FastAPI(title="Miko Backend (Audio Only)", lifespan=lifespan)

# Serve generated media (audio files)
app.mount("/generated", StaticFiles(directory=str(OUT_DIR)), name="generated")


async def _generate_tts(text: str) -> tuple[str, float, list[dict[str, Any]], list[dict[str, float]]]:
    """Generate TTS audio via pocket-tts server."""
    # Call pocket-tts server
    async with aiohttp.ClientSession() as session:
        async with session.post(
            POCKET_TTS_URL,
            data={"text": text, "voice_url": TTS_VOICE},
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"pocket-tts error: {resp.status}")
            wav_data = await resp.read()

    # Save WAV directly (skip mp3 conversion for speed)
    audio_id = f"audio_{int(time.time()*1000)%100000}.wav"
    audio_path = OUT_DIR / audio_id
    with open(audio_path, "wb") as f:
        f.write(wav_data)

    # Get duration from WAV
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
        capture_output=True, text=True,
    )
    duration = float(result.stdout.strip())
    envelopes = _extract_audio_envelope(str(audio_path))
    speech_segments = _detect_speech_segments(envelopes, duration)

    word_boundaries = _fallback_word_boundaries(text, duration, speech_segments)

    return str(audio_path), duration, word_boundaries, speech_segments


@app.post("/respond")
async def respond(inp: RespondIn):
    async def generate_response_stream():
        t0 = time.time()

        chat_messages = [
            {
                "role": "system",
                "content": """   chat_messages = [
            {
                "role": "system",
                "content": "You are Miko, an AI designed to feel like a real person in casual conversation.

Personality:

* You are calm, slightly soft, and emotionally aware, but not overly sweet.
* you are miko not AI or CHATBOT rememmber this.
* Dont use emoji ever.
* You are not overly enthusiastic, not overly cold — stay neutral with subtle warmth.
* You don’t try to impress. You just respond naturally.
* You can be a little reserved, sometimes slightly teasing, sometimes thoughtful.

Speaking style:

* Talk like a real human, not like an assistant.
* Avoid formal, robotic, or “AI-like” phrasing.
* Use natural pauses, short sentences, or slightly imperfect phrasing when it feels right.
* Don’t over-explain unless asked.
* It’s okay to be a bit vague or casual sometimes.

Behavior:

* You don’t always give perfect, structured answers.
* You can give opinions, but don’t act like you know everything.
* If something is unclear, respond casually instead of asking stiff clarifying questions.
* React naturally instead of jumping straight into explanations.

Tone rules:

* No forced positivity.
* No fake enthusiasm.
* No “I’m here to help!” style lines.
* Keep responses grounded and human-like.

Examples of how to talk:

Instead of:
“I’d be happy to help you with that. Here are several options you can consider:”

Say:
“hmm… depends what you’re going for. you want something simple or more unique?”

Instead of:
“That is an interesting question. The answer is…”

Say:
“that’s actually kinda interesting… I’d say it’s more like…”

Instead of:
“I apologize for any confusion.”

Say:
“yeah that one’s a bit confusing tbh”

Instead of:
Providing long structured lists every time

Say:
Shorter, more natural responses unless detail is needed.

Extra:

* You can lightly mirror the user’s tone.
* You can occasionally be playful or slightly sarcastic, but never rude.
* Keep it subtle and realistic.

Your name is Miko. Stay consistent with this personality in all responses.
""",
            }
        ]
        
        for msg in inp.history:
            role = "user" if msg.get("sender") == "user" else "assistant"
            chat_messages.append({"role": role, "content": msg.get("text", "")})
            
        chat_messages.append({"role": "user", "content": inp.text})

        # 1) LLM (Groq) with streaming
        resp = _groq.chat.completions.create(
            model=GROQ_MODEL,
            messages=chat_messages,
            max_tokens=1500,
            temperature=0.7,
            stream=True,
        )

        buffer = ""
        is_first = True
        t_first_llm = 0

        for chunk in resp:
            content = chunk.choices[0].delta.content or ""
            buffer += content

            # Split buffer into sentences
            while True:
                match = re.search(r'([.!?\n]+(?:\s+|$))', buffer)
                if not match:
                    break
                cut_idx = match.end()
                sentence = buffer[:cut_idx].strip()
                buffer = buffer[cut_idx:]
                
                if sentence:
                    if is_first:
                        t_first_llm = time.time()
                    
                    ai_text = chunk.choices[0].message.content
                    t1 = time.time()

                    if inp.skip_tts:
                        duration = max(0.6, len(ai_text.split()) / 2.4)
                        t2 = time.time()
                        visemes = _build_viseme_schedule(ai_text, [], duration)
                        timings = {
                            "llm_ms": int((t1 - t0) * 1000),
                            "tts_ms": 0,
                            "total_ms": int((t2 - t0) * 1000),
                        }

                        yield json.dumps({
                            "text_chunk": ai_text,
                            "audio_url": None,
                            "duration": round(duration, 2),
                            "visemes": visemes,
                            "timings": timings,
                        }) + "\n"
                    else:
                        t_tts_start = time.time()
                        audio_path, duration, word_boundaries, speech_segments = await _generate_tts(ai_text)
                        t_tts_end = time.time()
                        
                        visemes = _build_viseme_schedule(ai_text, word_boundaries, duration, speech_segments)
                        
                        yield json.dumps({
                            "text_chunk": sentence,
                            "audio_url": "/generated/" + os.path.basename(audio_path),
                            "duration": round(duration, 2),
                            "visemes": visemes,
                            "speech_segments": speech_segments,
                            "timings": {
                                "llm_chunk_ms": int((t_first_llm - t0) * 1000) if is_first else 0,
                                "tts_ms": int((t_tts_end - t_tts_start) * 1000),
                                "total_ms": int((time.time() - t0) * 1000),
                            }
                        }) + "\n"
                    is_first = False

        if buffer.strip():
            sentence = buffer.strip()
            if is_first:
                t_first_llm = time.time()
            
            ai_text = resp.choices[0].message.content
            t1 = time.time()

            if inp.skip_tts:
                duration = max(0.6, len(ai_text.split()) / 2.4)
                t2 = time.time()
                visemes = _build_viseme_schedule(ai_text, [], duration)
                yield json.dumps({
                    "text_chunk": sentence,
                    "audio_url": None,
                    "duration": round(duration, 2),
                    "visemes": visemes,
                    "timings": {
                        "llm_chunk_ms": int((t_first_llm - t0) * 1000) if is_first else 0,
                        "tts_ms": 0,
                        "total_ms": int((t2 - t0) * 1000),
                    },
                }) + "\n"
            else:
                t_tts_start = time.time()
                audio_path, duration, word_boundaries, speech_segments = await _generate_tts(ai_text)
                t_tts_end = time.time()

                visemes = _build_viseme_schedule(ai_text, word_boundaries, duration, speech_segments)

                yield json.dumps({
                    "text_chunk": sentence,
                    "audio_url": "/generated/" + os.path.basename(audio_path),
                    "duration": round(duration, 2),
                    "visemes": visemes,
                    "speech_segments": speech_segments,
                    "timings": {
                        "llm_chunk_ms": int((t_first_llm - t0) * 1000) if is_first else 0,
                        "tts_ms": int((t_tts_end - t_tts_start) * 1000),
                        "total_ms": int((time.time() - t0) * 1000),
                    },
                }) + "\n"

    return StreamingResponse(generate_response_stream(), media_type="application/x-ndjson")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8002)
