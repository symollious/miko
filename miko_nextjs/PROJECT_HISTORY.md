# Miko Lip-Sync Project History

## Overview
Building a real-time lip-sync animation website for the Miko character with sub-200ms response time target.

## System Architecture
- **Frontend**: Next.js (React) - 70% video panel, 30% chat panel, cream/light theme
- **Backend**: FastAPI Python server
- **AI**: Groq (llama-3.1-8b-instant) for chat responses
- **TTS**: edge-tts (fallback) / pocket-tts (local, faster when available)
- **Character Directory**: `/Users/sahaj/Desktop/termux/miko_character/`
  - `listening.mp4` - idle/closed mouth pose
  - `speaking1.mp4` - speaking animation (various mouth positions)
  - `stanby.mp4` - fallback idle video

---

## Attempt 1: Simple Video Loop (Initial Implementation)
**Date**: Earlier attempts

### Approach
- Loop `speaking1.mp4` video
- Mux TTS audio over it using ffmpeg
- No actual lip-sync - just synchronized audio/video playback

### Implementation
```python
ffmpeg -stream_loop -1 -i speaking1.mp4 -i audio.mp3 -t <duration> -c:v libx264 -c:a aac output.mp4
```

### Results
- **Video Generation Time**: ~500ms-1s ✓ FAST
- **Lip-Sync Quality**: ❌ NONE - mouth moves randomly, not synced to audio
- **Smoothness**: ✓ Smooth (pre-encoded video)

### Verdict
Too fast but no actual lip-sync. Mouth animation doesn't match speech.

---

## Attempt 2: Volume-Based Mouth Overlay
**Date**: Previous session

### Approach
- Extract 3 mouth states from videos: CLOSED, HALF-OPEN, FULL-OPEN
- Analyze audio volume per frame
- Overlay correct mouth PNG onto base idle frame

### Implementation
```python
# Extract mouth regions
def _extract_mouth_frame(video, time):
    frame = extract_frame(video, time)
    return crop_to_mouth_region(frame)

# Map volume to mouth state
if volume < 0.25: use_closed_mouth()
elif volume < 0.6: use_half_mouth()
else: use_open_mouth()

# Overlay on each frame
frame.paste(mouth_img, (x, y))
```

### Results
- **Video Generation Time**: ~2-3s per response
- **Lip-Sync Quality**: ⚠️ Has basic correlation to audio
- **Visual Artifacts**: ❌ BLACK BOX around mouth - cropped region has hard edges
- **Smoothness**: ❌ CHOPPY - jumps between 3 discrete states

### Problems
1. **Black box artifact**: PNG overlay shows rectangular background
2. **Choppy transitions**: Only 3 states, no blending
3. **Position drift**: Mouth overlay doesn't align perfectly with face

### Verdict
Technically "syncs" but looks terrible with black box. Abandoned.

---

## Attempt 3: Full-Frame Viseme Cross-Fading
**Date**: Previous session

### Approach
- Extract 3 FULL poses (not just mouths): closed, half, fully open
- Cross-fade between full frames based on volume
- No cropping, no overlays - full frame blending

### Implementation
```python
poses = {
    'closed': extract_full_frame(listening.mp4, 0.0),
    'half': extract_full_frame(speaking1.mp4, middle),
    'open': extract_full_frame(speaking1.mp4, peak)
}

# Blend based on volume
if alpha < 0.5:
    blended = closed * (1-t) + half * t
else:
    blended = half * (1-t) + full * t
```

### Results
- **Video Generation Time**: ~20s per response
- **Lip-Sync Quality**: ⚠️ Better - smooth transitions
- **Visual Artifacts**: ✓ None - full frames
- **Smoothness**: ⚠️ Smooth blending but WHOLE FACE moves, not just mouth

### Problems
1. **Shaking**: Whole body/head moves, not just mouth
2. **Too slow**: 20s is unacceptable for real-time
3. **Unnatural**: Face "morphs" between completely different poses

### Verdict
Looks smoother but whole character shakes. Too slow. Abandoned.

---

## Attempt 4: Timestamp-Based Frame Selection
**Date**: Previous session

### Approach
- Map audio volume to timestamp in speaking video
- Volume 0 → use frame at t=0.2s (closed mouth)
- Volume 1 → use frame at t=3.5s (open mouth)
- Extract frame at calculated timestamp for each frame of output

