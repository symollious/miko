'use client';

import { useEffect, useMemo, useRef, useState, useCallback } from 'react';

// Mouth sprite filenames - 5 states from closed to wide open
const MOUTH_SPRITES = [
  '/mouths/solid/closed.png?v=2',
  '/mouths/solid/slight.png?v=2',
  '/mouths/solid/half.png?v=2',
  '/mouths/solid/open.png?v=2',
  '/mouths/solid/wide.png?v=2',
];

const VIDEO_SIZE = { width: 1450, height: 2560 };
const MOUTH_SIZE = { width: 140, height: 72 };
const MOUTH_ANCHOR = { x: 740, y: 845 };
const LIP_SYNC_LOOKAHEAD_SECONDS = 0.015;

const POCKET_TTS_WORKER_URL = 'https://kevinahm-pocket-tts-web.static.hf.space/inference-worker.js';
const POCKET_TTS_VOICE = 'eponine';

function getContainedVideoRect(panelRect) {
  const panelAspect = panelRect.width / panelRect.height;
  const videoAspect = VIDEO_SIZE.width / VIDEO_SIZE.height;

  if (panelAspect > videoAspect) {
    const height = panelRect.height;
    const width = height * videoAspect;
    return {
      left: (panelRect.width - width) / 2,
      top: 0,
      width,
      height,
    };
  }

  const width = panelRect.width;
  const height = width / videoAspect;
  return {
    left: 0,
    top: (panelRect.height - height) / 2,
    width,
    height,
  };
}

function getMouthRect(panel) {
  const panelRect = panel.getBoundingClientRect();
  const videoRect = getContainedVideoRect(panelRect);
  const scaleX = videoRect.width / VIDEO_SIZE.width;
  const scaleY = videoRect.height / VIDEO_SIZE.height;

  return {
    left: videoRect.left + (MOUTH_ANCHOR.x - MOUTH_SIZE.width / 2) * scaleX,
    top: videoRect.top + (MOUTH_ANCHOR.y - MOUTH_SIZE.height / 2) * scaleY,
    width: MOUTH_SIZE.width * scaleX,
    height: MOUTH_SIZE.height * scaleY,
  };
}

function scheduleOpenAt(visemes, timeSeconds) {
  if (!Array.isArray(visemes) || visemes.length === 0) return 0;

  for (let i = 0; i < visemes.length; i += 1) {
    const item = visemes[i];
    const start = Number(item.t) || 0;
    const duration = Math.max(Number(item.d) || 0, 0.001);
    const end = start + duration;

    if (timeSeconds < start) return 0;
    if (timeSeconds <= end) {
      const open = Number(item.open) || 0;
      const nextOpen = Number(visemes[i + 1]?.open ?? 0);
      const progress = (timeSeconds - start) / duration;

      if (progress > 0.68) {
        const blend = (progress - 0.68) / 0.32;
        return open + (nextOpen - open) * Math.min(1, Math.max(0, blend));
      }

      return open;
    }
  }

  return 0;
}

function speechGateAt(speechSegments, timeSeconds) {
  if (!Array.isArray(speechSegments) || speechSegments.length === 0) return 1;

  const fadeSeconds = 0.035;

  for (let i = 0; i < speechSegments.length; i += 1) {
    const segment = speechSegments[i];
    const start = Number(segment.t ?? segment.start ?? 0);
    const duration = Number(segment.d ?? segment.duration ?? 0);
    const end = Number(segment.end ?? start + duration);

    if (timeSeconds < start - fadeSeconds) return 0;

    if (timeSeconds <= end + fadeSeconds) {
      const fadeIn = Math.min(1, Math.max(0, (timeSeconds - start + fadeSeconds) / fadeSeconds));
      const fadeOut = Math.min(1, Math.max(0, (end + fadeSeconds - timeSeconds) / fadeSeconds));
      return Math.min(fadeIn, fadeOut);
    }
  }

  return 0;
}

