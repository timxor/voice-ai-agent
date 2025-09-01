"""
Configuration and constants for the voice AI agent.
"""
import os
import resend
from dotenv import load_dotenv

load_dotenv()

# =============================
# Server Configuration
# =============================
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8080))

# =============================
# OpenAI Configuration
# =============================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_REALTIME_MODEL = "gpt-realtime"
OPENAI_PREVIEW_MODEL = "gpt-4o-realtime-preview-2024-10-01"
VOICE = "alloy"
TEMPERATURE = 0.8

if not OPENAI_API_KEY:
    raise ValueError("Missing the OpenAI API key. Please set it in the .env file.")

# =============================
# Resend Email Configuration
# =============================
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
RESEND_FROM = os.getenv("RESEND_FROM", "updates@updates.timsiwula.com")

if not RESEND_API_KEY:
    raise ValueError("Missing RESEND_API_KEY. Please set it in the .env file.")

resend.api_key = RESEND_API_KEY

# Email recipients
email_string = os.environ.get("EMAIL_RECIPIENTS", "")
BOOKING_RECIPIENTS = [email.strip() for email in email_string.split(",") if email.strip()]

# =============================
# External Service Configuration
# =============================
# Optional: Geoapify
GEOAPIFY_API_KEY = os.getenv("GEOAPIFY_API_KEY")

# =============================
# Application Constants
# =============================
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

# =============================
# Twilio Configuration
# =============================
# Twilio media stream specifics
TWILIO_FRAME_MS = 20
COMMIT_THRESHOLD_MS = 60
