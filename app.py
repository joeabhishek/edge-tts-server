#!/usr/bin/env python3
"""
Edge TTS Server — Free, unlimited text-to-speech using Microsoft Edge neural voices.
Also acts as a thin Groq LLM proxy so the iOS client doesn't need to ship an API key
(GROQ_API_KEY is read from server env at request time).
Deploy to Render.com, Railway, or any cloud host.

API:
    POST /tts                     {"text": "Hello", "voice": "en-US-AriaNeural"} → audio/mpeg
    GET  /tts/stream?text=…       streaming MP3 (low-latency)
    GET  /voices                  list of available English voices
    GET  /health                  {"status": "ok"}
    POST /llm/chat/completions    OpenAI-compatible chat completions → Groq
                                  (server adds Authorization header from GROQ_API_KEY env)
"""

import asyncio
import os
import tempfile

import edge_tts
import requests
from flask import Flask, jsonify, request, Response, send_file

app = Flask(__name__)

DEFAULT_VOICE = "en-US-AriaNeural"


@app.route("/tts", methods=["POST"])
def tts():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()
    voice = data.get("voice", DEFAULT_VOICE)

    if not text:
        return jsonify({"error": "No text provided"}), 400

    try:
        output_file = tempfile.mktemp(suffix=".mp3")
        asyncio.run(_generate(text, voice, output_file))

        return send_file(
            output_file,
            mimetype="audio/mpeg",
            as_attachment=False,
            download_name="speech.mp3",
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


async def _generate(text: str, voice: str, path: str):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(path)


@app.route("/voices", methods=["GET"])
def voices():
    voice_list = asyncio.run(_list_voices())
    return jsonify(voice_list)


async def _list_voices():
    voices = await edge_tts.list_voices()
    return [
        {"name": v["ShortName"], "gender": v["Gender"], "locale": v["Locale"]}
        for v in voices
        if v["Locale"].startswith("en-")
    ]


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "voice": DEFAULT_VOICE})


@app.route("/tts/stream", methods=["GET"])
def tts_stream():
    """Streaming TTS — yields MP3 chunks as edge-tts generates them.
    Reduces time-to-first-audio because AVPlayer can buffer + play
    while the server is still synthesizing.
    Uses GET so AVPlayer can consume the URL directly."""
    text = request.args.get("text", "").strip()
    voice = request.args.get("voice", DEFAULT_VOICE)
    if not text:
        return jsonify({"error": "No text provided"}), 400

    def generate():
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            communicate = edge_tts.Communicate(text, voice)
            agen = communicate.stream()
            while True:
                try:
                    chunk = loop.run_until_complete(agen.__anext__())
                    if chunk["type"] == "audio":
                        yield chunk["data"]
                except StopAsyncIteration:
                    break
        finally:
            loop.close()

    return Response(
        generate(),
        mimetype="audio/mpeg",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/", methods=["GET"])
def root():
    return jsonify(
        {
            "service": "Edge TTS Server",
            "usage": 'POST /tts with {"text": "your text"}',
            "voices": "GET /voices",
            "health": "GET /health",
            "llm": "POST /llm/chat/completions (OpenAI-compatible Groq proxy)",
        }
    )


# ----------------------------------------------------------------------------
# Groq LLM proxy
#
# The iOS client used to ship a literal Groq API key in Secrets.swift, so every
# install on every teammate's device shared one free-tier rate-limit budget
# (~30 req/min). With multi-frame Live AI turns + multiple testers, that bucket
# emptied fast and the app surfaced "API error: HTTP 429".
#
# This route accepts the same OpenAI-compatible chat completions request body
# the iOS client used to send to api.groq.com directly, attaches the Bearer
# header server-side from the GROQ_API_KEY env var, and forwards. Streams the
# SSE response straight through when stream=true; buffers when stream=false.
# Key never leaves the server. To rotate, change the env var on Render.
# ----------------------------------------------------------------------------

GROQ_UPSTREAM = "https://api.groq.com/openai/v1/chat/completions"


@app.route("/llm/chat/completions", methods=["POST"])
def llm_chat_completions():
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        return (
            jsonify(
                {
                    "error": "Server misconfigured: GROQ_API_KEY env var is not set on this server."
                }
            ),
            500,
        )

    body = request.get_data()
    # Detect stream=true without parsing JSON (some clients pretty-print, some don't).
    body_compact = body.replace(b" ", b"").replace(b"\n", b"").replace(b"\t", b"")
    is_stream = b'"stream":true' in body_compact

    upstream_headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "Accept": "text/event-stream" if is_stream else "application/json",
    }

    try:
        upstream = requests.post(
            GROQ_UPSTREAM,
            data=body,
            headers=upstream_headers,
            stream=is_stream,
            timeout=60,
        )
    except requests.RequestException as e:
        return jsonify({"error": f"Upstream request failed: {e}"}), 502

    upstream_content_type = upstream.headers.get("Content-Type", "application/json")

    if is_stream:

        def relay():
            try:
                # chunk_size=None yields raw chunks as they arrive on the wire,
                # which is what we want for SSE — don't buffer whole events.
                for chunk in upstream.iter_content(chunk_size=None):
                    if chunk:
                        yield chunk
            finally:
                upstream.close()

        return Response(
            relay(),
            status=upstream.status_code,
            mimetype=upstream_content_type,
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )
    else:
        data = upstream.content
        upstream.close()
        return Response(
            data,
            status=upstream.status_code,
            mimetype=upstream_content_type,
        )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8765))
    app.run(host="0.0.0.0", port=port)
