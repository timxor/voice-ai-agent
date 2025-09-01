import json
import asyncio
from fastapi import APIRouter, WebSocket, Request
from fastapi.responses import HTMLResponse, JSONResponse
from twilio.twiml.voice_response import VoiceResponse, Connect

from call_state import CallState
from openai_client import connect_realtime, initialize_session
from twilio_stream import TwilioReceiver
from openai_sender import OpenAISender

router = APIRouter()

@router.get("/", response_class=JSONResponse)
async def root():
    return {"message": "Twilio Media Stream Server (refactored) is running!"}

@router.get("/healthz", response_class=JSONResponse)
async def health_check():
    """
    Basic health check endpoint.
    Returns status 'ok' to confirm the API is alive.
    """
    return {"status": "ok"}

@router.api_route("/incoming-call", methods=["GET", "POST"])
async def incoming_call(request: Request):
    """
    Respond to Twilio with TwiML that connects the call to our WebSocket endpoint.
    """
    host = request.url.hostname
    vr = VoiceResponse()
    vr.say(
        "Please wait while we connect your call to the A I voice assistant, powered by Twilio and the Open A I Realtime API.",
        voice="Google.en-US-Chirp3-HD-Aoede"
    )
    vr.pause(length=1)
    vr.say("Okay, you can start talking!", voice="Google.en-US-Chirp3-HD-Aoede")

    connect = Connect()
    connect.stream(url=f"wss://{host}/media-stream")
    vr.append(connect)
    return HTMLResponse(content=str(vr), media_type="application/xml")

@router.websocket("/media-stream")
async def media_stream(websocket: WebSocket):
    """
    Bridge between Twilio <-> OpenAI. Two tasks:
      1) TwilioReceiver: Twilio -> OpenAI
      2) OpenAISender:   OpenAI -> Twilio
    """
    print("Client connected")
    await websocket.accept()

    openai_ws = None
    try:
        openai_ws = await connect_realtime()
        await initialize_session(openai_ws)

        state = CallState()
        receiver = TwilioReceiver(websocket, openai_ws, state)
        sender = OpenAISender(websocket, openai_ws, state)

        recv_task = asyncio.create_task(receiver.run(), name="twilio->openai")
        send_task = asyncio.create_task(sender.run(), name="openai->twilio")

        await asyncio.wait([recv_task, send_task], return_when=asyncio.FIRST_COMPLETED)
    finally:
        # Close OpenAI ws defensively (websockets v13 has no .closed attr)
        if openai_ws is not None:
            try:
                await openai_ws.close()
            except Exception:
                pass
        # Close client websocket
        try:
            await websocket.close()
        except Exception:
            pass
