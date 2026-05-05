# Miko (Next.js + Pocket-TTS)

This is a migration of the Miko UI into Next.js with a **Node.js backend** (Next.js API routes).

## Setup

### 1) Copy character videos

Copy your character videos into:

- `miko_nextjs/public/character/`

Minimum needed:
- `stanby.mp4`
- `speaking1.mp4` (optional but recommended)

### 2) Environment variables

Create `miko_nextjs/.env.local` (do **not** commit tokens):

- `GROQ_API_KEY=...`
- `POCKET_TTS_VOICE=eponine` (optional)

### 3) Install + Run

In `miko_nextjs`:

- `npm install`
- `npm run dev`

Note: This project uses local Pocket-TTS via `uvx`, so you need `uv` installed.

Then open `http://localhost:3000`.

## Ports

- Next.js UI: `3000`
- Next.js API: `3000/api/*`
