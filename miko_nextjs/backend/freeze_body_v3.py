#!/usr/bin/env python3
"""
Freeze Body Video Generator v3
Uses listening.mp4 as base (neutral pose) + speaking1.mp4 mouth animation
"""

import os
import subprocess
import tempfile
from pathlib import Path
from PIL import Image
import numpy as np

class FreezeBodyGeneratorV3:
    def __init__(self, character_dir: Path, output_dir: Path):
        self.character_dir = character_dir
        self.output_dir = output_dir
        
        self.listening = character_dir / 'listening.mp4'
        self.speaking = character_dir / 'speaking1.mp4'
        
        if not self.listening.exists() or not self.speaking.exists():
            raise RuntimeError("Need both listening.mp4 and speaking1.mp4!")
            
    def _extract_frame(self, video: Path, time: float) -> Image.Image:
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            frame_path = f.name
        subprocess.run([
            'ffmpeg', '-y', '-ss', str(time), '-i', str(video),
            '-vframes', '1', '-q:v', '2', frame_path
        ], capture_output=True, check=True)
        img = Image.open(frame_path)
        os.remove(frame_path)
        return img
        
    def _get_video_info(self, video: Path):
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
        print("Generating frozen-body speaking video v3...")
        print("  Using listening.mp4 as base (neutral pose)")
        print("  Using speaking1.mp4 for mouth animation")
        
        speak_duration, speak_w, speak_h = self._get_video_info(self.speaking)
        listen_duration, listen_w, listen_h = self._get_video_info(self.listening)
        
        print(f"  Speaking: {speak_duration:.1f}s @ {speak_w}x{speak_h}")
        print(f"  Listening: {listen_duration:.1f}s @ {listen_w}x{listen_h}")
        
        # Use listening video dimensions (1450x2560)
        # We need to match speaking video mouth region to listening video
        # Speaking: 1088x1920, mouth at (424, 1248)
        # Listening: 1450x2560
        
        # Scale factor
        scale_x = listen_w / speak_w
        scale_y = listen_h / speak_h
        
        # Scaled mouth region for listening video
        mouth_x = int(424 * scale_x)
        mouth_y = int(1248 * scale_y)
        mouth_w = int(240 * scale_x)
        mouth_h = int(180 * scale_y)
        
        print(f"  Scaled mouth region: ({mouth_x}, {mouth_y}, {mouth_w}, {mouth_h})")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            # Extract base frame from listening.mp4 (neutral pose)
            base_img = self._extract_frame(self.listening, listen_duration / 2)
            print(f"  ✓ Base frame extracted: {base_img.size}")
            
            # Verify sizes match
            if base_img.size != (listen_w, listen_h):
                base_img = base_img.resize((listen_w, listen_h), Image.LANCZOS)
                
            # Generate frames
            num_frames = int(speak_duration * fps)
            frames_dir = tmpdir / 'frames'
            frames_dir.mkdir()
            
            print(f"  Generating {num_frames} frames...")
            
            for i in range(num_frames):
                t = i / fps
                
                # Extract speaking frame
                speak_img = self._extract_frame(self.speaking, t)
                
                # Resize speaking frame to match listening dimensions
                speak_img = speak_img.resize((listen_w, listen_h), Image.LANCZOS)
                
                # Crop mouth from speaking frame (using scaled coordinates)
                mouth = speak_img.crop((mouth_x, mouth_y, mouth_x + mouth_w, mouth_y + mouth_h))
                
                # Paste onto base
                final = base_img.copy()
                final.paste(mouth, (mouth_x, mouth_y))
                
                # Save
                final.save(frames_dir / f'frame_{i:04d}.png')
                
                if i % 30 == 0:
                    print(f"    Frame {i}/{num_frames}")
                    
            # Encode
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
    
    gen = FreezeBodyGeneratorV3(char_dir, out_dir)
    gen.generate()