### Implementation
```python
def volume_to_timestamp(vol):
    if vol < 0.2: return vol * 0.2 * duration
    elif vol < 0.7: return (0.2 + t * 0.4) * duration
    else: return (0.6 + t * 0.2) * duration

for each frame:
    ts = volume_to_timestamp(audio_volume[i])
    extract_frame(speaking_video, ts) → output_frame[i]
```

### Results
- **Video Generation Time**: ~100s per response ❌ EXTREMELY SLOW
- **Lip-Sync Quality**: ✓ BEST - actual frame from speaking video
- **Visual Artifacts**: ✓ None - natural frames
- **Smoothness**: ❌ CHOPPY - jumps between timestamps

### Problems
1. **Extremely slow**: Extracting each frame individually with ffmpeg
2. **Still choppy**: Discrete timestamp jumps, no interpolation
3. **Not real-time**: 100s for 6s video is useless

### Verdict
Best lip-sync quality but unusably slow. Abandoned.

---

## Attempt 5: Post-Processing Smoothing
**Date**: Current session

### Approach
- Take the choppy lip-sync video
- Apply motion interpolation to smooth frame transitions

### Methods Tried

#### 5a: Motion Interpolation (minterpolate)
```bash
ffmpeg -i choppy.mp4 -vf "minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc" smooth.mp4
```
**Time**: 96 seconds for 6s video  
**Result**: Smooth but too slow for real-time

#### 5b: Fast Frame Blending
```bash
ffmpeg -i choppy.mp4 -vf "fps=60,blend=all_mode=average" smooth.mp4
```
**Time**: 0.4 seconds  
**Result**: Failed - filter complexity error

#### 5c: Temporal Blend
```bash
ffmpeg -i choppy.mp4 -vf "tblend=average,framestep=2" smooth.mp4
```
**Time**: 0.4 seconds  
**Result**: Wrong duration (compressed to 1.5s)

### Verdict
Post-processing can smooth but either:
- Too slow for real-time (motion interpolation)
- Doesn't work correctly (fast methods)

---

## Current Status (Fast Mode - Working)

### Implementation
Reverted to **Attempt 1** (simple video loop) for speed:

```python
def _make_video_with_audio(audio_path, duration):
    ffmpeg -stream_loop -1 -i speaking1.mp4 -i audio_path -t duration output.mp4
```

### Current Stack
- **Groq AI**: ~300ms response
- **edge-tts**: ~2-5s audio generation
- **Video**: ~500ms (ffmpeg mux only)
- **Total**: ~3-6s end-to-end

### What's Working
- ✓ Fast response (<6s total)
- ✓ Audio plays correctly
- ✓ Video is smooth (pre-encoded)
- ✓ No visual artifacts
- ✓ Idle video (`listening.mp4`) plays when not speaking

### What's NOT Working
- ❌ **NO REAL LIP-SYNC** - mouth animation doesn't match speech
- ❌ Video just loops randomly, not driven by audio

---

## Technical Constraints Discovered

### 1. The 200ms Target is Impossible for Real Lip-Sync
| Component | Minimum Time | Can Optimize? |
|-----------|-------------|---------------|
| LLM (Groq) | ~300ms | ✓ Already fast |
| TTS (local) | ~500ms | ✓ pocket-tts |
| **Video Generation** | **~2-3s minimum** | ❌ Frame processing required |
| **With Real Lip-Sync** | **~3-5s** | ❌ Physics limitation |

**Conclusion**: 200ms total is impossible with any real lip-sync technique.

### 2. Real Lip-Sync Requires Frame-by-Frame Processing
- Must analyze audio → determine mouth shape → generate/overlay frame
- Each frame needs: decode, process, encode
- 30fps × 6s = 180 frames minimum
- Even at 10ms/frame = 1.8s + overhead = 3-5s realistic minimum

### 3. Discrete States Cause Choppiness
- 3 mouth states = noticeable jumps
- 10+ mouth states = smoother but slower extraction
- Continuous morphing = best but computationally expensive

### 4. Overlay vs Full Frame Trade-off
| Method | Speed | Quality | Artifacts |
|--------|-------|---------|-----------|
| Overlay mouths | Fast | Poor | Black box |
| Full frame blend | Slow | Medium | Whole face moves |
| Timestamp select | Very slow | Best | Choppy |
| Pre-encoded loop | Very fast | None | None |

---

## Unexplored Options

### 1. Pre-Render Cache (Instant Response)
- Generate 100-1000 common responses offline
- Store video + audio
- At runtime: pick closest match, stream instantly
- **Time**: <100ms (just file serving)
- **Limitation**: Fixed response set, can't handle arbitrary input

