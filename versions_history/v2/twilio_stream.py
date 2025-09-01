
import json
from config import LOG_EVENT_TYPES, SHOW_TIMING_MATH
from call_state import CallState

class TwilioReceiver:
    """
    Reads websocket frames from Twilio, forwards audio to OpenAI, and reacts to
    events like 'start', 'media', 'mark', 'stop', and speech-state changes.
    """
    def __init__(self, websocket, openai_ws, state: CallState):
        self.websocket = websocket
        self.openai_ws = openai_ws
        self.state = state

    async def run(self) -> None:
        async for data in self.websocket.iter_json():
            event = data.get("event")
            if event == "start":
                self.state.stream_sid = data["start"]["streamSid"]
            elif event == "media":
                # Forward caller audio to OpenAI
                self.state.latest_media_timestamp = int(data["media"].get("timestamp", self.state.latest_media_timestamp))
                await self.openai_ws.send(json.dumps({
                    "type": "input_audio_buffer.append",
                    "audio": {"type": "input_audio", "audio": data["media"]["payload"]},
                }))
            elif event == "mark":
                mark_name = data.get("mark", {}).get("name")
                if mark_name:
                    self.state.mark_queue.append(mark_name)
            elif event == "stop":
                # Commit any buffered audio at end-of-call
                await self.openai_ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
                break
            elif event == "clear":
                # Optional: handle clear instructions from assistant side
                pass

    async def speech_started(self) -> None:
        """
        Called when OpenAI detects the caller started speaking (server VAD).
        We truncate any in-flight assistant audio and clear the Twilio buffer.
        """
        if self.state.mark_queue and self.state.response_start_timestamp_twilio is not None:
            elapsed = self.state.latest_media_timestamp - self.state.response_start_timestamp_twilio
            if SHOW_TIMING_MATH:
                print(f"[truncate] latest={self.state.latest_media_timestamp} - start={self.state.response_start_timestamp_twilio} = {elapsed}ms")

            # Ask OpenAI to truncate its current audio at 'elapsed' ms
            if self.state.last_assistant_item:
                await self.openai_ws.send(json.dumps({
                    "type": "conversation.item.truncate",
                    "item_id": self.state.last_assistant_item,
                    "content_index": 0,
                    "audio_end_ms": max(0, elapsed),
                }))

            # Tell Twilio client to clear pending audio
            await self.websocket.send_json({"event": "clear", "streamSid": self.state.stream_sid})
            self.state.mark_queue.clear()
