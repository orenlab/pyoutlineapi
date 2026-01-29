# Configuration

Configuration options, environment variables, and safety controls.

## Setup

```python
from pyoutlineapi import AsyncOutlineClient

async with AsyncOutlineClient.from_env() as client:
    pass
```

## Environment variables

```bash
# Required
OUTLINE_API_URL=https://server.com:12345/secret
OUTLINE_CERT_SHA256=your-certificate-fingerprint

# Client settings
OUTLINE_TIMEOUT=10
OUTLINE_RETRY_ATTEMPTS=2
OUTLINE_MAX_CONNECTIONS=10
OUTLINE_RATE_LIMIT=100
OUTLINE_USER_AGENT=MyApp/1.0

# Feature flags
OUTLINE_ENABLE_CIRCUIT_BREAKER=true
OUTLINE_ENABLE_LOGGING=false
OUTLINE_JSON_FORMAT=false
OUTLINE_ALLOW_PRIVATE_NETWORKS=true
OUTLINE_RESOLVE_DNS_FOR_SSRF=false

# Circuit breaker settings
OUTLINE_CIRCUIT_FAILURE_THRESHOLD=5
OUTLINE_CIRCUIT_RECOVERY_TIMEOUT=60.0
OUTLINE_CIRCUIT_SUCCESS_THRESHOLD=2
OUTLINE_CIRCUIT_CALL_TIMEOUT=10.0
```

```python
# Python usage
from pyoutlineapi import AsyncOutlineClient

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
    rate_limit=50,
) as client:
    await client.get_server_info()
```

## Configuration object

```python
from pyoutlineapi import AsyncOutlineClient, OutlineClientConfig
from pydantic import SecretStr

config = OutlineClientConfig(
    api_url="https://server.com:12345/secret",
    cert_sha256=SecretStr("a" * 64),
    timeout=30,
    retry_attempts=5,
    max_connections=20,
    rate_limit=100,
    enable_circuit_breaker=True,
    enable_logging=True,
    json_format=False,
    allow_private_networks=True,
    resolve_dns_for_ssrf=False,
)

async with AsyncOutlineClient(config) as client:
    await client.get_server_info()

config = OutlineClientConfig.create_minimal(
    api_url="https://server.com:12345/secret",
    cert_sha256="a" * 64,
    timeout=10,
)

from pyoutlineapi import DevelopmentConfig, ProductionConfig

dev_config = DevelopmentConfig.from_env()
prod_config = ProductionConfig.from_env()
```

## Configuration management

```python
new_config = config.model_copy_immutable(
    timeout=20,
    enable_logging=True,
)

safe_config = config.get_sanitized_config()
logger.info(f"Using config: {safe_config}")

cert_value = config.get_cert_sha256()

if config.circuit_config:
    print(f"Threshold: {config.circuit_config.failure_threshold}")
    print(f"Timeout: {config.circuit_config.recovery_timeout}")
```

## SSRF controls

- `allow_private_networks=True` allows private/local IPs in the API URL.
- `resolve_dns_for_ssrf=True` resolves DNS and blocks if **any** A/AAAA record is private/reserved.
  This protects against DNS rebinding and mixed public/private records.
