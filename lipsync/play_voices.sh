#!/bin/bash
# Play all female voices in sequence for comparison

echo "🎤 Playing All Female Voices"
echo "=============================="
echo ""

VOICES_DIR="./female_voices_output"

if [ ! -d "$VOICES_DIR" ]; then
    echo "❌ Error: $VOICES_DIR not found"
    echo "Run: python3.10 generate_female_voices.py first"
    exit 1
fi

for voice in alba fantine cosette eponine azelma; do
    wav_file="$VOICES_DIR/${voice}.wav"
    
    if [ -f "$wav_file" ]; then
        echo "🔊 Playing: $voice"
        afplay "$wav_file"
        echo "   ✓ Finished"
        echo ""
    else
        echo "⚠️  Skipping: $voice (file not found)"
    fi
done

echo "=============================="
echo "✅ All voices played!"
echo ""
echo "Which voice did you like best?"
echo "  • alba - Clear, natural"
echo "  • fantine - Expressive"
echo "  • cosette - Soft, gentle"
echo "  • eponine - Dynamic"
echo "  • azelma - Warm"
