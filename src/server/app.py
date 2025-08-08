# src/server/app.py
import os
from fastapi import FastAPI, Request, HTTPException
import uvicorn
import requests
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from src.logger.config import setup_logger
from src.parser import SignalParser, SignalParserError
from src.trading import TradingStrategy

load_dotenv()

logger = setup_logger(__name__)

trading_strategy: TradingStrategy | None = None

def get_server_ip():
    if external_ip := os.getenv("SERVER_IP"):
        return external_ip

    try:
        response = requests.get('https://ipinfo.io/ip', timeout=5)
        return response.text.strip()
    except requests.RequestException as e:
        logger.error(f"Не удалось получить внешний IP: {e}")
        raise RuntimeError("Ошибка получения внешнего IP сервера")


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
    global trading_strategy

    logger.info("Сервер успешно запущен")
    server_ip = get_server_ip()
    logger.info(f"Ваш хук для TradingView: http://{server_ip}/webhook")

    # Инициализация торговой стратегии
    try:
        trading_strategy = TradingStrategy()
        logger.info("Торговая стратегия инициализирована")
    except Exception as e:
        logger.error(f"Ошибка инициализации торговой стратегии: {e}")
        raise RuntimeError(f"Не удалось инициализировать торговую стратегию: {e}")

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

        # Парсинг сигнала
        trading_signal = SignalParser.parse(data)

        # Обработка сигнала торговой стратегией
        if trading_strategy is None:
            logger.error("Торговая стратегия не инициализирована")
            raise HTTPException(status_code=500, detail="Trading strategy not initialized")

        success = trading_strategy.process_signal(trading_signal)

        if success:
            logger.info(f"Сигнал {trading_signal} успешно обработан")
            return {"status": "ok", "signal": str(trading_signal), "processed": True}
        else:
            logger.warning(f"Сигнал {trading_signal} не был обработан")
            return {"status": "ok", "signal": str(trading_signal), "processed": False}

    except SignalParserError as e:
        logger.error(f"Ошибка парсинга: {e}")
        raise HTTPException(status_code=400, detail=str(e))
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