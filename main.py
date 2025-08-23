# file: main.py
#
# Voice AI Agent with Twilio Integration
# Fixed audio codec issue - uses direct pass-through for OpenAI Realtime API audio
#
# Quick Start:
#
# python -m venv env
# source env/bin/activate
# pip install -r requirements.txt
#
# python main.py
#

import os
import json
import base64
import asyncio
import websockets
import httpx
import resend
from typing import Dict, Any, Optional, List

from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.websockets import WebSocketDisconnect
from twilio.twiml.voice_response import VoiceResponse, Connect
from dotenv import load_dotenv

load_dotenv()

# =============================
# Config & Constants
# =============================
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8080))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

VOICE = 'alloy'
TEMPERATURE = 0.8

# Optional: Geoapify for simple address validation (free tier available)
GEOAPIFY_API_KEY = os.getenv("GEOAPIFY_API_KEY")

# Resend settings for sending confirmation emails
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
RESEND_FROM = os.getenv("RESEND_FROM", "tim@timsiwula.com")
if not RESEND_API_KEY:
    raise ValueError("Missing RESEND_API_KEY. Please set it in the .env file.")
resend.api_key = RESEND_API_KEY


# Recipients to notify after booking
BOOKING_RECIPIENTS = [
    "siwulactim@gmail.com",
    "cpliang.doris@gmail.com",
]

# Recipients to notify after booking
# BOOKING_RECIPIENTS = [
#     "jeff@assorthealth.com",
#     "connor@assorthealth.com",
#     "cole@assorthealth.com",
#     "jciminelli@assorthealth.com",
#     "akumar@assorthealth.com",
#     "riley@assorthealth.com",
#     "siwulactim@gmail.com",
# ]

# What we need to collect
REQUIRED_FIELDS = {
    "patient_name": None,
    "date_of_birth": None,
    "insurance_payer_name": None,
    "insurance_payer_id": None,
    "has_referral": None,
    "referring_physician": None,  # only if has_referral is True
    "chief_complaint": None,
    "address": None,
    "address_is_valid": None,
    "phone": None,
    "email": None,  # optional
    "appointment_slot": None,  # structured {doctor, start, end}
}

SYSTEM_MESSAGE = (
    "You are a medical intake voice agent for Assort Health.\n"
    "Your goals:\n"
    "1) Collect: patient full name and date of birth.\n"
    "2) Collect insurance info: payer name and payer ID.\n"
    "3) Ask if they have a referral; if yes, capture the referring physician.\n"
    "4) Collect chief medical complaint / reason for visit.\n"
    "5) Collect demographics: full street address, city, state, ZIP.\n"
    "   - After the caller provides an address, call the `validate_address` tool.\n"
    "   - If invalid or missing components, politely ask for corrections.\n"
    "6) Collect contact info: phone (required) and email (optional).\n"
    "7) Offer best available providers and times. Use the `get_available_appointments`\n"
    "   tool to retrieve options, then help the caller choose one.\n"
    "8) The call is *not resolved* until all items are captured. Use short,\n"
    "   respectful prompts, confirm back key details, and avoid PII over-sharing.\n"
    "When everything is gathered, summarize details and call `finalize_appointment`\n"
    "with the structured JSON payload so the server can send confirmation emails.\n"
)

LOG_EVENT_TYPES = [
    "error",
    "response.content.done",
    "rate_limits.updated",
    "response.done",
    "input_audio_buffer.committed",
    "input_audio_buffer.speech_stopped",
    "input_audio_buffer.speech_started",
    "session.created",
    "response.function_call",
]

SHOW_TIMING_MATH = False

app = FastAPI()

if not OPENAI_API_KEY:
    raise ValueError("Missing the OpenAI API key. Please set it in the .env file.")

# =============================
# In-memory state per stream/call
# =============================
class IntakeState:
    def __init__(self):
        self.data: Dict[str, Any] = {k: None for k in REQUIRED_FIELDS.keys()}

    def update(self, **kwargs):
        self.data.update(**kwargs)

    def is_complete(self) -> bool:
        # email optional, referring_physician only if has_referral is True
        required = [
            "patient_name",
            "date_of_birth",
            "insurance_payer_name",
            "insurance_payer_id",
            "has_referral",
            "chief_complaint",
            "address",
            "address_is_valid",
            "phone",
            "appointment_slot",
        ]
        if self.data.get("has_referral") is True:
            required.append("referring_physician")
        return all(self.data.get(k) not in (None, "") for k in required)

    def to_json(self) -> str:
        return json.dumps(self.data, ensure_ascii=False)


