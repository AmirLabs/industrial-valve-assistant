from fastapi import FastAPI
from src.api.chat import router
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
app = FastAPI(title="Industrial Valve Assistant")

app.include_router(router, prefix="/api/v1")