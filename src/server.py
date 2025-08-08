import os
from fastapi import FastAPI, Request
from fastapi.responses import Response
from dotenv import load_dotenv

# Fix Python import path issue when using 'src' layout
import sys
import pathlib
sys.path.append(str(pathlib.Path(__file__).resolve().parent))

from routes.twilio import twilio_webhook

# Load environment variables from .env
load_dotenv()

app = FastAPI(title="Voice AI Agent")

@app.get("/")
async def health_check():
    return {"status": "ok"}

# Mount Twilio webhook endpoint
app.post("/twilio")(twilio_webhook)

def main():
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    print(f"🚀 Starting server at: http://{host}:{port}")
    uvicorn.run(
        "src.server:app",
        host=host,
        port=port,
        reload=True,
    )

if __name__ == "__main__":
    main()
