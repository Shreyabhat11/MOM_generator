from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import documents, health
from app.config import get_settings
from app.logging_conf import configure_logging

configure_logging()
settings = get_settings()

app = FastAPI(title="MoM Generator", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(documents.router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # Spec section 23: never leak stack traces to the client.
    return JSONResponse(status_code=500, content={"detail": "An unexpected error occurred."})
