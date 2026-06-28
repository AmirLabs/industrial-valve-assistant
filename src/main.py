from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.chat import router
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
app = FastAPI(title="Industrial Valve Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # later, change "*" to your real website domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")