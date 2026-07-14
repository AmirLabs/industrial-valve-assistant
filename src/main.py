from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.chat import router
from src.database.conversation_engine import init_conversation_db
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs once, when the server starts. Creates conversations.db / tables if missing.
    await init_conversation_db()
    yield
    # (nothing needed on shutdown for now)


app = FastAPI(title="Industrial Valve Assistant", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # later, change "*" to your real website domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")