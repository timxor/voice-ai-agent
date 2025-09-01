# file: main.py
# version: v4.1
import os
import json
import asyncio
import httpx
import resend
from typing import Dict, Any, Optional, List, cast, Union
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.websockets import WebSocketDisconnect
from starlette.websockets import WebSocketState
from twilio.twiml.voice_response import VoiceResponse, Connect
from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()

# =============================
# Config & Constants
# =============================
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8080))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_REALTIME_MODEL = "gpt-realtime"
OPENAI_PREVIEW_MODEL = "gpt-4o-realtime-preview-2024-10-01"
VOICE = "alloy"
TEMPERATURE = 0.8
if not OPENAI_API_KEY:
    raise ValueError("Missing the OpenAI API key. Please set it in the .env file.")

# Resend settings
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
RESEND_FROM = os.getenv("RESEND_FROM", "updates@updates.timsiwula.com")
if not RESEND_API_KEY:
    raise ValueError("Missing RESEND_API_KEY. Please set it in the .env file.")
resend.api_key = RESEND_API_KEY

# Email recipients
email_string = os.environ.get("EMAIL_RECIPIENTS", "")
BOOKING_RECIPIENTS = [email.strip() for email in email_string.split(",") if email.strip()]

# Optional: Geoapify
GEOAPIFY_API_KEY = os.getenv("GEOAPIFY_API_KEY")

REQUIRED_FIELDS = {
    "patient_name": None,
    "date_of_birth": None,
    "insurance_payer_name": None,
    "insurance_payer_id": None,
    "has_referral": None,
    "referring_physician": None,
    "chief_complaint": None,
    "address": None,
    "address_is_valid": None,
    "phone": None,
    "email": None,
    "appointment_slot": None,
}

SYSTEM_MESSAGE = (
    "You are a medical intake voice agent for Doctors.\n"
    "CRITICAL: Always acknowledge user responses immediately and proceed without pausing.\n"
    "Your goals:\n"
    "1) Collect: patient first name, last name and date of birth.\n"
    "2) Collect insurance info: payer name and payer ID.\n"
    "3) Ask if they have a referral; if yes, capture the referring physician.\n"
    "4) Collect chief medical complaint / reason for visit.\n"
    "5) Collect demographics: full street address, city, state, ZIP.\n"
    "   - After the caller provides an address, call the `validate_address` tool.\n"
    "   - If invalid or missing components, politely ask for corrections.\n"
    "6) Collect contact info: phone (required) and email (optional).\n"
    "7) Offer best available providers and times. Use the `get_available_appointments` tool.\n"
    "8) The call is *not resolved* until all items are captured. Use short, respectful prompts.\n"
    "When everything is gathered, call `finalize_appointment`.\n"
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
    "conversation.item.created",
    "response.audio.delta",
    "response.create",
]

# Twilio media stream specifics
TWILIO_FRAME_MS = 20
COMMIT_THRESHOLD_MS = 60

app = FastAPI()

# =============================
# In-memory state per stream/call
# =============================
class IntakeState:
    def __init__(self):
        self.data: Dict[str, Any] = {k: None for k in REQUIRED_FIELDS.keys()}

    def update(self, **kwargs):
        self.data.update(**kwargs)

    def is_complete(self) -> bool:
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
    {"start": "2025-08-22T09:00:00-05:00", "end": "2025-08-22T09:20:00-05:00"},
    {"start": "2025-08-22T10:40:00-05:00", "end": "2025-08-22T11:00:00-05:00"},
    {"start": "2025-08-22T13:30:00-05:00", "end": "2025-08-22T13:50:00-05:00"},
    {"start": "2025-08-23T11:10:00-05:00", "end": "2025-08-23T11:30:00-05:00"},
]