# Map of streamSid -> IntakeState
CALL_STATE: Dict[str, IntakeState] = {}


# =============================
# Utility: Fake providers & slots
# =============================
FAKE_PROVIDERS = [
    {"doctor": "Dr. Frank Smith", "specialty": "Primary Care"},
    {"doctor": "Dr. Jessica Nguyen", "specialty": "Internal Medicine"},
    {"doctor": "Dr. Sarah Chen", "specialty": "Family Medicine"},
]

FAKE_SLOTS = [
    {"start": "2025-08-22T09:00:00-05:00", "end": "2030-08-22T09:20:00-05:00"},
    {"start": "2025-08-22T10:40:00-05:00", "end": "2030-08-22T11:00:00-05:00"},
    {"start": "2025-08-22T13:30:00-05:00", "end": "2030-08-22T13:50:00-05:00"},
    {"start": "2025-08-23T11:10:00-05:00", "end": "2030-08-23T11:30:00-05:00"},
]


def get_fake_appointments() -> List[Dict[str, Any]]:
    out = []
    for p in FAKE_PROVIDERS:
        for s in FAKE_SLOTS:
            out.append({
                "doctor": p["doctor"],
                "specialty": p["specialty"],
                "start": s["start"],
                "end": s["end"],
            })
    return out


# =============================
# External: Address Validation (Geoapify)
# =============================
async def geoapify_validate(address_text: str) -> Dict[str, Any]:
    if not GEOAPIFY_API_KEY:
        return {"ok": False, "reason": "missing_geoapify_key"}

    url = "https://api.geoapify.com/v1/geocode/search"
    params = {"text": address_text, "apiKey": GEOAPIFY_API_KEY, "limit": 1}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, params=params)
        if r.status_code != 200:
            return {"ok": False, "reason": f"http_{r.status_code}"}
        data = r.json()
        features = data.get("features") or []
        if not features:
            return {"ok": False, "reason": "no_match"}
        props = features[0].get("properties", {})
        components = {
            "line1": props.get("address_line1"),
            "line2": props.get("address_line2"),
            "city": props.get("city"),
            "state": props.get("state_code") or props.get("state"),
            "postal_code": props.get("postcode"),
            "country": props.get("country_code"),
            "confidence": props.get("rank", {}).get("confidence") or props.get("confidence")
        }
        missing = [k for k in ("line1", "city", "state", "postal_code") if not components.get(k)]
        return {
            "ok": True,
            "is_valid": len(missing) == 0,
            "missing": missing,
            "normalized": components,
            "raw": props,
        }


# =============================
# Email sending
# =============================
def send_confirmation_email(appointment: Dict[str, Any], state: IntakeState) -> Optional[str]:
    # Send email via Resend to BOOKING_RECIPIENTS with appointment details. Returns error on failure.
    try:
        subject = f"New Appointment — {appointment.get('doctor')} @ {appointment.get('start')}"
        # Build a simple HTML summary
        html = f"""
        <h2>Tim's Voice AI Agent — New Appointment Reserved</h2>
        <p><strong>Patient:</strong> {state.data.get('patient_name')}<br/>
        <strong>DOB:</strong> {state.data.get('date_of_birth')}<br/>
        <strong>Phone:</strong> {state.data.get('phone')}<br/>
        <strong>Email:</strong> {state.data.get('email') or '—'}<br/>
        <strong>Insurance:</strong> {state.data.get('insurance_payer_name')} (ID: {state.data.get('insurance_payer_id')})<br/>
        <strong>Referral:</strong> {state.data.get('has_referral')}<br/>
        <strong>Referring Physician:</strong> {state.data.get('referring_physician') or '—'}<br/>
        <strong>Chief Complaint:</strong> {state.data.get('chief_complaint')}<br/>
        <strong>Address:</strong> {state.data.get('address')}<br/>
        <strong>Address Valid:</strong> {state.data.get('address_is_valid')}</p>
        <p><strong>Doctor:</strong> {appointment.get('doctor')}<br/>
        <strong>Specialty:</strong> {appointment.get('specialty')}<br/>
        <strong>Start:</strong> {appointment.get('start')}<br/>
        <strong>End:</strong> {appointment.get('end')}</p>
        """
        payload = {
            "from": RESEND_FROM,
            "to": BOOKING_RECIPIENTS,
            "subject": subject,
            "html": html,
        }
        # Send
        resend.Emails.send(payload)
        return None
    except Exception as e:
        return str(e)