### 2. GPU-Based Lip-Sync (Wav2Lip)
- Use trained AI model (Wav2Lip, VideoRetalking)
- Input: audio + reference frame → Output: lip-sync video
- **Time**: ~1-2s on GPU, ~10s+ on CPU
- **Requirement**: GPU + ML model setup
- **Status**: Not attempted - requires CUDA/GPU

### 3. Higher Frame Rate + Blended States
- Extract 10+ mouth positions from speaking video
- Cross-fade between adjacent states (not jump)
- **Time**: ~5-10s (more frames to process)
- **Quality**: Better than 3 states
- **Status**: Not implemented

### 4. WebGL/Shader-Based (Client-Side)
- Do lip-sync in browser using WebGL shaders
- Server sends: mouth textures + audio + timing data
- Client composites in real-time
- **Time**: Server ~1s, client real-time
- **Requirement**: Complex frontend implementation
- **Status**: Not attempted

---

## File Structure

```
miko_nextjs/
├── app/
│   ├── page.jsx              # Main UI (70% video, 30% chat)
│   ├── api/respond/route.js  # Proxy to Python backend
│   └── layout.jsx
├── backend/
│   ├── main.py               # FastAPI server (current: fast mode)
│   ├── mouth_lipsync.py      # Attempt 2 (overlay - abandoned)
│   ├── viseme_lipsync.py     # Attempt 3 (full frame blend - abandoned)
│   ├── real_lipsync.py       # Attempt 2 refined (overlay v2 - abandoned)
│   ├── timestamp_lipsync.py   # Attempt 4 (timestamp select - abandoned)
│   └── fast_lipsync.py        # Attempt 2 with ffmpeg (abandoned)
├── public/
│   ├── generated/            # Output videos
│   └── smooth_test/          # Post-processing experiments
└── PROJECT_HISTORY.md        # This file
```

---

## Key Learnings

1. **Real lip-sync is computationally expensive** - can't be done in <3s on CPU
2. **Discrete mouth states cause choppiness** - need continuous variation
3. **Overlay techniques have artifacts** - black boxes, misalignment
4. **Full-frame blending causes shaking** - whole face moves unnaturally
5. **Pre-encoded loops are smooth but not synced** - quality vs speed trade-off
6. **Post-processing smoothing is too slow** - 96s for 6s video

---

## Recommendations

### For Production (Fast, Acceptable Quality)
- **Use current fast mode** (simple video loop)
- **Accept no real lip-sync**
- **Focus on other UX improvements** (faster TTS, better UI)

### For Quality Demo (Slow but Impressive)
- **Use timestamp-based method** (Attempt 4)
- **Pre-render responses** (cache common phrases)
- **Accept 10-30s generation time** for wow factor

### For Real-Time Lip-Sync (Future Work)
- **Needs GPU** (Wav2Lip or similar)
- **Or client-side rendering** (WebGL shaders)
- **Or pre-rendered cache** (limited responses)

---

## Attempt 6: FrameCache + Volume-to-Timestamp Mapping
**Date**: May 1, 2025 (Session 2)

