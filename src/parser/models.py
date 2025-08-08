# src/parser/models.py
from enum import Enum
from dataclasses import dataclass
from typing import Optional


class SignalType(Enum):
    LONG = "long"
    SHORT = "short"


@dataclass
class TradingSignal:
    symbol: str
    signal: SignalType
    timeframe: Optional[str] = None

    def __str__(self) -> str:
        return f"{self.symbol} {self.signal.value}"

    @property
    def is_long(self) -> bool:
        return self.signal == SignalType.LONG

    @property
    def is_short(self) -> bool:
        return self.signal == SignalType.SHORT