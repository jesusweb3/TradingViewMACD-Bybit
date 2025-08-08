# src/trading/signal_filter.py
from typing import Optional
from src.parser.models import TradingSignal, SignalType
from src.logger.config import setup_logger


class SignalFilter:
    def __init__(self):
        self.logger = setup_logger(__name__)
        self.last_signal: Optional[SignalType] = None

    def should_process(self, signal: TradingSignal) -> bool:
        """
        Проверяет должен ли сигнал быть обработан на основе чередования
        """
        if self.last_signal is None:
            # Первый сигнал - всегда обрабатываем
            self.last_signal = signal.signal
            self.logger.info(f"Первый сигнал {signal.signal.value} - принят к обработке")
            return True

        if self.last_signal == signal.signal:
            # Одинаковый сигнал подряд - игнорируем
            self.logger.info(f"Дублирующий сигнал {signal.signal.value} - игнорируется")
            return False

        # Противоположный сигнал - обрабатываем и обновляем состояние
        self.last_signal = signal.signal
        self.logger.info(f"Чередующий сигнал {signal.signal.value} - принят к обработке")
        return True