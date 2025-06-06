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
            cert_sha256="your-certificate-fingerprint"
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
    retry_attempts=3  # Number of retry attempts for failed requests
)
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

        print("Server configured successfully")
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
        # Get detailed server metrics
        metrics = await client.get_experimental_metrics()

        # Server-level metrics
        server_metrics = metrics.server
        print(f"Server tunnel time: {server_metrics.tunnel_time.seconds}s")
        print(f"Server data transferred: {server_metrics.data_transferred.bytes} bytes")

        # Access key metrics
        for key_id, key_metrics in metrics.access_keys.items():
            print(f"Key {key_id}:")
            print(f"  Tunnel time: {key_metrics.tunnel_time.seconds}s")
            print(f"  Data transferred: {key_metrics.data_transferred.bytes} bytes")

        # Get metrics for specific time range
        recent_metrics = await client.get_experimental_metrics(since="2024-01-01T00:00:00Z")
```

### Error Handling

```python
from pyoutlineapi import AsyncOutlineClient, APIError, OutlineError


async def robust_client():
    try:
        async with AsyncOutlineClient(
                api_url="https://your-server:port/api",
                cert_sha256="your-cert-fingerprint",
                retry_attempts=5  # Increase retry attempts
        ) as client:
            # Your operations here
            server = await client.get_server_info()

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

    finally:
        # Always clean up
        await client.__aexit__(None, None, None)
```

### Batch Operations

```python
async def batch_operations():
    async with AsyncOutlineClient(...) as client:
        # Create multiple keys concurrently
        tasks = [
            client.create_access_key(name=f"User {i}")
            for i in range(1, 6)
        ]
        keys = await asyncio.gather(*tasks)

        print(f"Created {len(keys)} keys")

        # Set data limits for all keys
        limit_tasks = [
            client.set_access_key_data_limit(key.id, 5 * 1024 ** 3)
            for key in keys
        ]
        await asyncio.gather(*limit_tasks)

        print("Applied data limits to all keys")
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
from pyoutlineapi import AccessKey


async def get_user_keys(client: AsyncOutlineClient) -> List[AccessKey]:
    keys = await client.get_access_keys()
    return keys.access_keys
```

### 4. Configure Timeouts Appropriately

```python
# For slow networks or large operations
client = AsyncOutlineClient(
    ...,
    timeout=60,  # 60 second timeout
    retry_attempts=5
)
```

## API Reference

### Client Methods

#### Server Management

- `get_server_info() -> Server | JsonDict`
- `rename_server(name: str) -> bool`
- `set_hostname(hostname: str) -> bool`
- `set_default_port(port: int) -> bool`

#### Access Key Management

- `create_access_key(**kwargs) -> AccessKey | JsonDict`
- `create_access_key_with_id(key_id: str, **kwargs) -> AccessKey | JsonDict`
- `get_access_keys() -> AccessKeyList | JsonDict`
- `get_access_key(key_id: str) -> AccessKey | JsonDict`
- `rename_access_key(key_id: str, name: str) -> bool`
- `delete_access_key(key_id: str) -> bool`

#### Data Limits

- `set_access_key_data_limit(key_id: str, bytes_limit: int) -> bool`
- `remove_access_key_data_limit(key_id: str) -> bool`
- `set_global_data_limit(bytes_limit: int) -> bool`
- `remove_global_data_limit() -> bool`

#### Metrics

- `get_metrics_status() -> MetricsStatusResponse | JsonDict`
- `set_metrics_status(enabled: bool) -> bool`
- `get_transfer_metrics() -> ServerMetrics | JsonDict`
- `get_experimental_metrics(since: str = None) -> ExperimentalMetrics | JsonDict`

## Requirements

- Python 3.10+
- aiohttp
- pydantic
- A running Outline VPN Server

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for a detailed history of changes.

## Support

- 📖 [Documentation](https://github.com/orenlab/pyoutlineapi)
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