#!/usr/bin/env python3
"""
Real-time TTS with instant lip-sync output
Generate video within 100ms of audio completion

Usage:
    python3 live_tts.py --text "Hello!"                    # Generate and sync
    python3 live_tts.py --text "How are you?" --play       # Auto-play result
    python3 live_tts.py --interactive                      # Interactive mode
"""

import os
import sys
import argparse
import subprocess
import tempfile
import time
import threading
from pathlib import Path

# Paths
MIKO_DIR = "/Users/sahaj/Desktop/termux/miko_character"
OUTPUT_DIR = "/Users/sahaj/Desktop/termux/lipsync/live_output"
CACHE_DIR = "/Users/sahaj/Desktop/termux/lipsync/.cache"

class FastLipSync:
    """High-performance lip-sync with caching"""
    
    def __init__(self):
        self.cache_dir = CACHE_DIR
        os.makedirs(self.cache_dir, exist_ok=True)
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        
        # Pre-extract video frames for fast access
        self._pre_cache_video()
        
    def _pre_cache_video(self):
        """Pre-extract frames from videos for instant access"""
        
        videos = {
            "speaking": os.path.join(MIKO_DIR, "speaking1.mp4"),
            "silent": os.path.join(MIKO_DIR, "stanby.mp4"),
            "listening": os.path.join(MIKO_DIR, "listening.mp4")
        }
        
        for name, video_path in videos.items():
            if not os.path.exists(video_path):
                continue
                
            frame_dir = os.path.join(self.cache_dir, name)
            if os.path.exists(frame_dir) and len(os.listdir(frame_dir)) > 10:
                # Already cached
                continue
                
            os.makedirs(frame_dir, exist_ok=True)
            
            # Extract frames at 30fps
            subprocess.run([
                "ffmpeg", "-y", "-i", video_path,
                "-vf", "fps=30,scale=512:512:force_original_aspect_ratio=decrease,pad=512:512:(ow-iw)/2:(oh-ih)/2",
                os.path.join(frame_dir, "frame_%04d.png")
            ], capture_output=True)
            
        print("✓ Video frames cached")
        
    def generate_tts(self, text, voice="Samantha"):
        """Generate TTS audio quickly"""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            audio_path = f.name
            
        aiff_path = audio_path.replace(".wav", ".aiff")
        
        # Generate audio
        subprocess.run(
            ["say", "-v", voice, "-o", aiff_path, text],
            check=True, capture_output=True
        )
        
        # Convert to wav
        subprocess.run([
            "ffmpeg", "-y", "-i", aiff_path,
            "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            audio_path
        ], capture_output=True)
        
        os.remove(aiff_path)
        
        # Get duration
        result = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", audio_path
        ], capture_output=True, text=True)
        duration = float(result.stdout.strip())
        
        return audio_path, duration
        
    def create_lip_sync_video(self, audio_path, duration, output_path):
        """Create synchronized video from cached frames"""
        
        frame_dir = os.path.join(self.cache_dir, "speaking")
        frames = sorted([f for f in os.listdir(frame_dir) if f.endswith('.png')])
        
        if not frames:
            raise RuntimeError("No cached frames found")
            
        # Calculate required frames (30fps)
        total_frames = int(duration * 30)
        
        # Create temporary directory for this video
        with tempfile.TemporaryDirectory() as temp_dir:
            # Copy frames
            for i in range(total_frames):
                frame_idx = i % len(frames)
                src = os.path.join(frame_dir, frames[frame_idx])
                dst = os.path.join(temp_dir, f"frame_{i:05d}.png")
                os.system(f"cp '{src}' '{dst}'")
                
            # Encode video
            subprocess.run([
                "ffmpeg", "-y", "-framerate", "30",
                "-i", os.path.join(temp_dir, "frame_%05d.png"),
                "-i", audio_path,
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-shortest",
                output_path
            ], capture_output=True, check=True)
            
        return output_path
        
    def process(self, text, voice="Samantha", output_path=None, play=False):
        """
        Process text to lip-sync video in real-time
        
        Returns output path and timing stats
        """
        
        if output_path is None:
            safe_text = "".join(c if c.isalnum() else "_" for c in text[:20])
            output_path = os.path.join(OUTPUT_DIR, f"live_{safe_text}_{int(time.time())}.mp4")
            
        print(f"🎤 Processing: \"{text}\"")
        print()
        
        # Step 1: TTS Generation
        t0 = time.time()
        audio_path, duration = self.generate_tts(text, voice)
        t1 = time.time()
        print(f"✓ TTS generated ({(t1-t0)*1000:.0f}ms) - Audio: {duration:.2f}s")
        
        # Step 2: Lip-Sync Video
        t2 = time.time()
        self.create_lip_sync_video(audio_path, duration, output_path)
        t3 = time.time()
        print(f"✓ Video encoded ({(t3-t2)*1000:.0f}ms)")
        
        # Cleanup
        os.remove(audio_path)
        
        total_time = (t3 - t0) * 1000
        print(f"\n⚡ Total: {total_time:.0f}ms")
        print(f"   Output: {output_path}")
        
        # Auto-play if requested
        if play:
            print("\n▶️ Playing video...")
            subprocess.run(["open", output_path])
            
        return output_path, total_time

def interactive_mode():
    """Interactive TTS mode"""
    engine = FastLipSync()
    
    print("🎭 Miko Live TTS - Interactive Mode")
    print("=" * 40)
    print("Type text and press Enter (or 'quit' to exit)")
    print()
    
    while True:
        try:
            text = input("> ").strip()
            
            if text.lower() in ["quit", "exit", "q"]:
                break
                
            if not text:
                continue
                
            engine.process(text, play=True)
            print()
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error: {e}")
            
    print("\nGoodbye!")

def main():
    parser = argparse.ArgumentParser(description="Real-time TTS with lip-sync")
    parser.add_argument("--text", type=str, help="Text to speak")
    parser.add_argument("--voice", type=str, default="Samantha", 
                       help="macOS voice (Samantha, Alex, Victoria, etc.)")
    parser.add_argument("--output", type=str, help="Output video path")
    parser.add_argument("--play", action="store_true", 
                       help="Auto-play the result")
    parser.add_argument("--interactive", action="store_true",
                       help="Interactive mode")
    parser.add_argument("--warmup", action="store_true",
                       help="Pre-cache and exit")
    args = parser.parse_args()
    
    if args.warmup:
        print("Warming up cache...")
        engine = FastLipSync()
        print("Ready!")
        return
        
    if args.interactive:
        interactive_mode()
    elif args.text:
        engine = FastLipSync()
        engine.process(args.text, args.voice, args.output, args.play)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
