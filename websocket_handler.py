"""
WebSocket handler for managing realtime communication between Twilio and OpenAI.
"""
import json
import asyncio
from typing import Optional, List
from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect
from starlette.websockets import WebSocketState
from openai import AsyncOpenAI

from config import OPENAI_API_KEY, OPENAI_PREVIEW_MODEL, LOG_EVENT_TYPES
from models import IntakeState, CALL_STATE
from openai_service import OpenAIService
from address_service import AddressService
from appointment_service import AppointmentService
from email_service import EmailService
from utils import normalize_event_to_dict, safe_parse_arguments, safe_task


class WebSocketHandler:
    """Handles WebSocket connections for realtime voice communication."""

    @staticmethod
    async def handle_media_stream(websocket: WebSocket):
        """Main WebSocket handler for media stream from Twilio."""
        await websocket.accept()
        try:
            client = AsyncOpenAI(api_key=OPENAI_API_KEY)
            async with client.beta.realtime.connect(model=OPENAI_PREVIEW_MODEL) as openai_ws:
                await OpenAIService.initialize_session(openai_ws)

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
                                    await openai_ws.send({
                                        "type": "input_audio_buffer.append",
                                        "audio": data["media"]["payload"]
                                    })
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
                            response = normalize_event_to_dict(event)
                            t = response.get("type")

                            if t in LOG_EVENT_TYPES:
                                if t == "error" and response.get("error", {}).get("code") == "input_audio_buffer_commit_empty":
                                    continue
                                print("OpenAI event:", response, flush=True)

                            if t == "response.audio.delta" and "delta" in response:
                                if websocket.client_state != WebSocketState.CONNECTED:
                                    break
                                audio_payload = response["delta"]
                                await websocket.send_json({
                                    "event": "media",
                                    "streamSid": stream_sid,
                                    "media": {"payload": audio_payload}
                                })
                                if response_start_timestamp_twilio is None:
                                    response_start_timestamp_twilio = latest_media_timestamp
                                if response.get("item_id"):
                                    last_assistant_item = response["item_id"]
                                await WebSocketHandler.send_mark(websocket, stream_sid)

                            elif t == "input_audio_buffer.speech_started":
                                await handle_speech_started_event()

                            elif t == "response.function_call":
                                await WebSocketHandler.handle_function_call(
                                    response, openai_ws, state, stream_sid
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

    @staticmethod
    async def send_mark(connection: WebSocket, sid: Optional[str]):
        """Send a mark event to Twilio WebSocket."""
        if sid and connection.client_state == WebSocketState.CONNECTED:
            await connection.send_json({
                "event": "mark",
                "streamSid": sid,
                "mark": {"name": "responsePart"}
            })

    @staticmethod
    async def handle_function_call(response, openai_ws, state, stream_sid):
        """Handle function calls from OpenAI."""
        name = response.get("name")
        call_id = response.get("id") or response.get("call_id")
        args = safe_parse_arguments(response.get("arguments"))

        if state is None and stream_sid:
            state = CALL_STATE.setdefault(stream_sid, IntakeState())

        if name == "validate_address":
            address_text = args.get("address_text", "") or args.get("address") or ""
            result = await AddressService.validate_address(address_text)
            if state is not None:
                state.update(address=address_text, address_is_valid=result.get("is_valid"))
            await OpenAIService.send_function_result(openai_ws, call_id, result)

        elif name == "update_intake_state":
            if state is not None:
                mapped = dict(args)
                if "full_name" in mapped:
                    mapped["patient_name"] = mapped.pop("full_name")
                if "referral_physician" in mapped:
                    mapped["referring_physician"] = mapped.pop("referral_physician")
                state.update(**mapped)

                if "patient_name" in mapped:
                    full_name = mapped["patient_name"]
                    print(f"Caller full name: {full_name}")

            await OpenAIService.send_function_result(
                openai_ws, call_id, {"ok": True, "state": state.data if state else {}}
            )

        elif name == "get_available_appointments":
            slots = AppointmentService.get_available_appointments()
            await OpenAIService.send_function_result(openai_ws, call_id, {"appointments": slots})

        elif name == "finalize_appointment":
            appt = args.get("appointment") or {}
            if state is not None:
                state.update(appointment_slot=appt)
            if state and state.is_complete():
                err = EmailService.send_confirmation_email(appt, state)
                await OpenAIService.send_function_result(
                    openai_ws, call_id, {"ok": err is None, "email_error": err, "state_complete": True}
                )
            else:
                await OpenAIService.send_function_result(
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
