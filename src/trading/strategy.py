# src/trading/strategy.py
from typing import Optional
from .engine import TradingEngine
from .config import TradingConfig
from .signal_filter import SignalFilter
from src.parser.models import TradingSignal, SignalType
from src.logger.config import setup_logger


class TradingStrategy:
    def __init__(self):
        self.logger = setup_logger(__name__)
        self.config = TradingConfig.from_env()
        self.signal_filter = SignalFilter()
        self.engine: Optional[TradingEngine] = None

    def _get_engine(self, symbol: str) -> TradingEngine:
        if self.engine is None or self.engine.symbol != symbol:
            self.logger.info(f"Создание торгового движка для {symbol}")
            self.engine = TradingEngine(self.config, symbol)
        return self.engine

    def process_signal(self, signal: TradingSignal) -> bool:
        try:
            # Уровень 1: Фильтр чередования
            if not self.signal_filter.should_process(signal):
                return True  # Сигнал корректно отфильтрован

            self.logger.info(f"Обработка сигнала: {signal}")
            engine = self._get_engine(signal.symbol)

            # Уровень 2: Проверка текущей позиции на бирже
            current_position = engine.get_current_position()

            if current_position is None:
                # Нет позиции - просто открываем
                return self._open_new_position(engine, signal)

            # Есть позиция - проверяем направление
            current_side = current_position['side']  # "Buy" или "Sell"
            current_signal = SignalType.LONG if current_side == "Buy" else SignalType.SHORT

            if current_signal == signal.signal:
                # Позиция уже в нужном направлении (открыта руками)
                self.logger.info(f"Позиция {signal.signal.value} уже открыта - пропускаем")
                return True

            # Нужно закрыть текущую и открыть новую
            return self._reverse_position(engine, signal)

        except Exception as e:
            self.logger.error(f"Ошибка обработки сигнала {signal}: {e}")
            return False

    def _open_new_position(self, engine: TradingEngine, signal: TradingSignal) -> bool:
        """Открытие новой позиции когда текущей нет"""
        self.logger.info(f"Открытие новой позиции {signal.signal.value}")

        if signal.is_long:
            return engine.open_long()
        else:
            return engine.open_short()

    def _reverse_position(self, engine: TradingEngine, signal: TradingSignal) -> bool:
        """Закрытие текущей позиции и открытие новой"""
        self.logger.info(f"Разворот позиции в {signal.signal.value}")

        # Закрываем текущую
        if not engine.close_position():
            self.logger.error("Не удалось закрыть текущую позицию")
            return False

        # Открываем новую
        if signal.is_long:
            return engine.open_long()
        else:
            return engine.open_short()

    def get_position_info(self, symbol: str):
        if self.engine and self.engine.symbol == symbol:
            return self.engine.get_current_position()
        return None

    def get_balance(self) -> float:
        if self.engine:
            return self.engine.get_account_balance()

        # Создаем временный движок если нет активного
        temp_engine = TradingEngine(self.config, "BTCUSDT")
        return temp_engine.get_account_balance()