# src/trading/bybit/config.py
import os
from dataclasses import dataclass

@dataclass
class BybitConfig:
    api_key: str
    secret: str
    testnet: bool
    position_size: float
    leverage: int

    @classmethod
    def from_env(cls) -> 'BybitConfig':
        api_key = os.getenv('BYBIT_API_KEY')
        secret = os.getenv('BYBIT_SECRET')

        if not api_key or not secret:
            raise ValueError("BYBIT_API_KEY и BYBIT_SECRET должны быть установлены")

        testnet = os.getenv('BYBIT_TESTNET', 'false').lower() == 'true'
        position_size = float(os.getenv('POSITION_SIZE', '100'))
        leverage = int(os.getenv('LEVERAGE', '10'))

        return cls(
            api_key=api_key,
            secret=secret,
            testnet=testnet,
            position_size=position_size,
            leverage=leverage
        )