# PyOutlineAPI

A modern, async-first Python client for the [Outline VPN Server API](https://github.com/Jigsaw-Code/outline-server) with
advanced features including circuit breaker protection, health monitoring, and comprehensive batch operations.

[![tests](https://github.com/orenlab/pyoutlineapi/actions/workflows/python_tests.yml/badge.svg)](https://github.com/orenlab/pyoutlineapi/actions/workflows/python_tests.yml)
[![codecov](https://codecov.io/gh/orenlab/pyoutlineapi/branch/main/graph/badge.svg?token=D0MPKCKFJQ)](https://codecov.io/gh/orenlab/pyoutlineapi)
[![Security Rating](https://sonarcloud.io/api/project_badges/measure?project=orenlab_pyoutlineapi&metric=security_rating)](https://sonarcloud.io/summary/new_code?id=orenlab_pyoutlineapi)
[![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=orenlab_pyoutlineapi&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=orenlab_pyoutlineapi)
[![Vulnerabilities](https://sonarcloud.io/api/project_badges/measure?project=orenlab_pyoutlineapi&metric=vulnerabilities)](https://sonarcloud.io/summary/new_code?id=orenlab_pyoutlineapi)
![PyPI - Downloads](https://img.shields.io/pypi/dm/pyoutlineapi)
![PyPI - Version](https://img.shields.io/pypi/v/pyoutlineapi)
![Python Version](https://img.shields.io/pypi/pyversions/pyoutlineapi)

## ✨ Features

### Core Features

- ⚡ **Async-first design** with full asyncio support and connection pooling
- 🔒 **Enterprise-grade security** with TLS certificate fingerprint verification
- ✅ **Type-safe** with comprehensive Pydantic models and static typing
- 📊 **Complete API coverage** including experimental server metrics
- 🎯 **Advanced key management** with custom IDs, data limits, and flexible configuration
- 🌐 **Flexible response formats** - return JSON dict or typed Pydantic models

### Advanced Features

- 🛡️ **Circuit breaker protection** with automatic failure detection and recovery
- 🏥 **Health monitoring** with comprehensive status checks and metrics
- 🚀 **Batch operations** for efficient bulk key management
- 🔄 **Smart retry logic** with exponential backoff and rate limiting
- 📈 **Performance metrics** collection and monitoring
- 🎛️ **Dynamic configuration** with runtime parameter updates
- 📚 **Production-ready** with comprehensive logging and debugging support

### Reliability Features

- 🛠️ **Robust error handling** with detailed exception hierarchy
- 🔧 **Connection management** with automatic session handling
- ⚡ **Performance optimization** with configurable connection pooling
- 🎯 **Graceful degradation** when services are temporarily unavailable

## 🚀 Installation

### From PyPI (Recommended)

```bash
pip install pyoutlineapi
```

### With Poetry

```bash
poetry add pyoutlineapi
```

### Development Installation

```bash
git clone https://github.com/orenlab/pyoutlineapi.git
cd pyoutlineapi
pip install -e ".[dev]"
```

## 📋 Requirements

- Python 3.10+
- aiohttp >= 3.8.0
- pydantic >= 2.0.0
- A running Outline VPN Server

## 🎯 Quick Start

### Basic Usage

```python
import asyncio
from pyoutlineapi import AsyncOutlineClient, DataLimit


async def main():
    # Initialize client with context manager (recommended)
    async with AsyncOutlineClient.create(
            api_url="https://your-outline-server:port/secret-path",
            cert_sha256="your-certificate-fingerprint",
            enable_logging=True
    ) as client:
        # Get server information
        server = await client.get_server_info()
        print(f"Connected to {server.name} (v{server.version})")

        # Create a new access key with data limit
        key = await client.create_access_key(
            name="Alice",
            limit=DataLimit(bytes=5 * 1024 ** 3)  # 5 GB limit
        )
        print(f"Created key: {key.access_url}")

        # Get comprehensive server summary
        summary = await client.get_server_summary()
        print(f"Server healthy: {summary['healthy']}")
        print(f"Access keys count: {summary['access_keys_count']}")


if __name__ == "__main__":
    asyncio.run(main())
```

### Advanced Configuration

```python
from pyoutlineapi import AsyncOutlineClient, CircuitConfig


async def advanced_setup():
    # Custom circuit breaker configuration
    circuit_config = CircuitConfig(
        failure_threshold=3,  # Open after 3 failures
        recovery_timeout=30.0,  # Wait 30s before retry
        success_threshold=2,  # Need 2 successes to close
        failure_rate_threshold=0.5,  # 50% failure rate threshold
        min_calls_to_evaluate=5  # Minimum calls before evaluation
    )

    async with AsyncOutlineClient(
            api_url="https://your-server:port/secret-path",
            cert_sha256="your-cert-fingerprint",
            json_format=False,  # Return Pydantic models (default)
            timeout=30,  # Request timeout
            retry_attempts=3,  # Retry failed requests
            enable_logging=True,  # Debug logging
            max_connections=10,  # Connection pool size
            rate_limit_delay=0.1,  # 100ms between requests
            circuit_breaker_enabled=True,  # Enable circuit breaker
            circuit_config=circuit_config,  # Custom configuration
            enable_health_monitoring=True,  # Health monitoring
            enable_metrics_collection=True  # Performance metrics
    ) as client:
        # Check health with detailed metrics
        health = await client.health_check(include_detailed_metrics=True)
        print(f"Health Status: {health['healthy']}")

        # Monitor circuit breaker
        cb_status = await client.get_circuit_breaker_status()
        print(f"Circuit State: {cb_status['state']}")


asyncio.run(advanced_setup())
```

## 🔧 Core Operations

### Server Management

```python
async def manage_server():
    async with AsyncOutlineClient.create(api_url, cert_sha256) as client:
        # Get server information
        server = await client.get_server_info()
        print(f"Server: {server.name}, Version: {server.version}")

        # Configure server
        await client.rename_server("Production VPN Server")
        await client.set_hostname("vpn.yourcompany.com")
        await client.set_default_port(8388)

        # Get comprehensive summary
        summary = await client.get_server_summary(metrics_since="24h")
        print(f"Health: {summary['healthy']}")
        print(f"Keys: {summary['access_keys_count']}")
```

### Access Key Management

```python
async def manage_keys():
    async with AsyncOutlineClient.create(api_url, cert_sha256) as client:
        # Create keys with various configurations
        basic_key = await client.create_access_key(name="John Doe")

        premium_key = await client.create_access_key(
            name="Premium User",
            port=9999,
            method="chacha20-ietf-poly1305",
            limit=DataLimit(bytes=10 * 1024 ** 3)  # 10 GB
        )

        # Create key with specific ID
        custom_key = await client.create_access_key_with_id(
            "user-123",
            name="Custom User",
            limit=DataLimit(bytes=5 * 1024 ** 3)
        )

        # List and manage existing keys
        keys = await client.get_access_keys()
        for key in keys.access_keys:
            print(f"Key: {key.name} ({key.id})")

            # Update key
            await client.rename_access_key(key.id, f"Updated-{key.name}")
            await client.set_access_key_data_limit(key.id, 20 * 1024 ** 3)
```

### Batch Operations

```python
async def batch_operations():
    async with AsyncOutlineClient.create(api_url, cert_sha256) as client:
        # Bulk key creation
        configs = [
            {"name": "Employee-001", "limit": DataLimit(bytes=10 * 1024 ** 3)},
            {"name": "Employee-002", "limit": DataLimit(bytes=10 * 1024 ** 3)},
            {"name": "Contractor-001", "limit": DataLimit(bytes=5 * 1024 ** 3)},
            {"name": "Guest-User", "limit": DataLimit(bytes=1 * 1024 ** 3)},
        ]

        # Create all keys concurrently
        results = await client.batch_create_access_keys(
            configs,
            fail_fast=False,  # Continue on errors
            max_concurrent=3  # Limit concurrent operations
        )

        successful = sum(1 for r in results if not isinstance(r, Exception))
        print(f"Created {successful}/{len(configs)} keys successfully")

        # Batch rename operations
        key_ids = [r.id for r in results if not isinstance(r, Exception)]
        rename_pairs = [(kid, f"Renamed-{i}") for i, kid in enumerate(key_ids)]

        await client.batch_rename_access_keys(rename_pairs, max_concurrent=2)

        # Batch delete
        await client.batch_delete_access_keys(key_ids[:2], fail_fast=False)
```

## 🏥 Health Monitoring & Circuit Breaker

### Health Monitoring

```python
async def monitor_health():
    async with AsyncOutlineClient.create(
            api_url, cert_sha256,
            enable_health_monitoring=True,
            enable_metrics_collection=True
    ) as client:
        # Basic health check
        health = await client.health_check()
        print(f"Healthy: {'✅' if health['healthy'] else '❌'}")

        # Detailed health check
        detailed = await client.health_check(include_detailed_metrics=True)
        for check_name, check_data in detailed['checks'].items():
            status = "✅" if check_data['status'] == 'healthy' else "⚠️"
            print(f"{status} {check_name}: {check_data['message']}")

        # Performance metrics
        metrics = client.get_performance_metrics()
        print(f"Success Rate: {metrics['success_rate']:.1%}")
        print(f"Avg Response: {metrics['avg_response_time']:.3f}s")
        print(f"Total Requests: {metrics['total_requests']}")
```

### Circuit Breaker Protection

```python
async def circuit_breaker_example():
    circuit_config = CircuitConfig(
        failure_threshold=2,
        recovery_timeout=10.0
    )

    async with AsyncOutlineClient(
            api_url, cert_sha256,
            circuit_breaker_enabled=True,
            circuit_config=circuit_config
    ) as client:
        # Monitor circuit breaker status
        status = await client.get_circuit_breaker_status()
        print(f"Circuit State: {status['state']}")
        print(f"Success Rate: {status['metrics']['success_rate']:.1%}")

        # Use circuit protected operations
        try:
            async with client.circuit_protected_operation():
                result = await client.get_server_info()
                print(f"Protected operation successful: {result.name}")
        except Exception as e:
            print(f"Operation failed: {e}")

        # Manual circuit breaker management
        await client.reset_circuit_breaker()  # Reset if needed
```

## 📊 Metrics and Monitoring

### Transfer Metrics

```python
async def monitor_usage():
    async with AsyncOutlineClient.create(api_url, cert_sha256) as client:
        # Enable metrics collection
        await client.set_metrics_status(True)

        # Get transfer metrics
        metrics = await client.get_transfer_metrics()
        total_bytes = sum(metrics.bytes_transferred_by_user_id.values())
        print(f"Total transferred: {total_bytes / 1024 ** 3:.2f} GB")

        # Per-user breakdown
        for user_id, bytes_used in metrics.bytes_transferred_by_user_id.items():
            gb_used = bytes_used / 1024 ** 3
            print(f"User {user_id}: {gb_used:.2f} GB")
```

### Experimental Metrics

```python
async def detailed_metrics():
    async with AsyncOutlineClient.create(api_url, cert_sha256) as client:
        # Get experimental metrics for different time periods
        metrics_24h = await client.get_experimental_metrics("24h")
        metrics_7d = await client.get_experimental_metrics("7d")
        metrics_30d = await client.get_experimental_metrics("30d")

        # Server-level metrics
        server_metrics = metrics_24h.server
        print(f"Server tunnel time: {server_metrics.tunnel_time.seconds}s")
        print(f"Server data: {server_metrics.data_transferred.bytes} bytes")

        # Access key metrics
        for key_metric in metrics_24h.access_keys:
            print(f"Key {key_metric.access_key_id}:")
            print(f"  Tunnel time: {key_metric.tunnel_time.seconds}s")
            print(f"  Data: {key_metric.data_transferred.bytes} bytes")
```

## 🎛️ Advanced Features

### Data Limits Management

```python
async def manage_data_limits():
    async with AsyncOutlineClient.create(api_url, cert_sha256) as client:
        # Set global data limit for all keys
        await client.set_global_data_limit(100 * 1024 ** 3)  # 100 GB
        print("Set global 100GB limit")

        # Create key with individual limit
        key = await client.create_access_key(
            name="VIP User",
            limit=DataLimit(bytes=200 * 1024 ** 3)  # 200 GB
        )

        # Update individual limits
        await client.set_access_key_data_limit(key.id, 150 * 1024 ** 3)
        print("Updated VIP user to 150GB")

        # Remove limits
        await client.remove_access_key_data_limit(key.id)
        await client.remove_global_data_limit()
        print("Removed all limits")
```

### Dynamic Configuration

```python
async def dynamic_config():
    async with AsyncOutlineClient.create(api_url, cert_sha256) as client:
        # Configure logging at runtime
        client.configure_logging("DEBUG", "%(levelname)s: %(message)s")

        # Reconfigure circuit breaker
        client.configure_circuit_breaker(
            failure_threshold=5,
            recovery_timeout=60.0,
            failure_rate_threshold=0.3
        )

        # Test the updated configuration
        server = await client.get_server_info()
        print(f"Server accessible: {server.name}")
```

### JSON Response Format

```python
async def json_responses():
    # Configure client to return raw JSON
    async with AsyncOutlineClient.create(
            api_url, cert_sha256,
            json_format=True
    ) as client:
        # All responses will be JSON dictionaries
        server_data = await client.get_server_info()
        print(f"Server: {server_data['name']}")

        keys_data = await client.get_access_keys()
        for key in keys_data['accessKeys']:
            print(f"Key: {key['id']}")
```

## 🛠️ Error Handling

### Comprehensive Error Handling

```python
from pyoutlineapi import APIError, CircuitOpenError, OutlineError


async def robust_error_handling():
    try:
        async with AsyncOutlineClient.create(
                api_url, cert_sha256,
                retry_attempts=3,
                enable_logging=True
        ) as client:
            # Check health first
            health = await client.health_check()
            if not health['healthy']:
                print("⚠️ Server health issues detected")
                return

            # Perform operations
            server = await client.get_server_info()
            print(f"✅ Connected to {server.name}")

    except CircuitOpenError as e:
        print(f"⚠️ Circuit breaker open, retry after {e.retry_after}s")
    except APIError as e:
        if e.status_code == 404:
            print("❌ Server endpoint not found")
        elif e.status_code == 401:
            print("❌ Authentication failed - check certificate")
        else:
            print(f"❌ API Error {e.status_code}: {e}")
    except OutlineError as e:
        print(f"❌ Outline client error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
```

## 🎯 Best Practices

### 1. Always Use Context Managers

```python
# ✅ Recommended - automatic resource management
async with AsyncOutlineClient.create(api_url, cert) as client:
    result = await client.get_server_info()

# ❌ Avoid - manual resource management
client = AsyncOutlineClient(api_url, cert)
# ... manual session management required
```

### 2. Enable Circuit Breaker for Production

```python
# ✅ Production configuration
async with AsyncOutlineClient.create(
        api_url, cert_sha256,
        circuit_breaker_enabled=True,
        enable_health_monitoring=True,
        enable_logging=True,
        retry_attempts=3
) as client:
    # Operations with automatic protection
    pass
```

### 3. Use Batch Operations for Efficiency

```python
# ✅ Efficient batch creation
configs = [{"name": f"User-{i}"} for i in range(10)]
results = await client.batch_create_access_keys(configs, max_concurrent=3)

# ❌ Inefficient individual operations
for i in range(10):
    await client.create_access_key(name=f"User-{i}")
```

### 4. Monitor Performance

```python
# Regular health and performance monitoring
health = await client.health_check(include_detailed_metrics=True)
if not health['healthy']:
    print("⚠️ Server issues detected")

metrics = client.get_performance_metrics()
if metrics['failure_rate'] > 0.1:  # 10% failure rate
    print("⚠️ High failure rate detected")
```

### 5. Handle Data Limits Properly

```python
from pyoutlineapi.models import DataLimit

# ✅ Correct GB to bytes conversion
data_limit_gb = 5
limit = DataLimit(bytes=data_limit_gb * 1024 ** 3)  # Use 1024^3 for GB

await client.create_access_key(name="User", limit=limit)
```

## 📚 API Reference

### Client Initialization

```python
AsyncOutlineClient(
    api_url: str,  # Outline server API URL
cert_sha256: str,  # Certificate fingerprint
json_format: bool = False,  # Return JSON vs Pydantic models
timeout: int = 30,  # Request timeout (seconds)
retry_attempts: int = 3,  # Number of retry attempts
enable_logging: bool = False,  # Enable debug logging
user_agent: str = "PyOutlineAPI/0.4.0",  # Custom user agent
max_connections: int = 10,  # Connection pool size
rate_limit_delay: float = 0.0,  # Delay between requests
circuit_breaker_enabled: bool = True,  # Enable circuit breaker
circuit_config: CircuitConfig = None,  # Circuit breaker config
enable_health_monitoring: bool = True,  # Health monitoring
enable_metrics_collection: bool = True  # Performance metrics
)
```

### Server Management

| Method                              | Description               | Returns              |
|-------------------------------------|---------------------------|----------------------|
| `get_server_info()`                 | Get server information    | `Server \| JsonDict` |
| `rename_server(name)`               | Rename the server         | `bool`               |
| `set_hostname(hostname)`            | Set hostname for keys     | `bool`               |
| `set_default_port(port)`            | Set default port          | `bool`               |
| `get_server_summary(metrics_since)` | Comprehensive server info | `dict`               |

### Access Key Management

| Method                                    | Description                 | Returns                     |
|-------------------------------------------|-----------------------------|-----------------------------|
| `create_access_key(**kwargs)`             | Create new access key       | `AccessKey \| JsonDict`     |
| `create_access_key_with_id(id, **kwargs)` | Create key with specific ID | `AccessKey \| JsonDict`     |
| `get_access_keys()`                       | List all access keys        | `AccessKeyList \| JsonDict` |
| `get_access_key(key_id)`                  | Get specific access key     | `AccessKey \| JsonDict`     |
| `rename_access_key(key_id, name)`         | Rename access key           | `bool`                      |
| `delete_access_key(key_id)`               | Delete access key           | `bool`                      |

### Batch Operations

| Method                                       | Description             | Returns                        |
|----------------------------------------------|-------------------------|--------------------------------|
| `batch_create_access_keys(configs, ...)`     | Create multiple keys    | `list[AccessKey \| Exception]` |
| `batch_delete_access_keys(key_ids, ...)`     | Delete multiple keys    | `list[bool \| Exception]`      |
| `batch_rename_access_keys(pairs, ...)`       | Rename multiple keys    | `list[bool \| Exception]`      |
| `batch_operations_with_resilience(ops, ...)` | Custom batch operations | `list[Any \| Exception]`       |

### Data Limits

| Method                                     | Description              | Returns |
|--------------------------------------------|--------------------------|---------|
| `set_access_key_data_limit(key_id, bytes)` | Set key data limit       | `bool`  |
| `remove_access_key_data_limit(key_id)`     | Remove key data limit    | `bool`  |
| `set_global_data_limit(bytes)`             | Set global data limit    | `bool`  |
| `remove_global_data_limit()`               | Remove global data limit | `bool`  |

### Metrics & Monitoring

| Method                            | Description            | Returns                             |
|-----------------------------------|------------------------|-------------------------------------|
| `get_metrics_status()`            | Check metrics status   | `MetricsStatusResponse \| JsonDict` |
| `set_metrics_status(enabled)`     | Enable/disable metrics | `bool`                              |
| `get_transfer_metrics()`          | Get transfer metrics   | `ServerMetrics \| JsonDict`         |
| `get_experimental_metrics(since)` | Get detailed metrics   | `ExperimentalMetrics \| JsonDict`   |

### Health & Circuit Breaker

| Method                                   | Description                    | Returns               |
|------------------------------------------|--------------------------------|-----------------------|
| `health_check(include_detailed_metrics)` | Comprehensive health check     | `dict`                |
| `get_performance_metrics()`              | Get performance metrics        | `dict`                |
| `get_circuit_breaker_status()`           | Circuit breaker status         | `dict`                |
| `reset_circuit_breaker()`                | Reset circuit breaker          | `bool`                |
| `force_circuit_open()`                   | Force circuit open             | `bool`                |
| `circuit_protected_operation()`          | Context manager for protection | `AsyncContextManager` |

### Configuration

| Method                                 | Description                   | Returns                 |
|----------------------------------------|-------------------------------|-------------------------|
| `configure_logging(level, format)`     | Configure logging             | `None`                  |
| `configure_circuit_breaker(**kwargs)`  | Update circuit breaker config | `None`                  |
| `parse_response(data, model, as_json)` | Parse API response            | `BaseModel \| JsonDict` |

### Properties

| Property                  | Description              | Type                            |
|---------------------------|--------------------------|---------------------------------|
| `circuit_breaker_enabled` | Circuit breaker status   | `bool`                          |
| `circuit_state`           | Current circuit state    | `str \| None`                   |
| `is_healthy`              | Last health check result | `bool`                          |
| `api_url`                 | API URL (sanitized)      | `str`                           |
| `session`                 | Current HTTP session     | `aiohttp.ClientSession \| None` |

## 🔧 Real-World Examples

### VPN User Management System

```python
class VPNUserManager:
    """Production-ready VPN user management."""

    def __init__(self, api_url: str, cert_sha256: str):
        self.api_url = api_url
        self.cert_sha256 = cert_sha256

    async def create_user(self, username: str, data_limit_gb: int = 10):
        async with AsyncOutlineClient.create(self.api_url, self.cert_sha256) as client:
            key = await client.create_access_key(
                name=username,
                limit=DataLimit(bytes=data_limit_gb * 1024 ** 3)
            )
            return {
                "user_id": key.id,
                "username": username,
                "access_url": key.access_url,
                "data_limit_gb": data_limit_gb
            }

    async def get_user_usage(self, user_id: str) -> float:
        async with AsyncOutlineClient.create(self.api_url, self.cert_sha256) as client:
            metrics = await client.get_transfer_metrics()
            usage_bytes = metrics.bytes_transferred_by_user_id.get(user_id, 0)
            return usage_bytes / (1024 ** 3)  # Convert to GB

    async def bulk_create_users(self, usernames: list[str], data_limit_gb: int = 10):
        async with AsyncOutlineClient.create(self.api_url, self.cert_sha256) as client:
            configs = [
                {"name": username, "limit": DataLimit(bytes=data_limit_gb * 1024 ** 3)}
                for username in usernames
            ]
            return await client.batch_create_access_keys(configs, fail_fast=False)


# Usage
manager = VPNUserManager(api_url, cert_sha256)
user = await manager.create_user("alice@company.com", 25)
usage = await manager.get_user_usage(user["user_id"])
```

### Monitoring Dashboard

```python
async def collect_dashboard_data():
    """Collect comprehensive monitoring data."""
    async with AsyncOutlineClient.create(
            api_url, cert_sha256,
            enable_health_monitoring=True,
            enable_metrics_collection=True
    ) as client:
        dashboard = {}

        # Server status and info
        try:
            server = await client.get_server_info()
            dashboard['server'] = {
                'name': server.name,
                'version': server.version,
                'status': 'online',
                'uptime': time.time() - (server.created_timestamp_ms / 1000)
            }
        except Exception as e:
            dashboard['server'] = {'status': 'offline', 'error': str(e)}

        # Health metrics
        health = await client.health_check(include_detailed_metrics=True)
        dashboard['health'] = health

        # User statistics
        keys = await client.get_access_keys()
        dashboard['users'] = {
            'total': len(keys.access_keys),
            'active': len([k for k in keys.access_keys if k.name])
        }

        # Usage metrics
        try:
            metrics = await client.get_transfer_metrics()
            total_usage = sum(metrics.bytes_transferred_by_user_id.values())
            dashboard['usage'] = {
                'total_gb': total_usage / (1024 ** 3),
                'by_user': {
                    uid: bytes_used / (1024 ** 3)
                    for uid, bytes_used in metrics.bytes_transferred_by_user_id.items()
                }
            }
        except Exception:
            dashboard['usage'] = {'total_gb': 0, 'by_user': {}}

        # Performance metrics
        dashboard['performance'] = client.get_performance_metrics()

        return dashboard
```

## 🔗 Links & Resources

- 📖 **[Documentation](https://orenlab.github.io/pyoutlineapi/)** - Comprehensive API documentation
- 🐛 **[Issue Tracker](https://github.com/orenlab/pyoutlineapi/issues)** - Bug reports and feature requests
- 💬 **[Discussions](https://github.com/orenlab/pyoutlineapi/discussions)** - Community discussions and support
- 📋 **[Changelog](CHANGELOG.md)** - Version history and changes
- 🔒 **[Security Policy](SECURITY.md)** - Security reporting and policies

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- The **Jigsaw team** for creating Outline VPN
- **Contributors** who have helped improve this project
- The **Python async/typing community** for inspiration and best practices

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details on:

- Setting up the development environment
- Running tests and code quality checks
- Submitting pull requests
- Reporting issues

## 🆘 Support

If you encounter any issues or need help:

1. Check the [documentation](https://orenlab.github.io/pyoutlineapi/)
2. Search existing [issues](https://github.com/orenlab/pyoutlineapi/issues)
3. Create a new issue with detailed information
4. Join our [discussions](https://github.com/orenlab/pyoutlineapi/discussions) for community support

---

**Made with ❤️ by the PyOutlineAPI team**