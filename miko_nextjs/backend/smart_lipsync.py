#!/usr/bin/env python3
"""
Smart Lip-Sync: Cross-fade between discrete mouth poses
No segment splicing - smooth interpolation based on volume
Target: <1s generation, smooth animation
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import List
from PIL import Image
import numpy as np

class SmartLipSync:
    """
    Extracts 5 discrete mouth poses, cross-fades based on audio volume
    Frozen body + smooth mouth transitions
    """
    
    def __init__(self, character_dir: Path, output_dir: Path):
        self.character_dir = character_dir
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Use frozen video if available
        frozen = character_dir / 'speaking_frozen.mp4'
        if frozen.exists():
            self.video = frozen
            print("✓ Using frozen-body video")
        else:
            self.video = character_dir / 'speaking1.mp4'
            print("⚠ Using original video")
            
        self.base_frame = None
        self.mouth_poses = []  # List of (image, coords)
        self._prepare_poses()
        
    def _extract_frame(self, video: Path, time: float) -> Image.Image:
        """Extract frame at time"""
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            frame_path = f.name
        
        subprocess.run([
            'ffmpeg', '-y', '-ss', str(time), '-i', str(video),
            '-vframes', '1', '-q:v', '2', frame_path
        ], capture_output=True, check=True)
        
        img = Image.open(frame_path)
        os.remove(frame_path)
        return img
        
    def _prepare_poses(self):
        """Extract base frame + 5 mouth poses from frozen video"""
        print("Preparing mouth poses...")
        
        # Get video duration
        result = subprocess.run([
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', str(self.video)
        ], capture_output=True, text=True)
        duration = float(result.stdout.strip())
        
        w, h = self._extract_frame(self.video, 0).size
        print(f"  Video: {duration:.1f}s @ {w}x{h}")
        
        # Mouth region
        self.mouth_x = w // 2 - 120
        self.mouth_y = int(h * 0.65)
        self.mouth_w = 240
        self.mouth_h = 180
        
        # Extract 5 key mouth poses from different timestamps
        # These represent: closed → slight → half → open → wide
        pose_times = [0.2, duration*0.25, duration*0.4, duration*0.6, duration*0.8]
        
        for i, t in enumerate(pose_times):
            frame = self._extract_frame(self.video, t)
            mouth = frame.crop((self.mouth_x, self.mouth_y, 
                               self.mouth_x + self.mouth_w, self.mouth_y + self.mouth_h))
            self.mouth_poses.append(mouth)
            print(f"  ✓ Pose {i}: t={t:.2f}s, size={mouth.size}")
            
        # Base frame (body with closed-ish mouth)
        base_img = self._extract_frame(self.video, 0.1)
        # Paste first pose (closed mouth) onto base to create clean starting point
        base_img.paste(self.mouth_poses[0], (self.mouth_x, self.mouth_y))
        self.base_frame = base_img
        print(f"  ✓ Base frame ready")
        
    def _volume_to_mouth_blend(self, volume: float) -> Image.Image:
        """
        Map volume (0-1) to blended mouth image
        Cross-fades between adjacent poses for smoothness
        """
        # 5 poses = 4 intervals
        # volume 0.0-0.25 = pose 0-1
        # volume 0.25-0.5 = pose 1-2
        # volume 0.5-0.75 = pose 2-3
        # volume 0.75-1.0 = pose 3-4
        
        scaled_vol = volume * 4  # 0 to 4
        idx = int(scaled_vol)  # 0, 1, 2, 3, or 4
        t = scaled_vol - idx  # fractional part for blending
        
        # Clamp
        if idx >= 4:
            return self.mouth_poses[4]
        if idx < 0:
            return self.mouth_poses[0]
            
        # Cross-fade between idx and idx+1
        img1 = np.array(self.mouth_poses[idx]).astype(float)
        img2 = np.array(self.mouth_poses[idx + 1]).astype(float)
        
        blended = img1 * (1 - t) + img2 * t
        blended = np.clip(blended, 0, 255).astype(np.uint8)
        
        return Image.fromarray(blended)
        
    def _get_volume_curve(self, audio_path: str, num_frames: int) -> List[float]:
        """Get per-frame volume (0-1) from audio"""
        # Get duration
        result = subprocess.run([
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', audio_path
        ], capture_output=True, text=True)
        duration = float(result.stdout.strip())
        
        # Detect silence
        result = subprocess.run([
            'ffmpeg', '-i', audio_path,
            '-af', 'silencedetect=noise=-40dB:d=0.05',
            '-f', 'null', '-'
        ], capture_output=True, text=True)
        
        silence_periods = []
        current_start = None
        for line in result.stderr.split('\n'):
            if 'silence_start:' in line:
                try:
                    current_start = float(line.split('silence_start:')[1].split()[0])
                except:
                    pass
            elif 'silence_end:' in line and current_start is not None:
                try:
                    end = float(line.split('silence_end:')[1].split()[0])
                    silence_periods.append((current_start, end))
                    current_start = None
                except:
                    pass
        
        # Build volume curve
        frame_duration = duration / num_frames
        volumes = []
        
        for i in range(num_frames):
            t = i * frame_duration
            
            # Check silence
            in_silence = any(start <= t <= end for start, end in silence_periods)
            
            if in_silence:
                volumes.append(0.0)
            else:
                # Create wave pattern
                # Multiple frequencies for natural mouth movement
                wave = 0.5 + 0.4 * np.sin(t * 12) + 0.15 * np.sin(t * 25)
                wave = max(0.0, min(1.0, wave))
                volumes.append(wave)
                
        return volumes
        
    def generate(self, audio_path: str, text: str, duration: float) -> str:
        """Generate lip-sync video with cross-fading mouths"""
        import time
        t0 = time.time()
        
        video_id = f"smart_{int(time.time()*1000)%100000}.mp4"
        out_path = self.output_dir / video_id
        
        fps = 30
        num_frames = int(duration * fps)
        
        print(f"Generating {num_frames} frames with smart lip-sync...")
        
        # Get volume curve
        volumes = self._get_volume_curve(audio_path, num_frames)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            frames_dir = Path(tmpdir) / 'frames'
            frames_dir.mkdir()
            
            # Generate each frame
            for i in range(num_frames):
                vol = volumes[i]
                
                # Get blended mouth for this volume
                mouth = self._volume_to_mouth_blend(vol)
                
                # Paste onto base
                frame = self.base_frame.copy()
                frame.paste(mouth, (self.mouth_x, self.mouth_y))
                
                # Save
                frame.save(frames_dir / f'f_{i:05d}.png')
                
                if i % 50 == 0:
                    print(f"  Frame {i}/{num_frames} (vol={vol:.2f})")
                    
            # Encode video
            print("  Encoding...")
            subprocess.run([
                'ffmpeg', '-y', '-framerate', str(fps),
                '-i', str(frames_dir / 'f_%05d.png'),
                '-i', audio_path,
                '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                '-preset', 'veryfast', '-crf', '23',
                '-c:a', 'aac', '-b:a', '192k',
                '-shortest', '-movflags', '+faststart',
                str(out_path)
            ], capture_output=True, check=True)
            
        elapsed = time.time() - t0
        print(f"✓ Done: {elapsed:.1f}s")
        return f"/generated/{video_id}"
