# src/trading/bybit/strategy.py
import time
from .engine import BybitEngine
from .config import BybitConfig
from ..signal_filter import SignalFilter
from src.parser.models import TradingSignal, SignalType
from src.logger.config import setup_logger


class BybitStrategy:
    def __init__(self, symbol: str = "ETHUSDT"):
        self.logger = setup_logger(__name__)
        self.config = BybitConfig.from_env()
        self.signal_filter = SignalFilter()
        self.engine = BybitEngine(self.config, symbol)

    def process_signal(self, signal: TradingSignal) -> bool:
        try:
            # Уровень 1: Фильтр чередования
            if not self.signal_filter.should_process(signal):
                return True

            # Уровень 2: Проверка текущей позиции на бирже
            current_position = self.engine.get_current_position()

            if current_position is None:
                return self._open_new_position(signal)

            current_side = current_position['side']
            current_signal = SignalType.LONG if current_side == "Buy" else SignalType.SHORT

            if current_signal == signal.signal:
                self.logger.info(f"Позиция {signal.signal.value} уже открыта - пропускаем")
                return True

            return self._reverse_position(signal)

        except Exception as e:
            self.logger.error(f"Ошибка обработки сигнала {signal}: {e}")
            return False

    def _open_new_position(self, signal: TradingSignal) -> bool:
        """Открытие новой позиции когда текущей нет"""

        if signal.is_long:
            return self.engine.open_long()
        else:
            return self.engine.open_short()

    def _reverse_position(self, signal: TradingSignal) -> bool:
        """Закрытие текущей позиции и открытие новой"""
        self.logger.info(f"Разворот позиции в {signal.signal.value}")

        if not self.engine.close_position():
            self.logger.error("Не удалось закрыть текущую позицию")
            return False

        # Задержка после закрытия
        time.sleep(1)

        if signal.is_long:
            return self.engine.open_long()
        else:
            return self.engine.open_short()

    def get_position_info(self):
        return self.engine.get_current_position()

    def get_balance(self) -> float:
        return self.engine.get_account_balance()