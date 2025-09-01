"""
OpenAI service for managing realtime sessions and function calls.
"""
from typing import Optional, Any
from config import SYSTEM_MESSAGE, VOICE, TEMPERATURE


class OpenAIService:
    """Service for managing OpenAI realtime sessions."""

    @staticmethod
    async def initialize_session(openai_ws, stream_sid: Optional[str] = None):
        """Initialize an OpenAI realtime session with tools and configuration."""
        # print(f"Initializing OpenAI session for stream_sid: {stream_sid}", flush=True)
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
        # print(f"Sending session update: {session_update}", flush=True)
        await openai_ws.send(session_update)
        await OpenAIService.send_initial_conversation_item(openai_ws)

    @staticmethod
    async def send_initial_conversation_item(openai_ws):
        """Send the initial conversation item to start the session."""
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
        await openai_ws.send(initial_conversation_item)
        await openai_ws.send({"type": "response.create"})

    @staticmethod
    async def send_function_result(openai_ws, call_id: str, result: Any):
        """Send function call result back to OpenAI."""
        payload = {
            "type": "conversation.item.create",
            "item": {
                "type": "function_result",
                "call_id": call_id,
                "output": result
            }
        }
        await openai_ws.send(payload)
        await openai_ws.send({"type": "response.create"})
