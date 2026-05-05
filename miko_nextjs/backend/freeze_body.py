#!/usr/bin/env python3
"""
Freeze Body Video Generator
Creates a speaking video with frozen body + moving mouth only
Uses single base frame + mouth overlays
"""

import os
import subprocess
import tempfile
from pathlib import Path
from PIL import Image

class FreezeBodyGenerator:
    """
    Generates a frozen-body speaking video:
    - Body/head from listening.mp4 (single frozen frame)
    - Only mouth animates from speaking1.mp4
    """
    
    def __init__(self, character_dir: Path, output_dir: Path):
        self.character_dir = character_dir
        self.output_dir = output_dir
        
        self.listening = character_dir / 'listening.mp4'
        self.speaking = character_dir / 'speaking1.mp4'
        
        if not self.listening.exists() or not self.speaking.exists():
            raise RuntimeError("Need both listening.mp4 and speaking1.mp4")
            
    def _extract_frame(self, video: Path, time: float, output: Path):
        """Extract single frame"""
        subprocess.run([
            'ffmpeg', '-y', '-ss', str(time), '-i', str(video),
            '-vframes', '1', '-q:v', '2', str(output)
        ], capture_output=True, check=True)
        
    def _get_video_info(self, video: Path):
        """Get duration and resolution"""
        result = subprocess.run([
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', str(video)
        ], capture_output=True, text=True)
        duration = float(result.stdout.strip())
        
        result = subprocess.run([
            'ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height',
            '-of', 'default=noprint_wrappers=1', str(video)
        ], capture_output=True, text=True)
        lines = result.stdout.strip().split('\n')
        width = int(lines[0].split('=')[1])
        height = int(lines[1].split('=')[1])
        
        return duration, width, height
        
    def generate(self, output_name: str = "speaking_frozen.mp4", fps: int = 30):
        """
        Generate frozen-body speaking video
        Base frame from listening.mp4, mouth animation from speaking1.mp4
        """
        print("Generating frozen-body speaking video...")
        
        # Get video info
        speak_duration, width, height = self._get_video_info(self.speaking)
        listen_duration, _, _ = self._get_video_info(self.listening)
        
        print(f"  Speaking video: {speak_duration:.1f}s @ {width}x{height}")
        
        # Mouth region for speaking1.mp4 (1088x1920)
        # Center of face, lower half where mouth is
        mouth_x = 424  # manually tuned for this character
        mouth_y = 1248  # lower face area
        mouth_w = 240
        mouth_h = 180
        
        print(f"  Mouth region: ({mouth_x}, {mouth_y}, {mouth_w}, {mouth_h})")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            # Step 1: Extract base frame from listening.mp4 (frozen body)
            base_frame = tmpdir / 'base.png'
            self._extract_frame(self.listening, listen_duration / 2, base_frame)
            print(f"  ✓ Base frame extracted")
            
            # Step 2: Resize base to match speaking video
            base_img = Image.open(base_frame)
            base_img = base_img.resize((width, height), Image.LANCZOS)
            base_img.save(base_frame)
            
            # Step 3: Extract mouth frames from speaking video
            num_frames = int(speak_duration * fps)
            frames_dir = tmpdir / 'frames'
            frames_dir.mkdir()
            
            print(f"  Generating {num_frames} frames with mouth animation...")
            
            for i in range(num_frames):
                t = i / fps
                
                # Extract frame from speaking video
                speak_frame = tmpdir / f'speak_{i:04d}.png'
                self._extract_frame(self.speaking, t, speak_frame)
                
                # Crop mouth
                speak_img = Image.open(speak_frame)
                mouth = speak_img.crop((mouth_x, mouth_y, mouth_x + mouth_w, mouth_y + mouth_h))
                
                # Paste onto base
                final = base_img.copy()
                final.paste(mouth, (mouth_x, mouth_y))
                
                # Save
                final.save(frames_dir / f'frame_{i:04d}.png')
                
                if i % 30 == 0:
                    print(f"    Frame {i}/{num_frames}")
                    
                # Cleanup temp
                speak_frame.unlink()
                
            # Step 4: Encode video
            print("  Encoding final video...")
            output_path = self.character_dir / output_name
            
            subprocess.run([
                'ffmpeg', '-y', '-framerate', str(fps),
                '-i', str(frames_dir / 'frame_%04d.png'),
                '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                '-preset', 'medium', '-crf', '18',  # High quality
                str(output_path)
            ], capture_output=True, check=True)
            
        print(f"✓ Done: {output_path}")
        return output_path


if __name__ == "__main__":
    import sys
    
    char_dir = Path("/Users/sahaj/Desktop/termux/miko_character")
    out_dir = Path("/Users/sahaj/Desktop/termux/miko_nextjs/public/generated")
    
    gen = FreezeBodyGenerator(char_dir, out_dir)
    gen.generate()
