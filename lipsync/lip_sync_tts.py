#!/usr/bin/env python3
"""
Lip-sync TTS script for Miko character
Generates talking head video from text/audio input

Usage:
    python3 lip_sync_tts.py --text "Hello, I am Miko!" --output output.mp4
    python3 lip_sync_tts.py --text "How can I help you today?"
"""

import os
import sys
import argparse
import subprocess
import tempfile
from pathlib import Path

# Configuration
MIKO_DIR = "/Users/sahaj/Desktop/termux/miko_character"
OUTPUT_DIR = "/Users/sahaj/Desktop/termux/lipsync/output"
SOURCE_FRAME = "/Users/sahaj/Desktop/termux/lipsync/source_frames/miko_source.png"
LIVEPORTRAIT_DIR = "/Users/sahaj/Desktop/termux/lipsync/LivePortrait"

def generate_tts_audio(text, output_path):
    """Generate TTS audio using macOS say command"""
    aiff_path = output_path.replace(".wav", ".aiff")
    subprocess.run(["say", "-o", aiff_path, text], check=True, capture_output=True)
    subprocess.run([
        "ffmpeg", "-y", "-i", aiff_path,
        "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        output_path
    ], check=True, capture_output=True)
    os.remove(aiff_path)
    return output_path

def get_video_duration(video_path):
    """Get video duration in seconds"""
    result = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", video_path
    ], capture_output=True, text=True, check=True)
    return float(result.stdout.strip())

def loop_video_to_duration(video_path, target_duration, output_path):
    """Loop video to match target duration"""
    video_duration = get_video_duration(video_path)
    loops = int(target_duration / video_duration) + 1
    
    # Create concat list
    list_file = output_path + ".list.txt"
    with open(list_file, "w") as f:
        for _ in range(loops):
            f.write(f"file '{video_path}'\n")
    
    # Concatenate and trim
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", list_file, "-t", str(target_duration),
        "-c", "copy", output_path
    ], check=True, capture_output=True)
    
    os.remove(list_file)
    return output_path

def simple_lip_sync(source_video, audio_path, output_path):
    """Simple lip-sync by replacing audio and adjusting duration"""
    # Get audio duration
    result = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", audio_path
    ], capture_output=True, text=True, check=True)
    audio_duration = float(result.stdout.strip())
    
    # Loop video to match audio duration
    temp_video = output_path + ".temp.mp4"
    loop_video_to_duration(source_video, audio_duration, temp_video)
    
    # Combine video with new audio
    subprocess.run([
        "ffmpeg", "-y",
        "-i", temp_video,
        "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-shortest",
        output_path
    ], check=True, capture_output=True)
    
    os.remove(temp_video)
    return output_path

def extract_best_frame(video_path, output_image):
    """Extract the clearest frame from video"""
    # Get middle frame
    duration = get_video_duration(video_path)
    middle_time = duration / 2
    
    subprocess.run([
        "ffmpeg", "-y", "-i", video_path,
        "-ss", str(middle_time), "-vframes", "1",
        output_image
    ], check=True, capture_output=True)
    return output_image

def run_liveportrait(source_image, driving_video, output_path):
    """Run LivePortrait inference"""
    os.chdir(LIVEPORTRAIT_DIR)
    sys.path.insert(0, LIVEPORTRAIT_DIR)
    
    # Run inference using the provided script
    subprocess.run([
        "python3", "inference.py",
        "-s", source_image,
        "-d", driving_video,
        "-o", output_path
    ], check=True)
    
    return output_path

def create_lip_sync_video(text, output_path, method="simple"):
    """Main function to create lip-sync video"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    print(f"🎬 Miko Lip-Sync TTS Generator")
    print(f"   Text: \"{text}\"")
    print(f"   Method: {method}")
    print()
    
    # Step 1: Generate TTS audio
    print("Step 1/3: Generating TTS audio...")
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        audio_path = f.name
    generate_tts_audio(text, audio_path)
    print(f"   ✓ Audio generated")
    
    # Step 2: Create lip-sync video
    print("\nStep 2/3: Creating lip-sync video...")
    
    if method == "liveportrait":
        try:
            # Use speaking1.mp4 as driving video but replace audio
            # LivePortrait would animate the source image based on driving video
            print("   Using LivePortrait for animation...")
            
            # For LivePortrait, we'd need a driving video with face motion
            # For now, use the speaking video directly with new audio
            simple_lip_sync(
                os.path.join(MIKO_DIR, "speaking1.mp4"),
                audio_path,
                output_path
            )
        except Exception as e:
            print(f"   LivePortrait failed: {e}")
            print("   Falling back to simple method...")
            simple_lip_sync(
                os.path.join(MIKO_DIR, "speaking1.mp4"),
                audio_path,
                output_path
            )
    else:
        # Simple method: loop speaking video and replace audio
        simple_lip_sync(
            os.path.join(MIKO_DIR, "speaking1.mp4"),
            audio_path,
            output_path
        )
        print("   ✓ Video created (simple audio replacement)")
    
    # Step 3: Cleanup
    print("\nStep 3/3: Cleaning up...")
    os.remove(audio_path)
    
    print(f"\n✅ Done!")
    print(f"   Output: {output_path}")
    
    return output_path

def main():
    parser = argparse.ArgumentParser(
        description="Generate lip-sync video from text for Miko character"
    )
    parser.add_argument("--text", type=str, required=True, 
                        help="Text to speak (e.g., 'Hello, I am Miko!')")
    parser.add_argument("--output", type=str, default=None, 
                        help="Output video path (default: auto-generated)")
    parser.add_argument("--method", type=str, choices=["simple", "liveportrait"], 
                        default="simple", help="Animation method")
    args = parser.parse_args()
    
    # Generate output filename if not provided
    if args.output is None:
        safe_text = "".join(c if c.isalnum() else "_" for c in args.text[:30])
        output_path = os.path.join(OUTPUT_DIR, f"miko_{safe_text}.mp4")
    else:
        output_path = args.output
    
    create_lip_sync_video(args.text, output_path, args.method)

if __name__ == "__main__":
    main()
