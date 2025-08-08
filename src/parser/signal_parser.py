# src/parser/signal_parser.py
from typing import Dict, Any
from .models import TradingSignal, SignalType
from src.logger.config import setup_logger

logger = setup_logger(__name__)


class SignalParserError(Exception):
    pass


class SignalParser:
    REQUIRED_FIELDS = {'symbol', 'signal'}

    @staticmethod
    def parse(webhook_data: Dict[str, Any]) -> TradingSignal:
        try:
            SignalParser._validate_data(webhook_data)

            symbol = webhook_data['symbol'].upper()
            signal_str = webhook_data['signal'].lower()
            timeframe = webhook_data.get('timeframe')

            signal_type = SignalParser._parse_signal_type(signal_str)

            trading_signal = TradingSignal(
                symbol=symbol,
                signal=signal_type,
                timeframe=timeframe
            )

            logger.info(f"Парсинг успешен: {trading_signal}")
            return trading_signal

        except Exception as e:
            logger.error(f"Ошибка парсинга сигнала: {e}")
            raise SignalParserError(f"Не удалось распарсить сигнал: {e}")

    @staticmethod
    def _validate_data(data: Dict[str, Any]) -> None:
        if not isinstance(data, dict):
            raise ValueError("Данные должны быть словарем")

        missing_fields = SignalParser.REQUIRED_FIELDS - data.keys()
        if missing_fields:
            raise ValueError(f"Отсутствуют обязательные поля: {missing_fields}")

        if not data['symbol'] or not isinstance(data['symbol'], str):
            raise ValueError("Поле 'symbol' должно быть непустой строкой")

        if not data['signal'] or not isinstance(data['signal'], str):
            raise ValueError("Поле 'signal' должно быть непустой строкой")

    @staticmethod
    def _parse_signal_type(signal_str: str) -> SignalType:
        try:
            return SignalType(signal_str)
        except ValueError:
            raise ValueError(f"Неизвестный тип сигнала: {signal_str}. Поддерживаются: long, short")