# =============================
# FastAPI Routes (Twilio)
# =============================
app = FastAPI()

@app.get("/", response_class=JSONResponse)
async def index_page():
    return {"message": "Tim's Twilio Media Stream Server is running!"}

@app.post("/", response_class=HTMLResponse)
async def root_incoming(request: Request):
    return await handle_incoming_call(request)

@app.api_route("/incoming-call", methods=["GET", "POST"])
async def handle_incoming_call(request: Request):
    response = VoiceResponse()
    response.say(
        "Please wait while we connect your call to Tim's AI voice assistant.",
    )
    response.pause(length=1)
    response.say("Okay, you can start talking!")
    host = request.url.hostname
    connect = Connect()
    connect.stream(url=f"wss://{host}/media-stream")
    response.append(connect)
    return HTMLResponse(content=str(response), media_type="application/xml")


# =============================
# Realtime Session & Tooling
# =============================

async def initialize_session(openai_ws, stream_sid: Optional[str] = None):
    # Initialize the OpenAI Realtime session and declare tools the model can call.
    tools = [
        {
            "type": "function",
            "name": "validate_address",
            "description": "Validate and normalize a US mailing address string; returns missing fields if any.",
            "parameters": {
                "type": "object",
                "properties": {
                    "address_text": {"type": "string", "description": "The raw address as provided by caller"},
                },
                "required": ["address_text"],
            },
        },
        {
            "type": "function",
            "name": "update_intake_state",
            "description": "Persist one or more collected intake fields into the server-side call state.",
            "parameters": {
                "type": "object",
                "additionalProperties": True,
            },
        },
        {
            "type": "function",
            "name": "get_available_appointments",
            "description": "Return a list of available appointment slots with provider names.",
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "type": "function",
            "name": "finalize_appointment",
            "description": (
                "Mark the intake as complete and trigger confirmation emails. Must include the chosen "
                "appointment slot {doctor,start,end}."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "appointment": {
                        "type": "object",
                        "properties": {
                            "doctor": {"type": "string"},
                            "specialty": {"type": "string"},
                            "start": {"type": "string"},
                            "end": {"type": "string"},
                        },
                        "required": ["doctor", "start", "end"],
                    }
                },
                "required": ["appointment"],
            },
        },
    ]

    session_update = {
        "type": "session.update",
        "session": {
            "turn_detection": {"type": "server_vad"},
            "input_audio_format": "g711_ulaw",
            "output_audio_format": "g711_ulaw",
            "voice": VOICE,
            "instructions": SYSTEM_MESSAGE,
            "modalities": ["text", "audio"],
            "temperature": TEMPERATURE,
            "tools": tools,
        },
    }
    await openai_ws.send(json.dumps(session_update))

    # Proactive greeting
    await send_initial_conversation_item(openai_ws)


async def send_initial_conversation_item(openai_ws):
    initial_conversation_item = {
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": (
                        "Greet the caller: 'Hello, this is Doris! I will help schedule your doctors visit. "
                        "I will collect a few details like your name, date of birth, insurance, address, and contact info, "
                        "then offer available appointment times. Let's start with your full name."
                    ),
                }
            ],
        },
    }
    await openai_ws.send(json.dumps(initial_conversation_item))
    await openai_ws.send(json.dumps({"type": "response.create"}))


# Helper to send a function result back to the model
async def send_function_result(openai_ws, call_id: str, result: Any):
    payload = {
        "type": "conversation.item.create",
        "item": {
            "type": "function_result",
            "call_id": call_id,
            "output": result,
        },
    }
    await openai_ws.send(json.dumps(payload))
    # Ask the model to continue
    await openai_ws.send(json.dumps({"type": "response.create"}))


