
import os
from dotenv import load_dotenv

load_dotenv()

# --- Runtime config ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PORT = int(os.getenv("PORT", "8080"))
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.8"))
VOICE = os.getenv("VOICE", "alloy")

# --- System prompt ---
SYSTEM_MESSAGE = (
    "You are a helpful, accurate medical-intake assistant. "
    "Infer intent, explain briefly, and keep responses short. "
    "Use plain language and confirm critical details. "
    "Always stay positive, but work in a joke when appropriate."
)

# --- Logging/diagnostics ---
LOG_EVENT_TYPES = [
    "error", "response.content.done", "rate_limits.updated", "response.done",
    "input_audio_buffer.committed", "input_audio_buffer.speech_stopped",
    "input_audio_buffer.speech_started", "session.created", "session.updated"
]
SHOW_TIMING_MATH = False
