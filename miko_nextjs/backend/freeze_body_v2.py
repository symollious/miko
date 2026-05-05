#!/usr/bin/env python3
"""
Freeze Body Video Generator v2
Uses speaking1.mp4 only - extracts closed-mouth frame as base
This ensures perfect alignment
"""

import os
import subprocess
import tempfile
from pathlib import Path
from PIL import Image

class FreezeBodyGeneratorV2:
    """
    Creates frozen-body video using ONLY speaking1.mp4
    - Base: Frame at t=0.1s (mouth closed/starting position)
    - Animation: Mouth crops from rest of video
    """
    
    def __init__(self, character_dir: Path, output_dir: Path):
        self.character_dir = character_dir
        self.output_dir = output_dir
        
        self.speaking = character_dir / 'speaking1.mp4'
        
        if not self.speaking.exists():
            raise RuntimeError("Need speaking1.mp4!")
            
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
        Base from t=0.1s (closed mouth), animate mouth from rest of video
        """
        print("Generating frozen-body speaking video v2...")
        
        # Get video info
        duration, width, height = self._get_video_info(self.speaking)
        
        print(f"  Speaking video: {duration:.1f}s @ {width}x{height}")
        
        # Mouth region (for 1088x1920 speaking video)
        # These coordinates should be tuned for your character
        mouth_x = 424  # center-ish
        mouth_y = 1248  # lower face
        mouth_w = 240
        mouth_h = 180
        
        print(f"  Mouth region: ({mouth_x}, {mouth_y}, {mouth_w}, {mouth_h})")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            # Step 1: Extract base frame from t=0.1s (mouth closed)
            base_frame = tmpdir / 'base.png'
            self._extract_frame(self.speaking, 0.1, base_frame)
            print(f"  ✓ Base frame extracted (t=0.1s, closed mouth)")
            
            base_img = Image.open(base_frame)
            
            # Step 2: Generate frames with mouth animation
            # Skip first 0.5s to avoid the closed-mouth base
            start_time = 0.5
            end_time = duration
            num_frames = int((end_time - start_time) * fps)
            
            frames_dir = tmpdir / 'frames'
            frames_dir.mkdir()
            
            print(f"  Generating {num_frames} frames...")
            
            for i in range(num_frames):
                t = start_time + (i / fps)
                
                # Extract frame
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
                    
                speak_frame.unlink()
                
            # Step 3: Encode video
            print("  Encoding final video...")
            output_path = self.character_dir / output_name
            
            subprocess.run([
                'ffmpeg', '-y', '-framerate', str(fps),
                '-i', str(frames_dir / 'frame_%04d.png'),
                '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                '-preset', 'medium', '-crf', '18',
                str(output_path)
            ], capture_output=True, check=True)
            
        print(f"✓ Done: {output_path}")
        return output_path


if __name__ == "__main__":
    char_dir = Path("/Users/sahaj/Desktop/termux/miko_character")
    out_dir = Path("/Users/sahaj/Desktop/termux/miko_nextjs/public/generated")
    
    gen = FreezeBodyGeneratorV2(char_dir, out_dir)
    gen.generate()
