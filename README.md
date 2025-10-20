# PyOutlineAPI

**Enterprise-grade async Python client for Outline VPN Server Management API**

[![tests](https://github.com/orenlab/pyoutlineapi/actions/workflows/python_tests.yml/badge.svg)](https://github.com/orenlab/pyoutlineapi/actions/workflows/python_tests.yml)
[![codecov](https://codecov.io/gh/orenlab/pyoutlineapi/branch/main/graph/badge.svg?token=D0MPKCKFJQ)](https://codecov.io/gh/orenlab/pyoutlineapi)
[![Security Rating](https://sonarcloud.io/api/project_badges/measure?project=orenlab_pyoutlineapi&metric=security_rating)](https://sonarcloud.io/summary/new_code?id=orenlab_pyoutlineapi)
[![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=orenlab_pyoutlineapi&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=orenlab_pyoutlineapi)
[![Vulnerabilities](https://sonarcloud.io/api/project_badges/measure?project=orenlab_pyoutlineapi&metric=vulnerabilities)](https://sonarcloud.io/summary/new_code?id=orenlab_pyoutlineapi)

![PyPI - Downloads](https://img.shields.io/pypi/dm/pyoutlineapi)
![PyPI - Version](https://img.shields.io/pypi/v/pyoutlineapi)
![Python Version](https://img.shields.io/pypi/pyversions/pyoutlineapi)
![License](https://img.shields.io/pypi/l/pyoutlineapi)

---

## 🎯 Overview

PyOutlineAPI is a modern, **production-ready** Python library for managing [Outline VPN](https://getoutline.org/)
servers. Built with async/await, type safety, and enterprise reliability patterns.

### Why PyOutlineAPI?

- **🚀 Async-First Architecture** - Built on aiohttp with efficient connection pooling and concurrent operations
- **🔒 Security by Design** - Certificate pinning, SecretStr, automatic sensitive data filtering, audit logging
- **🛡️ Production-Ready** - Circuit breaker, health monitoring, graceful shutdown, exponential backoff retry
- **📝 100% Type Safe** - Full type hints, mypy strict mode compatible, runtime validation with Pydantic v2
- **⚡ High Performance** - Batch operations, rate limiting, lazy loading, memory-optimized data structures
- **🎯 Developer Experience** - Rich IDE support, comprehensive docs, 60+ practical examples

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
# Generate .env template
python -c "from pyoutlineapi import quick_setup; quick_setup()"

# Edit .env.example → .env
OUTLINE_API_URL=https://your-server.com:12345/your-secret-path
OUTLINE_CERT_SHA256=your-64-character-sha256-fingerprint
```

### 2. Basic Usage

```python
from pyoutlineapi import AsyncOutlineClient
import asyncio


async def main():
    # Environment variables (recommended)
    async with AsyncOutlineClient.from_env() as client:
        # Get server info
        server = await client.get_server_info()
        print(f"Server: {server.name} (v{server.version})")

        # Create access key
        key = await client.create_access_key(name="Alice")
        print(f"Access URL: {key.access_url}")

        # List all keys
        keys = await client.get_access_keys()
        print(f"Total keys: {keys.count}")


asyncio.run(main())
```

### 3. Direct Configuration

```python
from pyoutlineapi import OutlineClientConfig
from pydantic import SecretStr

# Minimal configuration
config = OutlineClientConfig.create_minimal(
    api_url="https://server.com:12345/secret",
    cert_sha256="abc123...",
    timeout=10,
    enable_logging=True
)

async with AsyncOutlineClient(config) as client:
    server = await client.get_server_info()
```

---

## ✨ Core Features

### 📋 Access Key Management

```python
from pyoutlineapi.models import DataLimit

# Create key with data limit
key = await client.create_access_key(
    name="Alice",
    limit=DataLimit.from_gigabytes(10)  # 10 GB limit
)

# Create with custom settings
key = await client.create_access_key(
    name="Bob",
    port=8388,
    method="chacha20-ietf-poly1305",
    password="custom-password"
)

# Create with specific ID
key = await client.create_access_key_with_id(
    key_id="user-001",
    name="Charlie"
)

# List and filter
keys = await client.get_access_keys()
limited_keys = keys.filter_with_limits()  # Keys with data limits
unlimited_keys = keys.filter_without_limits()
alice_keys = keys.get_by_name("Alice")
key = keys.get_by_id("1")

# Manage keys
await client.rename_access_key("1", "Alice Smith")
await client.set_access_key_data_limit("1", 5_000_000_000)  # 5 GB
await client.remove_access_key_data_limit("1")
await client.delete_access_key("1")
```

### ⚙️ Server Configuration

```python
# Get server info
server = await client.get_server_info()
print(f"Name: {server.name}")
print(f"Port: {server.port_for_new_access_keys}")
print(f"Metrics: {server.metrics_enabled}")
print(f"Created: {server.created_timestamp_seconds}")

# Configure server
await client.rename_server("Production VPN")
await client.set_hostname("vpn.example.com")
await client.set_default_port(443)

# Global data limits (affects all keys)
await client.set_global_data_limit(100 * 1024 ** 3)  # 100 GB
await client.remove_global_data_limit()
```

### 📊 Metrics & Monitoring

```python
# Enable/disable metrics
await client.set_metrics_status(True)
status = await client.get_metrics_status()

# Transfer metrics
metrics = await client.get_transfer_metrics()
print(f"Total: {metrics.total_gigabytes:.2f} GB")
print(f"Active keys: {metrics.key_count}")

# Top consumers
for key_id, bytes_used in metrics.get_top_consumers(5):
    print(f"{key_id}: {bytes_used / 1024 ** 3:.2f} GB")

# Per-key usage
usage = metrics.get_usage_for_key("key-123")
print(f"Key 123: {usage / 1024 ** 3:.2f} GB")

# Experimental metrics (detailed analytics)
exp = await client.get_experimental_metrics("24h")
print(f"Server tunnel time: {exp.server.tunnel_time.hours:.1f} hours")
print(f"Server traffic: {exp.server.data_transferred.gigabytes:.2f} GB")
print(f"Peak bandwidth: {exp.server.bandwidth.peak.data.bytes} bytes")
print(f"Locations: {len(exp.server.locations)}")

# Per-key experimental metrics
key_metric = exp.get_key_metric("key-123")
if key_metric:
    print(f"Key tunnel time: {key_metric.tunnel_time.minutes:.1f} min")
```

---

## 🛡️ Enterprise Features

### Circuit Breaker Pattern

**Automatic protection against cascading failures with intelligent failure detection and recovery.**

```python
from pyoutlineapi import CircuitOpenError

# Enable circuit breaker
async with AsyncOutlineClient.from_env(
        enable_circuit_breaker=True,
        circuit_failure_threshold=5,  # Open after 5 failures
        circuit_recovery_timeout=60.0,  # Test recovery after 60s
        circuit_success_threshold=2  # Close after 2 successes
) as client:
    try:
        await client.get_server_info()
    except CircuitOpenError as e:
        print(f"Circuit open - retry after {e.retry_after}s")

    # Monitor circuit health
    metrics = client.get_circuit_metrics()
    if metrics:
        print(f"State: {metrics['state']}")  # CLOSED/OPEN/HALF_OPEN
        print(f"Success rate: {metrics['success_rate']:.2%}")
        print(f"Total calls: {metrics['total_calls']}")
        print(f"Failed calls: {metrics['failed_calls']}")

    # Reset circuit manually (emergency)
    await client.reset_circuit_breaker()
```

**Circuit States:**

- **CLOSED** - Normal operation, requests pass through
- **OPEN** - Failures exceeded threshold, requests blocked immediately
- **HALF_OPEN** - Testing recovery, limited requests allowed

### Health Monitoring

**Comprehensive health checks with caching, custom checks, and performance tracking.**

```python
from pyoutlineapi.health_monitoring import HealthMonitor

async with AsyncOutlineClient.from_env() as client:
    monitor = HealthMonitor(client, cache_ttl=30.0)

    # Quick connectivity check
    is_healthy = await monitor.quick_check()
    print(f"Quick check: {is_healthy}")

    # Comprehensive health check
    health = await monitor.comprehensive_check()
    print(f"Overall health: {health.healthy}")
    print(f"Total checks: {health.total_checks}")
    print(f"Passed: {health.passed_checks}")
    print(f"Degraded: {health.is_degraded}")

    # Check details
    for check_name, result in health.checks.items():
        print(f"{check_name}: {result['status']}")
        if 'message' in result:
            print(f"  → {result['message']}")

    # Failed checks
    if not health.healthy:
        print(f"Failed: {health.failed_checks}")
        print(f"Warnings: {health.warning_checks}")

    # Performance metrics
    print(f"Connectivity time: {health.metrics.get('connectivity_time', 0):.3f}s")
    print(f"Success rate: {health.metrics.get('success_rate', 0):.2%}")


    # Custom health check
    async def check_disk_space(client):
        # Your custom logic
        return {
            "status": "healthy",
            "message": "Disk space OK"
        }


    monitor.add_custom_check("disk_space", check_disk_space)
    health = await monitor.comprehensive_check(force_refresh=True)

    # Wait for service recovery
    if await monitor.wait_for_healthy(timeout=120, check_interval=5):
        print("Service recovered!")
    else:
        print("Service still unhealthy after 120s")

    # Performance tracking
    monitor.record_request(success=True, duration=0.5)
    monitor.record_request(success=False, duration=5.0)

    metrics = monitor.get_metrics()
    print(f"Total requests: {metrics['total_requests']}")
    print(f"Avg response time: {metrics['avg_response_time']:.3f}s")
    print(f"Uptime: {metrics['uptime']:.1f}s")
```

### Batch Operations

**High-performance parallel operations with concurrency control and comprehensive error tracking.**

```python
from pyoutlineapi.batch_operations import BatchOperations
from pyoutlineapi.models import DataLimit

async with AsyncOutlineClient.from_env() as client:
    batch = BatchOperations(client, max_concurrent=10)

    # Batch create (100 keys)
    configs = [
        {"name": f"User{i}", "limit": DataLimit.from_gigabytes(5)}
        for i in range(1, 101)
    ]
    result = await batch.create_multiple_keys(configs, fail_fast=False)

    print(f"Created: {result.successful}/{result.total}")
    print(f"Failed: {result.failed}")
    print(f"Success rate: {result.success_rate:.2%}")

    # Get successful keys
    keys = result.get_successful_results()
    failures = result.get_failures()

    # Validation errors
    if result.has_validation_errors:
        print(f"Validation errors: {result.validation_errors}")

    # Batch rename
    pairs = [(key.id, f"User-{i}") for i, key in enumerate(keys, 1)]
    result = await batch.rename_multiple_keys(pairs)

    # Batch set data limits
    limits = [(key.id, 10 * 1024 ** 3) for key in keys]  # 10 GB each
    result = await batch.set_multiple_data_limits(limits)

    # Batch delete
    key_ids = [key.id for key in keys]
    result = await batch.delete_multiple_keys(key_ids)

    # Batch fetch (parallel retrieval)
    result = await batch.fetch_multiple_keys(key_ids)

    # Custom batch operations
    operations = [
        lambda: client.get_access_key(key_id)
        for key_id in key_ids
    ]
    result = await batch.execute_custom_operations(operations)

    # Dynamic concurrency adjustment
    await batch.set_concurrency(20)  # Increase to 20 concurrent operations
```

### Metrics Collection

**Automatic periodic metrics collection with Prometheus export and temporal queries.**

```python
from pyoutlineapi.metrics_collector import MetricsCollector

async with AsyncOutlineClient.from_env() as client:
    # Initialize collector
    collector = MetricsCollector(
        client,
        interval=60,  # Collect every 60 seconds
        max_history=1440  # Keep 24 hours (1440 minutes)
    )

    # Start collection
    await collector.start()
    await asyncio.sleep(3600)  # Run for 1 hour

    # Get latest snapshot
    snapshot = collector.get_latest_snapshot()
    if snapshot:
        print(f"Keys: {snapshot.key_count}")
        print(f"Total traffic: {snapshot.total_bytes_transferred}")

    # Usage statistics
    stats = collector.get_usage_stats(period_minutes=60)
    print(f"Period: {stats.duration:.1f}s")
    print(f"Total: {stats.gigabytes_transferred:.2f} GB")
    print(f"Rate: {stats.bytes_per_second / 1024:.2f} KB/s")
    print(f"Peak: {stats.peak_bytes / 1024 ** 3:.2f} GB")
    print(f"Active keys: {len(stats.active_keys)}")
    print(f"Snapshots: {stats.snapshots_count}")

    # Per-key usage
    key_usage = collector.get_key_usage("key-123", period_minutes=60)
    print(f"Key 123 traffic: {key_usage['total_bytes'] / 1024 ** 3:.2f} GB")
    print(f"Key 123 rate: {key_usage['bytes_per_second'] / 1024:.2f} KB/s")

    # Time-based queries
    cutoff = time.time() - 3600  # Last hour
    recent_snapshots = collector.get_snapshots_after(cutoff)

    # Export metrics
    data = collector.export_to_dict()
    print(f"Collection duration: {data['collection_end'] - data['collection_start']:.1f}s")
    print(f"Snapshots: {data['snapshots_count']}")

    # Prometheus format (full)
    prometheus = collector.export_prometheus_format(include_per_key=True)
    print(prometheus)

    # Prometheus format (summary only)
    summary = collector.export_prometheus_summary()
    print(summary)

    # Collector stats
    print(f"Running: {collector.is_running}")
    print(f"Uptime: {collector.uptime:.1f}s")
    print(f"Snapshots collected: {collector.snapshots_count}")

    # Stop collection
    await collector.stop()

# Or use as context manager
async with MetricsCollector(client, interval=60) as collector:
    await asyncio.sleep(3600)
    stats = collector.get_usage_stats()
```

### Audit Logging

**Production-ready audit trail with async queue processing, sensitive data filtering, and flexible storage.**

```python
from pyoutlineapi import DefaultAuditLogger, set_default_audit_logger

# Default audit logger (built-in)
audit_logger = DefaultAuditLogger(
    enable_async=True,  # Non-blocking queue processing
    queue_size=5000  # Large queue for high throughput
)

async with AsyncOutlineClient.from_env(audit_logger=audit_logger) as client:
    # All operations are automatically audited
    key = await client.create_access_key(name="Alice")
    # 📝 [AUDIT] create_access_key on {key.id} | {'name': 'Alice', 'success': True}

    await client.rename_access_key(key.id, "Alice Smith")
    # 📝 [AUDIT] rename_access_key on {key.id} | {'new_name': 'Alice Smith', 'success': True}

    await client.delete_access_key(key.id)
    # 📝 [AUDIT] delete_access_key on {key.id} | {'success': True}

    # Failed operations also logged
    try:
        await client.delete_access_key("non-existent")
    except Exception:
        pass
    # 📝 [AUDIT] delete_access_key on non-existent | {'success': False, 'error': '...'}


# Custom audit logger
class CustomAuditLogger:
    def log_action(self, action: str, resource: str, **kwargs) -> None:
        # Your logging logic (database, file, Syslog, etc.)
        print(f"AUDIT: {action} on {resource} - {kwargs}")

    async def alog_action(self, action: str, resource: str, **kwargs) -> None:
        # Async version
        self.log_action(action, resource, **kwargs)

    async def shutdown(self) -> None:
        # Cleanup
        pass


# Global audit logger (singleton)
set_default_audit_logger(DefaultAuditLogger(enable_async=True))

# All clients now use this logger
async with AsyncOutlineClient.from_env() as client1:
    await client1.create_access_key(name="User1")

async with AsyncOutlineClient.from_env() as client2:
    await client2.create_access_key(name="User2")

# Disable audit logging (testing)
from pyoutlineapi import NoOpAuditLogger

async with AsyncOutlineClient.from_env(audit_logger=NoOpAuditLogger()) as client:
    await client.create_access_key(name="Test")  # No audit logs
```

**Audited Operations:**

- Access Keys: `create`, `delete`, `rename`, `set_data_limit`, `remove_data_limit`
- Server: `rename_server`, `set_hostname`, `set_default_port`
- Data Limits: `set_global_data_limit`, `remove_global_data_limit`
- Metrics: `set_metrics_status`

**Security Features:**

- Automatic sensitive data filtering (passwords, tokens, secrets)
- Correlation IDs for request tracing
- Success/failure tracking
- Graceful shutdown with queue draining

---

## ⚙️ Configuration

### Environment Variables (✅ Recommended)

```bash
# Required
OUTLINE_API_URL=https://server.com:12345/secret
OUTLINE_CERT_SHA256=your-certificate-fingerprint

# Client settings (optional)
OUTLINE_TIMEOUT=10
OUTLINE_RETRY_ATTEMPTS=2
OUTLINE_MAX_CONNECTIONS=10
OUTLINE_RATE_LIMIT=100
OUTLINE_USER_AGENT=MyApp/1.0

# Feature flags (optional)
OUTLINE_ENABLE_CIRCUIT_BREAKER=true
OUTLINE_ENABLE_LOGGING=false
OUTLINE_JSON_FORMAT=false

# Circuit breaker settings (optional)
OUTLINE_CIRCUIT_FAILURE_THRESHOLD=5
OUTLINE_CIRCUIT_RECOVERY_TIMEOUT=60.0
OUTLINE_CIRCUIT_SUCCESS_THRESHOLD=2
OUTLINE_CIRCUIT_CALL_TIMEOUT=10.0
```

```python
# Load from .env file
async with AsyncOutlineClient.from_env() as client:
    await client.get_server_info()

# Custom .env file
async with AsyncOutlineClient.from_env(env_file=".env.prod") as client:
    await client.get_server_info()

# Override specific settings
async with AsyncOutlineClient.from_env(
        timeout=30,
        enable_logging=True,
        rate_limit=50
) as client:
    await client.get_server_info()
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
    max_connections=20,
    rate_limit=100,
    enable_circuit_breaker=True,
    enable_logging=True,
    json_format=False,
)

async with AsyncOutlineClient(config) as client:
    await client.get_server_info()

# Minimal configuration
config = OutlineClientConfig.create_minimal(
    api_url="https://server.com:12345/secret",
    cert_sha256="abc123...",
    timeout=10
)

# Environment-specific presets
from pyoutlineapi import DevelopmentConfig, ProductionConfig

# Development: relaxed security, extra logging
dev_config = DevelopmentConfig.from_env()

# Production: enforces HTTPS, strict validation
prod_config = ProductionConfig.from_env()
```

### Configuration Management

```python
# Immutable copy with overrides
new_config = config.model_copy_immutable(
    timeout=20,
    enable_logging=True
)

# Safe config for logging (secrets masked)
safe_config = config.get_sanitized_config()
logger.info(f"Using config: {safe_config}")
# Output: {'api_url': 'https://server.com/***', 'cert_sha256': '***MASKED***', ...}

# Get cert value (use with caution)
cert_value = config.get_cert_sha256()

# Circuit breaker config
if config.circuit_config:
    print(f"Threshold: {config.circuit_config.failure_threshold}")
    print(f"Timeout: {config.circuit_config.recovery_timeout}")
```

---

## 🚨 Error Handling

### Exception Hierarchy

```python
from pyoutlineapi.exceptions import (
    OutlineError,  # Base exception
    APIError,  # API request failures
    CircuitOpenError,  # Circuit breaker open
    ConfigurationError,  # Invalid configuration
    ValidationError,  # Data validation failures
    ConnectionError,  # Connection issues
    TimeoutError,  # Request timeouts
)
```

### Comprehensive Error Handling

```python
from pyoutlineapi.exceptions import (
    CircuitOpenError,
    APIError,
    ConnectionError,
    TimeoutError,
    get_retry_delay,
    is_retryable,
    get_safe_error_dict
)

async with AsyncOutlineClient.from_env() as client:
    try:
        server = await client.get_server_info()

    except CircuitOpenError as e:
        # Circuit breaker opened
        print(f"Service failing - retry after {e.retry_after}s")
        await asyncio.sleep(e.retry_after)

    except APIError as e:
        # API-specific errors
        print(f"Status: {e.status_code}")
        print(f"Endpoint: {e.endpoint}")

        if e.is_client_error:  # 4xx
            print("Client error - check request")
        elif e.is_server_error:  # 5xx
            print("Server error - retry may help")
        elif e.is_rate_limit_error:  # 429
            print("Rate limited")

        if e.is_retryable:
            delay = get_retry_delay(e)
            await asyncio.sleep(delay)

    except ConnectionError as e:
        # Connection failures
        print(f"Failed to connect to {e.host}:{e.port}")

    except TimeoutError as e:
        # Timeout errors
        print(f"Timeout after {e.timeout}s on {e.operation}")

    except OutlineError as e:
        # Generic handling
        safe_dict = get_safe_error_dict(e)
        logger.error(f"Error: {safe_dict}")
```

### Retry Strategy

```python
from pyoutlineapi.exceptions import APIError, is_retryable, get_retry_delay


async def robust_operation(max_attempts: int = 3):
    """Operation with exponential backoff retry."""
    for attempt in range(max_attempts):
        try:
            async with AsyncOutlineClient.from_env() as client:
                return await client.get_server_info()

        except APIError as e:
            if not is_retryable(e) or attempt == max_attempts - 1:
                raise

            delay = get_retry_delay(e) or 1.0
            backoff_delay = delay * (2 ** attempt)  # Exponential backoff

            print(f"Attempt {attempt + 1} failed, retrying in {backoff_delay}s")
            await asyncio.sleep(backoff_delay)
```

---

## 📚 Advanced Usage

### Rate Limiting & Connection Pooling

```python
# Configure rate limiting
config = OutlineClientConfig.from_env(
    rate_limit=50,  # Max 50 concurrent requests
    max_connections=20,  # Connection pool size
)

async with AsyncOutlineClient(config) as client:
    # Check rate limiter stats
    stats = client.get_rate_limiter_stats()
    print(f"Active: {stats['active']}/{stats['limit']}")
    print(f"Available: {stats['available']}")

    # Adjust dynamically
    await client.set_rate_limit(100)

    # Monitor active requests
    print(f"Active requests: {client.active_requests}")
    print(f"Available slots: {client.available_slots}")
```

### Health Checks & Monitoring

```python
async with AsyncOutlineClient.from_env() as client:
    # Quick health check
    health = await client.health_check()
    print(f"Healthy: {health['healthy']}")
    print(f"Response time: {health.get('response_time_ms')}ms")
    print(f"Circuit: {health['circuit_state']}")

    # Comprehensive server summary
    summary = await client.get_server_summary()
    print(f"Server: {summary['server']['name']}")
    print(f"Keys: {summary['access_keys_count']}")
    print(f"Metrics enabled: {summary['server'].get('metricsEnabled')}")

    if summary['transfer_metrics']:
        print(f"Total traffic: {summary['transfer_metrics']}")

    # Client status
    status = client.get_status()
    print(f"Connected: {status['connected']}")
    print(f"Circuit state: {status['circuit_state']}")
    print(f"Active requests: {status['active_requests']}")
    print(f"Rate limit: {status['rate_limit']}")
```

### JSON Format (Alternative to Models)

```python
# Global JSON format
config = OutlineClientConfig.from_env(json_format=True)
async with AsyncOutlineClient(config) as client:
    # Returns dict instead of Pydantic model
    server_dict = await client.get_server_info()
    print(server_dict["name"])

# Per-request JSON format
async with AsyncOutlineClient.from_env() as client:
    # Override default format for specific request
    server_dict = await client.get_server_info(as_json=True)
    server_model = await client.get_server_info(as_json=False)
```

### Custom Metrics Collection

```python
from pyoutlineapi.base_client import MetricsCollector


class PrometheusMetrics:
    """Custom metrics collector for Prometheus."""

    def increment(self, metric: str, *, tags: dict | None = None) -> None:
        # Your Prometheus counter
        pass

    def timing(self, metric: str, value: float, *, tags: dict | None = None) -> None:
        # Your Prometheus histogram
        pass

    def gauge(self, metric: str, value: float, *, tags: dict | None = None) -> None:
        # Your Prometheus gauge
        pass


metrics = PrometheusMetrics()
async with AsyncOutlineClient.from_env(metrics=metrics) as client:
    # All operations are automatically tracked
    await client.get_server_info()
```

---

## 🎯 Best Practices

### ✅ Use Environment Variables

```python
# ✅ Secure - credentials never in code
async with AsyncOutlineClient.from_env() as client:
    pass

# ❌ Insecure - secrets visible in code/logs
client = AsyncOutlineClient.create(
    api_url="https://...",  # Secret path exposed!
    cert_sha256="..."  # Certificate exposed!
)
```

### ✅ Always Use Context Managers

```python
# ✅ Automatic resource cleanup
async with AsyncOutlineClient.from_env() as client:
    await client.get_server_info()
# Session closed automatically

# ❌ Manual cleanup required
client = AsyncOutlineClient.from_env()
await client.__aenter__()
try:
    await client.get_server_info()
finally:
    await client.shutdown()  # Easy to forget!
```

### ✅ Handle Specific Exceptions

```python
# ✅ Specific error handling
try:
    key = await client.get_access_key("key-id")
except APIError as e:
    if e.status_code == 404:
        print("Key not found")
    elif e.is_server_error:
        print("Server error - retry")

# ❌ Catch-all hides errors
try:
    key = await client.get_access_key("key-id")
except Exception:
    pass  # Silent failure - bad!
```

### ✅ Enable Production Features

```python
# ✅ Production configuration
config = ProductionConfig.from_env(
    enable_circuit_breaker=True,
    circuit_failure_threshold=5,
    rate_limit=50,
)
audit = DefaultAuditLogger(enable_async=True, queue_size=5000)
client = AsyncOutlineClient(config, audit_logger=audit)

# ❌ No protection
config = OutlineClientConfig.from_env(enable_circuit_breaker=False)
client = AsyncOutlineClient(config, audit_logger=NoOpAuditLogger())
```

### ✅ Use Batch Operations for Multiple Items

```python
# ✅ Efficient batch operations
batch = BatchOperations(client, max_concurrent=10

```python
# ✅ Efficient batch operations
batch = BatchOperations(client, max_concurrent=10)
configs = [{"name": f"User{i}"} for i in range(1, 101)]
result = await batch.create_multiple_keys(configs)
# ~10 concurrent requests, much faster!

# ❌ Sequential operations (slow)
for i in range(1, 101):
    await client.create_access_key(name=f"User{i}")
    # 100 sequential requests - very slow!
```

### ✅ Monitor Health & Performance

```python
# ✅ Active monitoring
monitor = HealthMonitor(client, cache_ttl=30)
health = await monitor.comprehensive_check()

if not health.healthy:
    logger.error(f"Service unhealthy: {health.failed_checks}")
    # Alert operations team

# Track performance
monitor.record_request(success=True, duration=0.5)
metrics = monitor.get_metrics()

# ❌ No monitoring
await client.get_server_info()
# Hope it works!
```

---

## 🐳 Docker Example

**Dockerfile:**

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
ENV OUTLINE_ENABLE_CIRCUIT_BREAKER="true"
ENV OUTLINE_CIRCUIT_FAILURE_THRESHOLD="5"
ENV OUTLINE_RATE_LIMIT="50"

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import asyncio; from app import health_check; exit(0 if asyncio.run(health_check()) else 1)"

CMD ["python", "app.py"]
```

**docker-compose.yml:**

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

**app.py:**

```python
"""Production Outline VPN Manager"""
import asyncio
import logging
import signal
from pyoutlineapi import AsyncOutlineClient
from pyoutlineapi.health_monitoring import HealthMonitor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global client for health checks
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
        logger.error(f"Health check failed: {e}")
        return False


async def main():
    """Main application logic."""
    logger.info("Starting Outline VPN Manager...")

    async with AsyncOutlineClient.from_env() as client:
        # Wait for service
        monitor = HealthMonitor(client)
        if not await monitor.wait_for_healthy(timeout=60):
            logger.error("Service not healthy after 60s")
            return 1

        logger.info("Service healthy - starting operations")

        # Your application logic here
        server = await client.get_server_info()
        logger.info(f"Managing server: {server.name}")

        # Keep running
        while True:
            await asyncio.sleep(60)
            health = await monitor.comprehensive_check()
            if not health.healthy:
                logger.warning(f"Health degraded: {health.failed_checks}")

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

---

## 📖 Complete Production Example

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
            # Setup audit logging
            audit_logger = DefaultAuditLogger(
                enable_async=True,
                queue_size=5000
            )

            # Initialize client
            self.client = AsyncOutlineClient.from_env(
                audit_logger=audit_logger,
                enable_circuit_breaker=True,
                circuit_failure_threshold=5,
                rate_limit=50
            )
            await self.client.__aenter__()

            # Initialize health monitor
            self.monitor = HealthMonitor(self.client, cache_ttl=30)

            # Wait for service
            logger.info("Waiting for service to become healthy...")
            if not await self.monitor.wait_for_healthy(timeout=120):
                logger.error("Service not healthy after 120s")
                return False

            logger.info("Service healthy!")

            # Initialize metrics collector
            self.collector = MetricsCollector(
                self.client,
                interval=60,
                max_history=1440  # 24 hours
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
                "limit": DataLimit.from_gigabytes(10)
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
                    # Send alert to operations team

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
                await asyncio.sleep(300)  # Every 5 minutes

                stats = self.collector.get_usage_stats(period_minutes=5)

                logger.info("=== Metrics Report ===")
                logger.info(f"Traffic: {stats.gigabytes_transferred:.2f} GB")
                logger.info(f"Rate: {stats.bytes_per_second / 1024:.2f} KB/s")
                logger.info(f"Active keys: {len(stats.active_keys)}")
                logger.info(f"Snapshots: {stats.snapshots_count}")

            except Exception as e:
                logger.error(f"Metrics report error: {e}")

    async def run(self) -> int:
        """Main application loop."""
        try:
            # Initialize
            if not await self.initialize():
                return 1

            # Get server info
            server = await self.client.get_server_info()
            logger.info(f"Managing server: {server.name} (v{server.version})")

            # Create sample users
            await self.create_users(10)

            # Start background tasks
            monitor_task = asyncio.create_task(self.monitor_loop())
            metrics_task = asyncio.create_task(self.metrics_report())

            # Wait for shutdown signal
            await self.shutdown_event.wait()

            # Cancel tasks
            monitor_task.cancel()
            metrics_task.cancel()

            logger.info("Shutting down gracefully...")
            return 0

        except CircuitOpenError as e:
            logger.error(f"Circuit open: retry after {e.retry_after}s")
            return 1

        except OutlineError as e:
            logger.error(f"Error: {e}")
            return 1

        finally:
            await self.cleanup()

    async def cleanup(self) -> None:
        """Cleanup resources."""
        if self.collector:
            await self.collector.stop()
            logger.info("Metrics collector stopped")

        if self.client:
            await self.client.shutdown()
            logger.info("Client shutdown complete")

    def handle_signal(self, sig):
        """Handle shutdown signals."""
        logger.info(f"Received signal {sig}, initiating shutdown...")
        self.shutdown_event.set()


async def main():
    """Entry point."""
    manager = OutlineManager()

    # Setup signal handlers
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig,
            lambda s=sig: manager.handle_signal(s)
        )

    return await manager.run()


if __name__ == "__main__":
    exit(asyncio.run(main()))
```

---

## 🧪 Testing

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run all tests
pytest

# With coverage
pytest --cov=pyoutlineapi --cov-report=html --cov-report=term

# Specific test file
pytest tests/test_client.py -v

# Run with markers
pytest -m "not slow"  # Skip slow tests
pytest -m integration  # Only integration tests

# Type checking
mypy pyoutlineapi --strict

# Linting
ruff check pyoutlineapi

# Formatting
ruff format pyoutlineapi

# Security checks
bandit -r pyoutlineapi
```

---

## 🔧 Development

```bash
# Clone repository
git clone https://github.com/orenlab/pyoutlineapi.git
cd pyoutlineapi

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows

# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest

# Build documentation
cd docs
make html
```

---

## 🤝 Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for:

- Code of Conduct
- Development setup
- Coding standards
- Testing guidelines
- Pull request process

---

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details.

Copyright (c) 2025 Denis Rozhnovskiy

---

## 🔗 Links

- **Documentation**: [GitHub Wiki](https://github.com/orenlab/pyoutlineapi/wiki)
- **Changelog**: [CHANGELOG.md](CHANGELOG.md)
- **Issues**: [GitHub Issues](https://github.com/orenlab/pyoutlineapi/issues)
- **Discussions**: [GitHub Discussions](https://github.com/orenlab/pyoutlineapi/discussions)
- **PyPI**: [pypi.org/project/pyoutlineapi](https://pypi.org/project/pyoutlineapi/)
- **Outline VPN**: [getoutline.org](https://getoutline.org/)

---

## 💬 Support

- 📧 **Email**: `pytelemonbot@mail.ru`
- 🐛 **Bug Reports**: [GitHub Issues](https://github.com/orenlab/pyoutlineapi/issues)
- 💡 **Feature Requests**: [GitHub Discussions](https://github.com/orenlab/pyoutlineapi/discussions)
- 📖 **Documentation**: [Wiki](https://github.com/orenlab/pyoutlineapi/wiki)

---

## 🏆 Features Summary

| Feature                | Description                                          | Status |
|------------------------|------------------------------------------------------|--------|
| **Async/Await**        | Built on aiohttp with efficient connection pooling   | ✅      |
| **Type Safety**        | 100% type hints, Pydantic v2 validation              | ✅      |
| **Circuit Breaker**    | Automatic failure detection and recovery             | ✅      |
| **Health Monitoring**  | Comprehensive health checks with custom checks       | ✅      |
| **Audit Logging**      | Production-ready audit trail with async queue        | ✅      |
| **Batch Operations**   | High-performance parallel operations                 | ✅      |
| **Metrics Collection** | Automatic periodic collection with Prometheus export | ✅      |
| **Rate Limiting**      | Configurable concurrent request limits               | ✅      |
| **Retry Logic**        | Exponential backoff with jitter                      | ✅      |
| **Configuration**      | Environment variables, Pydantic models, presets      | ✅      |
| **Security**           | Certificate pinning, SecretStr, data filtering       | ✅      |
| **Error Handling**     | Rich exception hierarchy with retry guidance         | ✅      |
| **Documentation**      | Comprehensive docs with 60+ examples                 | ✅      |

---

## 📊 Project Status

![GitHub last commit](https://img.shields.io/github/last-commit/orenlab/pyoutlineapi)
![GitHub issues](https://img.shields.io/github/issues/orenlab/pyoutlineapi)
![GitHub pull requests](https://img.shields.io/github/issues-pr/orenlab/pyoutlineapi)
![GitHub stars](https://img.shields.io/github/stars/orenlab/pyoutlineapi?style=social)

---

**Made with ❤️ by [Denis Rozhnovskiy](https://github.com/orenlab)**

*PyOutlineAPI - Enterprise-grade Python client for Outline VPN Server*

**Version 0.4.0** - Complete architectural overhaul with enterprise patterns

[⬆ Back to top](#pyoutlineapi)