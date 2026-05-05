# Miko Lip-Sync TTS System

Generate talking head videos from text for the Miko character.

## Quick Start

### Generate a lip-sync video:
```bash
cd /Users/sahaj/Desktop/termux/lipsync
python3 lip_sync_tts.py --text "Hello, I am Miko!"
```

### With custom output path:
```bash
python3 lip_sync_tts.py --text "How can I help you today?" --output my_video.mp4
```

## How It Works

1. **TTS Generation**: Uses macOS `say` command to generate speech audio
2. **Video Looping**: Loops the `speaking1.mp4` clip to match audio duration
3. **Audio Replacement**: Replaces original audio with TTS audio

## Files

- `lip_sync_tts.py` - Main script for generating lip-sync videos
- `source_frames/miko_source.png` - Source frame extracted from video
- `output/` - Generated videos are saved here
- `LivePortrait/` - AI animation framework (advanced option)

## Methods

### Simple Method (Default)
Loops the existing speaking animation and replaces audio.
- **Pros**: Fast, works immediately
- **Cons**: Mouth movements don't match speech exactly

### LivePortrait Method (Advanced)
Uses AI to animate a static image based on driving video.
- **Pros**: Can create more realistic animations
- **Cons**: Requires proper setup, more complex

## Examples

```bash
# Basic usage
python3 lip_sync_tts.py --text "Welcome to my world!"

# Custom output
python3 lip_sync_tts.py --text "Let me help you with that." --output help.mp4

# Try LivePortrait (if properly configured)
python3 lip_sync_tts.py --text "Advanced animation" --method liveportrait
```

## Output Location

All generated videos are saved to:
```
/Users/sahaj/Desktop/termux/lipsync/output/
```

## Limitations

- **Simple method**: Mouth animation is from original video, not synced to speech
- **Audio**: Uses macOS built-in TTS (can be enhanced with other TTS engines)
- **Length**: Best for short phrases (under 30 seconds)

## Enhancement Options

For true lip-sync where mouth matches speech:

1. **Wav2Lip**: Download model from HuggingFace, integrate into pipeline
2. **SadTalker**: Set up for audio-driven facial animation
3. **Cloud APIs**: Use services like D-ID, HeyGen for professional results

## Requirements

- macOS (for `say` TTS command)
- Python 3.9+
- ffmpeg
- ffprobe

## Troubleshooting

**"ffmpeg not found"**: Install with `brew install ffmpeg`

**"say command failed"**: Check macOS TTS is working: `say "test"`

**Video too short/long**: Script automatically loops video to match audio duration
