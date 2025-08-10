# src/trading/binance/config.py
import os
from dataclasses import dataclass

@dataclass
class BinanceConfig:
    api_key: str
    secret: str
    testnet: bool
    position_size: float
    leverage: int

    @classmethod
    def from_env(cls) -> 'BinanceConfig':
        api_key = os.getenv('BINANCE_API_KEY')
        secret = os.getenv('BINANCE_SECRET')

        if not api_key or not secret:
            raise ValueError("BINANCE_API_KEY и BINANCE_SECRET должны быть установлены")

        testnet = os.getenv('BINANCE_TESTNET', 'false').lower() == 'true'
        position_size = float(os.getenv('POSITION_SIZE', '100'))
        leverage = int(os.getenv('LEVERAGE', '10'))

        return cls(
            api_key=api_key,
            secret=secret,
            testnet=testnet,
            position_size=position_size,
            leverage=leverage
        )