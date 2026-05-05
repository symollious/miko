#!/usr/bin/env python3
"""
Real-time Live Lip-Sync System for Miko
Processes audio chunks and outputs synchronized video frames

Usage:
    python3 live_lip_sync.py --mode mic          # Use microphone input
    python3 live_lip_sync.py --mode file --input audio.wav  # Use audio file
    python3 live_lip_sync.py --stream            # Stream to virtual camera
"""

import os
import sys
import argparse
import subprocess
import tempfile
import threading
import queue
import time
import numpy as np
from pathlib import Path
from collections import deque

# Configuration
MIKO_DIR = "/Users/sahaj/Desktop/termux/miko_character"
OUTPUT_DIR = "/Users/sahaj/Desktop/termux/lipsync/live_output"
CHUNK_DURATION = 0.1  # 100ms chunks
OVERLAP = 0.02  # 20ms overlap for smooth transitions

# Video segment cache
SPEAKING_VIDEO = os.path.join(MIKO_DIR, "speaking1.mp4")
SILENT_VIDEO = os.path.join(MIKO_DIR, "stanby.mp4")
LISTENING_VIDEO = os.path.join(MIKO_DIR, "listening.mp4")

class AudioChunkProcessor:
    """Process audio chunks and determine video state"""
    
    def __init__(self, threshold_db=-30):
        self.threshold_db = threshold_db
        self.buffer = deque(maxlen=10)  # 1 second history
        self.is_speaking = False
        
    def analyze_chunk(self, audio_chunk_path):
        """Analyze audio chunk and return state"""
        # Get volume
        result = subprocess.run([
            "ffmpeg", "-i", audio_chunk_path, "-af", "volumedetect",
            "-f", "null", "-"
        ], capture_output=True, text=True)
        
        mean_volume = -100
        for line in result.stderr.split('\n'):
            if 'mean_volume' in line:
                try:
                    mean_volume = float(line.split(':')[1].split()[0])
                except:
                    pass
        
        self.buffer.append(mean_volume)
        avg_volume = np.mean(self.buffer) if self.buffer else -100
        
        # Determine state
        if mean_volume > self.threshold_db:
            self.is_speaking = True
            return "speaking"
        elif avg_volume > self.threshold_db - 10:
            # Transition state
            return "speaking" if self.is_speaking else "listening"
        else:
            self.is_speaking = False
            return "silent"

class VideoSegmentCache:
    """Cache video segments for fast access"""
    
    def __init__(self):
        self.cache_dir = tempfile.mkdtemp()
        self.segments = {}
        self._prepare_segments()
        
    def _prepare_segments(self):
        """Extract video segments at different phases"""
        videos = {
            "speaking": SPEAKING_VIDEO,
            "silent": SILENT_VIDEO,
            "listening": LISTENING_VIDEO
        }
        
        for name, video_path in videos.items():
            if not os.path.exists(video_path):
                continue
                
            # Get duration
            result = subprocess.run([
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", video_path
            ], capture_output=True, text=True)
            duration = float(result.stdout.strip())
            
            # Extract frames at 30fps
            segment_dir = os.path.join(self.cache_dir, name)
            os.makedirs(segment_dir, exist_ok=True)
            
            subprocess.run([
                "ffmpeg", "-y", "-i", video_path,
                "-vf", "fps=30,scale=512:512:force_original_aspect_ratio=decrease,pad=512:512:(ow-iw)/2:(oh-ih)/2",
                "-pix_fmt", "rgb24",
                os.path.join(segment_dir, "frame_%04d.png")
            ], capture_output=True)
            
            # Store metadata
            frames = sorted([f for f in os.listdir(segment_dir) if f.endswith('.png')])
            self.segments[name] = {
                "dir": segment_dir,
                "frames": frames,
                "duration": duration,
                "fps": 30,
                "current_frame": 0
            }
            
        print(f"✓ Cached {len(self.segments)} video segments")
        
    def get_frame(self, state, delta_time=0):
        """Get next frame for given state"""
        if state not in self.segments:
            state = "silent" if "silent" in self.segments else list(self.segments.keys())[0]
        
        segment = self.segments[state]
        
        # Advance frame based on time
        segment["current_frame"] += int(delta_time * segment["fps"])
        segment["current_frame"] %= len(segment["frames"])
        
        frame_file = segment["frames"][segment["current_frame"]]
        return os.path.join(segment["dir"], frame_file)
        
    def cleanup(self):
        """Clean up cache directory"""
        import shutil
        shutil.rmtree(self.cache_dir, ignore_errors=True)

