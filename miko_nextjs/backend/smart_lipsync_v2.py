#!/usr/bin/env python3
"""
Smart Lip-Sync v2: Frame-accurate volume mapping
Extracts all unique mouth frames from frozen video, maps audio RMS to frame index
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import List, Tuple
from PIL import Image
import numpy as np

class SmartLipSyncV2:
    """
    Extracts ~60 mouth frames from frozen video (one full open-close cycle)
    Maps audio RMS volume directly to frame index for accurate lip-sync
    """
    
    def __init__(self, character_dir: Path, output_dir: Path):
        self.character_dir = character_dir
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Use frozen video
        self.video = character_dir / 'speaking_frozen.mp4'
        if not self.video.exists():
            raise RuntimeError("Need speaking_frozen.mp4!")
            
        self.base_frame = None
        self.mouth_frames = []  # List of mouth images, indexed by openness (0=closed, max=open)
        self._prepare_frames()
        
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
        
    def _get_video_info(self, video: Path) -> Tuple[float, int, int, int]:
        """Get duration, width, height, fps"""
        result = subprocess.run([
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', str(video)
        ], capture_output=True, text=True)
        duration = float(result.stdout.strip())
        
        result = subprocess.run([
            'ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height,r_frame_rate',
            '-of', 'default=noprint_wrappers=1', str(video)
        ], capture_output=True, text=True)
        lines = result.stdout.strip().split('\n')
        width = int(lines[0].split('=')[1])
        height = int(lines[1].split('=')[1])
        fps_frac = lines[2].split('=')[1]
        num, den = map(int, fps_frac.split('/'))
        fps = num / den
        
        return duration, width, height, fps
        
    def _prepare_frames(self):
        """Extract mouth frames from frozen video (one full cycle)"""
        print("Preparing mouth frames from frozen video...")
        
        duration, w, h, fps = self._get_video_info(self.video)
        total_frames = int(duration * fps)
        
        print(f"  Frozen video: {duration:.1f}s @ {w}x{h}, {fps}fps, {total_frames} frames")
        
        # Mouth region
        self.mouth_x = w // 2 - 120
        self.mouth_y = int(h * 0.65)
        self.mouth_w = 240
        self.mouth_h = 180
        
        print(f"  Mouth region: ({self.mouth_x}, {self.mouth_y}, {self.mouth_w}, {self.mouth_h})")
        
        # Sample every Nth frame to get ~40-50 unique mouth positions
        # Skip first and last to avoid duplicates
        sample_every = max(1, total_frames // 45)
        
        for i in range(1, total_frames - 1, sample_every):
            t = i / fps
            frame = self._extract_frame(self.video, t)
            mouth = frame.crop((self.mouth_x, self.mouth_y, 
                               self.mouth_x + self.mouth_w, self.mouth_y + self.mouth_h))
            self.mouth_frames.append(mouth)
            
        print(f"  ✓ Extracted {len(self.mouth_frames)} mouth frames")
        
        # Sort frames by "mouth openness" (brightness of mouth area)
        # More open mouth = brighter (more teeth/skin visible)
        brightness_scores = []
        for mouth in self.mouth_frames:
            arr = np.array(mouth.convert('L'))  # grayscale
            brightness = np.mean(arr)
            brightness_scores.append(brightness)
            
        # Sort by brightness (ascending = closed to open)
        sorted_indices = np.argsort(brightness_scores)
        self.mouth_frames = [self.mouth_frames[i] for i in sorted_indices]
        
        print(f"  ✓ Sorted by mouth openness (closed → open)")
        
        # Base frame (body with closed mouth)
        base_img = self._extract_frame(self.video, 0.1)
        base_img.paste(self.mouth_frames[0], (self.mouth_x, self.mouth_y))
        self.base_frame = base_img
        print(f"  ✓ Base frame ready")
        
    def _get_rms_volumes(self, audio_path: str, num_frames: int, fps: int) -> List[float]:
        """Get per-frame RMS volume (0-1) from audio using ffmpeg"""
        # Use astats filter to get RMS level per frame
        # This is more accurate than silence detection
        
        duration = num_frames / fps
        
        # Get audio stats
        result = subprocess.run([
            'ffmpeg', '-i', audio_path,
            '-af', 'astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level',
            '-f', 'null', '-'
        ], capture_output=True, text=True)
        
        # Parse RMS levels
        rms_values = []
        for line in result.stderr.split('\n'):
            if 'RMS_level=' in line:
                try:
                    val = float(line.split('RMS_level=')[1].split()[0])
                    rms_values.append(val)
                except:
                    pass
        
        if not rms_values:
            # Fallback: simple wave
            return [0.3 + 0.4 * np.sin(i * 0.5) for i in range(num_frames)]
            
        # Resample to match video frames
        # RMS values are per audio sample block, need to map to video frames
        frame_step = len(rms_values) / num_frames
        sampled = []
        for i in range(num_frames):
            idx = int(i * frame_step)
            if idx < len(rms_values):
                sampled.append(rms_values[idx])
            else:
                sampled.append(rms_values[-1] if rms_values else -60)
                
        # Convert dB to linear scale (0-1)
        # RMS is in dB, typically -60 (silent) to -10 (loud)
        min_db, max_db = -50, -10
        linear = []
        for db in sampled:
            # Clamp and normalize
            clamped = max(min_db, min(max_db, db))
            normalized = (clamped - min_db) / (max_db - min_db)
            linear.append(normalized)
            
        return linear
        
    def _get_volume_curve(self, audio_path: str, num_frames: int) -> List[float]:
        """Get smooth volume curve with attack/decay for natural mouth movement"""
        fps = 30
        volumes = self._get_rms_volumes(audio_path, num_frames, fps)
        
        # Apply smoothing (attack/decay) for natural mouth movement
        # Mouth opens fast, closes slower
        smoothed = []
        prev_vol = 0
        attack = 0.7  # 70% of new value (fast attack)
        decay = 0.3   # 30% of new value (slow decay)
        
        for vol in volumes:
            if vol > prev_vol:
                # Opening - fast
                new_vol = attack * vol + (1 - attack) * prev_vol
            else:
                # Closing - slow
                new_vol = decay * vol + (1 - decay) * prev_vol
            smoothed.append(new_vol)
            prev_vol = new_vol
            
        return smoothed
        
    def generate(self, audio_path: str, text: str, duration: float) -> str:
        """Generate lip-sync video with frame-accurate mouth mapping - FAST version using pipe"""
        import time
        t0 = time.time()
        
        video_id = f"smart2_{int(time.time()*1000)%100000}.mp4"
        out_path = self.output_dir / video_id
        
        fps = 15  # 15fps is enough for lip-sync, 2x faster than 30fps
        num_frames = int(duration * fps)
        
        print(f"Generating {num_frames} frames at {fps}fps with RMS-based lip-sync...")
        print(f"  Using {len(self.mouth_frames)} mouth frames")
        
        # Get volume curve
        volumes = self._get_volume_curve(audio_path, num_frames)
        
        # Pre-convert all mouth frames to numpy arrays for fast pasting
        base_np = np.array(self.base_frame)
        mouth_nps = [np.array(m) for m in self.mouth_frames]
        
        # Start ffmpeg with rawvideo input pipe
        cmd = [
            'ffmpeg', '-y',
            '-f', 'rawvideo',
            '-vcodec', 'rawvideo',
            '-s', f'{self.base_frame.size[0]}x{self.base_frame.size[1]}',
            '-pix_fmt', 'rgb24',
            '-r', str(fps),
            '-i', '-',  # Read from stdin
            '-i', audio_path,
            '-c:v', 'libx264',
            '-pix_fmt', 'yuv420p',
            '-preset', 'ultrafast',
            '-crf', '28',
            '-c:a', 'aac',
            '-b:a', '128k',
            '-shortest',
            str(out_path)
        ]
        
        ffmpeg_proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        
        # Generate and pipe frames
        for i in range(num_frames):
            vol = volumes[i]
            
            # Map volume to mouth frame index
            frame_idx = int(vol * (len(self.mouth_frames) - 1))
            frame_idx = max(0, min(len(self.mouth_frames) - 1, frame_idx))
            
            # Fast numpy paste
            frame = base_np.copy()
            mouth = mouth_nps[frame_idx]
            frame[self.mouth_y:self.mouth_y+self.mouth_h, 
                  self.mouth_x:self.mouth_x+self.mouth_w] = mouth
            
            # Write to ffmpeg stdin
            ffmpeg_proc.stdin.write(frame.tobytes())
            
            if i % 30 == 0:
                print(f"  Frame {i}/{num_frames} (vol={vol:.2f})")
        
        ffmpeg_proc.stdin.close()
        ffmpeg_proc.wait()
        
        elapsed = time.time() - t0
        print(f"✓ Done: {elapsed:.1f}s")
        return f"/generated/{video_id}"
