# Female Voice Generator with PocketTTS

Generate audio samples for all female voices available in PocketTTS from Kyutai.

## Features

✅ **5 Female Voices** - All available female voice models from Kyutai's PocketTTS  
✅ **Clean Implementation** - Fresh code without bugs from previous versions  
✅ **Batch Processing** - Generates all voices in one run  
✅ **Error Handling** - Continues even if individual voices fail  
✅ **Custom Text** - Use your own text for generation  
✅ **Organized Output** - All files saved with clear naming  
✅ **CPU-Only** - No GPU required, runs efficiently on CPU

## Installation

```bash
# Requires Python 3.10 or higher
python3.10 -m pip install pocket-tts scipy --user
```

## Usage

### Basic Usage (Default Text)
```bash
python3.10 generate_female_voices.py
```

### Custom Text
```bash
python3.10 generate_female_voices.py --text "Hello, I am Miko!"
```

### Custom Output Directory
```bash
python3.10 generate_female_voices.py --output-dir ./my_voices
```

### List All Available Voices
```bash
python3.10 generate_female_voices.py --list-voices
```

## Female Voices Included

The script generates audio for these 5 female voices:

1. **alba** - Clear, natural female voice
2. **fantine** - Expressive female voice
3. **cosette** - Soft, gentle female voice
4. **eponine** - Dynamic female voice
5. **azelma** - Warm female voice

All voices are based on characters from Les Misérables and are **100% female** - no male voices included!

## Output

All generated audio files are saved as WAV files (24kHz sample rate):
- `alba.wav`
- `fantine.wav`
- `cosette.wav`
- `eponine.wav`
- `azelma.wav`

## Examples

### Generate with Custom Text
```bash
python3.10 generate_female_voices.py \
  --text "Welcome to my channel! Today we'll explore AI voices." \
  --output-dir ./youtube_voices
```

### Quick Test
```bash
python3.10 generate_female_voices.py --text "Testing, one, two, three."
```

## Output Format

The script provides detailed progress:

```
🎤 Generating Female Voices with PocketTTS
📝 Text: "Hello, I am Miko!"
📁 Output: ./female_voices_output
🔢 Total voices: 5
============================================================

Loading TTS model... (this may take a moment)
✓ Model loaded (sample rate: 24000 Hz)

[1/5] Generating: alba... ✓ Saved to alba.wav
[2/5] Generating: fantine... ✓ Saved to fantine.wav
[3/5] Generating: cosette... ✓ Saved to cosette.wav
[4/5] Generating: eponine... ✓ Saved to eponine.wav
[5/5] Generating: azelma... ✓ Saved to azelma.wav

============================================================
✅ Successfully generated: 5/5
📁 All files saved to: ./female_voices_output
```

## Troubleshooting

### Python Version Error
PocketTTS requires Python 3.10 or higher. Use `python3.10` instead of `python3`:
```bash
python3.10 --version  # Should show 3.10 or higher
```

### Package Not Found
```bash
python3.10 -m pip install pocket-tts scipy --user
```

### Permission Denied
```bash
chmod +x generate_female_voices.py
```

### First Run is Slow
The first time you run the script, it will download the TTS model and voice embeddings from HuggingFace. This is normal and only happens once. Subsequent runs will be much faster.

## Technical Details

- **Model**: Kyutai PocketTTS (100M parameters)
- **Sample Rate**: 24kHz
- **Format**: WAV (PCM)
- **Latency**: ~200ms for first audio chunk
- **Speed**: ~6x real-time on MacBook Air M4
- **CPU Cores**: Uses only 2 CPU cores
- **Language**: English only (more languages planned)

## Voice Cloning

You can also use custom voice files for voice cloning:

```python
from pocket_tts import TTSModel
import scipy.io.wavfile

tts_model = TTSModel.load_model()
voice_state = tts_model.get_state_for_audio_prompt("./my_voice.wav")
audio = tts_model.generate_audio(voice_state, "Hello world!")
scipy.io.wavfile.write("output.wav", tts_model.sample_rate, audio.numpy())
```

## Integration with Miko

To use these voices with the Miko character:

1. Generate voices with your desired text
2. Choose your favorite voice
3. Use the audio file with `lip_sync_tts.py` or other lip-sync scripts

```bash
# Generate voices
python3.10 generate_female_voices.py --text "Hello, I am Miko!"

# Use with lip-sync (example)
python3 lip_sync_tts.py --audio ./female_voices_output/alba.wav
```

## Resources

- 🔊 [Demo](https://kyutai.org/pocket-tts)
- 🐱‍💻 [GitHub Repository](https://github.com/kyutai-labs/pocket-tts)
- 🤗 [HuggingFace Model Card](https://huggingface.co/kyutai/pocket-tts)
- 📄 [Paper](https://arxiv.org/abs/2501.00123)
- 📚 [Documentation](https://kyutai-labs.github.io/pocket-tts/)

## License

This script uses Kyutai's PocketTTS. Please respect voice model licenses and prohibited uses (no impersonation without consent, no misinformation, etc.).
