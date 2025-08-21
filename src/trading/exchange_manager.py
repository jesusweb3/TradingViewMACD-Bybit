# src/trading/exchange_manager.py
import os
from enum import Enum
from typing import Union
from .bybit import BybitStrategy
from .binance import BinanceStrategy
from src.logger.config import setup_logger


class ExchangeType(Enum):
    BYBIT = "bybit"
    BINANCE = "binance"


class ExchangeManager:
    def __init__(self):
        self.logger = setup_logger(__name__)
        self.active_exchange = self._detect_active_exchange()

    def _detect_active_exchange(self) -> ExchangeType:
        bybit_enabled = os.getenv('BYBIT_ENABLED', 'false').lower() == 'true'
        binance_enabled = os.getenv('BINANCE_ENABLED', 'false').lower() == 'true'

        if bybit_enabled and binance_enabled:
            raise ValueError("Ошибка: BYBIT_ENABLED и BINANCE_ENABLED не могут быть одновременно true")

        if not bybit_enabled and not binance_enabled:
            raise ValueError("Ошибка: Должна быть включена одна из бирж (BYBIT_ENABLED=true или BINANCE_ENABLED=true)")

        if bybit_enabled:
            self.logger.info("Активная биржа: ByBit")
            return ExchangeType.BYBIT
        else:
            self.logger.info("Активная биржа: Binance")
            return ExchangeType.BINANCE

    def get_trading_strategy(self, symbol: str = None) -> Union[BybitStrategy, BinanceStrategy]:
        if symbol is None:
            # Читаем символ из переменных окружения
            if self.active_exchange == ExchangeType.BYBIT:
                symbol = os.getenv('BYBIT_SYMBOL', 'ETHUSDT')
            else:
                symbol = os.getenv('BINANCE_SYMBOL', 'ETHUSDC')

        self.logger.info(f"Инициализация торговой стратегии для {symbol}")

        if self.active_exchange == ExchangeType.BYBIT:
            return BybitStrategy(symbol)
        elif self.active_exchange == ExchangeType.BINANCE:
            return BinanceStrategy(symbol)
        else:
            raise ValueError(f"Неизвестная биржа: {self.active_exchange}")

    @property
    def is_bybit_active(self) -> bool:
        return self.active_exchange == ExchangeType.BYBIT

    @property
    def is_binance_active(self) -> bool:
        return self.active_exchange == ExchangeType.BINANCE