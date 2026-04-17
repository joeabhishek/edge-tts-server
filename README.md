# Edge TTS Server

Free, unlimited text-to-speech using Microsoft Edge neural voices.

## Deploy to Render.com (Free)

1. Create a GitHub repo and push the `tts-server/` folder
2. Go to [render.com](https://render.com) → New → Web Service
3. Connect your GitHub repo
4. Settings:
   - **Root Directory**: `tts-server`
   - **Runtime**: Docker
   - **Instance Type**: Free
5. Deploy

Your server will be at: `https://your-service-name.onrender.com`

## API

```bash
# Text to speech
curl -X POST https://your-server.onrender.com/tts \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world", "voice": "en-US-AriaNeural"}' \
  -o speech.mp3

# List voices
curl https://your-server.onrender.com/voices

# Health check
curl https://your-server.onrender.com/health
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
python app.py
```
