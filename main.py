import os
import json
import base64
import asyncio
import websockets
import httpx
import resend
from dotenv import load_dotenv
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, WebSocket, Request
from fastapi.websockets import WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from twilio.twiml.voice_response import VoiceResponse, Connect

# =============================
# Configuration
# =============================
load_dotenv()
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8080))

# OpenAI API
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
VOICE = os.getenv("VOICE", "onyx")

# Geoapify Address API
GEOAPIFY_API_KEY = os.getenv("GEOAPIFY_API_KEY")

# Resend Email API
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
RESEND_FROM = os.getenv("RESEND_FROM", "tim@timsiwula.com")
if not RESEND_API_KEY:
    raise ValueError("Missing RESEND_API_KEY. Please set it in the .env file.")
resend.api_key = RESEND_API_KEY

# System Prompt Context defining the Agents goal
SYSTEM_MESSAGE = (
    "You are a concise, professional medical intake assistant for a clinic. "
    "Your goal is to collect, confirm, and validate the following from the caller: "
    "1) Patient full name, 2) Date of birth, 3) Contact phone number, and 4) Optional email. "
    "Do not consider the call resolved until you have all required items (name, DOB, phone). "
    "Validation rules: "
    "- Name: ask for first and last; confirm spelling if unclear. "
    "- DOB: accept formats like YYYY-MM-DD or MM/DD/YYYY; repeat back normalized as MM-DD-YYYY. "
    "- Phone: capture a single 10–15 digit number; read it back to confirm. "
    "- Email (optional): basic format user@domain.tld; if not provided, proceed. "
    "Dialogue style: Ask one question at a time. Be courteous and efficient. "
    "After all required info is confirmed, say: 'Thank you. We will follow up with you shortly. Goodbye.' "
    "Then emit exactly one line on its own that starts with '##PATIENT_DATA## ' followed by a minified JSON object "
    "with keys: name (string), dob (MM-DD-YYYY), phone (string), email (string or null). "
    "Example final line: ##PATIENT_DATA## {\"name\":\"Ada Lovelace\",\"dob\":\"10-12-1815\",\"phone\":\"+13125551234\",\"email\":null} "
    "Do not include any other text on that line. "
)

# Recipients to notify after booking
BOOKING_RECIPIENTS = [
    "siwulactim@gmail.com",
    "cpliang.doris@gmail.com",
]

LOG_EVENT_TYPES = [
    'error', 'response.content.done', 'rate_limits.updated',
    'response.done', 'input_audio_buffer.committed',
    'input_audio_buffer.speech_stopped', 'input_audio_buffer.speech_started',
    'session.created', 'response.output_text.delta', 'response.audio.delta'
]
SHOW_TIMING_MATH = False

app = FastAPI()


# =============================
# New: In-memory "DB"
# =============================
PATIENT_DB = {}  # id -> dict
NEXT_ID = 1


# =============================
# Routes
# =============================
if not OPENAI_API_KEY:
    raise ValueError('Missing the OpenAI API key. Please set it in the .env file.')

@app.get("/", response_class=JSONResponse)
async def index_page():
    return {"message": "Tim's Voice AI Assistant Media Stream Server is running!"}

# Optional debugging endpoint to inspect captured patients
@app.get("/patients", response_class=JSONResponse)
async def list_patients():
    return {"count": len(PATIENT_DB), "patients": PATIENT_DB}

# Some providers POST to root; delegate to incoming-call handler to avoid 405s.
@app.post("/", response_class=HTMLResponse)
async def root_incoming(request: Request):
    return await handle_incoming_call(request)

@app.api_route("/incoming-call", methods=["GET", "POST"])
async def handle_incoming_call(request: Request):
    """Return TwiML to connect the call to the WebSocket media stream."""
    response = VoiceResponse()
    response.say("Hi, this is Eevee. How can I help you schedule your doctors appointment today?")
    host = request.url.hostname
    connect = Connect()
    connect.stream(url=f'wss://{host}/media-stream')
    response.append(connect)
    return HTMLResponse(content=str(response), media_type="application/xml")


