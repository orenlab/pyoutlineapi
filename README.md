# PyOutlineAPI

[![tests](https://github.com/orenlab/pyoutlineapi/actions/workflows/python_tests.yml/badge.svg)](https://github.com/orenlab/pyoutlineapi/actions/workflows/python_tests.yml)
[![codecov](https://codecov.io/gh/orenlab/pyoutlineapi/branch/main/graph/badge.svg?token=D0MPKCKFJQ)](https://codecov.io/gh/orenlab/pyoutlineapi)
[![Security Rating](https://sonarcloud.io/api/project_badges/measure?project=orenlab_pyoutlineapi&metric=security_rating)](https://sonarcloud.io/summary/new_code?id=orenlab_pyoutlineapi)
[![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=orenlab_pyoutlineapi&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=orenlab_pyoutlineapi)
[![Vulnerabilities](https://sonarcloud.io/api/project_badges/measure?project=orenlab_pyoutlineapi&metric=vulnerabilities)](https://sonarcloud.io/summary/new_code?id=orenlab_pyoutlineapi)

![PyPI - Downloads](https://img.shields.io/pypi/dm/pyoutlineapi)
![PyPI - Version](https://img.shields.io/pypi/v/pyoutlineapi)
![Python Version](https://img.shields.io/pypi/pyversions/pyoutlineapi)
![License](https://img.shields.io/pypi/l/pyoutlineapi)

**Production-ready async Python client for Outline VPN Server Management API**

[Installation](#-installation) •
[Quick Start](#-quick-start) •
[Features](#-features) •
[Documentation](#-documentation) •
[Examples](#-examples)

---

## 🎯 Overview

PyOutlineAPI is a modern, enterprise-grade Python library for managing [Outline VPN](https://getoutline.org/) servers.
Built with async/await, type safety, and production reliability in mind.

### Key Features

- **🚀 Async-First** - Built on aiohttp with efficient connection pooling
- **🔒 Secure by Default** - SecretStr, input validation, audit logging, sensitive data filtering
- **🛡️ Production-Ready** - Circuit breaker, health monitoring, graceful shutdown, retry logic
- **📝 Fully Typed** - 100% type hints, mypy strict mode compatible
- **⚡ High Performance** - Batch operations, rate limiting, lazy loading
- **🎯 Developer Friendly** - Rich IDE support, comprehensive docs, practical examples

---

## 📦 Installation

**Requirements:** Python 3.10+

```bash
pip install pyoutlineapi
```

**Optional dependencies:**

```bash
# Metrics collection with SortedContainers
pip install pyoutlineapi[metrics]

# Development tools
pip install pyoutlineapi[dev]
```

---

## 🚀 Quick Start

### 1. Setup Configuration

```bash
# Generate template
python -c "from pyoutlineapi import quick_setup; quick_setup()"

# Edit .env file
OUTLINE_API_URL=https://your-server.com:12345/your-secret-path
OUTLINE_CERT_SHA256=your-64-character-sha256-fingerprint
```

### 2. Basic Usage

```python
from pyoutlineapi import AsyncOutlineClient
import asyncio


async def main():
    # Use environment variables (recommended)
    async with AsyncOutlineClient.from_env() as client:
        # Get server info
        server = await client.get_server_info()
        print(f"Server: {server.name}")

        # Create access key
        key = await client.create_access_key(name="Alice")
        print(f"Access URL: {key.access_url}")

        # List all keys
        keys = await client.get_access_keys()
        print(f"Total keys: {keys.count}")


asyncio.run(main())
```

---

## ⚙️ Configuration

### Environment Variables (✅ Recommended)

**Most secure approach** - credentials never appear in code:

```python
from pyoutlineapi import AsyncOutlineClient

# Load from .env file
async with AsyncOutlineClient.from_env() as client:
    await client.get_server_info()

# Custom environment file
async with AsyncOutlineClient.from_env(env_file=".env.prod") as client:
    await client.get_server_info()

# Override specific settings
async with AsyncOutlineClient.from_env(
        timeout=30,
        enable_logging=True,
        enable_circuit_breaker=True
) as client:
    await client.get_server_info()
```

**Available environment variables:**

```bash
# Required
OUTLINE_API_URL=https://server.com:12345/secret
OUTLINE_CERT_SHA256=your-certificate-fingerprint

# Optional (with defaults)
OUTLINE_TIMEOUT=10
OUTLINE_RETRY_ATTEMPTS=2
OUTLINE_MAX_CONNECTIONS=10
OUTLINE_RATE_LIMIT=100
OUTLINE_ENABLE_CIRCUIT_BREAKER=true
OUTLINE_ENABLE_LOGGING=false
OUTLINE_JSON_FORMAT=false

# Circuit Breaker
OUTLINE_CIRCUIT_FAILURE_THRESHOLD=5
OUTLINE_CIRCUIT_RECOVERY_TIMEOUT=60.0
OUTLINE_CIRCUIT_CALL_TIMEOUT=10.0
```

### Configuration Object

```python
from pyoutlineapi import OutlineClientConfig
from pydantic import SecretStr

# Full configuration
config = OutlineClientConfig(
    api_url="https://server.com:12345/secret",
    cert_sha256=SecretStr("abc123..."),
    timeout=30,
    retry_attempts=5,
    enable_circuit_breaker=True,
    enable_logging=True,
)

async with AsyncOutlineClient(config) as client:
    await client.get_server_info()

# Environment-specific configs
from pyoutlineapi import DevelopmentConfig, ProductionConfig

# Development: relaxed security, extra logging
dev_config = DevelopmentConfig.from_env()

# Production: enforces HTTPS, strict validation
prod_config = ProductionConfig.from_env()
```

---

## ✨ Core Features

### Access Key Management

```python
from pyoutlineapi.models import DataLimit

# Create key with data limit
key = await client.create_access_key(
    name="Alice",
    limit=DataLimit.from_gigabytes(10)
)

# Create with custom settings
key = await client.create_access_key(
    name="Bob",
    port=8388,
    method="chacha20-ietf-poly1305",
    limit=DataLimit(bytes=5_000_000_000)
)

# Create with specific ID
key = await client.create_access_key_with_id(
    key_id="user-001",
    name="Charlie"
)

# List and filter
keys = await client.get_access_keys()
limited_keys = keys.filter_with_limits()  # Only keys with limits
key = keys.get_by_id("key-id")  # Find by ID

# Manage keys
await client.rename_access_key("key-id", "New Name")
await client.set_access_key_data_limit("key-id", 10_000_000_000)
await client.remove_access_key_data_limit("key-id")
await client.delete_access_key("key-id")
```

### Server Configuration

```python
# Get server info
server = await client.get_server_info()
print(f"Name: {server.name}")
print(f"Port: {server.port_for_new_access_keys}")
print(f"Metrics: {server.metrics_enabled}")
print(f"Global limit: {server.has_global_limit}")

# Configure server
await client.rename_server("Production VPN")
await client.set_hostname("vpn.example.com")
await client.set_default_port(443)

# Global data limits
await client.set_global_data_limit(100 * 1024 ** 3)  # 100 GB
await client.remove_global_data_limit()
```

### Metrics & Monitoring

```python
# Check metrics status
status = await client.get_metrics_status()
await client.set_metrics_status(True)

# Get transfer metrics
metrics = await client.get_transfer_metrics()
print(f"Total: {metrics.total_gigabytes:.2f} GB")
print(f"Active keys: {metrics.key_count}")

# Top consumers
for key_id, bytes_used in metrics.get_top_consumers(5):
    print(f"{key_id}: {bytes_used / 1024 ** 3:.2f} GB")

# Experimental metrics (24h window)
exp = await client.get_experimental_metrics("24h")
print(f"Tunnel time: {exp.server.tunnel_time.seconds}s")
print(f"Locations: {len(exp.server.locations)}")
```

---

## 📝 Audit Logging

**Production-ready audit logging with async queue processing and automatic sensitive data filtering.**

### Default Audit Logger

```python
from pyoutlineapi import AsyncOutlineClient

# Automatic audit logging (enabled by default)
async with AsyncOutlineClient.from_env() as client:
    key = await client.create_access_key(name="Alice")
    # 📝 [AUDIT] create_access_key on 1 | {'name': 'Alice', 'success': True}

    await client.rename_access_key(key.id, "Alice Smith")
    # 📝 [AUDIT] rename_access_key on 1 | {'new_name': 'Alice Smith', 'success': True}

    await client.delete_access_key(key.id)
    # 📝 [AUDIT] delete_access_key on 1 | {'success': True}
```

### Custom Audit Logger

```python
import json
from pathlib import Path


class JsonFileAuditLogger:
    """Log audit events to JSON Lines file."""

    def __init__(self, filepath: str = "audit.jsonl"):
        self.filepath = Path(filepath)

    def log_action(self, action: str, resource: str, **kwargs) -> None:
        """Synchronous logging."""
        with open(self.filepath, "a") as f:
            json.dump({"action": action, "resource": resource, **kwargs}, f)
            f.write("\n")

    async def alog_action(self, action: str, resource: str, **kwargs) -> None:
        """Async logging."""
        self.log_action(action, resource, **kwargs)

    async def shutdown(self) -> None:
        """Cleanup."""
        pass


# Use custom logger
audit_logger = JsonFileAuditLogger("production.jsonl")
async with AsyncOutlineClient.from_env(audit_logger=audit_logger) as client:
    await client.create_access_key(name="Bob")
```

### Global Audit Logger

```python
from pyoutlineapi import set_default_audit_logger, DefaultAuditLogger

# Configure once at application startup
global_logger = DefaultAuditLogger(
    enable_async=True,  # Non-blocking queue
    queue_size=5000  # Large queue for high throughput
)
set_default_audit_logger(global_logger)

# All clients use this logger
async with AsyncOutlineClient.from_env() as client1:
    await client1.create_access_key(name="User1")

async with AsyncOutlineClient.from_env() as client2:
    await client2.create_access_key(name="User2")
```

### Disable Audit Logging

```python
from pyoutlineapi import NoOpAuditLogger

# For testing environments
async with AsyncOutlineClient.from_env(
        audit_logger=NoOpAuditLogger()
) as client:
    await client.create_access_key(name="Test")  # No audit logs
```

### Audited Operations

**Access Keys:** `create`, `delete`, `rename`, `set_data_limit`, `remove_data_limit`  
**Server:** `rename_server`, `set_hostname`, `set_default_port`  
**Data Limits:** `set_global_data_limit`, `remove_global_data_limit`  
**Metrics:** `set_metrics_status`

### Security Features

```python
# Sensitive data automatically filtered
key = await client.create_access_key(
    name="Alice",
    password="secret123"  # Masked in logs as '***REDACTED***'
)

# Failed operations also logged
try:
    await client.delete_access_key("non-existent")
except Exception:
    pass
# 📝 [AUDIT] delete_access_key on non-existent | {'success': False, 'error': '...'}
```

---

## 🛡️ Enterprise Features

### Circuit Breaker

Automatic protection against cascading failures:

```python
from pyoutlineapi import OutlineClientConfig, CircuitOpenError
from pydantic import SecretStr

config = OutlineClientConfig(
    api_url="https://server.com:12345/secret",
    cert_sha256=SecretStr("abc123..."),
    enable_circuit_breaker=True,
    circuit_failure_threshold=5,  # Open after 5 failures
    circuit_recovery_timeout=60.0,  # Test recovery after 60s
)

async with AsyncOutlineClient(config) as client:
    try:
        await client.get_server_info()
    except CircuitOpenError as e:
        print(f"Circuit open - retry after {e.retry_after}s")

    # Monitor circuit health
    metrics = client.get_circuit_metrics()
    if metrics:
        print(f"State: {metrics['state']}")
        print(f"Success rate: {metrics['success_rate']:.2%}")
```

**Circuit States:**

- **CLOSED** - Normal operation
- **OPEN** - Service failing, requests blocked
- **HALF_OPEN** - Testing recovery

### Health Monitoring

```python
from pyoutlineapi.health_monitoring import HealthMonitor

async with AsyncOutlineClient.from_env() as client:
    monitor = HealthMonitor(client, cache_ttl=30.0)

    # Quick check
    is_healthy = await monitor.quick_check()

    # Comprehensive check
    health = await monitor.comprehensive_check()
    print(f"Healthy: {health.healthy}")
    print(f"Checks: {list(health.checks.keys())}")

    if not health.healthy:
        for check in health.failed_checks:
            print(f"Failed: {check}")

    # Wait for service recovery
    if await monitor.wait_for_healthy(timeout=120):
        print("Service recovered!")
```

### Batch Operations

```python
from pyoutlineapi.batch_operations import BatchOperations
from pyoutlineapi.models import DataLimit

async with AsyncOutlineClient.from_env() as client:
    batch = BatchOperations(client, max_concurrent=10)

    # Create multiple keys
    configs = [
        {"name": f"User{i}", "limit": DataLimit.from_gigabytes(5)}
        for i in range(1, 101)
    ]

    result = await batch.create_multiple_keys(configs)
    print(f"Created: {result.successful}/{result.total}")
    print(f"Success rate: {result.success_rate:.2%}")

    if result.has_errors:
        print(f"Failed: {result.failed}")

    # Get successful keys
    keys = result.get_successful_results()

    # Batch delete
    key_ids = [key.id for key in keys]
    result = await batch.delete_multiple_keys(key_ids)
```

### Metrics Collection

```python
from pyoutlineapi.metrics_collector import MetricsCollector

async with AsyncOutlineClient.from_env() as client:
    collector = MetricsCollector(
        client,
        interval=60,  # Collect every 60s
        max_history=1440  # Keep 24 hours
    )

    await collector.start()
    await asyncio.sleep(3600)  # Run for 1 hour

    # Get usage stats
    stats = collector.get_usage_stats(period_minutes=60)
    print(f"Total: {stats.total_bytes_transferred / 1024 ** 3:.2f} GB")
    print(f"Rate: {stats.bytes_per_second / 1024:.2f} KB/s")
    print(f"Active keys: {len(stats.active_keys)}")

    # Export Prometheus format
    print(collector.export_prometheus_format())

    await collector.stop()
```

---

## 🚨 Error Handling

### Exception Hierarchy

```python
from pyoutlineapi.exceptions import (
    OutlineError,  # Base exception
    APIError,  # API failures
    CircuitOpenError,  # Circuit breaker open
    ConfigurationError,  # Invalid config
    ValidationError,  # Data validation
    ConnectionError,  # Connection failures
    TimeoutError,  # Request timeouts
)
```

### Handling Patterns

```python
from pyoutlineapi.exceptions import CircuitOpenError, APIError

async with AsyncOutlineClient.from_env() as client:
    try:
        server = await client.get_server_info()

    except CircuitOpenError as e:
        print(f"Circuit open - retry after {e.retry_after}s")
        await asyncio.sleep(e.retry_after)

    except APIError as e:
        if e.status_code == 404:
            print("Resource not found")
        elif e.is_server_error:  # 5xx
            print(f"Server error: {e}")

        if e.is_retryable:
            print("Will retry automatically")

    except ConnectionError as e:
        print(f"Connection failed: {e.host}")

    except TimeoutError as e:
        print(f"Timeout after {e.timeout}s")
```

### Retry with Backoff

```python
from pyoutlineapi.exceptions import APIError, get_retry_delay
import asyncio


async def robust_operation():
    for attempt in range(3):
        try:
            async with AsyncOutlineClient.from_env() as client:
                return await client.get_server_info()

        except APIError as e:
            if not e.is_retryable or attempt == 2:
                raise

            delay = get_retry_delay(e) or 1.0
            await asyncio.sleep(delay * (2 ** attempt))
```

---

## 📚 Advanced Usage

### Rate Limiting

```python
config = OutlineClientConfig(
    api_url="...",
    cert_sha256=SecretStr("..."),
    rate_limit=50,  # Max 50 concurrent requests
    max_connections=20,  # Connection pool size
)

async with AsyncOutlineClient(config) as client:
    # Check stats
    stats = client.get_rate_limiter_stats()
    print(f"Active: {stats['active']}/{stats['limit']}")

    # Adjust dynamically
    await client.set_rate_limit(100)
```

### Utility Methods

```python
async with AsyncOutlineClient.from_env() as client:
    # Health check
    health = await client.health_check()
    print(f"Healthy: {health['healthy']}")
    print(f"Circuit: {health['circuit_state']}")

    # Server summary
    summary = await client.get_server_summary()
    print(f"Keys: {summary['access_keys_count']}")
    print(f"Data: {summary.get('transfer_metrics', {})}")

    # Safe config for logging
    safe = client.get_sanitized_config()
    logger.info(f"Config: {safe}")  # No secrets exposed
```

### JSON Format

```python
# Return raw JSON instead of Pydantic models
async with AsyncOutlineClient.from_env() as client:
    # Per-request
    server_json = await client.get_server_info(as_json=True)
    print(server_json["name"])

    # Global setting
    config = OutlineClientConfig.from_env(json_format=True)
    async with AsyncOutlineClient(config) as client:
        keys_json = await client.get_access_keys()
        print(keys_json["accessKeys"])
```

---

## 🎯 Best Practices

### 1. Use Environment Variables

```python
# ✅ Secure
async with AsyncOutlineClient.from_env() as client:
    pass

# ❌ Insecure - credentials in code
client = AsyncOutlineClient.create(
    api_url="https://...",  # Secret visible!
    cert_sha256="..."
)
```

### 2. Always Use Context Managers

```python
# ✅ Automatic cleanup
async with AsyncOutlineClient.from_env() as client:
    await client.get_server_info()

# ❌ Manual cleanup required
client = AsyncOutlineClient.from_env()
await client.__aenter__()
try:
    await client.get_server_info()
finally:
    await client.shutdown()
```

### 3. Handle Specific Exceptions

```python
# ✅ Specific handling
try:
    key = await client.get_access_key("key-id")
except APIError as e:
    if e.status_code == 404:
        print("Key not found")

# ❌ Catch-all
try:
    key = await client.get_access_key("key-id")
except Exception:
    pass  # Silent failure
```

### 4. Enable Audit Logging in Production

```python
# ✅ Production
audit_logger = DefaultAuditLogger(enable_async=True, queue_size=5000)
client = AsyncOutlineClient.from_env(audit_logger=audit_logger)

# ❌ No audit trail
client = AsyncOutlineClient.from_env(audit_logger=NoOpAuditLogger())
```

### 5. Configure Circuit Breaker

```python
# ✅ Production
config = OutlineClientConfig.from_env(
    enable_circuit_breaker=True,
    circuit_failure_threshold=5,
    circuit_recovery_timeout=60.0,
)

# ❌ No protection against cascading failures
config = OutlineClientConfig.from_env(enable_circuit_breaker=False)
```

---

## 🐳 Docker Example

**Dockerfile:**

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

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import asyncio; from app import health; asyncio.run(health())"

CMD ["python", "app.py"]
```

**docker-compose.yml:**

```yaml
version: '3.8'

services:
  outline-manager:
    build: .
    env_file: .env
    environment:
      - OUTLINE_ENABLE_LOGGING=true
      - OUTLINE_ENABLE_CIRCUIT_BREAKER=true
    restart: unless-stopped
    healthcheck:
      test: [ "CMD", "python", "-c", "import asyncio; from app import health; asyncio.run(health())" ]
      interval: 30s
      timeout: 10s
      retries: 3
```

---

## 📖 Complete Example

```python
"""
Production-ready Outline VPN management application.
"""
import asyncio
import logging
from pyoutlineapi import AsyncOutlineClient
from pyoutlineapi.health_monitoring import HealthMonitor
from pyoutlineapi.batch_operations import BatchOperations
from pyoutlineapi.exceptions import OutlineError, CircuitOpenError

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    try:
        async with AsyncOutlineClient.from_env() as client:
            # Health check
            monitor = HealthMonitor(client)
            health = await monitor.comprehensive_check()

            if not health.healthy:
                logger.error(f"Service unhealthy: {health.failed_checks}")
                return 1

            # Get server info
            server = await client.get_server_info()
            logger.info(f"Connected to: {server.name}")

            # Create keys in batch
            batch = BatchOperations(client, max_concurrent=5)
            configs = [{"name": f"User{i}"} for i in range(1, 11)]

            result = await batch.create_multiple_keys(configs)
            logger.info(f"Created: {result.successful}/{result.total}")

            # List keys
            keys = await client.get_access_keys()
            logger.info(f"Total keys: {keys.count}")

            # Metrics
            if server.metrics_enabled:
                metrics = await client.get_transfer_metrics()
                logger.info(f"Total: {metrics.total_gigabytes:.2f} GB")

            return 0

    except CircuitOpenError as e:
        logger.error(f"Circuit open: retry after {e.retry_after}s")
        return 1

    except OutlineError as e:
        logger.error(f"Error: {e}")
        return 1


if __name__ == "__main__":
    exit(asyncio.run(main()))
```

---

## 🧪 Testing

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# With coverage
pytest --cov=pyoutlineapi --cov-report=html

# Type checking
mypy pyoutlineapi

# Linting
ruff check .

# Formatting
ruff format .
```

---

## 🤝 Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## 📄 License

MIT License - see [LICENSE](LICENSE) file.

Copyright (c) 2025 Denis Rozhnovskiy

---

## 🔗 Links

- **Documentation**: [GitHub Wiki](https://github.com/orenlab/pyoutlineapi/wiki)
- **Issues**: [GitHub Issues](https://github.com/orenlab/pyoutlineapi/issues)
- **Discussions**: [GitHub Discussions](https://github.com/orenlab/pyoutlineapi/discussions)
- **PyPI**: [pypi.org/project/pyoutlineapi](https://pypi.org/project/pyoutlineapi/)
- **Outline VPN**: [getoutline.org](https://getoutline.org/)

---

## 💬 Support

- 📧 Email: `pytelemonbot@mail.ru`
- 🐛 Bug Reports: [GitHub Issues](https://github.com/orenlab/pyoutlineapi/issues)
- 💡 Feature Requests: [GitHub Discussions](https://github.com/orenlab/pyoutlineapi/discussions)

---

**Made with ❤️ by [Denis Rozhnovskiy](https://github.com/orenlab)**

*PyOutlineAPI - Production-ready Python client for Outline VPN Server*

[⬆ Back to top](#pyoutlineapi)