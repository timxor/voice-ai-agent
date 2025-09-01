
from fastapi import FastAPI
from config import OPENAI_API_KEY, PORT
from endpoints import router as endpoints_router

app = FastAPI()

if not OPENAI_API_KEY:
    raise ValueError("Missing the OPENAI_API_KEY. Please set it in .env")

# Mount endpoints
app.include_router(endpoints_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
