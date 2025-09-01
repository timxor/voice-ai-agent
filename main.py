"""
Voice AI Agent - Refactored main entry point.
Coordinates FastAPI app, routes, and WebSocket handling.
"""
import uvicorn
from fastapi import FastAPI, WebSocket

from config import HOST, PORT
from routes import Routes
from websocket_handler import WebSocketHandler

# Initialize FastAPI app
app = FastAPI()

# Setup routes
routes = Routes(app)

# Setup WebSocket endpoint
@app.websocket("/media-stream")
async def handle_media_stream(websocket: WebSocket):
    """WebSocket endpoint for handling media streams from Twilio."""
    await WebSocketHandler.handle_media_stream(websocket)


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
