# src/server/app.py
import os
import time
from fastapi import FastAPI, Request, HTTPException
import uvicorn
import requests
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from src.logger.config import setup_logger
from src.parser import SignalParser, SignalParserError
from typing import Union
from src.trading import ExchangeManager, BybitStrategy
from .watchdog import ServerWatchdog

# Загружаем переменные из .env файла
load_dotenv()

logger = setup_logger(__name__)

# Глобальные переменные
exchange_manager: ExchangeManager | None = None
trading_strategy: Union[BybitStrategy, None] = None
watchdog: ServerWatchdog | None = None


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
    global exchange_manager, trading_strategy, watchdog

    logger.info("Сервер успешно запущен")
    server_ip = get_server_ip()
    logger.info(f"Ваш хук для TradingView: http://{server_ip}/webhook")

    # Инициализация менеджера бирж
    try:
        exchange_manager = ExchangeManager()
        logger.info("Exchange Manager инициализирован")
    except Exception as e:
        logger.error(f"Ошибка инициализации Exchange Manager: {e}")
        raise RuntimeError(f"Не удалось инициализировать Exchange Manager: {e}")

    # Инициализация торговой стратегии
    try:
        trading_strategy = exchange_manager.get_trading_strategy()
        logger.info("Торговая стратегия инициализирована")
    except Exception as e:
        logger.error(f"Ошибка инициализации торговой стратегии: {e}")
        raise RuntimeError(f"Не удалось инициализировать торговую стратегию: {e}")

    # Запуск watchdog
    try:
        watchdog = ServerWatchdog(check_interval=300, max_connections=50)
        import asyncio
        asyncio.create_task(watchdog.start())
        logger.info("Watchdog запущен")
    except Exception as e:
        logger.error(f"Ошибка запуска watchdog: {e}")

    yield

    # Остановка watchdog при завершении
    if watchdog:
        watchdog.stop()


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


@app.get("/health")
async def health_check():
    """Health check эндпоинт для watchdog"""
    return {
        "status": "ok",
        "timestamp": time.time(),
        "trading_active": trading_strategy is not None,
        "watchdog_active": watchdog is not None and watchdog.is_running,
        "active_exchange": exchange_manager.active_exchange.value if exchange_manager else None
    }


def start_server():
    logger.info("Запуск сервера")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=80,
        log_level="error"
    )