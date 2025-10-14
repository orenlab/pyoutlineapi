# PyOutlineAPI

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MIT License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Type Checked](https://img.shields.io/badge/type--checked-mypy-blue.svg)](http://mypy-lang.org/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

> **Production-ready async Python client for Outline VPN Server API**

Modern, type-safe, and secure Python library for managing [Outline VPN](https://getoutline.org/) servers. Built with
async/await, comprehensive error handling, and battle-tested reliability.

## ✨ Why PyOutlineAPI?

- 🚀 **Blazing Fast** - Lazy loading, minimal overhead, async-first design
- 🔒 **Security First** - SecretStr for credentials, input sanitization, path traversal protection
- 📝 **100% Type Safe** - Complete type hints, mypy strict mode compatible
- 🛡️ **Production Ready** - Circuit breaker, retry logic, rate limiting, health monitoring
- 🎯 **Complete API Coverage** - All Outline API v1.0 endpoints fully implemented
- 🧩 **Zero Dependencies Bloat** - Optional addons, import only what you need
- 📚 **Excellent Documentation** - Comprehensive examples, docstrings, and type hints

## 🎯 Key Features

### Security & Reliability

- ✅ **SecretStr Protection** - Sensitive data never exposed in logs or errors
- ✅ **Input Validation** - Pydantic v2 models with strict validation
- ✅ **Path Traversal Protection** - Prevents injection attacks
- ✅ **Circuit Breaker Pattern** - Prevents cascading failures
- ✅ **Automatic Retries** - Configurable retry logic for transient failures
- ✅ **Rate Limiting** - Protects against API overload

### Developer Experience

- ✅ **Async/Await Native** - Built for modern Python async code
- ✅ **Type Hints Everywhere** - Full IDE autocomplete support
- ✅ **Context Managers** - Automatic resource cleanup
- ✅ **Rich Error Messages** - Detailed exceptions with context
- ✅ **Environment Config** - Load settings from .env files
- ✅ **Debug Logging** - Optional detailed logging with sanitization

### Performance

- ✅ **Lazy Loading** - Features loaded only when needed
- ✅ **Connection Pooling** - Efficient HTTP connection reuse
- ✅ **Concurrent Requests** - Configurable rate limiting
- ✅ **Minimal Memory** - Small footprint, efficient design


## 📦 Installation

```bash
pip install pyoutlineapi
```

**Requirements:**

- Python 3.10 or higher
- aiohttp
- pydantic >= 2.0
- pydantic-settings

## 🚀 Quick Start

### Basic Usage

```python
from pyoutlineapi import AsyncOutlineClient

async with AsyncOutlineClient.create(
        api_url="https://your-server.com:12345/secret-path",
        cert_sha256="your-certificate-fingerprint",
) as client:
    # Get server information
    server = await client.get_server_info()
    print(f"Server: {server.name}")

    # Create access key
    key = await client.create_access_key(name="Alice")
    print(f"Access URL: {key.access_url}")

    # List all keys
    keys = await client.get_access_keys()
    print(f"Total keys: {keys.count}")
```

### Environment-Based Configuration

**Step 1:** Generate configuration template

```python
from pyoutlineapi import quick_setup

quick_setup()  # Creates .env.example
```

**Step 2:** Edit `.env` file

```bash
OUTLINE_API_URL=https://your-server.com:12345/secret-path
OUTLINE_CERT_SHA256=your-certificate-fingerprint

# Optional settings
OUTLINE_TIMEOUT=30
OUTLINE_RETRY_ATTEMPTS=3
OUTLINE_RATE_LIMIT=100
OUTLINE_ENABLE_CIRCUIT_BREAKER=true
OUTLINE_ENABLE_LOGGING=false
```

**Step 3:** Use in your application

```python
from pyoutlineapi import AsyncOutlineClient

# Automatically loads from .env
async with AsyncOutlineClient.from_env() as client:
    server = await client.get_server_info()
    print(f"Connected to: {server.name}")
```

## 📚 Core API

### Server Management

```python
# Get comprehensive server information
server = await client.get_server_info()
print(f"Name: {server.name}")
print(f"ID: {server.server_id}")
print(f"Port: {server.port_for_new_access_keys}")
print(f"Created: {server.created_timestamp_ms}")

# Rename server
await client.rename_server("Production VPN")

# Configure hostname for access keys
await client.set_hostname("vpn.example.com")

# Set default port for new keys
await client.set_default_port(443)
```

### Access Key Management

#### Creating Keys

```python
from pyoutlineapi.models import DataLimit

# Simple key creation
key = await client.create_access_key(name="Alice")

# Key with data limit
key = await client.create_access_key(
    name="Bob",
    limit=DataLimit(bytes=10 * 1024 ** 3)  # 10 GB
)

# Key with custom settings
key = await client.create_access_key(
    name="Charlie",
    port=8388,
    method="chacha20-ietf-poly1305",
    limit=DataLimit(bytes=5 * 1024 ** 3)
)

# Key with specific ID
key = await client.create_access_key_with_id(
    key_id="user-001",
    name="Alice"
)
```

#### Managing Keys

```python
# Get all access keys
keys = await client.get_access_keys()
print(f"Total keys: {keys.count}")

for key in keys.access_keys:
    print(f"{key.name}: {key.access_url}")

# Get specific key
key = await client.get_access_key("key-id")

# Rename key
await client.rename_access_key("key-id", "Alice Smith")

# Delete key
success = await client.delete_access_key("key-id")
```

### Data Limits

#### Per-Key Limits

```python
from pyoutlineapi.models import DataLimit

# Set data limit for specific key
await client.set_access_key_data_limit(
    key_id="key-id",
    bytes_limit=5 * 1024 ** 3  # 5 GB
)

# Remove limit from key
await client.remove_access_key_data_limit("key-id")
```

#### Global Limits

```python
# Set global limit for all keys
await client.set_global_data_limit(100 * 1024 ** 3)  # 100 GB

# Remove global limit
await client.remove_global_data_limit()
```

### Metrics & Monitoring

```python
# Check metrics status
status = await client.get_metrics_status()
print(f"Metrics enabled: {status.metrics_enabled}")

# Enable/disable metrics
await client.set_metrics_status(True)

# Get transfer metrics
metrics = await client.get_transfer_metrics()
print(f"Total transferred: {metrics.total_bytes / 1024 ** 3:.2f} GB")

for key_id, bytes_used in metrics.bytes_transferred_by_user_id.items():
    mb = bytes_used / 1024 ** 2
    print(f"Key {key_id}: {mb:.2f} MB")

# Get experimental metrics
exp_metrics = await client.get_experimental_metrics("24h")
print(f"Server data: {exp_metrics.server.data_transferred.bytes}")
print(f"Locations: {len(exp_metrics.server.locations)}")
```

## 🛡️ Advanced Features

### Circuit Breaker Pattern

Prevent cascading failures with automatic circuit breaker protection:

```python
from pyoutlineapi import OutlineClientConfig
from pyoutlineapi.circuit_breaker import CircuitConfig

config = OutlineClientConfig(
    api_url="https://server.com:12345/secret",
    cert_sha256="abc123...",
    enable_circuit_breaker=True,
    circuit_failure_threshold=5,  # Open after 5 failures
    circuit_recovery_timeout=60.0,  # Test recovery after 60s
)

async with AsyncOutlineClient(config) as client:
    try:
        await client.get_server_info()
    except CircuitOpenError as e:
        print(f"Circuit open, retry after {e.retry_after}s")

    # Check circuit state
    if client.circuit_state == "OPEN":
        print("Service experiencing issues")

    # Get circuit metrics
    metrics = client.get_circuit_metrics()
    if metrics:
        print(f"Success rate: {metrics['success_rate']:.2%}")
```

### Rate Limiting

Control concurrent requests to protect your server:

```python
# Configure rate limit (default: 100 concurrent requests)
config = OutlineClientConfig(
    api_url="...",
    cert_sha256="...",
    rate_limit=50,  # Max 50 concurrent requests
)

async with AsyncOutlineClient(config) as client:
    # Check current rate limiter status
    stats = client.get_rate_limiter_stats()
    print(f"Active: {stats['active']}/{stats['limit']}")
    print(f"Available: {stats['available']}")

    # Dynamically adjust rate limit
    await client.set_rate_limit(100)  # Increase to 100
```

### Health Monitoring

Comprehensive health checks for production systems:

```python
from pyoutlineapi.health_monitoring import HealthMonitor

async with AsyncOutlineClient.from_env() as client:
    monitor = HealthMonitor(client)

    # Quick connectivity check
    if await monitor.quick_check():
        print("✅ Service reachable")

    # Comprehensive health check
    health = await monitor.comprehensive_check()

    if not health.healthy:
        print("❌ Service unhealthy")
        for check_name in health.failed_checks:
            result = health.checks[check_name]
            print(f"  {check_name}: {result['message']}")

    if health.is_degraded:
        print("⚠️  Service degraded but operational")

    # Wait for service to become healthy
    if await monitor.wait_for_healthy(timeout=120):
        print("Service recovered!")


    # Custom health checks
    async def check_key_count(client):
        keys = await client.get_access_keys()
        return {
            "status": "healthy" if keys.count > 0 else "warning",
            "count": keys.count,
            "message": f"{keys.count} keys configured"
        }


    monitor.add_custom_check("key_count", check_key_count)
    health = await monitor.comprehensive_check()
```

### Batch Operations

Efficient bulk operations with concurrency control:

```python
from pyoutlineapi.batch_operations import BatchOperations
from pyoutlineapi.models import DataLimit

async with AsyncOutlineClient.from_env() as client:
    batch = BatchOperations(client, max_concurrent=10)

    # Create multiple keys
    configs = [
        {"name": "User1", "limit": DataLimit(bytes=1024 ** 3)},
        {"name": "User2", "limit": DataLimit(bytes=2 * 1024 ** 3)},
        {"name": "User3", "port": 8388},
    ]

    result = await batch.create_multiple_keys(configs)
    print(f"Created: {result.successful}/{result.total}")
    print(f"Success rate: {result.success_rate:.2%}")

    if result.has_errors:
        for error in result.get_failures():
            print(f"Error: {error}")

    # Delete multiple keys
    key_ids = ["key1", "key2", "key3"]
    result = await batch.delete_multiple_keys(key_ids)

    # Rename multiple keys
    pairs = [
        ("key1", "Alice"),
        ("key2", "Bob"),
        ("key3", "Charlie"),
    ]
    result = await batch.rename_multiple_keys(pairs)

    # Set multiple data limits
    limits = [
        ("key1", 5 * 1024 ** 3),  # 5 GB
        ("key2", 10 * 1024 ** 3),  # 10 GB
    ]
    result = await batch.set_multiple_data_limits(limits)
```

### Metrics Collection

Automated metrics collection with historical data:

```python
from pyoutlineapi.metrics_collector import MetricsCollector

async with AsyncOutlineClient.from_env() as client:
    # Create collector with 1-minute interval
    collector = MetricsCollector(
        client,
        interval=60,  # Collect every 60 seconds
        max_history=1440,  # Keep 24 hours (1440 minutes)
    )

    # Start collection
    await collector.start()

    # Let it run...
    await asyncio.sleep(3600)  # 1 hour

    # Stop collection
    await collector.stop()

    # Get usage statistics
    stats = collector.get_usage_stats(period_minutes=60)
    print(f"Total bytes: {stats.total_bytes_transferred}")
    print(f"Avg rate: {stats.bytes_per_second / 1024:.2f} KB/s")
    print(f"Active keys: {len(stats.active_keys)}")

    # Per-key usage
    usage = collector.get_key_usage("key-id", period_minutes=60)
    print(f"Key usage: {usage['total_bytes'] / 1024 ** 2:.2f} MB")

    # Export data
    data = collector.export_to_dict()

    # Prometheus format
    prom_metrics = collector.export_prometheus_format()
```

## ⚙️ Configuration

### Environment Variables

All configuration options with `OUTLINE_` prefix:

```bash
# Required
OUTLINE_API_URL=https://server.com:12345/secret
OUTLINE_CERT_SHA256=your-certificate-fingerprint

# Client Settings
OUTLINE_TIMEOUT=30                    # Request timeout (seconds)
OUTLINE_RETRY_ATTEMPTS=3              # Number of retries
OUTLINE_MAX_CONNECTIONS=10            # Connection pool size
OUTLINE_RATE_LIMIT=100                # Max concurrent requests

# Features
OUTLINE_ENABLE_CIRCUIT_BREAKER=true   # Enable circuit breaker
OUTLINE_ENABLE_LOGGING=false          # Enable debug logging
OUTLINE_JSON_FORMAT=false             # Return JSON instead of models

# Circuit Breaker
OUTLINE_CIRCUIT_FAILURE_THRESHOLD=5   # Failures before opening
OUTLINE_CIRCUIT_RECOVERY_TIMEOUT=60.0 # Recovery timeout (seconds)
```

### Configuration Objects

```python
from pyoutlineapi import OutlineClientConfig
from pydantic import SecretStr

# Minimal configuration
config = OutlineClientConfig.create_minimal(
    api_url="https://server.com:12345/secret",
    cert_sha256="abc123...",
)

# Full configuration
config = OutlineClientConfig(
    api_url="https://server.com:12345/secret",
    cert_sha256=SecretStr("abc123..."),
    timeout=60,
    retry_attempts=5,
    max_connections=20,
    rate_limit=200,
    enable_circuit_breaker=True,
    enable_logging=True,
)

# From environment
config = OutlineClientConfig.from_env()

# From custom .env file
config = OutlineClientConfig.from_env(".env.production")
```

### Environment-Specific Configs

```python
from pyoutlineapi import DevelopmentConfig, ProductionConfig

# Development: logging enabled, circuit breaker disabled
dev_config = DevelopmentConfig.from_env()

# Production: strict security, circuit breaker enabled
prod_config = ProductionConfig.from_env()  # Enforces HTTPS

async with AsyncOutlineClient(prod_config) as client:
    await client.get_server_info()
```

### Safe Configuration Display

```python
# Get sanitized config (safe for logging)
safe_config = client.get_sanitized_config()
print(safe_config)
# Output:
# {
#     'api_url': 'https://server.com:12345/***',
#     'cert_sha256': '***MASKED***',
#     'timeout': 30,
#     ...
# }

# Never do this (exposes secrets):
print(client.config)  # ❌ Unsafe!

# Always use sanitized version:
print(client.get_sanitized_config())  # ✅ Safe
```

## 🚨 Error Handling

### Exception Hierarchy

```python
from pyoutlineapi.exceptions import (
    OutlineError,  # Base exception
    APIError,  # API request failures
    CircuitOpenError,  # Circuit breaker open
    ConfigurationError,  # Invalid configuration
    ValidationError,  # Data validation errors
    ConnectionError,  # Connection failures
    TimeoutError,  # Request timeouts
)

try:
    async with AsyncOutlineClient.from_env() as client:
        await client.get_server_info()

except APIError as e:
    print(f"API error: {e}")
    print(f"Status: {e.status_code}")
    print(f"Endpoint: {e.endpoint}")

    if e.is_client_error:
        print("Client error (4xx) - fix your request")
    elif e.is_server_error:
        print("Server error (5xx) - can retry")

    if e.is_retryable:
        print("This error is retryable")

except CircuitOpenError as e:
    print(f"Circuit open, retry after {e.retry_after}s")

except ConfigurationError as e:
    print(f"Configuration error in '{e.field}': {e}")
    if e.security_issue:
        print("⚠️  Security issue detected")

except ConnectionError as e:
    print(f"Connection failed: {e.host}:{e.port}")

except TimeoutError as e:
    print(f"Request timed out after {e.timeout}s")

except OutlineError as e:
    print(f"Generic error: {e}")
    print(f"Details: {e.details}")
```

### Retry Logic

```python
from pyoutlineapi.exceptions import get_retry_delay

try:
    await client.get_server_info()
except Exception as e:
    delay = get_retry_delay(e)
    if delay:
        print(f"Retrying in {delay}s")
        await asyncio.sleep(delay)
        # Retry operation
    else:
        print("Error is not retryable")
        raise
```

## 🎯 Best Practices

### 1. Always Use Context Managers

```python
# ✅ Good - automatic cleanup
async with AsyncOutlineClient.from_env() as client:
    await client.get_server_info()

# ❌ Bad - manual cleanup required
client = AsyncOutlineClient.from_env()
await client.__aenter__()
try:
    await client.get_server_info()
finally:
    await client.__aexit__(None, None, None)
```

### 2. Environment-Based Configuration

```python
# ✅ Good - secure, flexible
async with AsyncOutlineClient.from_env() as client:
    pass

# ❌ Bad - hardcoded credentials
async with AsyncOutlineClient.create(
        api_url="https://server.com:12345/secret123",  # Secret in code!
        cert_sha256="abc123...",
) as client:
    pass
```

### 3. Error Handling

```python
# ✅ Good - specific error handling
try:
    key = await client.get_access_key(key_id)
except APIError as e:
    if e.status_code == 404:
        print("Key not found")
    elif e.is_retryable:
        # Retry logic
        pass
    else:
        raise

# ❌ Bad - catching all exceptions
try:
    key = await client.get_access_key(key_id)
except Exception:
    pass  # Silently fails
```

### 4. Resource Limits

```python
# ✅ Good - configure limits
config = OutlineClientConfig.from_env()
config.rate_limit = 50  # Reasonable limit
config.max_connections = 10  # Control pool size

# ❌ Bad - no limits
config.rate_limit = 1000  # Too high
config.max_connections = 100  # Excessive
```

### 5. Logging

```python
# ✅ Good - use sanitized logging
import logging

logger = logging.getLogger(__name__)

safe_config = client.get_sanitized_config()
logger.info(f"Connected: {safe_config}")

# ❌ Bad - exposes secrets
logger.info(f"Config: {client.config}")  # Leaks secrets!
```

## 🔧 Performance Tips

### 1. Lazy Loading

```python
# Core client - fast import
from pyoutlineapi import AsyncOutlineClient

# Addons - import only when needed
from pyoutlineapi.health_monitoring import HealthMonitor  # +~5ms
from pyoutlineapi.batch_operations import BatchOperations  # +~3ms
from pyoutlineapi.metrics_collector import MetricsCollector  # +~4ms
```

### 2. Connection Pooling

```python
# Reuse client instance
async with AsyncOutlineClient.from_env() as client:
    # Connection pool reused for all requests
    await client.get_server_info()
    await client.get_access_keys()
    await client.get_transfer_metrics()
```

### 3. Batch Operations

```python
# ✅ Good - batch operations
batch = BatchOperations(client, max_concurrent=10)
result = await batch.create_multiple_keys(configs)

# ❌ Bad - sequential operations
for config in configs:
    await client.create_access_key(**config)  # Slow!
```

### 4. Rate Limiting

```python
# Configure based on your needs
config = OutlineClientConfig(
    api_url="...",
    cert_sha256="...",
    rate_limit=100,  # 100 concurrent requests
    max_connections=20,  # 20 connection pool size
)
```

## 🐳 Docker Example

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Environment variables
ENV OUTLINE_API_URL=""
ENV OUTLINE_CERT_SHA256=""
ENV OUTLINE_ENABLE_LOGGING="true"

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import asyncio; from app import health_check; asyncio.run(health_check())"

CMD ["python", "app.py"]
```

## 📖 Complete Example

```python
"""
Complete Outline VPN management application.

Features:
- Health monitoring
- Batch operations
- Metrics collection
- Error handling
- Graceful shutdown
"""
import asyncio
import logging
from pyoutlineapi import AsyncOutlineClient
from pyoutlineapi.health_monitoring import HealthMonitor
from pyoutlineapi.batch_operations import BatchOperations
from pyoutlineapi.metrics_collector import MetricsCollector
from pyoutlineapi.exceptions import OutlineError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    """Main application entry point."""
    try:
        async with AsyncOutlineClient.from_env() as client:
            # Health check
            monitor = HealthMonitor(client)
            health = await monitor.comprehensive_check()

            if not health.healthy:
                logger.error("❌ Service unhealthy!")
                for check in health.failed_checks:
                    logger.error(f"  {check}: {health.checks[check]}")
                return 1

            logger.info("✅ Service healthy")

            # Get server info
            server = await client.get_server_info()
            logger.info(f"📡 Connected to: {server.name}")
            logger.info(f"   ID: {server.server_id}")
            logger.info(f"   Port: {server.port_for_new_access_keys}")

            # Create access keys in batch
            batch = BatchOperations(client, max_concurrent=5)
            configs = [
                {"name": f"User{i}"}
                for i in range(1, 11)
            ]

            logger.info("🔑 Creating access keys...")
            result = await batch.create_multiple_keys(configs)
            logger.info(f"   Created: {result.successful}/{result.total}")

            if result.has_errors:
                logger.warning(f"   Errors: {result.failed}")
                for error in result.get_failures()[:3]:
                    logger.error(f"      {error}")

            # List all keys
            keys = await client.get_access_keys()
            logger.info(f"📋 Total keys: {keys.count}")

            for key in keys.access_keys[:5]:
                logger.info(f"   • {key.name or key.id}")

            # Get metrics
            if server.metrics_enabled:
                metrics = await client.get_transfer_metrics()
                total_gb = metrics.total_bytes / 1024 ** 3
                logger.info(f"📊 Total transferred: {total_gb:.2f} GB")

            return 0

    except OutlineError as e:
        logger.error(f"❌ Outline error: {e}")
        return 1
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
```

## 🧪 Testing

### Install Development Dependencies

```bash
# Clone repository
git clone https://github.com/orenlab/pyoutlineapi.git
cd pyoutlineapi

# Install with dev dependencies
pip install -e ".[dev]"
```

### Run Tests

```bash
# Run all tests
pytest

# With coverage
pytest --cov=pyoutlineapi --cov-report=html

# Type checking
mypy pyoutlineapi

# Linting
ruff check pyoutlineapi

# Format code
ruff format .
```

### Mock Client for Testing

```python
from unittest.mock import AsyncMock, Mock
from pyoutlineapi import AsyncOutlineClient
from pyoutlineapi.models import Server

# Create mock client
mock_client = AsyncMock(spec=AsyncOutlineClient)

# Mock server response
mock_client.get_server_info.return_value = Server(
    name="Test Server",
    server_id="test-123",
    metrics_enabled=True,
    created_timestamp_ms=1234567890,
    port_for_new_access_keys=8388,
)


# Use in tests
async def test_get_server():
    server = await mock_client.get_server_info()
    assert server.name == "Test Server"
```

## 🤝 Contributing

Contributions are welcome! Here's how to contribute: [CONTRIBUTING.md](CONTRIBUTING.md)

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details.

Copyright (c) 2025 Denis Rozhnovskiy

## 🔗 Links

- **Documentation**: [GitHub Wiki](https://github.com/orenlab/pyoutlineapi/wiki)
- **Issue Tracker**: [GitHub Issues](https://github.com/orenlab/pyoutlineapi/issues)
- **Discussions**: [GitHub Discussions](https://github.com/orenlab/pyoutlineapi/discussions)
- **Changelog**: [CHANGELOG.md](CHANGELOG.md)
- **Outline VPN**: [getoutline.org](https://getoutline.org/)
- **API Schema**: [outline-server/api.yml](https://github.com/Jigsaw-Code/outline-server/blob/master/src/shadowbox/server/api.yml)

## 💬 Support

Need help? Here's how to get support:

- 📧 **Email**: pytelemonbot@mail.ru
- 🐛 **Bug Reports**: [GitHub Issues](https://github.com/orenlab/pyoutlineapi/issues)
- 💡 **Feature Requests**: [GitHub Discussions](https://github.com/orenlab/pyoutlineapi/discussions)
- 📖 **Documentation**: [GitHub Wiki](https://github.com/orenlab/pyoutlineapi/wiki)

## ⭐ Show Your Support

If you find PyOutlineAPI useful, please consider:

- ⭐ **Starring** the repository
- 🐦 **Sharing** on social media
- 📝 **Writing** a blog post about your experience
- 🤝 **Contributing** code or documentation

## 🙏 Acknowledgments

- [Outline VPN](https://getoutline.org/) - The excellent VPN service
- [Jigsaw](https://jigsaw.google.com/) - Creators of Outline
- All [contributors](https://github.com/orenlab/pyoutlineapi/graphs/contributors) who helped improve this library

## 📈 Stats

![GitHub stars](https://img.shields.io/github/stars/orenlab/pyoutlineapi?style=social)
![GitHub forks](https://img.shields.io/github/forks/orenlab/pyoutlineapi?style=social)
![GitHub issues](https://img.shields.io/github/issues/orenlab/pyoutlineapi)
![GitHub pull requests](https://img.shields.io/github/issues-pr/orenlab/pyoutlineapi)

---

**Made with ❤️ by [Denis Rozhnovskiy](https://github.com/orenlab)**

*PyOutlineAPI - Production-ready Python client for Outline VPN Server*