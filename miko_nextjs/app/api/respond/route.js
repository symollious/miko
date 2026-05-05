import { NextResponse } from 'next/server.js';

export const runtime = 'nodejs';

const PYTHON_BACKEND = process.env.PYTHON_BACKEND_URL || 'http://127.0.0.1:8002';
const CLIENT_TTS = process.env.CLIENT_TTS === '1';

export async function POST(req) {
  let body;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON body' }, { status: 400 });
  }

  if (!body?.text) {
    return NextResponse.json({ error: 'Missing text' }, { status: 400 });
  }

  try {
    const res = await fetch(`${PYTHON_BACKEND}/respond`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        text: body.text,
        history: body.history || [],
        skip_tts: CLIENT_TTS,
      }),
    });

    if (!res.ok) {
      const err = await res.text();
      return NextResponse.json(
        { error: `Backend error (${res.status}): ${err.slice(0, 500)}` },
        { status: 502 }
      );
    }

    // Instead of parsing JSON, we return the fetch response body directly as a stream.
    return new Response(res.body, {
      headers: {
        'Content-Type': 'application/x-ndjson',
        'Cache-Control': 'no-cache, no-transform',
        'Connection': 'keep-alive',
      },
    });
  } catch (e) {
    return NextResponse.json(
      { error: `Proxy error: ${String(e?.message || e)}` },
      { status: 503 }
    );
  }
}
