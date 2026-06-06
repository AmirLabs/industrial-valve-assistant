from fastapi import FastAPI
from src.api.chat import router

app = FastAPI(title="Industrial Valve Assistant")

app.include_router(router, prefix="/api/v1")