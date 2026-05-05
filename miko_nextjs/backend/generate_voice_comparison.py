#!/usr/bin/env python3
"""
Generate lip-sync video comparison of all female pocket-tts voices
"""

import asyncio
import aiohttp
import subprocess
import tempfile
from pathlib import Path

# Female voices
FEMALE_VOICES = [
    "alba",
    "anna", 
    "cosette",
    "eponine",
    "eve",
    "fantine",
    "jane",
    "mary",
    "azelma"
]

TEST_TEXT = "Hello, I'm Miko. How are you doing today? It's wonderful to speak with you."
POCKET_TTS_URL = "http://localhost:8800/tts"
OUTPUT_DIR = Path("/Users/sahaj/Desktop/termux/miko_nextjs/public/voice_comparison")

async def generate_voice_audio(voice: str, text: str) -> tuple[Path, float]:
    """Generate audio for a voice"""
    async with aiohttp.ClientSession() as session:
        async with session.post(
            POCKET_TTS_URL,
            data={"text": text, "voice": voice},
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"pocket-tts error: {resp.status}")
            wav_data = await resp.read()

    # Save WAV
    audio_path = OUTPUT_DIR / f"{voice}.wav"
    with open(audio_path, "wb") as f:
        f.write(wav_data)

    # Get duration
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
        capture_output=True, text=True,
    )
    duration = float(result.stdout.strip())
    
    return audio_path, duration

def create_comparison_video():
    """Create a video showing all voices with labels"""
    
    # Create a text file for ffmpeg concat
    concat_file = OUTPUT_DIR / "concat.txt"
    with open(concat_file, "w") as f:
        for voice in FEMALE_VOICES:
            audio_path = OUTPUT_DIR / f"{voice}.wav"
            if audio_path.exists():
                f.write(f"file '{voice}.mp4'\n")
    
    # Generate individual videos with labels
    for voice in FEMALE_VOICES:
        audio_path = OUTPUT_DIR / f"{voice}.wav"
        if not audio_path.exists():
            continue
            
        # Get listening video (neutral pose)
        listening = "/Users/sahaj/Desktop/termux/miko_character/listening.mp4"
        output_video = OUTPUT_DIR / f"{voice}.mp4"
        
        # Add audio to listening video with label
        label = f"Voice: {voice}"
        
        cmd = [
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", listening,
            "-i", str(audio_path),
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-b:a", "128k",
            "-shortest",
            "-vf", f"drawtext=text='{label}':fontsize=60:fontcolor=white:box=1:boxcolor=black@0.5:x=(w-text_w)/2:y=50",
            "-movflags", "+faststart",
            str(output_video)
        ]
        
        subprocess.run(cmd, capture_output=True)
        print(f"✓ {voice} video created")

async def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    print("Generating audio for all female voices...")
    
    # Generate all voice audios
    for voice in FEMALE_VOICES:
        try:
            print(f"  Generating {voice}...")
            audio_path, duration = await generate_voice_audio(voice, TEST_TEXT)
            print(f"    ✓ {voice}: {duration:.1f}s")
        except Exception as e:
            print(f"    ✗ {voice}: {e}")
    
    print("\nCreating comparison videos...")
    create_comparison_video()
    
    # Create final comparison montage
    print("\nCreating final comparison video...")
    
    # Create a 3x3 grid of videos
    videos = [v for v in FEMALE_VOICES if (OUTPUT_DIR / f"{v}.mp4").exists()]
    if len(videos) >= 4:
        cmd = ["ffmpeg", "-y"]
        for v in videos[:4]:
            cmd.extend(["-i", str(OUTPUT_DIR / f"{v}.mp4")])
        cmd.extend([
            "-filter_complex", 
            "[0:v]scale=725:1280[v0];[1:v]scale=725:1280[v1];[2:v]scale=725:1280[v2];[3:v]scale=725:1280[v3];[v0][v1]hstack[top];[v2][v3]hstack[bottom];[top][bottom]vstack[out]",
            "-map", "[out]",
            "-map", "0:a",  # Use first audio
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac",
            "-shortest",
            str(OUTPUT_DIR / "comparison_2x2.mp4")
        ])
        subprocess.run(cmd, capture_output=True)
        print(f"✓ Created 2x2 comparison: {OUTPUT_DIR}/comparison_2x2.mp4")
    
    # Create sequential video
    with open(OUTPUT_DIR / "concat.txt", "w") as f:
        for v in videos:
            f.write(f"file '{v}.mp4'\n")
    
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(OUTPUT_DIR / "concat.txt"),
        "-c", "copy",
        str(OUTPUT_DIR / "all_voices_sequential.mp4")
    ], capture_output=True)
    print(f"✓ Created sequential: {OUTPUT_DIR}/all_voices_sequential.mp4")
    
    print(f"\nDone! Videos saved to: {OUTPUT_DIR}")

if __name__ == "__main__":
    asyncio.run(main())
