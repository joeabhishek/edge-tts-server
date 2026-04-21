# Edge TTS Server

Free, unlimited text-to-speech using Microsoft Edge neural voices, plus a thin
Groq LLM proxy so the iOS client doesn't need to ship an API key.

## Deploy to Render.com (Free)

1. Create a GitHub repo and push the `tts-server/` folder
2. Go to [render.com](https://render.com) → New → Web Service
3. Connect your GitHub repo
4. Settings:
   - **Root Directory**: `tts-server`
   - **Runtime**: Docker
   - **Instance Type**: Free
5. **Environment Variables** (Settings → Environment):
   - `GROQ_API_KEY` = your Groq API key from [console.groq.com](https://console.groq.com).
     Required for the `/llm/chat/completions` route. Without it, every LLM
     request returns HTTP 500 and the iOS app shows "API error: HTTP 500".
   - `LLM_RATE_LIMIT` (optional) = per-IP rate limit string for the LLM
     proxy. Default is `30 per minute` (matches Groq's free per-key
     ceiling). Examples: `60 per minute`, `5 per second`, `1000 per hour`.
     See [flask-limiter syntax](https://flask-limiter.readthedocs.io/en/stable/).
6. Deploy

Your server will be at: `https://your-service-name.onrender.com`

## API

```bash
# Text to speech
curl -X POST https://your-server.onrender.com/tts \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world", "voice": "en-US-AriaNeural"}' \
  -o speech.mp3

# Streaming TTS (low-latency)
curl "https://your-server.onrender.com/tts/stream?text=Hello+world" -o speech.mp3

# List voices
curl https://your-server.onrender.com/voices

# Health check
curl https://your-server.onrender.com/health

# Groq LLM proxy — same body shape as api.groq.com directly.
# Server adds Authorization: Bearer <GROQ_API_KEY> from env. Streams SSE
# straight through when "stream": true.
curl -X POST https://your-server.onrender.com/llm/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"llama-3.3-70b-versatile","messages":[{"role":"user","content":"Hi"}],"stream":false}'
```

## Available Voices

- `en-US-AriaNeural` — Warm, expressive female (default)
- `en-US-GuyNeural` — Natural male
- `en-US-JennyNeural` — Professional female
- `en-GB-SoniaNeural` — British female
- `en-US-DavisNeural` — Casual male

## Run Locally

```bash
pip install -r requirements.txt
export GROQ_API_KEY=gsk_...     # only needed if you'll exercise /llm/chat/completions
python app.py
```

## Rotating the Groq Key

Go to Render dashboard → this service → Environment → edit `GROQ_API_KEY` →
**Save Changes**. Render redeploys with the new value; iOS clients keep
working without a rebuild.

## Per-IP Rate Limiting

The `/llm/chat/completions` route enforces a per-IP throttle (default 30
req/min) so a single device — or a runaway loop — can't drain the upstream
Groq budget for the whole team. Hit limits return HTTP 429 with a JSON
`error` body. iOS already surfaces 429 as the "API error" toast.

Tune via `LLM_RATE_LIMIT` env var (string format, e.g. `60 per minute`).
Render's load balancer forwards the real client IP via `X-Forwarded-For`,
which `werkzeug.middleware.proxy_fix.ProxyFix` plumbs into
`request.remote_addr` — that's what `flask-limiter` keys on.

The TTS routes (`/tts`, `/tts/stream`, `/voices`, `/health`) are NOT
rate-limited — they're unauthenticated, edge-cached, and don't proxy to a
metered upstream.
