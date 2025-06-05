# PyOutlineAPI

A modern, async-first Python client for the [Outline VPN Server API](https://github.com/Jigsaw-Code/outline-server) with
full support for the latest schema and strict data validation using Pydantic.

[![tests](https://github.com/orenlab/pyoutlineapi/actions/workflows/python_tests.yml/badge.svg)](https://github.com/orenlab/pyoutlineapi/actions/workflows/python_tests.yml)
[![codecov](https://codecov.io/gh/orenlab/pyoutlineapi/branch/main/graph/badge.svg?token=D0MPKCKFJQ)](https://codecov.io/gh/orenlab/pyoutlineapi)
[![Security Rating](https://sonarcloud.io/api/project_badges/measure?project=orenlab_pyoutlineapi&metric=security_rating)](https://sonarcloud.io/summary/new_code?id=orenlab_pyoutlineapi)
[![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=orenlab_pyoutlineapi&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=orenlab_pyoutlineapi)
[![Vulnerabilities](https://sonarcloud.io/api/project_badges/measure?project=orenlab_pyoutlineapi&metric=vulnerabilities)](https://sonarcloud.io/summary/new_code?id=orenlab_pyoutlineapi)
![PyPI - Downloads](https://img.shields.io/pypi/dm/pyoutlineapi)

---

## Features

- ⚡ **Async-first** design for high-concurrency applications
- ✅ **Strict typing** and validation via Pydantic models
- 🔒 **Certificate fingerprint verification** for secure TLS connections
- 📡 **Up-to-date schema support** for all Outline VPN Server API endpoints
- 📊 **Traffic metrics** and server usage monitoring
- 🧰 **Advanced key management** with data limits, naming, and custom ports
- 🔁 **Flexible response options**: return JSON or typed models
- 🤝 **Async context manager** support for clean client lifecycle
- 🚫 **Robust error handling** with meaningful exception types

---

## Installation

Install from PyPI:

```bash
pip install pyoutlineapi
```

Or with Poetry:

```bash
poetry add pyoutlineapi
```

---

## Quick Example

```python
import asyncio
from pyoutlineapi import AsyncOutlineClient


async def main():
    async with AsyncOutlineClient(
            api_url="https://your-outline-server:port/api",
            cert_sha256="your-certificate-fingerprint"
    ) as client:
        server = await client.get_server_info()
        print(f"Connected to {server.name} (v{server.version})")

        key = await client.create_access_key(name="Test User")
        print(f"Created access key: {key.access_url}")


if __name__ == "__main__":
    asyncio.run(main())
```

---

## Client Initialization

```python
from pyoutlineapi import AsyncOutlineClient

client = AsyncOutlineClient(
    api_url="https://your-outline-server:port/api",
    cert_sha256="your-certificate-fingerprint",
    json_format=False,  # If True, returns raw JSON instead of models
    timeout=20.0  # Optional timeout (in seconds)
)
```

---

## Access Key Management

```python
from pyoutlineapi import AsyncOutlineClient, DataLimit


async def manage_keys():
    async with AsyncOutlineClient(...) as client:
        key = await client.create_access_key(
            name="Limited User",
            port=8388,
            limit=DataLimit(bytes=5 * 1024 ** 3)
        )
        print(f"Created key: {key.access_url}")

        keys = await client.get_access_keys()
        for k in keys.access_keys:
            print(f"{k.id}: {k.name or 'Unnamed'}")

        await client.rename_access_key(1, "Updated Name")
        await client.set_access_key_data_limit(1, 10 * 1024 ** 3)
        await client.delete_access_key(1)
```

---

## Server Configuration

```python
async def configure_server():
    async with AsyncOutlineClient(...) as client:
        await client.rename_server("My VPN Server")
        await client.set_hostname("vpn.example.com")
        await client.set_default_port(8388)

        hostname = await client.get_hostname()
        port = await client.get_default_port()
        print(f"Hostname: {hostname}, Default port: {port}")
```

---

## Metrics & Usage Monitoring

```python
from pyoutlineapi import MetricsPeriod


async def monitor_usage():
    async with AsyncOutlineClient(...) as client:
        await client.set_metrics_status(True)

        metrics = await client.get_transfer_metrics(MetricsPeriod.MONTHLY)
        for user_id, bytes_used in metrics.bytes_transferred_by_user_id.items():
            print(f"{user_id}: {bytes_used / 1024 ** 3:.2f} GB")

        enabled = await client.get_metrics_status()
        print(f"Metrics enabled: {enabled}")
```

---

## Error Handling

```python
from pyoutlineapi import AsyncOutlineClient, OutlineError, APIError


async def safe_call():
    try:
        async with AsyncOutlineClient(...) as client:
            await client.get_server_info()
    except APIError as e:
        print(f"API error: {e.status_code} - {e.message}")
    except OutlineError as e:
        print(f"Unexpected Outline error: {e}")
```

---

## License

[MIT](./LICENSE)

---

## Links

- 📘 [Official Outline Server API Schema](https://github.com/Jigsaw-Code/outline-server/blob/master/src/shadowbox/server/api.yml)
