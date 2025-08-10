# src/trading/bybit/engine.py
from pybit.unified_trading import HTTP
from typing import Optional, Dict, Any
from .config import BybitConfig
from src.logger.config import setup_logger


class BybitEngine:
    def __init__(self, config: BybitConfig, symbol: str):
        self.config = config
        self.symbol = symbol
        self.logger = setup_logger(__name__)

        self.session = HTTP(
            testnet=self.config.testnet,
            api_key=self.config.api_key,
            api_secret=self.config.secret
        )

        self.current_position = None
        self.qty_step = None
        self.min_order_qty = None
        self.max_order_qty = None
        self.tick_size = None

        self._initialize()

    def _initialize(self):
        self._get_instrument_info()
        self._setup_leverage()

    def _get_instrument_info(self):
        try:
            response = self.session.get_instruments_info(
                category="linear",
                symbol=self.symbol
            )

            if response['retCode'] == 0 and response['result']['list']:
                instrument = response['result']['list'][0]

                lot_size_filter = instrument['lotSizeFilter']
                self.qty_step = float(lot_size_filter['qtyStep'])
                self.min_order_qty = float(lot_size_filter['minOrderQty'])
                self.max_order_qty = float(lot_size_filter['maxOrderQty'])

                price_filter = instrument['priceFilter']
                self.tick_size = float(price_filter['tickSize'])
                self.logger.info(
                    f"Параметры {self.symbol}: QtyStep={self.qty_step}, MinQty={self.min_order_qty}, TickSize={self.tick_size}")
            else:
                raise RuntimeError(
                    f"Не удалось получить информацию об инструменте {self.symbol}: {response.get('retMsg', 'Unknown error')}")

        except Exception as e:
            self.logger.error(f"Ошибка получения информации об инструменте: {e}")
            raise

    def _setup_leverage(self):
        try:
            response = self.session.set_leverage(
                category="linear",
                symbol=self.symbol,
                buyLeverage=str(self.config.leverage),
                sellLeverage=str(self.config.leverage)
            )

            if response['retCode'] == 0:
                self.logger.info(f"Плечо установлено {self.config.leverage}x для {self.symbol}")
            elif response.get('retCode') == 110043:
                self.logger.info(f"Плечо уже установлено {self.config.leverage}x для {self.symbol}")
            else:
                self.logger.error(f"Не удалось установить плечо: {response['retMsg']}")

        except Exception as e:
            if "110043" in str(e):
                self.logger.info(f"Плечо уже установлено {self.config.leverage}x для {self.symbol}")
            else:
                self.logger.error(f"Ошибка установки плеча: {e}")

    def _round_quantity(self, quantity: float) -> float:
        if self.qty_step is None:
            return round(quantity, 3)

        precision = len(str(self.qty_step).split('.')[-1]) if '.' in str(self.qty_step) else 0
        rounded_qty = round(quantity / self.qty_step) * self.qty_step
        rounded_qty = round(rounded_qty, precision)

        if rounded_qty < self.min_order_qty:
            rounded_qty = self.min_order_qty
        elif rounded_qty > self.max_order_qty:
            rounded_qty = self.max_order_qty

        return rounded_qty

    def _round_price(self, price: float) -> float:
        if self.tick_size is None:
            return round(price, 2)

        precision = len(str(self.tick_size).split('.')[-1]) if '.' in str(self.tick_size) else 0
        rounded_price = round(price / self.tick_size) * self.tick_size
        return round(rounded_price, precision)

    def get_account_balance(self) -> float:
        try:
            response = self.session.get_wallet_balance(accountType="UNIFIED")

            if response['retCode'] == 0:
                for coin in response['result']['list'][0]['coin']:
                    if coin['coin'] == 'USDT':
                        return float(coin['walletBalance'])
            return 0

        except Exception as e:
            self.logger.error(f"Ошибка получения баланса: {e}")
            return 0

    def get_current_position(self) -> Optional[Dict[str, Any]]:
        try:
            response = self.session.get_positions(
                category="linear",
                symbol=self.symbol
            )

            if response['retCode'] == 0 and response['result']['list']:
                position = response['result']['list'][0]
                size = float(position['size'])

                if size > 0:
                    return {
                        'side': position['side'],
                        'size': size,
                        'entry_price': float(position['avgPrice']),
                        'unrealized_pnl': float(position['unrealisedPnl'])
                    }
            return None

        except Exception as e:
            self.logger.error(f"Ошибка получения позиции: {e}")
            return None

    def get_current_price(self) -> float:
        try:
            response = self.session.get_tickers(
                category="linear",
                symbol=self.symbol
            )

            if response['retCode'] == 0 and response['result']['list']:
                return float(response['result']['list'][0]['lastPrice'])
            return 0

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
            opposite_side = "Sell" if position['side'] == "Buy" else "Buy"
            rounded_size = self._round_quantity(position['size'])

            response = self.session.place_order(
                category="linear",
                symbol=self.symbol,
                side=opposite_side,
                orderType="Market",
                qty=str(rounded_size),
                reduceOnly=True
            )

            if response['retCode'] == 0:
                self.logger.info(f"Закрыта {position['side']} позиция, PnL: {position['unrealized_pnl']} USDT")
                self.current_position = None
                return True
            else:
                self.logger.error(f"Не удалось закрыть позицию: {response['retMsg']}")
                return False

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

        if quantity < self.min_order_qty:
            self.logger.error(f"Количество {quantity} меньше минимального {self.min_order_qty}")
            return False

        try:
            response = self.session.place_order(
                category="linear",
                symbol=self.symbol,
                side=side,
                orderType="Market",
                qty=str(quantity)
            )

            if response['retCode'] == 0:
                direction = "Long" if side == "Buy" else "Short"
                self.logger.info(f"Открыта {direction} позиция: {self.config.position_size} USDT по {current_price}")
                self.current_position = {
                    'side': side,
                    'size': quantity,
                    'entry_price': current_price
                }
                return True
            else:
                self.logger.error(f"Не удалось открыть позицию: {response['retMsg']}")
                return False

        except Exception as e:
            self.logger.error(f"Ошибка открытия позиции: {e}")
            return False

    def open_long(self) -> bool:
        return self.open_position("Buy")

    def open_short(self) -> bool:
        return self.open_position("Sell")