class LiveLipSync:
    """Main live lip-sync engine"""
    
    def __init__(self, output_dir=OUTPUT_DIR):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        
        self.audio_processor = AudioChunkProcessor()
        self.video_cache = VideoSegmentCache()
        
        self.frame_queue = queue.Queue(maxsize=30)  # 1 second buffer
        self.audio_queue = queue.Queue(maxsize=10)
        
        self.running = False
        self.last_state = "silent"
        self.last_frame_time = time.time()
        
    def process_audio_chunk(self, audio_chunk_path):
        """Process single audio chunk and return video state"""
        state = self.audio_processor.analyze_chunk(audio_chunk_path)
        return state
        
    def generate_frame_sequence(self, state, num_frames=3):
        """Generate sequence of frames for given state"""
        frames = []
        for _ in range(num_frames):
            current_time = time.time()
            delta = current_time - self.last_frame_time
            self.last_frame_time = current_time
            
            frame_path = self.video_cache.get_frame(state, delta)
            frames.append(frame_path)
            
        return frames
        
    def start_microphone_stream(self):
        """Start processing from microphone"""
        import subprocess
        
        print("🎤 Starting microphone stream...")
        print("   Speak now! Press Ctrl+C to stop")
        print()
        
        # Use ffmpeg to capture from microphone in chunks
        chunk_count = 0
        
        try:
            while True:
                chunk_start = time.time()
                
                # Record 100ms chunk
                chunk_file = os.path.join(self.output_dir, f"chunk_{chunk_count:06d}.wav")
                
                subprocess.run([
                    "ffmpeg", "-y", "-f", "avfoundation",
                    "-i", ":0",  # Default microphone
                    "-t", str(CHUNK_DURATION),
                    "-ar", "16000", "-ac", "1",
                    chunk_file
                ], capture_output=True, timeout=CHUNK_DURATION + 0.5)
                
                if os.path.exists(chunk_file):
                    # Process chunk
                    state = self.process_audio_chunk(chunk_file)
                    frames = self.generate_frame_sequence(state, num_frames=3)
                    
                    # Output frames
                    for frame in frames:
                        output_frame = os.path.join(
                            self.output_dir, 
                            f"frame_{chunk_count:06d}.png"
                        )
                        os.system(f"cp '{frame}' '{output_frame}'")
                        
                    # Optional: create video stream
                    if chunk_count % 30 == 0:  # Every second
                        self._update_live_video(chunk_count)
                    
                    os.remove(chunk_file)
                    
                chunk_count += 1
                
                # Maintain timing
                elapsed = time.time() - chunk_start
                sleep_time = CHUNK_DURATION - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    
        except KeyboardInterrupt:
            print("\n\n🛑 Stopping stream...")
            self._finalize_video()
            
    def process_audio_file(self, audio_file, output_video=None):
        """Process entire audio file and generate synchronized video"""
        if output_video is None:
            output_video = os.path.join(
                self.output_dir, 
                f"live_sync_{int(time.time())}.mp4"
            )
            
        print(f"🎬 Processing audio file: {audio_file}")
        print(f"   Chunk size: {CHUNK_DURATION*1000:.0f}ms")
        print()
        
        # Split audio into chunks
        temp_dir = tempfile.mkdtemp()
        
        try:
            # Get audio duration
            result = subprocess.run([
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", audio_file
            ], capture_output=True, text=True, check=True)
            duration = float(result.stdout.strip())
            
            num_chunks = int(duration / CHUNK_DURATION) + 1
            
            print(f"Step 1/3: Splitting audio ({num_chunks} chunks)...")
            
            # Process each chunk
            frame_list = []
            
            for i in range(num_chunks):
                start_time = i * CHUNK_DURATION
                chunk_file = os.path.join(temp_dir, f"chunk_{i:04d}.wav")
                
                subprocess.run([
                    "ffmpeg", "-y", "-i", audio_file,
                    "-ss", str(start_time), "-t", str(CHUNK_DURATION),
                    "-ar", "16000", "-ac", "1",
                    chunk_file
                ], capture_output=True)
                
                if os.path.exists(chunk_file):
                    state = self.process_audio_chunk(chunk_file)
                    
                    # Get 3 frames per chunk (for 30fps output)
                    for _ in range(3):
                        frame_path = self.video_cache.get_frame(state, CHUNK_DURATION/3)
                        frame_name = f"frame_{i:04d}_{_}.png"
                        output_frame = os.path.join(temp_dir, frame_name)
                        os.system(f"cp '{frame_path}' '{output_frame}'")
                        frame_list.append(output_frame)
                        
                # Progress
                if (i + 1) % 10 == 0:
                    print(f"   {i+1}/{num_chunks} chunks processed...")
                    
            print(f"\nStep 2/3: Encoding video ({len(frame_list)} frames)...")
            
            # Create video from frames
            frame_pattern = os.path.join(temp_dir, "frame_%04d_*.png")
            
            subprocess.run([
                "ffmpeg", "-y", "-framerate", "30",
                "-pattern_type", "glob", "-i", os.path.join(temp_dir, "*.png"),
                "-i", audio_file,
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-shortest",
                output_video
            ], capture_output=True)
            
            print(f"\nStep 3/3: Finalizing...")
            print(f"   ✓ Video saved: {output_video}")
            
            return output_video
            
        finally:
            # Cleanup
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            
    def _update_live_video(self, frame_num):
        """Update ongoing live video file"""
        # Implementation for streaming preview
        pass
        
    def _finalize_video(self):
        """Finalize and cleanup"""
        self.video_cache.cleanup()
        print("   ✓ Cleanup complete")
        
    def run(self, mode="file", input_file=None, output=None):
        """Main entry point"""
        try:
            if mode == "mic":
                self.start_microphone_stream()
            elif mode == "file":
                if input_file is None:
                    print("Error: --input required for file mode")
                    return
                self.process_audio_file(input_file, output)
            else:
                print(f"Unknown mode: {mode}")
                
        finally:
            self.video_cache.cleanup()

def main():
    parser = argparse.ArgumentParser(description="Live Lip-Sync for Miko")
    parser.add_argument("--mode", type=str, default="file", 
                       choices=["mic", "file", "stream"],
                       help="Input mode: mic, file, or stream")
    parser.add_argument("--input", type=str, help="Input audio file")
    parser.add_argument("--output", type=str, help="Output video file")
    args = parser.parse_args()
    
    engine = LiveLipSync()
    engine.run(args.mode, args.input, args.output)

if __name__ == "__main__":
    main()
