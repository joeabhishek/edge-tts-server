#!/usr/bin/env python3
"""
Edge TTS Server — Free, unlimited text-to-speech using Microsoft Edge neural voices.
Deploy to Render.com, Railway, or any cloud host.

API:
    POST /tts  {"text": "Hello", "voice": "en-US-AriaNeural"} → audio/mpeg
    GET /voices → list of available English voices
    GET /health → {"status": "ok"}
"""

import asyncio
import os
import tempfile
from flask import Flask, request, send_file, jsonify, Response
import edge_tts

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
    return jsonify({
        "service": "Edge TTS Server",
        "usage": "POST /tts with {\"text\": \"your text\"}",
        "voices": "GET /voices",
        "health": "GET /health",
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8765))
    app.run(host="0.0.0.0", port=port)
