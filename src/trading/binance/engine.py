# src/trading/binance/engine.py
from binance.client import Client
from binance.exceptions import BinanceAPIException
from typing import Optional, Dict, Any
from .config import BinanceConfig
from src.logger.config import setup_logger


class BinanceEngine:
    def __init__(self, config: BinanceConfig, symbol: str):
        self.config = config
        self.symbol = symbol
        self.logger = setup_logger(__name__)

        self.client = Client(
            api_key=self.config.api_key,
            api_secret=self.config.secret,
            testnet=self.config.testnet
        )

        # Устанавливаем URL только для testnet, для mainnet используется дефолтный
        if self.config.testnet:
            self.client.FUTURES_URL = 'https://testnet.binancefuture.com/fapi'

        self.current_position = None
        self.qty_precision = None
        self.price_precision = None
        self.min_qty = None
        self.min_notional = None

        self._initialize()

    def _initialize(self):
        self._get_symbol_info()
        self._setup_leverage()

    def _get_symbol_info(self):
        try:
            exchange_info = self.client.futures_exchange_info()

            symbol_info = None
            for symbol in exchange_info['symbols']:
                if symbol['symbol'] == self.symbol:
                    symbol_info = symbol
                    break

            if not symbol_info:
                raise RuntimeError(f"Символ {self.symbol} не найден")

            self.qty_precision = symbol_info['quantityPrecision']
            self.price_precision = symbol_info['pricePrecision']

            for filter_item in symbol_info['filters']:
                if filter_item['filterType'] == 'LOT_SIZE':
                    self.min_qty = float(filter_item['minQty'])
                elif filter_item['filterType'] == 'MIN_NOTIONAL':
                    self.min_notional = float(filter_item['minNotional'])

            self.logger.info(
                f"Параметры {self.symbol}: QtyPrecision={self.qty_precision}, MinQty={self.min_qty}, MinNotional={self.min_notional}")

        except Exception as e:
            self.logger.error(f"Ошибка получения информации о символе: {e}")
            raise

    def _setup_leverage(self):
        try:
            self.client.futures_change_leverage(
                symbol=self.symbol,
                leverage=self.config.leverage
            )
            self.logger.info(f"Плечо установлено {self.config.leverage}x для {self.symbol}")

        except BinanceAPIException as e:
            if e.code == -4028:
                self.logger.info(f"Плечо уже установлено {self.config.leverage}x для {self.symbol}")
            else:
                self.logger.error(f"Ошибка установки плеча: {e}")
        except Exception as e:
            self.logger.error(f"Ошибка установки плеча: {e}")

    def _round_quantity(self, quantity: float) -> float:
        if self.qty_precision is None:
            return round(quantity, 3)

        rounded_qty = round(quantity, self.qty_precision)

        if rounded_qty < self.min_qty:
            rounded_qty = self.min_qty

        return rounded_qty

    def _round_price(self, price: float) -> float:
        if self.price_precision is None:
            return round(price, 2)

        return round(price, self.price_precision)

    def get_account_balance(self) -> float:
        try:
            account = self.client.futures_account()

            for asset in account['assets']:
                if asset['asset'] == 'USDT':
                    return float(asset['walletBalance'])
            return 0

        except Exception as e:
            self.logger.error(f"Ошибка получения баланса: {e}")
            return 0

    def get_current_position(self) -> Optional[Dict[str, Any]]:
        try:
            positions = self.client.futures_position_information(symbol=self.symbol)

            if positions:
                position = positions[0]
                size = abs(float(position['positionAmt']))

                if size > 0:
                    side = "Buy" if float(position['positionAmt']) > 0 else "Sell"
                    return {
                        'side': side,
                        'size': size,
                        'entry_price': float(position['entryPrice']),
                        'unrealized_pnl': float(position['unRealizedProfit'])
                    }
            return None

        except Exception as e:
            self.logger.error(f"Ошибка получения позиции: {e}")
            return None

    def get_current_price(self) -> float:
        try:
            ticker = self.client.futures_symbol_ticker(symbol=self.symbol)
            return float(ticker['price'])

        except Exception as e:
            self.logger.error(f"Ошибка получения цены: {e}")
            return 0

    def _calculate_quantity(self, price: float) -> float:
        total_value = self.config.position_size * self.config.leverage
        raw_quantity = total_value / price
        rounded_quantity = self._round_quantity(raw_quantity)

        self.logger.info(f"Расчет: {total_value} USDT / {price} = {rounded_quantity} {self.symbol}")
        return rounded_quantity

    def close_position(self) -> bool:
        position = self.get_current_position()
        if not position:
            return True

        try:
            opposite_side = "SELL" if position['side'] == "Buy" else "BUY"
            rounded_size = self._round_quantity(position['size'])

            self.client.futures_create_order(
                symbol=self.symbol,
                side=opposite_side,
                type='MARKET',
                quantity=rounded_size,
                reduceOnly=True
            )

            self.logger.info(f"Закрыта {position['side']} позиция, PnL: {position['unrealized_pnl']} USDT")
            self.current_position = None
            return True

        except Exception as e:
            self.logger.error(f"Ошибка закрытия позиции: {e}")
            return False

    def open_position(self, side: str) -> bool:
        current_price = self.get_current_price()
        if current_price == 0:
            self.logger.error("Не удалось получить текущую цену")
            return False

        quantity = self._calculate_quantity(current_price)
        balance = self.get_account_balance()

        if balance < self.config.position_size:
            self.logger.error(f"Недостаточно средств. Требуется: {self.config.position_size}, доступно: {balance}")
            return False

        if quantity < self.min_qty:
            self.logger.error(f"Количество {quantity} меньше минимального {self.min_qty}")
            return False

        try:
            self.client.futures_create_order(
                symbol=self.symbol,
                side=side,
                type='MARKET',
                quantity=quantity
            )

            direction = "Long" if side == "BUY" else "Short"
            self.logger.info(f"Открыта {direction} позиция: {self.config.position_size} USDT по {current_price}")
            self.current_position = {
                'side': "Buy" if side == "BUY" else "Sell",
                'size': quantity,
                'entry_price': current_price
            }
            return True

        except Exception as e:
            self.logger.error(f"Ошибка открытия позиции: {e}")
            return False

    def open_long(self) -> bool:
        return self.open_position("BUY")

    def open_short(self) -> bool:
        return self.open_position("SELL")