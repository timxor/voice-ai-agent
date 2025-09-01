
import json
from config import LOG_EVENT_TYPES
from openai_client import forward_audio_delta_to_twilio
from call_state import CallState
from twilio_stream import TwilioReceiver  # for speech_started handling

class OpenAISender:
    """
    Reads events from OpenAI Realtime and pushes audio back to Twilio.
    """
    def __init__(self, websocket, openai_ws, state: CallState):
        self.websocket = websocket
        self.openai_ws = openai_ws
        self.state = state

    async def run(self) -> None:
        try:
            async for raw in self.openai_ws:
                msg = json.loads(raw)
                t = msg.get("type")
                if t in LOG_EVENT_TYPES:
                    print("OpenAI event:", t, msg)

                if t == "response.output_audio.delta" and "delta" in msg:
                    await forward_audio_delta_to_twilio(msg, self.state.stream_sid, self.websocket)
                    # Track start time for truncation math
                    if msg.get("item_id") and msg["item_id"] != self.state.last_assistant_item:
                        self.state.response_start_timestamp_twilio = self.state.latest_media_timestamp
                        self.state.last_assistant_item = msg["item_id"]

                elif t == "input_audio_buffer.speech_started":
                    # Caller started speaking
                    await self._on_speech_started()

        except Exception as e:
            print("Error in OpenAISender:", e)

    async def _on_speech_started(self) -> None:
        await TwilioReceiver(self.websocket, self.openai_ws, self.state).speech_started()

    async def send_mark(self, name: str) -> None:
        """Optional: send a 'mark' back to the Twilio client."""
        self.state.mark_queue.append(name)
        await self.websocket.send_json({
            "event": "mark",
            "streamSid": self.state.stream_sid,
            "mark": {"name": name}
        })
