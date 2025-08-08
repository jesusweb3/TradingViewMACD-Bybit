# src/server/app.py
from fastapi import FastAPI, Request, HTTPException
import uvicorn
import os
from contextlib import asynccontextmanager
from src.logger.config import setup_logger

logger = setup_logger(__name__)


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    return request.client.host


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("Сервер успешно запущен")
    logger.info(f"Ваш хук для TradingView: http://pboard.space/webhook")
    yield


app = FastAPI(lifespan=lifespan)

ALLOWED_IPS = {
    "52.89.214.238",
    "34.212.75.30",
    "54.218.53.128",
    "52.32.178.7",
    "5.145.227.179"
}

DEVELOPMENT_MODE = os.getenv("DEV_MODE", "false").lower() == "true"


@app.post("/webhook")
async def webhook_handler(request: Request):
    try:
        client_ip = get_client_ip(request)

        if not DEVELOPMENT_MODE and client_ip not in ALLOWED_IPS:
            raise HTTPException(status_code=403, detail="Forbidden")

        data = await request.json()
        logger.info(f"Получен вебхук от {client_ip}: {data}")
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Ошибка в webhook_handler: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def start_server():
    logger.info("Запуск сервера")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=80,
        log_level="error"
    )