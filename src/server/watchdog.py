# src/server/watchdog.py
import asyncio
import aiohttp
import psutil
import os
import sys
from src.logger.config import setup_logger


class ServerWatchdog:
    def __init__(self, check_interval: int = 300, max_connections: int = 100):
        self.logger = setup_logger(__name__)
        self.check_interval = check_interval
        self.max_connections = max_connections
        self.health_url = "http://127.0.0.1:80/health"
        self.consecutive_failures = 0
        self.max_failures = 3
        self.is_running = False

    async def start(self):
        """Запуск watchdog в фоновом режиме"""
        if self.is_running:
            return

        self.is_running = True
        self.logger.info(f"Watchdog запущен: проверка каждые {self.check_interval} сек")

        while self.is_running:
            try:
                await self._perform_checks()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                self.logger.error(f"Ошибка в watchdog: {e}")
                await asyncio.sleep(30)  # короткая пауза при ошибке

    def stop(self):
        """Остановка watchdog"""
        self.is_running = False
        self.logger.info("Watchdog остановлен")

    async def _perform_checks(self):
        """Выполнение всех проверок"""
        http_ok = await self._check_http_health()
        connections_ok = self._check_connections()

        if http_ok and connections_ok:
            self.consecutive_failures = 0
            self.logger.info("Watchdog: все проверки прошли успешно")
        else:
            self.consecutive_failures += 1
            self.logger.warning(f"Watchdog: обнаружены проблемы (неудач подряд: {self.consecutive_failures})")

            if self.consecutive_failures >= self.max_failures:
                await self._handle_critical_failure()

    async def _check_http_health(self) -> bool:
        """Проверка HTTP порта через self-request"""
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self.health_url) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("status") == "ok":
                            return True

            self.logger.warning("HTTP health check: неверный ответ сервера")
            return False

        except asyncio.TimeoutError:
            self.logger.warning("HTTP health check: таймаут")
            return False
        except Exception as e:
            self.logger.warning(f"HTTP health check: ошибка {e}")
            return False

    def _check_connections(self) -> bool:
        """Проверка количества TCP соединений"""
        try:
            current_pid = os.getpid()
            process = psutil.Process(current_pid)

            # Получаем все соединения процесса (используем net_connections вместо connections)
            connections = process.net_connections(kind='tcp')

            # Фильтруем только ESTABLISHED соединения
            established = [conn for conn in connections if conn.status == 'ESTABLISHED']

            connection_count = len(established)

            if connection_count > self.max_connections:
                self.logger.warning(f"Слишком много соединений: {connection_count}/{self.max_connections}")
                return False

            self.logger.info(f"TCP соединений: {connection_count}/{self.max_connections}")
            return True

        except Exception as e:
            self.logger.error(f"Ошибка проверки соединений: {e}")
            return False

    async def _handle_critical_failure(self):
        """Обработка критической ошибки - перезапуск сервера"""
        self.logger.error("КРИТИЧЕСКАЯ ОШИБКА: перезапуск сервера через 5 секунд...")

        # Даем время для записи логов
        await asyncio.sleep(5)

        # Принудительный перезапуск процесса
        try:
            # Получаем текущие аргументы запуска
            python_executable = sys.executable
            script_path = sys.argv[0]

            self.logger.info(f"Перезапуск: {python_executable} {script_path}")

            # Перезапускаем процесс
            os.execv(python_executable, [python_executable, script_path])

        except Exception as e:
            self.logger.error(f"Ошибка перезапуска: {e}")
            # Если перезапуск не удался, завершаем процесс
            self.logger.error("Принудительное завершение процесса")
            os._exit(1)