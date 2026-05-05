#!/usr/bin/env python3
"""
Advanced lip-sync with LivePortrait animation
Animates Miko's face based on audio-driven motion
"""

import os
import sys
import argparse
import subprocess
import tempfile
from pathlib import Path

# Paths
MIKO_DIR = "/Users/sahaj/Desktop/termux/miko_character"
OUTPUT_DIR = "/Users/sahaj/Desktop/termux/lipsync/output"
SOURCE_FRAME = "/Users/sahaj/Desktop/termux/lipsync/source_frames/miko_source.png"
LIVEPORTRAIT_DIR = "/Users/sahaj/Desktop/termux/lipsync/LivePortrait"

def generate_tts_audio(text, output_path, voice="Samantha"):
    """Generate TTS audio with specified voice"""
    aiff_path = output_path.replace(".wav", ".aiff")
    # macOS say command with voice option
    subprocess.run(
        ["say", "-v", voice, "-o", aiff_path, text],
        check=True, capture_output=True
    )
    subprocess.run([
        "ffmpeg", "-y", "-i", aiff_path,
        "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        output_path
    ], check=True, capture_output=True)
    os.remove(aiff_path)
    return output_path

def get_audio_duration(audio_path):
    """Get audio duration in seconds"""
    result = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", audio_path
    ], capture_output=True, text=True, check=True)
    return float(result.stdout.strip())

def create_driving_video(duration, output_path, fps=30):
    """Create a driving video with face motion from the speaking video"""
    speaking_video = os.path.join(MIKO_DIR, "speaking1.mp4")
    
    # Calculate how many times to loop
    speaking_duration = float(subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", speaking_video
    ], capture_output=True, text=True, check=True).stdout.strip())
    
    loops = int(duration / speaking_duration) + 1
    
    # Create concat list
    list_file = output_path + ".list.txt"
    with open(list_file, "w") as f:
        for _ in range(loops):
            f.write(f"file '{speaking_video}'\n")
    
    # Concatenate and trim to exact duration
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", list_file, "-t", str(duration),
        "-vf", "fps=30,scale=512:512:force_original_aspect_ratio=decrease,pad=512:512:(ow-iw)/2:(oh-ih)/2",
        "-pix_fmt", "yuv420p",
        "-c:v", "libx264", output_path
    ], check=True, capture_output=True)
    
    os.remove(list_file)
    return output_path

def run_liveportrait(source_image, driving_video, output_dir):
    """Run LivePortrait inference"""
    # Change to LivePortrait directory and run
    original_dir = os.getcwd()
    os.chdir(LIVEPORTRAIT_DIR)
    
    try:
        result = subprocess.run([
            "python3", "inference.py",
            "-s", source_image,
            "-d", driving_video,
            "-o", output_dir,
            "--no_save_anim",  # Don't save animation pickle
        ], capture_output=True, text=True, check=True)
        
        # Find the output video
        output_files = list(Path(output_dir).glob("*.mp4"))
        if output_files:
            return str(output_files[0])
        else:
            raise RuntimeError("LivePortrait did not generate output video")
    finally:
        os.chdir(original_dir)

def combine_video_audio(video_path, audio_path, output_path):
    """Combine video with audio"""
    subprocess.run([
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-shortest",
        output_path
    ], check=True, capture_output=True)
    return output_path

def create_animated_lip_sync(text, output_path, voice="Samantha"):
    """Create lip-sync video with LivePortrait animation"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    print(f"🎬 Miko Advanced Lip-Sync Generator")
    print(f"   Text: \"{text}\"")
    print(f"   Voice: {voice}")
    print()
    
    # Step 1: Generate TTS audio
    print("Step 1/4: Generating TTS audio...")
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        audio_path = f.name
    generate_tts_audio(text, audio_path, voice)
    audio_duration = get_audio_duration(audio_path)
    print(f"   ✓ Audio generated ({audio_duration:.1f}s)")
    
    # Step 2: Create driving video
    print("\nStep 2/4: Creating driving video...")
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        driving_video_path = f.name
    create_driving_video(audio_duration, driving_video_path)
    print(f"   ✓ Driving video created")
    
    # Step 3: Run LivePortrait
    print("\nStep 3/4: Running LivePortrait animation...")
    with tempfile.TemporaryDirectory() as temp_output_dir:
        try:
            animated_video = run_liveportrait(SOURCE_FRAME, driving_video_path, temp_output_dir)
            print(f"   ✓ Animation generated")
            
            # Step 4: Combine with audio
            print("\nStep 4/4: Combining video with TTS audio...")
            combine_video_audio(animated_video, audio_path, output_path)
            print(f"   ✓ Final video created")
        except Exception as e:
            print(f"   LivePortrait failed: {e}")
            print("   Falling back to simple method...")
            # Fallback: just use the driving video with new audio
            combine_video_audio(driving_video_path, audio_path, output_path)
    
    # Cleanup
    print("\nCleaning up...")
    os.remove(audio_path)
    os.remove(driving_video_path)
    
    print(f"\n✅ Done!")
    print(f"   Output: {output_path}")
    
    return output_path

def main():
    parser = argparse.ArgumentParser(
        description="Generate advanced lip-sync video with LivePortrait animation"
    )
    parser.add_argument("--text", type=str, required=True,
                        help="Text to speak")
    parser.add_argument("--output", type=str, default=None,
                        help="Output video path")
    parser.add_argument("--voice", type=str, default="Samantha",
                        help="macOS voice (Samantha, Alex, Victoria, etc.)")
    args = parser.parse_args()
    
    # Generate output filename if not provided
    if args.output is None:
        safe_text = "".join(c if c.isalnum() else "_" for c in args.text[:30])
        output_path = os.path.join(OUTPUT_DIR, f"miko_adv_{safe_text}.mp4")
    else:
        output_path = args.output
    
    create_animated_lip_sync(args.text, output_path, args.voice)

if __name__ == "__main__":
    main()