# =============================
# Media Stream (Twilio <-> OpenAI Realtime)
# =============================
@app.websocket("/media-stream")
async def handle_media_stream(websocket: WebSocket):
    """Bridge audio between Twilio and OpenAI, and capture structured patient data."""
    print("Client connected")
    await websocket.accept()

    # Per-connection state
    stream_sid = None
    latest_media_timestamp = 0
    last_assistant_item = None
    mark_queue = []
    response_start_timestamp_twilio = None

    # New: accumulate text output so we can detect the structured marker
    output_text_buffer = []
    patient_data_captured = False

    async def finalize_and_close():
        """Close the stream after completion."""
        try:
            await websocket.send_json({"event": "stop", "streamSid": stream_sid})
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass

    try:
        async with websockets.connect(
            'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01',
            extra_headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "OpenAI-Beta": "realtime=v1"
            }
        ) as openai_ws:
            await initialize_session(openai_ws)

            async def receive_from_twilio():
                nonlocal stream_sid, latest_media_timestamp, response_start_timestamp_twilio, last_assistant_item
                try:
                    async for message in websocket.iter_text():
                        data = json.loads(message)
                        if data['event'] == 'media' and openai_ws.open:
                            latest_media_timestamp = int(data['media']['timestamp'])
                            audio_append = {
                                "type": "input_audio_buffer.append",
                                "audio": data['media']['payload']
                            }
                            await openai_ws.send(json.dumps(audio_append))

                        elif data['event'] == 'start':
                            stream_sid = data['start']['streamSid']
                            print(f"Incoming stream has started {stream_sid}")
                            response_start_timestamp_twilio = None
                            last_assistant_item = None

                        elif data['event'] == 'mark':
                            if mark_queue:
                                mark_queue.pop(0)

                        elif data['event'] == 'stop':
                            # Twilio ended the stream
                            print("Twilio sent stop.")
                            if openai_ws.open:
                                try:
                                    await openai_ws.close()
                                except Exception:
                                    pass
                except WebSocketDisconnect:
                    print("Client disconnected.")
                    if openai_ws.open:
                        await openai_ws.close()

            async def send_to_twilio():
                nonlocal stream_sid, last_assistant_item, response_start_timestamp_twilio
                nonlocal output_text_buffer, patient_data_captured
                try:
                    async for openai_message in openai_ws:
                        response = json.loads(openai_message)

                        # Log selected event types
                        if response.get('type') in LOG_EVENT_TYPES:
                            print(f"Received event: {response['type']}", response)

                        # --- AUDIO back to Twilio ---
                        if response.get('type') == 'response.audio.delta' and 'delta' in response:
                            # Pass-through audio
                            audio_payload = base64.b64encode(
                                base64.b64decode(response['delta'])
                            ).decode('utf-8')
                            await websocket.send_json({
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": {"payload": audio_payload}
                            })

                            if response_start_timestamp_twilio is None:
                                response_start_timestamp_twilio = latest_media_timestamp

                            if response.get('item_id'):
                                last_assistant_item = response['item_id']

                            await send_mark(websocket, stream_sid)

                        # --- TEXT delta: accumulate for marker detection ---
                        # Realtime emits text as 'response.output_text.delta'
                        if response.get('type') == 'response.output_text.delta':
                            chunk = response.get('delta') or ''
                            if chunk:
                                output_text_buffer.append(chunk)
                                combined = ''.join(output_text_buffer)

                                # Try to detect the marker line with JSON
                                # Pattern: ##PATIENT_DATA## { ... }
                                m = re.search(r"##PATIENT_DATA##\s*(\{.*?\})", combined)
                                if m and not patient_data_captured:
                                    json_text = m.group(1)
                                    try:
                                        data = json.loads(json_text)
                                        # Normalize/ensure keys exist
                                        name = data.get("name")
                                        dob = data.get("dob")
                                        phone = data.get("phone")
                                        email = data.get("email", None)

                                        if name and dob and phone:
                                            # Save to in-memory DB
                                            patient_id = save_patient_record({
                                                "name": name,
                                                "dob": dob,
                                                "phone": phone,
                                                "email": email
                                            })
                                            print(f"[INTAKE] Saved patient_id={patient_id}: "
                                                  f"{PATIENT_DB[patient_id]}")

                                            patient_data_captured = True

                                            # After the AI says goodbye (it already did per instructions),
                                            # give it a beat and end the stream.
                                            asyncio.create_task(end_call_soon())

                                    except json.JSONDecodeError:
                                        # Ignore until full JSON arrives
                                        pass

                        # Interruption handling heuristic
                        if response.get('type') == 'input_audio_buffer.speech_started':
                            if last_assistant_item:
                                await handle_speech_started_event(openai_ws, websocket,
                                                                  stream_sid,
                                                                  latest_media_timestamp,
                                                                  response_start_timestamp_twilio,
                                                                  last_assistant_item,
                                                                  mark_queue)

                except Exception as e:
                    print(f"Error in send_to_twilio: {e}")

            async def end_call_soon():
                # small pause to let final audio flush
                await asyncio.sleep(0.8)
                await finalize_and_close()

            await asyncio.gather(receive_from_twilio(), send_to_twilio())

    except Exception as e:
        print(f"Top-level media-stream error: {e}")


