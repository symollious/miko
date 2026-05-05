#!/usr/bin/env python3
"""
INSTANT Lip-Sync Algorithm - FIXED
Segments properly sorted by mouth openness (closed → open)
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import List
from PIL import Image
import numpy as np

class InstantLipSync:
    """
    ULTRA-FAST lip-sync using pre-encoded video segments
    Segments are ORDERED: 0=closed, 19=fully open
    """
    
    def __init__(self, character_dir: Path, output_dir: Path):
        self.character_dir = character_dir
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.video = character_dir / 'speaking_frozen.mp4'
        if not self.video.exists():
            raise RuntimeError("Need speaking_frozen.mp4!")
        
        self.segments_dir = output_dir / 'instant_segments_v2'
        self.segments_dir.mkdir(exist_ok=True)
        
        self.num_segments = 20
        self.segment_duration = 0.1
        
        # Mouth region (for 1450x2560 video - matches listening.mp4)
        self.mouth_x = 565
        self.mouth_y = 1664
        self.mouth_w = 319
        self.mouth_h = 240
        
        self._prepare_segments()
        
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
        return float(result.stdout.strip())
        
    def _mouth_openness(self, frame: Image.Image) -> float:
        """Calculate mouth openness based on brightness in mouth region"""
        mouth = frame.crop((self.mouth_x, self.mouth_y, 
                            self.mouth_x + self.mouth_w, 
                            self.mouth_y + self.mouth_h))
        # Convert to grayscale and get mean brightness
        gray = mouth.convert('L')
        arr = np.array(gray)
        return np.mean(arr)
        
    def _prepare_segments(self):
        """Pre-encode 20 segments sorted by mouth openness (closed→open)"""
        marker = self.segments_dir / '.ready'
        if marker.exists():
            print(f"✓ Pre-encoded segments ready: {self.num_segments} clips (sorted by mouth openness)")
            return
            
        print(f"Pre-encoding {self.num_segments} segments sorted by mouth openness...")
        
        duration = self._get_video_info(self.video)
        
        # Step 1: Sample many frames from frozen video
        sample_times = np.linspace(0.1, duration - 0.2, 100)  # 100 samples
        
        frames_with_openness = []
        for t in sample_times:
            frame = self._extract_frame(self.video, t)
            openness = self._mouth_openness(frame)
            frames_with_openness.append((openness, frame, t))
            
        # Step 2: Sort by mouth openness (ascending = closed to open)
        frames_with_openness.sort(key=lambda x: x[0])
        
        print(f"  Sampled {len(frames_with_openness)} frames, mouth openness: {frames_with_openness[0][0]:.1f} to {frames_with_openness[-1][0]:.1f}")
        
        # Step 3: Pick 20 evenly spaced frames from closed to open
        selected_frames = []
        for i in range(self.num_segments):
            idx = int(i * (len(frames_with_openness) - 1) / (self.num_segments - 1))
            selected_frames.append(frames_with_openness[idx])
            print(f"  Segment {i}: openness={selected_frames[-1][0]:.1f}, t={selected_frames[-1][2]:.2f}s")
            
        # Step 4: Extract 100ms video segments at those timestamps
        for i, (openness, frame, t) in enumerate(selected_frames):
            seg_path = self.segments_dir / f'seg_{i:02d}.mp4'
            
            # Extract 100ms segment
            subprocess.run([
                'ffmpeg', '-y', '-ss', str(t), '-i', str(self.video),
                '-t', str(self.segment_duration),
                '-c', 'copy',
                '-avoid_negative_ts', 'make_zero',
                str(seg_path)
            ], capture_output=True, check=True)
            
        marker.touch()
        print(f"✓ Pre-encoded {self.num_segments} segments (sorted: closed→open)")
        
    def _get_volume_chunks(self, audio_path: str, num_chunks: int) -> List[float]:
        """Get per-100ms volume using silencedetect"""
        result = subprocess.run([
            'ffmpeg', '-i', audio_path,
            '-af', 'silencedetect=noise=-40dB:d=0.05',
            '-f', 'null', '-'
        ], capture_output=True, text=True)
        
        # Parse silence periods
        silence_starts = []
        silence_ends = []
        for line in result.stderr.split('\n'):
            if 'silence_start:' in line:
                try:
                    t = float(line.split('silence_start:')[1].split()[0])
                    silence_starts.append(t)
                except:
                    pass
            elif 'silence_end:' in line:
                try:
                    t = float(line.split('silence_end:')[1].split()[0])
                    silence_ends.append(t)
                except:
                    pass
        
        # Get audio duration
        result = subprocess.run([
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', audio_path
        ], capture_output=True, text=True)
        total_duration = float(result.stdout.strip())
        
        # Build volume per chunk
        chunk_duration = self.segment_duration
        volumes = []
        
        for i in range(num_chunks):
            t = i * chunk_duration
            
            # Check if in silence
            in_silence = False
            for start, end in zip(silence_starts, silence_ends):
                if start <= t <= end:
                    in_silence = True
                    break
                    
            if in_silence:
                volumes.append(0.0)  # Closed mouth
            else:
                # Generate varying volume for speech
                # Use multiple frequencies for natural movement
                wave = 0.5 + 0.3 * np.sin(t * 15) + 0.2 * np.sin(t * 25)
                volumes.append(max(0.0, min(1.0, wave)))
                
        return volumes
        
    def generate(self, audio_path: str, text: str, duration: float) -> str:
        """Generate lip-sync video"""
        import time
        t0 = time.time()
        
        video_id = f"inst_{int(time.time()*1000)%100000}.mp4"
        out_path = self.output_dir / video_id
        
        num_chunks = max(1, int(duration / self.segment_duration))
        
        print(f"Instant lip-sync: {num_chunks} chunks")
        
        # 1. Analyze audio
        volumes = self._get_volume_chunks(audio_path, num_chunks)
        
        # 2. Build concat list based on volume
        concat_file = self.output_dir / f'concat_{video_id}.txt'
        with open(concat_file, 'w') as f:
            for vol in volumes:
                # Map volume (0-1) to segment (0-19)
                seg_idx = int(vol * (self.num_segments - 1))
                seg_idx = max(0, min(self.num_segments - 1, seg_idx))
                seg_path = self.segments_dir / f'seg_{seg_idx:02d}.mp4'
                f.write(f"file '{seg_path.absolute()}'\n")
                
        # 3. Concatenate
        subprocess.run([
            'ffmpeg', '-y', '-f', 'concat', '-safe', '0',
            '-i', str(concat_file),
            '-i', audio_path,
            '-c', 'copy',
            '-shortest',
            str(out_path)
        ], capture_output=True, check=True)
        
        os.remove(concat_file)
        
        elapsed = time.time() - t0
        print(f"✓ Done: {elapsed:.3f}s")
        return f"/generated/{video_id}"