@app.websocket("/media-stream")
async def handle_media_stream(websocket: WebSocket):
    # Bridge Twilio <-> OpenAI Realtime with tool/function handling and intake state.
    await websocket.accept()

    async with websockets.connect(
        "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01",
        extra_headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "OpenAI-Beta": "realtime=v1",
        },
        ping_interval=20,
    ) as openai_ws:
        await initialize_session(openai_ws)

        stream_sid: Optional[str] = None
        latest_media_timestamp = 0
        last_assistant_item = None
        mark_queue = []
        response_start_timestamp_twilio = None
        state: Optional[IntakeState] = None

        async def receive_from_twilio():
            nonlocal stream_sid, latest_media_timestamp, state
            try:
                async for message in websocket.iter_text():
                    data = json.loads(message)
                    if data.get("event") == "media" and openai_ws.open:
                        latest_media_timestamp = int(data["media"]["timestamp"])
                        await openai_ws.send(
                            json.dumps({
                                "type": "input_audio_buffer.append",
                                "audio": data["media"]["payload"],
                            })
                        )
                    elif data.get("event") == "start":
                        stream_sid = data["start"]["streamSid"]
                        CALL_STATE[stream_sid] = state = IntakeState()
                        latest_media_timestamp = 0
                    elif data.get("event") == "mark":
                        if mark_queue:
                            mark_queue.pop(0)
            except WebSocketDisconnect:
                # End of call: nothing else to do here
                pass

        async def send_to_twilio():
            nonlocal stream_sid, last_assistant_item, response_start_timestamp_twilio, state
            try:
                async for msg in openai_ws:
                    response = json.loads(msg)
                    t = response.get("type")
                    if t in LOG_EVENT_TYPES:
                        print("OpenAI event:", t, response)

                    # Audio back to Twilio
                    if t == "response.audio.delta" and "delta" in response:
                        # Direct pass-through of audio data from OpenAI to Twilio
                        audio_payload = response["delta"]
                        await websocket.send_json({
                            "event": "media",
                            "streamSid": stream_sid,
                            "media": {"payload": audio_payload},
                        })
                        if response_start_timestamp_twilio is None:
                            response_start_timestamp_twilio = latest_media_timestamp
                        if response.get("item_id"):
                            last_assistant_item = response["item_id"]
                        await send_mark(websocket, stream_sid)

                    # Interruption handling
                    if t == "input_audio_buffer.speech_started":
                        if last_assistant_item:
                            await handle_speech_started_event(openai_ws)

                    # ============ Tool / Function calling ============
                    if t == "response.function_call":
                        name = response.get("name")
                        call_id = response.get("id") or response.get("call_id")
                        args = response.get("arguments") or {}
                        # Ensure state exists
                        if state is None and stream_sid:
                            state = CALL_STATE.setdefault(stream_sid, IntakeState())

                        if name == "validate_address":
                            address_text = args.get("address_text", "")
                            result = await geoapify_validate(address_text)
                            # Save high-level validity
                            if state is not None:
                                state.update(address=address_text, address_is_valid=result.get("is_valid"))
                            await send_function_result(openai_ws, call_id, result)

                        elif name == "update_intake_state":
                            if state is not None:
                                state.update(**args)
                            await send_function_result(openai_ws, call_id, {"ok": True, "state": state.data if state else {}})

                        elif name == "get_available_appointments":
                            slots = get_fake_appointments()
                            await send_function_result(openai_ws, call_id, {"appointments": slots})

                        elif name == "finalize_appointment":
                            appt = args.get("appointment") or {}
                            if state is not None:
                                state.update(appointment_slot=appt)
                            # Only send emails if we have basic completion
                            if state and state.is_complete():
                                err = send_confirmation_email(appt, state)
                                await send_function_result(openai_ws, call_id, {
                                    "ok": err is None,
                                    "email_error": err,
                                    "state_complete": True,
                                })
                            else:
                                await send_function_result(openai_ws, call_id, {
                                    "ok": False,
                                    "reason": "missing_required_fields",
                                    "missing_keys": [k for k, v in (state.data if state else {}).items() if v in (None, "")],
                                })

            except Exception as e:
                print("Error in send_to_twilio:", e)

        async def handle_speech_started_event(openai_ws):
            nonlocal response_start_timestamp_twilio, last_assistant_item
            if mark_queue and response_start_timestamp_twilio is not None:
                elapsed = latest_media_timestamp - response_start_timestamp_twilio
                if last_assistant_item:
                    await openai_ws.send(json.dumps({
                        "type": "conversation.item.truncate",
                        "item_id": last_assistant_item,
                        "content_index": 0,
                        "audio_end_ms": elapsed,
                    }))
                await websocket.send_json({"event": "clear", "streamSid": stream_sid})
                mark_queue.clear()
                last_assistant_item = None
                response_start_timestamp_twilio = None

        async def send_mark(connection, stream_sid):
            if stream_sid:
                await connection.send_json({
                    "event": "mark",
                    "streamSid": stream_sid,
                    "mark": {"name": "responsePart"},
                })
                mark_queue.append("responsePart")

        await asyncio.gather(receive_from_twilio(), send_to_twilio())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