def get_fake_appointments() -> List[Dict[str, Any]]:
    out = []
    for p in FAKE_PROVIDERS:
        for s in FAKE_SLOTS:
            out.append(
                {
                    "doctor": p["doctor"],
                    "specialty": p["specialty"],
                    "start": s["start"],
                    "end": s["end"],
                }
            )
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
            "confidence": props.get("rank", {}).get("confidence") or props.get("confidence"),
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
    try:
        subject = f"New Appointment — {appointment.get('doctor')} @ {appointment.get('start')}"
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
        <strong>Specialty:</strong> {appointment.get('specialty') or '—'}<br/>
        <strong>Start:</strong> {appointment.get('start')}<br/>
        <strong>End:</strong> {appointment.get('end')}</p>
        """
        payload: Dict[str, Any] = {"from": RESEND_FROM, "to": BOOKING_RECIPIENTS, "subject": subject, "html": html}
        resend.Emails.send(cast(Dict[str, Any], payload))
        return None
    except Exception as e:
        return str(e)


# =============================
# FastAPI Routes (Twilio)
# =============================
@app.get("/", response_class=JSONResponse)
async def index_page():
    return {
        "message": "Tim's Realtime Voice AI Agent that you can call at +1 (872) 224-3989 — Server is running."
    }


@app.post("/", response_class=HTMLResponse)
async def root_incoming(request: Request):
    return await handle_incoming_call(request)


@app.api_route("/incoming-call", methods=["GET", "POST"])
async def handle_incoming_call(request: Request):
    response = VoiceResponse()
    host = request.url.hostname
    if "ngrok" in request.headers.get("host", ""):
        host = request.headers["host"]
    connect = Connect()
    connect.stream(url=f"wss://{host}/media-stream")
    response.append(connect)
    print(f"Using WebSocket URL: wss://{host}/media-stream", flush=True)
    return HTMLResponse(content=str(response), media_type="application/xml")


# =============================
# Realtime Session & Tooling
# =============================
async def initialize_session(openai_ws, stream_sid: Optional[str] = None):
    print(f"Initializing OpenAI session for stream_sid: {stream_sid}", flush=True)
    tools = [
        {
            "type": "function",
            "name": "validate_address",
            "description": "Validate and normalize a US mailing address string; returns missing fields if any.",
            "parameters": {
                "type": "object",
                "properties": {
                    "address_text": {"type": "string", "description": "The raw address as provided by caller"}
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
                "title": "UpdateIntakeStateArgs",
                "description": "Any subset of intake fields to persist into the server-side call state.",
                "properties": {
                    "full_name": {"type": "string", "description": "Patient full legal name."},
                    "date_of_birth": {"type": "string", "description": "YYYY-MM-DD."},
                    "phone": {"type": "string", "description": "E.164 preferred, but free-form accepted."},
                    "email": {"type": "string", "format": "email"},
                    "address": {"type": "string", "description": "Free-form street address."},
                    "insurance_payer_name": {"type": "string"},
                    "insurance_payer_id": {"type": "string"},
                    "has_referral": {"type": "boolean", "description": "Whether the patient has a referral."},
                    "referring_physician": {"type": "string", "description": "Doctor or clinic name, if any."},
                    "chief_complaint": {"type": "string", "description": "Reason for visit in patient's words."},
                    "metadata": {"type": "object", "description": "Optional structured extras.", "additionalProperties": True},
                },
                "additionalProperties": False,
            },
        },
        {"type": "function", "name": "get_available_appointments", "description": "List slots.", "parameters": {"type": "object", "properties": {}}},
        {
            "type": "function",
            "name": "finalize_appointment",
            "description": "Complete intake and send confirmations. Include {doctor,start,end}.",
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
            "input_audio_format": "g711_ulaw",
            "output_audio_format": "g711_ulaw",
            "turn_detection": {
                "type": "server_vad",
                "create_response": True,
                "interrupt_response": True,
                "threshold": 0.5,
                "silence_duration_ms": 800,
                "prefix_padding_ms": 300,
            },
            "voice": VOICE,
            "instructions": SYSTEM_MESSAGE + "\n\nIMPORTANT: After the user provides information, "
                                             "always acknowledge what you heard and proceed to the next question "
                                             "or step. Never wait in silence after receiving user input.",
            "modalities": ["text", "audio"],
            "temperature": TEMPERATURE,
            "tools": tools,
        },
    }
    print(f"Sending session update: {session_update}", flush=True)
    await openai_ws.send(session_update)
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
                        "Greet the caller: 'Let's schedule your doctor's visit."
                    ),
                }
            ],
        },
    }
    # print("Sending initial conversation item:", initial_conversation_item)
    await openai_ws.send(initial_conversation_item)
    await openai_ws.send({"type": "response.create"})
    # print("Initial conversation item and response.create sent")


async def send_function_result(openai_ws, call_id: str, result: Any):
    payload = {"type": "conversation.item.create", "item": {"type": "function_result", "call_id": call_id, "output": result}}
    await openai_ws.send(payload)
    await openai_ws.send({"type": "response.create"})


# =============================
# Helpers
# =============================
def _normalize_event_to_dict(event: Any) -> Dict[str, Any]:
    if isinstance(event, dict):
        return event
    if isinstance(event, (str, bytes, bytearray)):
        try:
            return json.loads(event if isinstance(event, str) else event.decode())
        except Exception:
            return {"type": "unknown", "raw": repr(event)}
    model_dump = getattr(event, "model_dump", None)
    if callable(model_dump):
        try:
            return model_dump()
        except Exception:
            pass
    data_attr = getattr(event, "data", None)
    if isinstance(data_attr, dict):
        return data_attr
    json_method = getattr(event, "json", None)
    if callable(json_method):
        try:
            return json.loads(event.json())
        except Exception:
            pass
    return {"type": "unknown", "raw": repr(event)}


def _safe_parse_arguments(args: Union[str, Dict[str, Any], None]) -> Dict[str, Any]:
    if args is None:
        return {}
    if isinstance(args, dict):
        return args
    if isinstance(args, (str, bytes, bytearray)):
        try:
            return json.loads(args if isinstance(args, str) else args.decode())
        except Exception:
            return {}


def get_callers_full_name_for_stream(stream_sid: Optional[str]) -> Optional[str]:
    if not stream_sid:
        return None
    state = CALL_STATE.get(stream_sid)
    return state.data.get("patient_name") if state else None


# =============================
# Task Error Handling
# =============================
async def safe_task(coro):
    try:
        await coro
    except Exception as e:
        # Print the full exception to get more details
        print(f"Task error: {e}", flush=True)


# =============================
# WebSocket Handler
# =============================
@app.websocket("/media-stream")
async def handle_media_stream(websocket: WebSocket):
    await websocket.accept()
    try:
        client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        async with client.beta.realtime.connect(model=OPENAI_PREVIEW_MODEL) as openai_ws:
            await initialize_session(openai_ws)
            response = await openai_ws.receive()
            print(f"Received session response: {response}", flush=True)
            last_assistant_item: Optional[str] = None
            stream_sid: Optional[str] = None
            latest_media_timestamp = 0
            mark_queue: List[str] = []
            response_start_timestamp_twilio = None
            state: Optional[IntakeState] = None

            # batching counters for committing
            frames_since_commit = 0
            ms_since_commit = 0

            async def receive_from_twilio():
                nonlocal stream_sid, latest_media_timestamp, state
                try:
                    async for message in websocket.iter_text():
                        data = json.loads(message)

                        if data.get("event") == "media":
                            try:
                                latest_media_timestamp = int(data["media"]["timestamp"])
                                print(f"Appending audio at timestamp {latest_media_timestamp}", flush=True)
                                # append audio
                                await openai_ws.send( {"type": "input_audio_buffer.append", "audio": data["media"]["payload"]} )

                            except Exception as e:
                                print("OpenAI WebSocket error (append)")
                                break

                        elif data.get("event") == "start":
                            stream_sid = data["start"]["streamSid"]
                            CALL_STATE[stream_sid] = state = IntakeState()
                            latest_media_timestamp = 0

                        elif data.get("event") == "mark":
                            if mark_queue:
                                mark_queue.pop(0)

                except WebSocketDisconnect:
                    print("Twilio WebSocket disconnected")

            async def send_to_twilio():
                nonlocal stream_sid, last_assistant_item, response_start_timestamp_twilio, state
                try:
                    async for event in openai_ws:
                        response = _normalize_event_to_dict(event)
                        t = response.get("type")

                        if t in LOG_EVENT_TYPES:
                            if t == "error" and response.get("error", {}).get("code") == "input_audio_buffer_commit_empty":
                                continue
                            print("OpenAI event:", response, flush=True)

                        if t == "response.audio.delta" and "delta" in response:
                            if websocket.client_state != WebSocketState.CONNECTED:
                                break
                            audio_payload = response["delta"]
                            await websocket.send_json(
                                {"event": "media", "streamSid": stream_sid, "media": {"payload": audio_payload}}
                            )
                            if response_start_timestamp_twilio is None:
                                response_start_timestamp_twilio = latest_media_timestamp
                            if response.get("item_id"):
                                last_assistant_item = response["item_id"]
                            await send_mark(websocket, stream_sid)

                        elif t == "input_audio_buffer.speech_started":
                            await handle_speech_started_event()

                        elif t == "response.function_call":
                            name = response.get("name")
                            call_id = response.get("id") or response.get("call_id")
                            args = _safe_parse_arguments(response.get("arguments"))
                            if state is None and stream_sid:
                                state = CALL_STATE.setdefault(stream_sid, IntakeState())

                            if name == "validate_address":
                                address_text = args.get("address_text", "") or args.get("address") or ""
                                result = await geoapify_validate(address_text)
                                if state is not None:
                                    state.update(address=address_text, address_is_valid=result.get("is_valid"))
                                await send_function_result(openai_ws, call_id, result)

                            # get the callers first name and last name / full_name
                            # The caller’s name is stored as a single string in state.data["patient_name"].
                            # There are no separate first_name or last_name fields persisted by default.
                            elif name == "update_intake_state":
                                if state is not None:
                                    mapped = dict(args)
                                    if "full_name" in mapped:
                                        mapped["patient_name"] = mapped.pop("full_name")
                                    if "referral_physician" in mapped:
                                        mapped["referring_physician"] = mapped.pop("referral_physician")
                                    state.update(**mapped)

                                    if "patient_name" in mapped:
                                        # assign the caller’s first and last name to a variable called 'full_name'
                                        full_name = mapped["patient_name"]
                                        # print the callers full name
                                        print(f"Caller full name: {full_name}")

                                await send_function_result(
                                    openai_ws, call_id, {"ok": True, "state": state.data if state else {}}
                                )

                            elif name == "get_available_appointments":
                                slots = get_fake_appointments()
                                await send_function_result(openai_ws, call_id, {"appointments": slots})

                            elif name == "finalize_appointment":
                                appt = args.get("appointment") or {}
                                if state is not None:
                                    state.update(appointment_slot=appt)
                                if state and state.is_complete():
                                    err = send_confirmation_email(appt, state)
                                    await send_function_result(
                                        openai_ws, call_id, {"ok": err is None, "email_error": err, "state_complete": True}
                                    )
                                else:
                                    await send_function_result(
                                        openai_ws,
                                        call_id,
                                        {
                                            "ok": False,
                                            "reason": "missing_required_fields",
                                            "missing_keys": [
                                                k for k, v in (state.data if state else {}).items() if v in (None, "")
                                            ],
                                        },
                                    )

                        elif t == "session.created":
                            print(f"Session created at {latest_media_timestamp}")

                        elif t == "input_audio_buffer.speech_stopped":
                            print(f"Speech stopped detected at {latest_media_timestamp}")

                        elif t == "response.created":
                            print(f"Response being created at {latest_media_timestamp}")

                except Exception as e:
                    print(f"Error in send_to_twilio: {e}", flush=True)

            async def handle_speech_started_event():
                nonlocal response_start_timestamp_twilio, last_assistant_item
                if mark_queue and websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_json({"event": "clear", "streamSid": stream_sid})
                    mark_queue.clear()
                last_assistant_item = None
                response_start_timestamp_twilio = None

            async def send_mark(connection: WebSocket, sid: Optional[str]):
                if sid and connection.client_state == WebSocketState.CONNECTED:
                    await connection.send_json({"event": "mark", "streamSid": sid, "mark": {"name": "responsePart"}})
                    mark_queue.append("responsePart")

            recv_task = asyncio.create_task(safe_task(receive_from_twilio()))
            send_task = asyncio.create_task(safe_task(send_to_twilio()))
            done, pending = await asyncio.wait({recv_task, send_task}, return_when=asyncio.FIRST_COMPLETED)
            for t in pending:
                t.cancel()

    except Exception as e:
        print(f"OpenAI bridge failed: {e}", flush=True)
        try:
            await websocket.close()
        finally:
            return


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
