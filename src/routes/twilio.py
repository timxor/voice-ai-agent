from fastapi import Request
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse

async def twilio_webhook(request: Request):
    # Twilio will POST form-encoded parameters
    form = await request.form()
    resp = VoiceResponse()
    resp.say("Hello! This is your voice AI agent.")
    # …then hand off to your STT/LLM services, etc.
    return Response(content=str(resp), media_type="application/xml")
