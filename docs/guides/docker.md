# Docker

## Setup

Make sure `OUTLINE_API_URL` and `OUTLINE_CERT_SHA256` are provided via environment variables or `.env`.

## Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV OUTLINE_API_URL=""
ENV OUTLINE_CERT_SHA256=""
ENV OUTLINE_ENABLE_LOGGING="true"
ENV OUTLINE_ENABLE_CIRCUIT_BREAKER="true"
ENV OUTLINE_CIRCUIT_FAILURE_THRESHOLD="5"
ENV OUTLINE_RATE_LIMIT="50"

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import asyncio; from app import health_check; exit(0 if asyncio.run(health_check()) else 1)"

CMD ["python", "app.py"]
```

## docker-compose.yml

```yaml
version: '3.8'

services:
  outline-manager:
    build: .
    env_file: .env.prod
    environment:
      - OUTLINE_ENABLE_LOGGING=true
      - OUTLINE_ENABLE_CIRCUIT_BREAKER=true
      - OUTLINE_CIRCUIT_FAILURE_THRESHOLD=5
      - OUTLINE_RATE_LIMIT=50
    restart: unless-stopped
    healthcheck:
      test: [ "CMD", "python", "-c", "import asyncio; from app import health_check; exit(0 if asyncio.run(health_check()) else 1)" ]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
    networks:
      - outline-net
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

networks:
  outline-net:
    driver: bridge
```

## app.py

```python
import asyncio
import logging

from pyoutlineapi import AsyncOutlineClient
from pyoutlineapi.health_monitoring import HealthMonitor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

_client = None
_monitor = None


async def health_check() -> bool:
    """Health check for Docker/Kubernetes."""
    global _client, _monitor

    if not _client:
        _client = AsyncOutlineClient.from_env()
        await _client.__aenter__()
        _monitor = HealthMonitor(_client)

    try:
        return await _monitor.quick_check()
    except Exception as e:
        logger.error("Health check failed: %s", e)
        return False


async def main() -> int:
    logger.info("Starting Outline VPN Manager...")

    async with AsyncOutlineClient.from_env() as client:
        monitor = HealthMonitor(client)
        if not await monitor.wait_for_healthy(timeout=60):
            logger.error("Service not healthy after 60s")
            return 1

        logger.info("Service healthy - starting operations")

        server = await client.get_server_info()
        logger.info("Managing server: %s", server.name)

        while True:
            await asyncio.sleep(60)
            health = await monitor.comprehensive_check()
            if not health.healthy:
                logger.warning("Health degraded: %s", health.failed_checks)

    return 0


if __name__ == "__main__":
    try:
        exit(asyncio.run(main()))
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")
    finally:
        if _client:
            asyncio.run(_client.shutdown())
```
