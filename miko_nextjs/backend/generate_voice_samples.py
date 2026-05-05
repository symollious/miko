#!/usr/bin/env python3
"""
Generate fresh voice samples for comparison
Each voice says their own name to prove they're different
"""

import asyncio
import aiohttp
from pathlib import Path

FEMALE_VOICES = ["alba", "anna", "cosette", "eponine", "eve", "fantine", "jane", "mary", "azelma"]
MALE_VOICES = ["jean", "george", "charles", "paul"]

POCKET_TTS_URL = "http://localhost:8800/tts"
OUTPUT_DIR = Path("/Users/sahaj/Desktop/termux/miko_nextjs/public/voice_samples")

async def generate_sample(voice: str, text: str) -> bool:
    """Generate a single voice sample"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                POCKET_TTS_URL,
                data={"text": text, "voice": voice},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    print(f"  ✗ {voice}: HTTP {resp.status}")
                    return False
                
                wav_data = await resp.read()
                output_path = OUTPUT_DIR / f"{voice}.wav"
                with open(output_path, "wb") as f:
                    f.write(wav_data)
                
                size_kb = len(wav_data) / 1024
                print(f"  ✓ {voice}: {size_kb:.1f}KB")
                return True
    except Exception as e:
        print(f"  ✗ {voice}: {e}")
        return False

async def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    print("\n=== GENERATING FEMALE VOICE SAMPLES ===")
    print("Each voice says their own name:\n")
    
    for voice in FEMALE_VOICES:
        text = f"Hello, my name is {voice}. I am a female voice."
        await generate_sample(voice, text)
        await asyncio.sleep(0.5)  # Small delay between requests
    
    print("\n=== GENERATING MALE VOICE SAMPLES ===")
    for voice in MALE_VOICES:
        text = f"Hello, my name is {voice}. I am a male voice."
        await generate_sample(voice, text)
        await asyncio.sleep(0.5)
    
    print(f"\n=== DONE ===")
    print(f"Samples saved to: {OUTPUT_DIR}")
    print(f"\nTest them:")
    for v in FEMALE_VOICES[:3]:
        print(f"  afplay {OUTPUT_DIR}/{v}.wav")

if __name__ == "__main__":
    asyncio.run(main())
