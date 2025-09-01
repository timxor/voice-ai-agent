"""
FastAPI routes for handling Twilio webhooks.
"""
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from twilio.twiml.voice_response import VoiceResponse, Connect


class Routes:
    """Contains all FastAPI route handlers."""

    def __init__(self, app: FastAPI):
        self.app = app
        self._setup_routes()

    def _setup_routes(self):
        """Setup all route handlers."""
        self.app.get("/", response_class=JSONResponse)(self.index_page)
        self.app.post("/", response_class=HTMLResponse)(self.root_incoming)
        self.app.api_route("/incoming-call", methods=["GET", "POST"])(self.handle_incoming_call)

    async def index_page(self):
        """Root endpoint returning status information."""
        return {
            "message": "Tim's Realtime Voice AI Agent that you can call at +1 (872) 224-3989 — Server is running."
        }

    async def root_incoming(self, request: Request):
        """Handle POST requests to root - redirect to incoming call handler."""
        return await self.handle_incoming_call(request)

    async def handle_incoming_call(self, request: Request):
        """Handle incoming call webhook from Twilio."""
        response = VoiceResponse()
        host = request.url.hostname
        if "ngrok" in request.headers.get("host", ""):
            host = request.headers["host"]
        connect = Connect()
        connect.stream(url=f"wss://{host}/media-stream")
        response.append(connect)
        print(f"Using WebSocket URL: wss://{host}/media-stream", flush=True)
        return HTMLResponse(content=str(response), media_type="application/xml")
