import http from 'http';
import { WebSocketServer } from 'ws';

const PORT = process.env.WS_PORT ? Number(process.env.WS_PORT) : 8001;
const API_BASE = process.env.MIKO_API_BASE || 'http://127.0.0.1:8002';

const server = http.createServer();
const wss = new WebSocketServer({ server, path: '/ws' });

wss.on('connection', (socket) => {
  socket.on('message', async (raw) => {
    let payload;
    try {
      payload = JSON.parse(String(raw));
    } catch {
      return;
    }

    const text = payload?.text;
    if (!text) return;

    try {
      const resp = await fetch(`${API_BASE}/respond`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ text }),
      });

      if (!resp.ok) {
        socket.send(JSON.stringify({ type: 'error', message: `Backend error: ${resp.status}` }));
        return;
      }

      const data = await resp.json();
      socket.send(JSON.stringify({ type: 'response', ...data }));
    } catch (e) {
      socket.send(JSON.stringify({ type: 'error', message: String(e) }));
    }
  });
});

server.listen(PORT, () => {
  // eslint-disable-next-line no-console
  console.log(`WS server listening on ws://localhost:${PORT}/ws (proxying ${API_BASE})`);
});
