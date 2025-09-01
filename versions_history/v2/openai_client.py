
import json
import base64
from typing import Any, Dict
import websockets

from config import OPENAI_API_KEY, TEMPERATURE, VOICE, SYSTEM_MESSAGE, LOG_EVENT_TYPES

REALTIME_WS_URL = f"wss://api.openai.com/v1/realtime?model=gpt-realtime&temperature={TEMPERATURE}&voice={VOICE}"

async def connect_realtime():
    """
    Establish a websocket connection to OpenAI Realtime with the proper headers.
    Returns an *open* websockets client.
    """
    return await websockets.connect(
        REALTIME_WS_URL,
        additional_headers={"Authorization": f"Bearer {OPENAI_API_KEY}"}
    )

async def initialize_session(openai_ws) -> None:
    """
    Send the initial session.update with instructions and audio formats.
    """
    session_update: Dict[str, Any] = {
        "type": "session.update",
        "session": {
            "type": "realtime",
            "model": "gpt-realtime",
            "output_modalities": ["audio"],
            "audio": {
                "input": {
                    "format": {"type": "audio/pcmu"},
                    "turn_detection": {"type": "server_vad"}
                },
                "output": {
                    "format": {"type": "audio/pcmu"}
                }
            },
            "instructions": SYSTEM_MESSAGE,
        }
    }
    await openai_ws.send(json.dumps(session_update))

async def forward_audio_delta_to_twilio(response: dict, stream_sid: str, websocket) -> None:
    """
    Convert the OpenAI 'response.output_audio.delta' into a Twilio 'media' frame.
    """
    # The Realtime API delta is base64; Twilio expects base64 payload in 'media.payload'.
    # Re-encode to normalize padding/format.
    b64 = base64.b64encode(base64.b64decode(response["delta"])).decode("utf-8")
    await websocket.send_json({
        "event": "media",
        "streamSid": stream_sid,
        "media": {"payload": b64}
    })