### Approach
- Pre-load ALL frames from speaking1.mp4 and listening.mp4 into memory (~151 frames each)
- Analyze audio volume per frame using ffmpeg silencedetect
- Map volume (0-1) to frame index using non-linear curve (from Attempt 4's algorithm)
- Select appropriate full frame from cache based on volume
- Encode selected frames into final video with ffmpeg

### Implementation
```python
class FrameCache:
    # Pre-loads all video frames into RAM as PNG bytes
    def _extract_frames(self, video_path, target_size=(1280, 720)):
        ffmpeg → extract all frames → store in list[bytes]

class LipSyncGenerator:
    # Maps volume to frame selection
    def volume_to_frame_index(self, volume, num_frames):
        if volume < 0.2: t_ratio = volume * 0.2
        elif volume < 0.7: t_ratio = 0.2 + ((volume - 0.2)/0.5) * 0.4
        else: t_ratio = 0.6 + ((volume - 0.7)/0.3) * 0.2
        return int(t_ratio * (num_frames - 1))
```

### Results
- **Generation Time**: ~1.16s for 11s video ✓ FAST (290 fps processing)
- **Lip-Sync Quality**: ✓ Volume-to-mouth mapping is accurate
- **Smoothness**: ❌ **CHOPPY** - each frame is a different full pose from the speaking video
- **Visual Artifacts**: ❌ **Whole character jumps around** because frames are from different positions in the animation

### Problems
1. **Choppy**: Jumping between frame 10, frame 80, frame 30 etc. causes the entire character body/hair/eyes to change position each frame
2. **Full-frame selection = full-body movement**: Can't just change the mouth; the whole character shifts
3. speaking1.mp4 and listening.mp4 have different resolutions (1088x1920 vs 1450x2560) causing additional visual discontinuities

### Verdict
Syncing algorithm is perfect but full-frame swapping makes the video unwatchably choppy. The underlying problem is **you can't pick random frames from a pre-recorded video and expect smooth playback** — the non-mouth parts of the character shift around.

---

## Attempt 7: Mouth-Only Overlay with ffmpeg (Revisited)
**Date**: May 1, 2025 (Session 2)

### Approach
Same idea as Attempt 2 but with better mouth extraction:
- Extract 5 mouth sprites (closed, slight, half, open, wide) from speaking1.mp4
- Create a mouth-only video stream from these sprites based on volume
- Use ffmpeg overlay filter to paste mouth video onto smooth listening.mp4 base

### Problems (Why Not Pursued Further)
1. **Resolution mismatch**: speaking1.mp4 is 1088x1920, listening.mp4 is 1450x2560 — mouth position and scale don't match perfectly
2. **Edge blending**: Rectangular mouth crop has hard edges that are visible against the face
3. **Still requires video encoding**: Even with overlay, ffmpeg must re-encode the entire video, adding latency
4. **Positioning fragility**: Exact pixel coordinates of the mouth shift between frames of the animated character

### Verdict
Overlay approach has fundamental issues with edge artifacts and resolution mismatches. Abandoned in favor of client-side approach.

---

## Attempt 8: Client-Side Real-Time Lip Sync (CURRENT - WORKING)
**Date**: May 1, 2025 (Session 2)

### Approach — Completely Different Architecture
**Key Insight**: Stop generating videos server-side entirely. Do the lip sync in the browser.

This is how VTubers actually work:
1. **Server** generates TTS audio only → saves to /generated/ → returns audio URL
2. **Frontend** plays smooth `listening.mp4` on loop (never re-encoded, always smooth)
3. **Frontend** plays the audio using HTML Audio element
4. **Web Audio API AnalyserNode** reads real-time volume from the audio stream
5. **Canvas overlay** draws the correct mouth sprite image on top of the character's mouth
6. **requestAnimationFrame** drives the animation at 60fps

### Implementation

**Backend** (main.py):
```python
@app.post("/respond")
async def respond(inp):
    ai_text = groq_chat(inp.text)      # ~300ms
    audio_url = await generate_tts(ai_text)  # ~2-5s
    # NO VIDEO GENERATION!
    return {"text": ai_text, "audio_url": audio_url}
```

**Frontend** (page.jsx):
```javascript
// Web Audio API for real-time volume
const source = audioContext.createMediaElementSource(audio);
const analyser = audioContext.createAnalyser();
source.connect(analyser).connect(audioContext.destination);

// Animation loop at 60fps
function animate() {
    analyser.getByteFrequencyData(dataArray);
    const volume = calculateVolume(dataArray);  // 0-1
    const mouthIdx = volumeToMouthState(volume); // 0-4
    drawMouthSprite(mouthIdx); // overlay on canvas
    requestAnimationFrame(animate);
}
```

**Mouth Sprites**: 5 states extracted from speaking1.mp4:
- `closed.png` - mouth closed (t=0.0s)
- `slight.png` - barely open (t=0.8s)
- `half.png` - half open (t=1.8s)
- `open.png` - open (t=2.8s)
- `wide.png` - wide open (t=3.8s)

### Results
- **Video Generation Time**: **0ms** — no video generation needed!
- **Total Response Time**: ~2-5s (LLM + TTS only)
- **Lip-Sync Quality**: ✓ Real-time volume tracking with smooth transitions
- **Smoothness**: ✓ **PERFECTLY SMOOTH** — base video never re-encoded
- **Frame Rate**: 60fps lip sync (browser native)
- **Visual Artifacts**: Needs tuning of mouth sprite position/scale

### Advantages
1. **Zero video processing** — server only does LLM + TTS
2. **Perfectly smooth base animation** — listening.mp4 plays natively in browser
3. **True real-time** — mouth updates every frame (16.6ms at 60fps)
4. **No choppiness** — base video is never interrupted or re-encoded
5. **Instant feedback** — mouth starts moving the instant audio starts

### What Needs Tuning
- Mouth sprite positioning (CSS coordinates on the canvas overlay)
- Mouth sprite scale to match the face in different viewport sizes
- Edge blending / feathering of mouth sprites to eliminate hard edges
- Volume threshold calibration for different TTS voices

---

## Current Active Servers

```
Frontend: http://localhost:3001 (Next.js)
Backend:  http://localhost:8002 (FastAPI)
```

**Current Mode**: Client-side real-time lip sync (Web Audio API + Canvas overlay)

---

## Attempt 9: Timed-Viseme Web Audio Sync (CURRENT)
**Date**: May 2, 2026

### Approach
Keep the successful client-side architecture, but replace raw volume tracking with a timed viseme schedule:
- Backend asks `edge-tts` for `WordBoundary` metadata while generating MP3 audio
- Backend converts word timings into lightweight phoneme-like mouth openness events
- Frontend unlocks a Web Audio context immediately on the user's click, then plays the decoded TTS buffer after the async LLM/TTS response returns
- Frontend drives mouth sprites from `audioContext.currentTime + 75ms lookahead`
- Two mouth sprite layers are cross-faded for smoother in-between shapes

### Why This Is Better
- **Server video generation remains 0ms**
- **Playback-side lip sync is <1 frame latency** once audio starts
- Word-boundary timing beats raw volume for consonants and silence
- Web Audio avoids browser autoplay failures caused by calling `audio.play()` after the async response delay
- The base video remains native/hardware accelerated and smooth

### Verified Results
- Production build passes
- FastAPI backend returns `visemes` alongside `audio_url`
- Playwright visual check confirmed mouth opacity/sprite changes while status is `Speaking...`
- Mouth close-up showed aligned open/closed transitions with no rectangular overlay box
- Desktop and narrow mobile layouts verified

### Alignment Fix
May 2, 2026 follow-up:
- Replaced full face-patch mouth sprites with normalized transparent mouth-only sprites in `public/mouths/clean/`
- Shrank the overlay from `250x90` to `140x72` and re-anchored it to the detected mouth center
- Removed the openness-based vertical translate that made the mouth bob between frames
- Verified in the in-app browser with close-up screenshots during `Speaking...`

### Micro Alignment Nudge
May 2, 2026 follow-up:
- Nudged the clean mouth overlay anchor slightly left/up from `718,852` to `715,844`
- Kept the sprite size and smoothing unchanged so only the mouth placement moves

### Close-Up Mouth Polish
May 2, 2026 follow-up:
- Kept the user-tuned mouth anchor at `740,840`
- Increased the mouth overlay from `140x72` to `148x76` for a barely larger close-up shape
- Reduced lip-sync lookahead from `75ms` to `15ms` and softened easing so the mouth no longer leads the voice
- Added a feathered skin-tone mouth cover behind the sprites to hide the original closed-mouth line during speech

### Current Active Servers

```
Frontend: http://localhost:3001 (Next.js)
Backend:  http://localhost:8002 (FastAPI)
```

**Current Mode**: Timed-viseme client-side lip sync (edge-tts word timings + Web Audio + feathered mouth overlay)

---

## Pocket TTS Voice Fix
**Date**: May 4, 2026

- Fixed Pocket TTS voice selection by sending `voice_url=eponine` to `/tts`
- Kept `POCKET_TTS_VOICE=eponine` as the preferred environment variable, with `TTS_VOICE` still supported as fallback
- This avoids Pocket TTS falling back to its default `alba` voice when the old unsupported `voice` field is ignored

---

## Pause-Aware Lip Sync
**Date**: May 4, 2026

- Added WAV energy analysis for Pocket TTS output to detect real voiced speech segments
- Fallback word/viseme timing now distributes mouth motion only inside voiced segments instead of across the full audio duration
- Frontend now gates mouth openness with `speech_segments`, so breath pauses and silent gaps close the mouth
- Verified `/api/respond` returns multiple speech segments for a phrase with a pause

---

## Solid Mouth Opacity Polish
**Date**: May 4, 2026

- Added `public/mouths/solid/` sprites with stronger mouth pixels and reduced semi-transparent fringe
- Switched the frontend mouth overlay from `clean` sprites to `solid` sprites
- Tightened the skin-tone cover so it hides the original mouth line without showing a visible face patch

---

*Last Updated: May 4, 2026*
