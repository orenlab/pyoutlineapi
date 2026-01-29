# PyOutlineAPI

**Enterprise-grade async Python client for Outline VPN Server Management API**

[![tests](https://github.com/orenlab/pyoutlineapi/actions/workflows/python_tests.yml/badge.svg)](https://github.com/orenlab/pyoutlineapi/actions/workflows/python_tests.yml)
[![codecov](https://codecov.io/gh/orenlab/pyoutlineapi/branch/main/graph/badge.svg?token=D0MPKCKFJQ)](https://codecov.io/gh/orenlab/pyoutlineapi)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](https://mypy-lang.org/)
[![Documentation](https://img.shields.io/badge/docs-pdoc-blue.svg)](https://orenlab.github.io/pyoutlineapi/)
[![Security Rating](https://sonarcloud.io/api/project_badges/measure?project=orenlab_pyoutlineapi&metric=security_rating)](https://sonarcloud.io/summary/new_code?id=orenlab_pyoutlineapi)
[![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=orenlab_pyoutlineapi&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=orenlab_pyoutlineapi)
[![Vulnerabilities](https://sonarcloud.io/api/project_badges/measure?project=orenlab_pyoutlineapi&metric=vulnerabilities)](https://sonarcloud.io/summary/new_code?id=orenlab_pyoutlineapi)

![PyPI - Downloads](https://img.shields.io/pypi/dm/pyoutlineapi)
![PyPI - Version](https://img.shields.io/pypi/v/pyoutlineapi)
![Python Version](https://img.shields.io/pypi/pyversions/pyoutlineapi)
![License](https://img.shields.io/pypi/l/pyoutlineapi)

---

## Overview

PyOutlineAPI is a modern, **production-ready** Python library for managing [Outline VPN](https://getoutline.org/)
servers.
It is async-first, type-safe, and designed for reliable operation in production.

Highlights:

- Async-first client built on aiohttp
- Certificate pinning + sensitive data protection
- Circuit breaker, health monitoring, retries with backoff
- Typed models (Pydantic v2) + rich validation
- Batch operations and rate limiting

---

## Installation

**Requirements:** Python 3.10+

Using `pip`:

```bash
pip install pyoutlineapi
```

Using `uv` (recommended):

```bash
uv add pyoutlineapi
```

**Optional dependencies:**

```bash
# Metrics collection support
pip install pyoutlineapi[metrics]

# Development tools
pip install pyoutlineapi[dev]
```

---

## Quick Start

### 1) Setup configuration

```bash
# Generate .env template
python -c "from pyoutlineapi import quick_setup; quick_setup()"

# Edit .env.example → .env
OUTLINE_API_URL=https://your-server.com:12345/your-secret-path
OUTLINE_CERT_SHA256=your-64-character-sha256-fingerprint
```

### 2) Minimal usage

```python
from pyoutlineapi import AsyncOutlineClient
import asyncio


async def main():
    async with AsyncOutlineClient.from_env() as client:
        server = await client.get_server_info()
        print(f"Server: {server.name} (v{server.version})")

        key = await client.create_access_key(name="Alice")
        print(f"Access URL: {key.access_url}")

        keys = await client.get_access_keys()
        print(f"Total keys: {keys.count}")


asyncio.run(main())
```

---

## Documentation

Detailed examples and guides are in `docs/guides/`. Start with the index:

- [Guides index](docs/guides/README.md) (full list)
- [Access keys](docs/guides/access-keys.md)
- [Server management](docs/guides/server-management.md)
- [Metrics](docs/guides/metrics.md)
- [Enterprise features](docs/guides/enterprise-features.md)
- [Configuration](docs/guides/configuration.md)
- [Error handling](docs/guides/error-handling.md)
- [Best practices](docs/guides/best-practices.md)

---

## License

MIT. See `LICENSE`.
