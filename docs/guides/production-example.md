# Production Example

## Setup

```python
from pyoutlineapi import AsyncOutlineClient

async with AsyncOutlineClient.from_env() as client:
    pass
```

```python
"""
Enterprise-grade Outline VPN management application.
Features: health monitoring, metrics collection, batch operations, audit logging.
"""
import asyncio
import logging
import signal
from typing import Optional

from pyoutlineapi import AsyncOutlineClient, DefaultAuditLogger
from pyoutlineapi.health_monitoring import HealthMonitor
from pyoutlineapi.batch_operations import BatchOperations
from pyoutlineapi.metrics_collector import MetricsCollector
from pyoutlineapi.exceptions import OutlineError, CircuitOpenError
from pyoutlineapi.models import DataLimit

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('outline_manager.log')
    ]
)
logger = logging.getLogger(__name__)


class OutlineManager:
    """Production-ready Outline VPN manager."""

    def __init__(self):
        self.client: Optional[AsyncOutlineClient] = None
        self.monitor: Optional[HealthMonitor] = None
        self.collector: Optional[MetricsCollector] = None
        self.shutdown_event = asyncio.Event()

    async def initialize(self) -> bool:
        """Initialize all components."""
        try:
            audit_logger = DefaultAuditLogger(
                enable_async=True,
                queue_size=5000,
            )

            self.client = AsyncOutlineClient.from_env(
                audit_logger=audit_logger,
                enable_circuit_breaker=True,
                circuit_failure_threshold=5,
                rate_limit=50,
            )
            await self.client.__aenter__()

            self.monitor = HealthMonitor(self.client, cache_ttl=30)

            logger.info("Waiting for service to become healthy...")
            if not await self.monitor.wait_for_healthy(timeout=120):
                logger.error("Service not healthy after 120s")
                return False

            logger.info("Service healthy!")

            self.collector = MetricsCollector(
                self.client,
                interval=60,
                max_history=1440,
            )
            await self.collector.start()
            logger.info("Metrics collection started")

            return True

        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            return False

    async def create_users(self, count: int) -> None:
        """Create multiple users with batch operations."""
        logger.info(f"Creating {count} users...")

        batch = BatchOperations(self.client, max_concurrent=10)
        configs = [
            {
                "name": f"User{i:04d}",
                "limit": DataLimit.from_gigabytes(10),
            }
            for i in range(1, count + 1)
        ]

        result = await batch.create_multiple_keys(configs, fail_fast=False)

        logger.info(f"Created: {result.successful}/{result.total}")
        logger.info(f"Success rate: {result.success_rate:.2%}")

        if result.has_errors:
            logger.warning(f"Errors: {result.errors}")

    async def monitor_loop(self) -> None:
        """Continuous health monitoring loop."""
        while not self.shutdown_event.is_set():
            try:
                health = await self.monitor.comprehensive_check()

                if not health.healthy:
                    logger.warning(f"Health check failed: {health.failed_checks}")

                if health.is_degraded:
                    logger.warning(f"Service degraded: {health.warning_checks}")

                await asyncio.sleep(30)

            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
                await asyncio.sleep(10)

    async def metrics_report(self) -> None:
        """Periodic metrics reporting."""
        while not self.shutdown_event.is_set():
            try:
                await asyncio.sleep(300)

                stats = self.collector.get_usage_stats(period_minutes=60)
                logger.info(
                    "1h traffic: %.2f GB | active keys: %d",
                    stats.gigabytes_transferred,
                    len(stats.active_keys),
                )

            except Exception as e:
                logger.error(f"Metrics report error: {e}")

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        self.shutdown_event.set()

        if self.collector:
            await self.collector.stop()

        if self.client:
            await self.client.shutdown()

    async def run(self) -> int:
        if not await self.initialize():
            return 1

        tasks = [
            asyncio.create_task(self.monitor_loop()),
            asyncio.create_task(self.metrics_report()),
        ]

        await self.shutdown_event.wait()

        for task in tasks:
            task.cancel()

        await self.shutdown()
        return 0


def setup_signal_handlers(manager: OutlineManager) -> None:
    def _handler(_sig, _frame):
        logger.info("Shutdown signal received")
        manager.shutdown_event.set()

    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)


async def main() -> int:
    manager = OutlineManager()
    setup_signal_handlers(manager)
    return await manager.run()


if __name__ == "__main__":
    try:
        exit(asyncio.run(main()))
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")
```
