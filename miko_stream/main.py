#!/usr/bin/env python3
"""
Miko Real-Time Streaming Server v2
Groq AI + Edge-TTS + 2K Lip-Sync Pipeline
"""

import os
import sys
import asyncio
import json
import time
import tempfile
import subprocess
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from groq import Groq

# Configuration
GROQ_API_KEY = "your_groq_api_key_here"
GROQ_MODEL = "llama-3.1-8b-instant"
MIKO_DIR = "/Users/sahaj/Desktop/termux/miko_character"
FRAMES_DIR = "/Users/sahaj/Desktop/termux/miko_stream/frames_cache"
OUTPUT_DIR = "/Users/sahaj/Desktop/termux/miko_stream/static/videos"
TTS_VOICE = "en-US-AriaNeural"  # Edge-TTS voice

os.makedirs(OUTPUT_DIR, exist_ok=True)

groq_client: Optional[Groq] = None

def count_frames(state):
    d = os.path.join(FRAMES_DIR, state)
    if not os.path.exists(d):
        return 0
    return len([f for f in os.listdir(d) if f.endswith('.png')])

class FrameBuffer:
    """Pre-cached 2K video frames for instant access"""
    def __init__(self):
        self.frames = {'speaking': [], 'silent': []}
        self._load_frames()

    def _load_frames(self):
        for state in ['speaking', 'silent']:
            d = os.path.join(FRAMES_DIR, state)
            if not os.path.exists(d):
                continue
            frame_files = sorted([f for f in os.listdir(d) if f.endswith('.png')])
            for frame_file in frame_files:
                with open(os.path.join(d, frame_file), 'rb') as f:
                    self.frames[state].append(f.read())
            print(f"  ✓ {state}: {len(self.frames[state])} frames loaded")

frame_buffer: Optional[FrameBuffer] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global groq_client, frame_buffer

    print("Starting Miko Stream v2...")
    groq_client = Groq(api_key=GROQ_API_KEY)
    print("✓ Groq client initialized")

    print("Loading 2K frame buffer...")
    frame_buffer = FrameBuffer()
    print(f"✓ FrameBuffer ready")

    yield
    print("✓ Shutdown complete")

app = FastAPI(title="Miko Stream v2", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/character", StaticFiles(directory=MIKO_DIR), name="character")

@app.get("/", response_class=HTMLResponse)
async def get_index():
    with open("templates/index.html", "r") as f:
        return f.read()

async def generate_tts_edge(text: str) -> tuple[str, float]:
    """Generate TTS audio using edge-tts (fast, high quality)"""
    import edge_tts

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        audio_path = f.name

    communicate = edge_tts.Communicate(text, TTS_VOICE)
    await communicate.save(audio_path)

    result = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", audio_path
    ], capture_output=True, text=True)
    duration = float(result.stdout.strip())

    return audio_path, duration

async def generate_lip_sync_video(audio_path: str, duration: float) -> str:
    """Generate 2K lip-sync video - single play, no looping"""
    video_id = f"resp_{int(time.time()*1000)%100000}.mp4"
    video_path = os.path.join(OUTPUT_DIR, video_id)

    base_video = os.path.join(MIKO_DIR, "speaking1.mp4")
    if not os.path.exists(base_video):
        base_video = os.path.join(MIKO_DIR, "stanby.mp4")

    subprocess.run([
        "ffmpeg", "-y",
        "-stream_loop", "-1",
        "-i", base_video,
        "-i", audio_path,
        "-t", str(duration),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-vf", "scale=2560:1440,fps=30",
        "-preset", "veryfast",
        "-crf", "23",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        video_path
    ], capture_output=True)

    os.remove(audio_path)
    return f"/static/videos/{video_id}"

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            user_text = message.get("text", "")

            t0 = time.time()

            # Step 1: Groq LLM
            response = groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": "You are Miko, a helpful AI companion. Keep responses concise (1-3 sentences max). Be warm and friendly."},
                    {"role": "user", "content": user_text}
                ],
                max_tokens=150,
                temperature=0.7
            )
            ai_text = response.choices[0].message.content
            t1 = time.time()

            # Step 2: Edge-TTS
            audio_path, duration = await generate_tts_edge(ai_text)
            t2 = time.time()

            # Step 3: 2K Lip-sync video (no loop)
            video_url = await generate_lip_sync_video(audio_path, duration)
            t3 = time.time()

            timings = {
                "llm_ms": int((t1 - t0) * 1000),
                "tts_ms": int((t2 - t1) * 1000),
                "video_ms": int((t3 - t2) * 1000),
                "total_ms": int((t3 - t0) * 1000)
            }

            await websocket.send_json({
                "type": "response",
                "text": ai_text,
                "video_url": video_url,
                "duration": round(duration, 2),
                "timings": timings
            })

    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print(f"WS error: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
