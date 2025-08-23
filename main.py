python
import os
import json
import asyncio
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import PlainTextResponse
from fastapi.websockets import WebSocketDisconnect
from twilio.twiml.voice_response import VoiceResponse, Connect
import websockets

# =============================
# Environment & Config
# =============================
load_dotenv()

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8080"))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_REALTIME_MODEL", "gpt-4o-realtime-preview-2024-12-17")
VOICE = os.getenv("VOICE", "alloy")

OPENAI_REALTIME_URL = os.getenv(
    "OPENAI_REALTIME_URL",
    f"wss://api.openai.com/v1/realtime?model={OPENAI_MODEL}",
)

WSS_TWILIO_STREAM_URL = os.getenv("WSS_TWILIO_STREAM_URL", "wss://your-domain.example/ws/twilio")

if not OPENAI_API_KEY:
    print("[WARN] OPENAI_API_KEY is not set; OpenAI bridge will not connect.")

# =============================
# FastAPI app
# =============================
app = FastAPI()

@app.get("/healthz")
async def healthz():
    return {"ok": True}

@app.post("/twilio/voice")
async def twilio_voice(_: Request):
    vr = VoiceResponse()
    connect = Connect()
    connect.stream(url=WSS_TWILIO_STREAM_URL)
    vr.append(connect)
    return PlainTextResponse(str(vr), media_type="text/xml")

# =============================
# Helpers
# =============================
async def send_session_update(openai_ws, voice_value: str) -> None:
    desired = {
        "type": "session.update",
        "session": {
            "input_audio_format": "g711_ulaw",
            "output_audio_format": "g711_ulaw",
            "voice": voice_value,
        },
    }
    print("[OpenAI] -> session.update", desired)
    await openai_ws.send(json.dumps(desired))

async def send_initial_prompt(openai_ws, session_ready_event: asyncio.Event) -> None:
    try:
        await asyncio.wait_for(session_ready_event.wait(), timeout=2.0)
    except asyncio.TimeoutError:
        pass
    await openai_ws.send(json.dumps({
        "type": "response.create",
        "response": {
            "modalities": ["audio"],
            "instructions": "Hello, how can I help you today?",
        }
    }))

# =============================
# WebSocket bridge
# =============================
@app.websocket("/ws/twilio")
async def ws_twilio(ws: WebSocket):
    await ws.accept()

    stream_sid: Optional[str] = None
    session_created = asyncio.Event()
    session_ready = asyncio.Event()
    pending_voice = VOICE

    async def openai_consumer(openai_ws):
        nonlocal stream_sid, pending_voice

        async for raw in openai_ws:
            try:
                evt = json.loads(raw)
            except Exception:
                print("[OpenAI] Non-JSON frame ignored")
                continue

            etype = evt.get("type")

            if etype == "session.created":
                print("[OpenAI] <- session.created")
                session_created.set()
                await send_session_update(openai_ws, pending_voice)
                # kick off greeting when formats are ready
                asyncio.create_task(send_initial_prompt(openai_ws, session_ready))
                continue

            if etype == "session.updated":
                sess = evt.get("session", {})
                iaf = sess.get("input_audio_format")
                oaf = sess.get("output_audio_format")
                v = sess.get("voice")
                print(f"[OpenAI] <- session.updated input={iaf} output={oaf} voice={v}")
                if iaf == "g711_ulaw" and oaf == "g711_ulaw":
                    session_ready.set()
                continue

            if etype == "response.audio.delta":
                b64 = evt.get("audio")
                if b64 and stream_sid:
                    await ws.send_text(json.dumps({
                        "event": "media",
                        "streamSid": stream_sid,
                        "media": {"payload": b64}
                    }))
                continue

            if etype == "error":
                message = (
                    evt.get("error", {}).get("message")
                    or evt.get("message", "")
                    or str(evt)
                )
                print(f"[OpenAI] <- error: {message}")
                if ("Supported values are:" in message or "Invalid value" in message) and pending_voice != "alloy":
                    pending_voice = "alloy"
                    print("[OpenAI] Retrying session.update with voice=alloy")
                    await send_session_update(openai_ws, pending_voice)
                continue

            # else: ignore other event types

    async def openai_producer(openai_ws):
        nonlocal stream_sid
        while True:
            try:
                raw = await ws.receive_text()
            except WebSocketDisconnect:
                print("[Twilio] disconnected")
                try:
                    await openai_ws.close()
                except Exception:
                    pass
                break

            try:
                obj = json.loads(raw)
            except Exception:
                print("[Twilio] Non-JSON frame ignored")
                continue

            event = obj.get("event")
            if event == "start":
                stream_sid = obj.get("start", {}).get("streamSid")
                print(f"[Twilio] start streamSid={stream_sid}")
                continue

            if event == "media":
                payload = obj.get("media", {}).get("payload")
                if payload:
                    await openai_ws.send(json.dumps({
                        "type": "input_audio_buffer.append",
                        "audio": payload
                    }))
                continue

            if event == "stop":
                print("[Twilio] stop")
                await openai_ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
                break

    try:
        async with websockets.connect(
            OPENAI_REALTIME_URL,
            extra_headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "OpenAI-Beta": "realtime=v1",
            },
            ping_interval=20,
            ping_timeout=20,
            max_size=2**23,
        ) as openai_ws:
            consumer = asyncio.create_task(openai_consumer(openai_ws))
            producer = asyncio.create_task(openai_producer(openai_ws))
            await asyncio.gather(consumer, producer)
    except Exception as e:
        print(f"[Bridge] OpenAI connect/bridge error: {e}")
        try:
            await ws.close()
        except Exception:
            pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