# =============================
# Helper functions
# =============================
def save_patient_record(record: dict) -> int:
    """Auto-increment and persist a patient record in memory."""
    global NEXT_ID
    pid = NEXT_ID
    PATIENT_DB[pid] = {
        "id": pid,
        "name": record.get("name"),
        "dob": record.get("dob"),
        "phone": record.get("phone"),
        "email": record.get("email", None)
    }
    NEXT_ID += 1
    return pid


async def handle_speech_started_event(openai_ws, websocket, stream_sid,
                                      latest_media_timestamp,
                                      response_start_timestamp_twilio,
                                      last_assistant_item,
                                      mark_queue):
    """Truncate current assistant audio when caller starts speaking (barge-in)."""
    if mark_queue and response_start_timestamp_twilio is not None:
        elapsed_time = latest_media_timestamp - response_start_timestamp_twilio
        truncate_event = {
            "type": "conversation.item.truncate",
            "item_id": last_assistant_item,
            "content_index": 0,
            "audio_end_ms": max(0, elapsed_time)
        }
        try:
            await openai_ws.send(json.dumps(truncate_event))
        except Exception:
            pass

        try:
            await websocket.send_json({"event": "clear", "streamSid": stream_sid})
        except Exception:
            pass

        mark_queue.clear()


async def send_mark(connection, stream_sid):
    if stream_sid:
        mark_event = {
            "event": "mark",
            "streamSid": stream_sid,
            "mark": {"name": "responsePart"}
        }
        await connection.send_json(mark_event)


async def send_initial_conversation_item(openai_ws):
    """Have the AI speak first with a short greeting and intake instruction."""
    initial_conversation_item = {
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": (
                        "Greet the caller briefly and begin intake. "
                        "Start by asking for their full name."
                    )
                }
            ]
        }
    }
    await openai_ws.send(json.dumps(initial_conversation_item))
    await openai_ws.send(json.dumps({"type": "response.create"}))


async def initialize_session(openai_ws):
    """Initialize Realtime session with voice and our intake system prompt."""
    session_update = {
        "type": "session.update",
        "session": {
            "turn_detection": {"type": "server_vad"},
            "input_audio_format": "g711_ulaw",
            "output_audio_format": "g711_ulaw",
            "voice": VOICE,
            "instructions": SYSTEM_MESSAGE,
            "modalities": ["text", "audio"],
            "temperature": 0.2
        }
    }
    print('Sending session update:', json.dumps(session_update))
    await openai_ws.send(json.dumps(session_update))

    # Have the AI speak first
    await send_initial_conversation_item(openai_ws)


# =============================
# Entrypoint
# =============================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
