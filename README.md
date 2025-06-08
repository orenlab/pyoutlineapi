# PyOutlineAPI

A modern, async-first Python client for the [Outline VPN Server API](https://github.com/Jigsaw-Code/outline-server) with
full support for the latest schema and strict data validation using Pydantic.

[![tests](https://github.com/orenlab/pyoutlineapi/actions/workflows/python_tests.yml/badge.svg)](https://github.com/orenlab/pyoutlineapi/actions/workflows/python_tests.yml)
[![codecov](https://codecov.io/gh/orenlab/pyoutlineapi/branch/main/graph/badge.svg?token=D0MPKCKFJQ)](https://codecov.io/gh/orenlab/pyoutlineapi)
[![Security Rating](https://sonarcloud.io/api/project_badges/measure?project=orenlab_pyoutlineapi&metric=security_rating)](https://sonarcloud.io/summary/new_code?id=orenlab_pyoutlineapi)
[![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=orenlab_pyoutlineapi&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=orenlab_pyoutlineapi)
[![Vulnerabilities](https://sonarcloud.io/api/project_badges/measure?project=orenlab_pyoutlineapi&metric=vulnerabilities)](https://sonarcloud.io/summary/new_code?id=orenlab_pyoutlineapi)
![PyPI - Downloads](https://img.shields.io/pypi/dm/pyoutlineapi)
![PyPI - Version](https://img.shields.io/pypi/v/pyoutlineapi)
![Python Version](https://img.shields.io/pypi/pyversions/pyoutlineapi)

## Features

- ⚡ **Async-first design** with full asyncio support and connection pooling
- 🔒 **Enterprise-grade security** with TLS certificate fingerprint verification
- ✅ **Type-safe** with comprehensive Pydantic models and static typing
- 🔄 **Smart retry logic** with exponential backoff for resilient connections
- 📊 **Complete metrics support** including experimental server metrics
- 🎯 **Advanced key management** with custom IDs, data limits, and flexible configuration
- 🌐 **Flexible response formats** - return JSON dict or typed Pydantic models
- 🛡️ **Robust error handling** with detailed exception hierarchy
- 📚 **Production-ready** with comprehensive logging and debugging support
- 🚀 **Batch operations** for creating multiple access keys efficiently
- 🏥 **Health checks** with automatic server status monitoring
- 🔧 **Advanced configuration** with rate limiting and connection management

## Installation

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

## Quick Start

```python
import asyncio
from pyoutlineapi import AsyncOutlineClient, DataLimit


async def main():
    # Initialize client with context manager (recommended)
    async with AsyncOutlineClient(
            api_url="https://your-outline-server:port/secret-path",
            cert_sha256="your-certificate-fingerprint",
            enable_logging=True  # Enable debug logging
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

        # List all keys
        keys = await client.get_access_keys()
        print(f"Total keys: {len(keys.access_keys)}")

        # Get comprehensive server summary
        summary = await client.get_server_summary()
        print(f"Server healthy: {summary['healthy']}")
        print(f"Access keys count: {summary['access_keys_count']}")


if __name__ == "__main__":
    asyncio.run(main())
```

## Configuration

### Client Options

```python
from pyoutlineapi import AsyncOutlineClient

client = AsyncOutlineClient(
    api_url="https://your-server:port/path",
    cert_sha256="certificate-fingerprint",
    json_format=False,  # Return Pydantic models (default) or raw JSON
    timeout=30,  # Request timeout in seconds
    retry_attempts=3,  # Number of retry attempts for failed requests
    enable_logging=True,  # Enable debug logging
    user_agent="MyApp/1.0",  # Custom user agent
    max_connections=10,  # Maximum connections in pool
    rate_limit_delay=0.1  # Minimum delay between requests (seconds)
)
```

### Factory Method

```python
# Use factory method for one-off operations
async def quick_operation():
    async with AsyncOutlineClient.create(
            "https://your-server:port/path",
            "certificate-fingerprint",
            enable_logging=True
    ) as client:
        server = await client.get_server_info()
        return server
```

## Usage Guide

### Server Management

```python
async def manage_server():
    async with AsyncOutlineClient(...) as client:
        # Get server information
        server = await client.get_server_info()
        print(f"Server: {server.name}, Version: {server.version}")

        # Configure server
        await client.rename_server("My VPN Server")
        await client.set_hostname("vpn.example.com")
        await client.set_default_port(8388)

        # Get comprehensive server summary
        summary = await client.get_server_summary()
        print(f"Server healthy: {summary['healthy']}")
        print(f"Keys count: {summary['access_keys_count']}")

        if summary.get('metrics'):
            total_bytes = sum(summary['metrics']['bytes_transferred_by_user_id'].values())
            print(f"Total data: {total_bytes / 1024 ** 3:.2f} GB")

        print("Server configured successfully")
```

### Health Monitoring

```python
async def monitor_server_health():
    async with AsyncOutlineClient(...) as client:
        # Manual health check
        is_healthy = await client.health_check()
        print(f"Server is healthy: {is_healthy}")

        # Force health check (ignore cache)
        is_healthy = await client.health_check(force=True)

        # Check last health status
        print(f"Last known health status: {client.is_healthy}")
```

### Access Key Management

#### Basic Key Operations

```python
async def basic_key_operations():
    async with AsyncOutlineClient(...) as client:
        # Create a simple key
        key = await client.create_access_key(name="John Doe")
        print(f"Access URL: {key.access_url}")

        # Get specific key
        retrieved_key = await client.get_access_key(key.id)

        # List all keys
        all_keys = await client.get_access_keys()
        for k in all_keys.access_keys:
            print(f"Key {k.id}: {k.name or 'Unnamed'}")

        # Rename key
        await client.rename_access_key(key.id, "John Smith")

        # Delete key
        await client.delete_access_key(key.id)
```

#### Advanced Key Configuration

```python
async def advanced_key_config():
    async with AsyncOutlineClient(...) as client:
        # Create key with custom configuration
        key = await client.create_access_key(
            name="Premium User",
            port=9999,
            method="chacha20-ietf-poly1305",
            password="custom-password",
            limit=DataLimit(bytes=10 * 1024 ** 3)  # 10 GB
        )

        # Create key with specific ID
        custom_key = await client.create_access_key_with_id(
            "custom-user-id",
            name="Custom ID User",
            limit=DataLimit(bytes=1024 ** 3)  # 1 GB
        )

        # Manage data limits
        await client.set_access_key_data_limit(key.id, 20 * 1024 ** 3)  # 20 GB
        await client.remove_access_key_data_limit(key.id)  # Remove limit
```

### Batch Operations

```python
async def batch_key_creation():
    async with AsyncOutlineClient(...) as client:
        # Prepare configurations for multiple keys
        configs = [
            {"name": "User1", "limit": DataLimit(bytes=1024 ** 3)},  # 1 GB
            {"name": "User2", "port": 8388},
            {"name": "User3", "limit": DataLimit(bytes=5 * 1024 ** 3)},  # 5 GB
            {"name": "User4", "method": "chacha20-ietf-poly1305"},
        ]

        # Create all keys in batch (fail on first error)
        results = await client.batch_create_access_keys(configs, fail_fast=True)
        print(f"Created {len(results)} keys successfully")

        # Create keys with error handling (continue on errors)
        results = await client.batch_create_access_keys(configs, fail_fast=False)

        successful_keys = []
        failed_keys = []

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                failed_keys.append((i, result))
                print(f"Failed to create key {i}: {result}")
            else:
                successful_keys.append(result)
                print(f"Created key: {result.name}")

        print(f"Successfully created: {len(successful_keys)} keys")
        print(f"Failed: {len(failed_keys)} keys")
```

### Global Data Limits

```python
async def manage_global_limits():
    async with AsyncOutlineClient(...) as client:
        # Set global data limit for all keys
        await client.set_global_data_limit(100 * 1024 ** 3)  # 100 GB total

        # Remove global limit
        await client.remove_global_data_limit()
```

### Metrics and Monitoring

#### Transfer Metrics

```python
async def monitor_usage():
    async with AsyncOutlineClient(...) as client:
        # Enable metrics collection
        await client.set_metrics_status(True)

        # Check if metrics are enabled
        status = await client.get_metrics_status()
        print(f"Metrics enabled: {status.metrics_enabled}")

        # Get transfer metrics
        metrics = await client.get_transfer_metrics()
        total_bytes = sum(metrics.bytes_transferred_by_user_id.values())
        print(f"Total data transferred: {total_bytes / 1024 ** 3:.2f} GB")

        # Per-user breakdown
        for user_id, bytes_used in metrics.bytes_transferred_by_user_id.items():
            gb_used = bytes_used / 1024 ** 3
            print(f"User {user_id}: {gb_used:.2f} GB")
```

#### Experimental Metrics

```python
async def detailed_metrics():
    async with AsyncOutlineClient(...) as client:
        # Get detailed server metrics for the last 24 hours
        metrics = await client.get_experimental_metrics("24h")

        # Server-level metrics
        server_metrics = metrics.server
        print(f"Server tunnel time: {server_metrics.tunnel_time.seconds}s")
        print(f"Server data transferred: {server_metrics.data_transferred.bytes} bytes")

        # Access key metrics
        for key_id, key_metrics in metrics.access_keys.items():
            print(f"Key {key_id}:")
            print(f"  Tunnel time: {key_metrics.tunnel_time.seconds}s")
            print(f"  Data transferred: {key_metrics.data_transferred.bytes} bytes")

        # Get metrics for the last 7 days
        weekly_metrics = await client.get_experimental_metrics("7d")

        # Get metrics for the last 30 days
        monthly_metrics = await client.get_experimental_metrics("30d")

        # Get metrics since a specific timestamp
        custom_metrics = await client.get_experimental_metrics("2024-01-01T00:00:00Z")
```

### Advanced Configuration

#### Logging Configuration

```python
async def configure_logging():
    async with AsyncOutlineClient(...) as client:
        # Configure logging level and format
        client.configure_logging(
            level="DEBUG",
            format_string="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

        # Now all API calls will be logged with debug information
        server = await client.get_server_info()
```

#### Rate Limiting

```python
async def rate_limited_client():
    # Client with rate limiting
    async with AsyncOutlineClient(
            api_url="https://your-server:port/path",
            cert_sha256="your-cert-fingerprint",
            rate_limit_delay=0.5  # 500ms delay between requests
    ) as client:
        # Requests will be automatically rate-limited
        for i in range(10):
            await client.get_server_info()  # Each request waits 500ms
```

### Error Handling

```python
from pyoutlineapi import AsyncOutlineClient, APIError, OutlineError


async def robust_client():
    try:
        async with AsyncOutlineClient(
                api_url="https://your-server:port/api",
                cert_sha256="your-cert-fingerprint",
                retry_attempts=5,  # Increase retry attempts
                enable_logging=True  # Enable logging for debugging
        ) as client:
            # Check server health first
            if not await client.health_check():
                print("Server is not healthy!")
                return

            # Your operations here
            server = await client.get_server_info()
            print(f"Connected to {server.name}")

    except APIError as e:
        # Handle API-specific errors (4xx, 5xx responses)
        print(f"API Error {e.status_code}: {e.message}")
        if e.status_code == 404:
            print("Resource not found")
        elif e.status_code >= 500:
            print("Server error - try again later")

    except OutlineError as e:
        # Handle other Outline-specific errors
        print(f"Outline Error: {e}")

    except Exception as e:
        # Handle unexpected errors
        print(f"Unexpected error: {e}")
```

### Working with JSON Responses

```python
async def json_responses():
    # Configure client to return raw JSON instead of Pydantic models
    async with AsyncOutlineClient(
            api_url="https://your-server:port/api",
            cert_sha256="your-cert-fingerprint",
            json_format=True  # Return JSON dictionaries
    ) as client:
        server_data = await client.get_server_info()
        print(f"Server name: {server_data['name']}")  # Access as dict

        keys_data = await client.get_access_keys()
        for key in keys_data['accessKeys']:
            print(f"Key ID: {key['id']}")

        # Summary also returns JSON format
        summary = await client.get_server_summary()
        print(f"Healthy: {summary['healthy']}")
```

## Advanced Usage

### Connection Management

```python
async def manual_session_management():
    # Manual session management (not recommended for most use cases)
    client = AsyncOutlineClient(
        api_url="https://your-server:port/api",
        cert_sha256="your-cert-fingerprint"
    )

    try:
        # Manually enter context
        await client.__aenter__()

        # Use client
        server = await client.get_server_info()
        print(f"Connected to {server.name}")

        # Check connection status
        print(f"Session active: {client.session and not client.session.closed}")
        print(f"API URL: {client.api_url}")

    finally:
        # Always clean up
        await client.__aexit__(None, None, None)
```

### Concurrent Operations

```python
async def concurrent_operations():
    async with AsyncOutlineClient(...) as client:
        # Create multiple keys concurrently
        tasks = [
            client.create_access_key(name=f"User {i}")
            for i in range(1, 6)
        ]
        keys = await asyncio.gather(*tasks)

        print(f"Created {len(keys)} keys")

        # Set data limits for all keys concurrently
        limit_tasks = [
            client.set_access_key_data_limit(key.id, 5 * 1024 ** 3)
            for key in keys
        ]
        await asyncio.gather(*limit_tasks)

        print("Applied data limits to all keys")
```

### Monitoring and Debugging

```python
async def debug_session():
    async with AsyncOutlineClient(
            api_url="https://your-server:port/api",
            cert_sha256="your-cert-fingerprint",
            enable_logging=True,
            timeout=60,  # Longer timeout for debugging
            retry_attempts=1  # Disable retries for debugging
    ) as client:
        # Client provides useful debugging information
        print(f"Client: {client}")  # Shows connection status
        print(f"API URL: {client.api_url}")
        print(f"Is healthy: {client.is_healthy}")

        # All method calls are logged when logging is enabled
        server = await client.get_server_info()

        # Get detailed server summary for monitoring
        summary = await client.get_server_summary()
        if not summary['healthy']:
            print(f"Server error: {summary.get('error')}")
```

## Best Practices

### 1. Always Use Context Managers

```python
# ✅ Recommended
async with AsyncOutlineClient(...) as client:
    await client.get_server_info()

# ❌ Not recommended
client = AsyncOutlineClient(...)
await client.get_server_info()  # Session not initialized
```

### 2. Handle Errors Appropriately

```python
# ✅ Specific error handling
try:
    key = await client.get_access_key("nonexistent")
except APIError as e:
    if e.status_code == 404:
        print("Key not found")
    else:
        raise  # Re-raise unexpected API errors
```

### 3. Use Type Hints

```python
from typing import List
from pyoutlineapi import AccessKey, AsyncOutlineClient


async def get_user_keys(client: AsyncOutlineClient) -> List[AccessKey]:
    keys = await client.get_access_keys()
    return keys.access_keys
```

### 4. Configure Timeouts and Retries Appropriately

```python
# For slow networks or large operations
client = AsyncOutlineClient(
    ...,
    timeout=60,  # 60 second timeout
    retry_attempts=5,  # More retry attempts
    rate_limit_delay=0.1  # Small delay between requests
)
```

### 5. Use Batch Operations for Multiple Keys

```python
# ✅ Efficient batch creation
configs = [{"name": f"User{i}"} for i in range(10)]
keys = await client.batch_create_access_keys(configs)

# ❌ Inefficient individual creation
keys = []
for i in range(10):
    key = await client.create_access_key(name=f"User{i}")
    keys.append(key)
```

### 6. Monitor Server Health

```python
# ✅ Check health before operations
async with AsyncOutlineClient(...) as client:
    if not await client.health_check():
        print("Server is not responding")
        return

    # Proceed with operations
    await client.get_server_info()
```

## API Reference

### Client Methods

#### Server Management

- `get_server_info() -> Server | JsonDict`
- `rename_server(name: str) -> bool`
- `set_hostname(hostname: str) -> bool`
- `set_default_port(port: int) -> bool`
- `get_server_summary() -> dict[str, Any]` - Comprehensive server information

#### Access Key Management

- `create_access_key(**kwargs) -> AccessKey | JsonDict`
- `create_access_key_with_id(key_id: str, **kwargs) -> AccessKey | JsonDict`
- `get_access_keys() -> AccessKeyList | JsonDict`
- `get_access_key(key_id: str) -> AccessKey | JsonDict`
- `rename_access_key(key_id: str, name: str) -> bool`
- `delete_access_key(key_id: str) -> bool`

#### Batch Operations

- `batch_create_access_keys(keys_config: list[dict], fail_fast: bool = True) -> list[AccessKey | Exception]`

#### Data Limits

- `set_access_key_data_limit(key_id: str, bytes_limit: int) -> bool`
- `remove_access_key_data_limit(key_id: str) -> bool`
- `set_global_data_limit(bytes_limit: int) -> bool`
- `remove_global_data_limit() -> bool`

#### Metrics

- `get_metrics_status() -> MetricsStatusResponse | JsonDict`
- `set_metrics_status(enabled: bool) -> bool`
- `get_transfer_metrics() -> ServerMetrics | JsonDict`
- `get_experimental_metrics(since: str) -> ExperimentalMetrics | JsonDict`

#### Health and Monitoring

- `health_check(force: bool = False) -> bool` - Check server health
- `configure_logging(level: str = "INFO", format_string: str = None) -> None`

#### Properties

- `is_healthy: bool` - Last known health status
- `session: Optional[aiohttp.ClientSession]` - Current session
- `api_url: str` - API URL (without sensitive parts)

## Requirements

- Python 3.10+
- aiohttp
- pydantic
- A running Outline VPN Server

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Changelog

See [CHANGELOG.md](https://github.com/orenlab/pyoutlineapi/blob/main/CHANGELOG.md) for a detailed history of changes.

## Support

- 📖 [Documentation](https://orenlab.github.io/pyoutlineapi/)
- 🐛 [Issue Tracker](https://github.com/orenlab/pyoutlineapi/issues)
- 💬 [Discussions](https://github.com/orenlab/pyoutlineapi/discussions)

## Related Projects

- [Outline Server](https://github.com/Jigsaw-Code/outline-server) - The Outline VPN Server
- [Outline Client](https://github.com/Jigsaw-Code/outline-client) - Official Outline VPN clients

## Acknowledgments

- The Jigsaw team for creating Outline VPN
- All contributors to this project
- The Python async/typing community for inspiration

---

**Made with ❤️ by the PyOutlineAPI team**