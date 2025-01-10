# PyOutlineAPI

A modern, async-first Python client for the Outline VPN Server API with comprehensive data validation through Pydantic
models.

[![Security Rating](https://sonarcloud.io/api/project_badges/measure?project=orenlab_pyoutlineapi&metric=security_rating)](https://sonarcloud.io/summary/new_code?id=orenlab_pyoutlineapi)
[![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=orenlab_pyoutlineapi&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=orenlab_pyoutlineapi)
[![Vulnerabilities](https://sonarcloud.io/api/project_badges/measure?project=orenlab_pyoutlineapi&metric=vulnerabilities)](https://sonarcloud.io/summary/new_code?id=orenlab_pyoutlineapi)
[![tests](https://github.com/orenlab/pyoutlineapi/actions/workflows/python_tests.yml/badge.svg)](https://github.com/orenlab/pyoutlineapi/actions/workflows/python_tests.yml)
[![codecov](https://codecov.io/gh/orenlab/pyoutlineapi/branch/main/graph/badge.svg?token=D0MPKCKFJQ)](https://codecov.io/gh/orenlab/pyoutlineapi)
![PyPI - Downloads](https://img.shields.io/pypi/dm/pyoutlineapi)

## Features

- **Async-First Design**: Built with modern async/await patterns for optimal performance
- **Type Safety**: Full typing support with runtime validation via Pydantic
- **Comprehensive API Coverage**: Support for all Outline VPN Server
  API [endpoints](https://github.com/Jigsaw-Code/outline-server/blob/master/src/shadowbox/server/api.yml)
- **Error Handling**: Robust error handling with custom exception types
- **SSL/TLS Security**: Certificate fingerprint verification for enhanced security
- **Flexible Response Format**: Choose between Pydantic models or JSON responses
- **Data Transfer Metrics**: Built-in support for monitoring server and key usage
- **Context Manager Support**: Clean resource management with async context managers

## Installation

Install via pip:

```bash
pip install pyoutlineapi
```

Or using Poetry:

```bash
poetry add pyoutlineapi
```

## Quick Start

Here's a simple example to get you started:

```python
import asyncio
from pyoutlineapi import AsyncOutlineClient


async def main():
    async with AsyncOutlineClient(
            api_url="https://your-outline-server:port/api",
            cert_sha256="your-certificate-fingerprint"
    ) as client:
        # Get server info
        server = await client.get_server_info()
        print(f"Connected to {server.name} running version {server.version}")

        # Create a new access key
        key = await client.create_access_key(name="TestUser")
        print(f"Created key: {key.access_url}")


if __name__ == "__main__":
    asyncio.run(main())
```

## Detailed Usage

### Client Configuration

The client can be configured with several options:

```python
from pyoutlineapi import AsyncOutlineClient

client = AsyncOutlineClient(
    api_url="https://your-outline-server:port/api",
    cert_sha256="your-certificate-fingerprint",
    json_format=True,  # Return JSON instead of Pydantic models
    timeout=30.0  # Request timeout in seconds
)
```

### Managing Access Keys

Create and manage access keys:

```python

from pyoutlineapi import AsyncOutlineClient, DataLimit


async def manage_keys():
    async with AsyncOutlineClient(...) as client:
        # Create a key with data limit
        key = await client.create_access_key(
            name="Limited User",
            port=8388,
            limit=DataLimit(bytes=5 * 1024 ** 3)  # 5 GB limit
        )

        # List all keys
        keys = await client.get_access_keys()
        for key in keys.access_keys:
            print(f"Key {key.id}: {key.name or 'unnamed'}")

        # Modify a key
        await client.rename_access_key(1, "New Name")
        await client.set_access_key_data_limit(1, 10 * 1024 ** 3)  # 10 GB

        # Delete a key
        await client.delete_access_key(1)
```

### Server Management

Configure server settings:

```python

from pyoutlineapi import AsyncOutlineClient


async def configure_server():
    async with AsyncOutlineClient(...) as client:
        # Update server name
        await client.rename_server("My VPN Server")

        # Set hostname for access keys
        await client.set_hostname("vpn.example.com")

        # Configure default port for new keys
        await client.set_default_port(8388)
```

### Metrics Collection

Monitor server usage:

```python
from pyoutlineapi import AsyncOutlineClient, MetricsPeriod


async def get_metrics():
    async with AsyncOutlineClient(...) as client:
        # Enable metrics collection
        await client.set_metrics_status(True)

        # Get transfer metrics
        metrics = await client.get_transfer_metrics(MetricsPeriod.MONTHLY)
        for user_id, bytes_transferred in metrics.bytes_transferred_by_user_id.items():
            print(f"User {user_id}: {bytes_transferred / 1024 ** 3:.2f} GB")
```

## Error Handling

The client provides custom exceptions for different error scenarios:

```python
from pyoutlineapi import AsyncOutlineClient, OutlineError, APIError


async def handle_errors():
    try:
        async with AsyncOutlineClient(...) as client:
            await client.get_server_info()
    except APIError as e:
        print(f"API error: {e}")
    except OutlineError as e:
        print(f"Client error: {e}")
```

## Contributing

We welcome contributions! Please see our [Contributing Guidelines](CONTRIBUTING.md) for details on how to submit pull
requests, report issues, and contribute to the project.

## Security

If you discover any security-related issues, please email `pytelemonbot@mail.ru` instead of using the issue tracker.

## License

PyOutlineAPI is open-sourced software licensed under the [MIT license](LICENSE).