function clamp01(value) {
  return Math.max(0, Math.min(1, value));
}

export default function HomePage() {
  const idleVideoRef = useRef(null);
  const videoPanelRef = useRef(null);
  const isSpeakingRef = useRef(false);

  const pocketWorkerRef = useRef(null);
  const pocketReadyRef = useRef(false);
  const pocketSampleRateRef = useRef(24000);
  const mouthARef = useRef(null);
  const mouthBRef = useRef(null);
  const audioContextRef = useRef(null);
  const sourceRef = useRef(null);
  const animationRef = useRef(null);
  const lipStateRef = useRef({ open: 0, low: -1, high: -1 });

  const [connected, setConnected] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [latencyMs, setLatencyMs] = useState('--');
  const [timingsText, setTimingsText] = useState('');
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState([]);
  const [mouthRect, setMouthRect] = useState(null);

  const statusText = useMemo(() => {
    if (!connected) return '● Disconnected';
    if (speaking) return '● Speaking...';
    if (processing) return '● Processing...';
    return '● Connected';
  }, [connected, processing, speaking]);

  // Setup idle video - plays natively, no canvas, no interference
  useEffect(() => {
    setConnected(true);
    const idle = idleVideoRef.current;
    if (!idle) return;
    idle.src = '/character/gen2.mp4';
    idle.preload = 'auto';
    idle.loop = true;
    idle.muted = true;
    idle.playsInline = true;
    idle.play().catch(() => {});
  }, []);

  const ensurePocketTtsReady = useCallback(async () => {
    if (pocketReadyRef.current) return;
    if (pocketWorkerRef.current) {
      await new Promise((resolve) => {
        const check = () => {
          if (pocketReadyRef.current) resolve();
          else setTimeout(check, 50);
        };
        check();
      });
      return;
    }

    const worker = new Worker(POCKET_TTS_WORKER_URL, { type: 'module' });
    pocketWorkerRef.current = worker;

    await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error('Pocket-TTS load timeout')), 180000);
      worker.onmessage = (e) => {
        const msg = e.data;
        if (msg?.type === 'bundle_loaded') {
          if (typeof msg.sampleRate === 'number') pocketSampleRateRef.current = msg.sampleRate;
        }
        if (msg?.type === 'loaded' || msg?.type === 'voices_loaded') {
          pocketReadyRef.current = true;
          clearTimeout(timeout);
          try {
            worker.postMessage({ type: 'set_voice', data: { voiceName: POCKET_TTS_VOICE } });
          } catch {}
          resolve();
        }
        if (msg?.type === 'error') {
          clearTimeout(timeout);
          reject(new Error(String(msg.error || 'Pocket-TTS worker error')));
        }
      };
      worker.postMessage({ type: 'load' });
    });
  }, []);

  const float32ToWavBlob = useCallback((samples, sampleRate) => {
    const numChannels = 1;
    const bitsPerSample = 16;
    const blockAlign = (numChannels * bitsPerSample) / 8;
    const byteRate = sampleRate * blockAlign;
    const dataSize = samples.length * 2;
    const buffer = new ArrayBuffer(44 + dataSize);
    const view = new DataView(buffer);

    const writeString = (offset, str) => {
      for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
    };

    writeString(0, 'RIFF');
    view.setUint32(4, 36 + dataSize, true);
    writeString(8, 'WAVE');
    writeString(12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, numChannels, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, byteRate, true);
    view.setUint16(32, blockAlign, true);
    view.setUint16(34, bitsPerSample, true);
    writeString(36, 'data');
    view.setUint32(40, dataSize, true);

    let offset = 44;
    for (let i = 0; i < samples.length; i++) {
      const s = Math.max(-1, Math.min(1, samples[i]));
      view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
      offset += 2;
    }

    return new Blob([buffer], { type: 'audio/wav' });
  }, []);

  const generatePocketTtsWavUrl = useCallback(async (text) => {
    await ensurePocketTtsReady();
    const worker = pocketWorkerRef.current;
    const sampleRate = pocketSampleRateRef.current;

    const chunks = [];

    await new Promise((resolve, reject) => {
      const onMessage = (e) => {
        const msg = e.data;
        if (!msg) return;

        if (msg.type === 'audio_chunk' && msg.data) {
          chunks.push(new Float32Array(msg.data));
        }

        if (msg.type === 'stream_ended') {
          worker.removeEventListener('message', onMessage);
          resolve();
        }

        if (msg.type === 'error') {
          worker.removeEventListener('message', onMessage);
          reject(new Error(String(msg.error || 'Pocket-TTS generate error')));
        }
      };

      worker.addEventListener('message', onMessage);
      worker.postMessage({ type: 'generate', data: { text, voice: POCKET_TTS_VOICE } });
    });

    const total = chunks.reduce((n, c) => n + c.length, 0);
    const merged = new Float32Array(total);
    let cursor = 0;
    for (const c of chunks) {
      merged.set(c, cursor);
      cursor += c.length;
    }

    const blob = float32ToWavBlob(merged, sampleRate);
    const url = URL.createObjectURL(blob);
    const duration = merged.length / sampleRate;
    return { url, duration };
  }, [ensurePocketTtsReady, float32ToWavBlob]);

  useEffect(() => {
    MOUTH_SPRITES.forEach((src) => {
      const image = new Image();
      image.src = src;
    });
  }, []);

  useEffect(() => {
    const panel = videoPanelRef.current;
    if (!panel) return undefined;

    const update = () => setMouthRect(getMouthRect(panel));
    update();

    let observer;
    if (typeof ResizeObserver !== 'undefined') {
      observer = new ResizeObserver(update);
      observer.observe(panel);
    }

    window.addEventListener('resize', update);
    return () => {
      window.removeEventListener('resize', update);
      if (observer) observer.disconnect();
    };
  }, []);

  const paintMouth = useCallback((targetOpen) => {
    const state = lipStateRef.current;
    const target = clamp01(targetOpen);
    const rate = target > state.open ? 0.18 : 0.12;
    state.open += (target - state.open) * rate;

    if (state.open < 0.015) state.open = 0;

    const scaled = state.open * (MOUTH_SPRITES.length - 1);
    const low = Math.max(0, Math.min(MOUTH_SPRITES.length - 1, Math.floor(scaled)));
    const high = Math.max(0, Math.min(MOUTH_SPRITES.length - 1, Math.ceil(scaled)));
    const mix = high === low ? 0 : scaled - low;
    const baseOpacity = state.open > 0.01 ? 1 : 0;
    const coverOpacity = Math.min(0.78, Math.max(0, (state.open - 0.005) * 1.45));

    const cover = mouthCoverRef.current;
    const a = mouthARef.current;
    const b = mouthBRef.current;
    if (!a || !b) return;

    if (state.low !== low) {
      a.src = MOUTH_SPRITES[low];
      state.low = low;
    }

    if (state.high !== high) {
      b.src = MOUTH_SPRITES[high];
      state.high = high;
    }

    if (cover) {
      cover.style.opacity = String(coverOpacity);
    }

    a.style.opacity = String((1 - mix) * baseOpacity);
    b.style.opacity = String(mix * baseOpacity);
    // Scale based on openness (1.0 = normal)
    const hScale = 1 + (state.open * 0.35);
    const vScale = 1.5 + (state.open * 0.25);
    const transform = `translateZ(0) scaleX(${hScale.toFixed(3)}) scaleY(${vScale.toFixed(3)})`;
    a.style.transform = transform;
    b.style.transform = transform;
  }, []);

  const unlockAudio = useCallback(async () => {
    if (typeof window === 'undefined') return null;

    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return null;

    if (!audioContextRef.current) {
      audioContextRef.current = new AudioContextClass();
    }

    const context = audioContextRef.current;
    if (context.state === 'suspended') {
      await context.resume();
    }

    const silent = context.createBuffer(1, 1, 22050);
    const source = context.createBufferSource();
    source.buffer = silent;
    source.connect(context.destination);
    source.start(0);

    return context;
  }, []);

  const stopLipSync = useCallback(() => {
    if (animationRef.current) {
      cancelAnimationFrame(animationRef.current);
      animationRef.current = null;
    }

    if (sourceRef.current) {
      try {
        sourceRef.current.stop();
      } catch {
        // The source may already have ended.
      }
      sourceRef.current.disconnect();
      sourceRef.current = null;
    }

    lipStateRef.current.open = 0;
    paintMouth(0);
    setSpeaking(false);
  }, [paintMouth]);

  const playSyncedAudio = useCallback(
    async (audioUrl, visemes, speechSegments) => {
      stopLipSync();

      const context = await unlockAudio();
      if (!context) return;

      const audioBuffer = await fetch(audioUrl)
        .then((res) => {
          if (!res.ok) throw new Error(`Audio fetch failed: ${res.status}`);
          return res.arrayBuffer();
        })
        .then((buffer) => context.decodeAudioData(buffer));

      const source = context.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(context.destination);
      sourceRef.current = source;

      await new Promise((resolve) => {
        let done = false;
        const startAt = context.currentTime + 0.02;

        const finish = () => {
          if (done) return;
          done = true;
          stopLipSync();
          resolve();
        };

        const animate = () => {
          const elapsed = Math.max(0, context.currentTime - startAt);
          const syncTime = elapsed + LIP_SYNC_LOOKAHEAD_SECONDS;
          const target = scheduleOpenAt(visemes, syncTime) * speechGateAt(speechSegments, syncTime);
          paintMouth(target);

          if (!done) {
            animationRef.current = requestAnimationFrame(animate);
          }
        };

        source.onended = finish;
        setSpeaking(true);
        animationRef.current = requestAnimationFrame(animate);
        source.start(startAt);
      });
    },
    [paintMouth, stopLipSync, unlockAudio]
  );

  const [audioQueue, setAudioQueue] = useState([]);
  const isPlayingRef = useRef(false);

  useEffect(() => {
    const processQueue = async () => {
      if (isPlayingRef.current || audioQueue.length === 0) return;
      isPlayingRef.current = true;
      
      const chunk = audioQueue[0];
      await playSyncedAudio(
        chunk.audio_url,
        chunk.visemes || [],
        chunk.speech_segments || []
      );
      
      setAudioQueue(prev => prev.slice(1));
      isPlayingRef.current = false;
    };
    processQueue();
  }, [audioQueue, playSyncedAudio]);

  const send = () => {
    const text = input.trim();
    if (!text) return;
    if (processing) return;

    const audioReady = unlockAudio().catch(() => null);

    setProcessing(true);
    setMessages((m) => [...m, { sender: 'user', text }]);
    setMessages((m) => [...m, { sender: 'ai', text: 'Generating...' }]);
    setInput('');
    setAudioQueue([]); // Clear old queue

    (async () => {
      try {
        const res = await fetch('/api/respond', {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ text, history: messages }),
        });

        if (!res.ok) {
          let errText = `Backend error (${res.status})`;
          try {
            const err = await res.json();
            if (err?.error) errText = String(err.error);
          } catch {
            // ignore
          }

          setConnected(false);
          setMessages((m) => {
            const next = [...m];
            const idx = next.findIndex((x) => x.sender === 'ai' && x.text === 'Generating...');
            if (idx !== -1) next.splice(idx, 1);
            next.push({ sender: 'ai', text: errText });
            return next;
          });
          setProcessing(false);
          return;
        }

        setConnected(true);
        await audioReady;

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          
          buffer += decoder.decode(value, { stream: true });
          
          let eolIndex;
          while ((eolIndex = buffer.indexOf('\n')) >= 0) {
            const line = buffer.slice(0, eolIndex).trim();
            buffer = buffer.slice(eolIndex + 1);
            if (!line) continue;
            
            try {
              const data = JSON.parse(line);
              
              if (data.text_chunk) {
                setMessages((m) => {
                  const next = [...m];
                  let idx = next.findIndex((x) => x.sender === 'ai' && x.text === 'Generating...');
                  if (idx !== -1) {
                    next[idx] = { ...next[idx], text: data.text_chunk };
                  } else {
                    const lastIdx = next.length - 1;
                    next[lastIdx] = { ...next[lastIdx], text: next[lastIdx].text + " " + data.text_chunk };
                  }
                  return next;
                });
              }

              if (data.timings) {
                setLatencyMs(String(data.timings.total_ms ?? '--'));
                setTimingsText(
                  `LLM Chunk: ${data.timings.llm_chunk_ms || 0}ms | TTS: ${data.timings.tts_ms}ms`
                );
              }

              if (data.audio_url) {
                setAudioQueue(prev => [...prev, data]);
              } else if (data.text_chunk) {
                (async () => {
                  try {
                    const { url, duration } = await generatePocketTtsWavUrl(data.text_chunk);
                    setAudioQueue((prev) => [
                      ...prev,
                      {
                        ...data,
                        audio_url: url,
                        duration,
                      },
                    ]);
                  } catch (err) {
                    console.error('Pocket-TTS error:', err);
                  }
                })();
              }
            } catch(e) {
              console.error("NDJSON Parse error", e);
            }
          }
        }

        setProcessing(false);
      } catch (e) {
        console.error('Send error:', e);
        setConnected(false);
        setMessages((m) => {
          const next = [...m];
          const idx = next.findIndex((x) => x.sender === 'ai' && x.text === 'Generating...');
          if (idx !== -1) next.splice(idx, 1);
          next.push({ sender: 'ai', text: 'Network error calling backend' });
          return next;
        });
        setProcessing(false);
      }
    })();
  };

  return (
    <div className="root">
      <div className="videoPanel" ref={videoPanelRef}>
        {/* Video plays natively - hardware accelerated, always smooth */}
        <video
          ref={idleVideoRef}
          className="videoLayer isVisible"
          playsInline
          autoPlay
          muted
        />

        <div
          className="mouthOverlay"
          style={
            mouthRect
              ? {
                  left: `${mouthRect.left}px`,
                  top: `${mouthRect.top}px`,
                  width: `${mouthRect.width}px`,
                  height: `${mouthRect.height}px`,
                }
              : undefined
          }
          aria-hidden="true"
        >
          <div ref={mouthCoverRef} className="mouthCover" />
          <img ref={mouthARef} className="mouthSprite" alt="" draggable={false} />
          <img ref={mouthBRef} className="mouthSprite" alt="" draggable={false} />
        </div>

        <div className="latencyBadge">
          ⚡ <span className="latencyVal">{latencyMs}</span>ms
        </div>
        <div className={`statusBadge ${connected ? (speaking ? 'speaking' : processing ? 'processing' : 'connected') : ''}`}>
          {statusText}
        </div>
      </div>

      <div className="chatPanel">
        <div className="chatHeader">
          <h2>Miko</h2>
          <div className="sub">Real-Time AI • Groq + Client Lip-Sync</div>
        </div>

        <div className="chatMessages">
          {messages.map((m, idx) => (
            <div key={idx} className={`msg ${m.sender}`}>{m.text}</div>
          ))}
        </div>

        <div className="timingsBar">{timingsText}</div>

        <div className="chatInputArea">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') send();
            }}
            placeholder="Say something..."
            className="userInput"
            autoComplete="off"
          />
          <button className="sendBtn" onClick={send} disabled={!connected || processing}>
            Send
          </button>
        </div>
      </div>

    </div>
  );
}
