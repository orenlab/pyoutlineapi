# Best Practices

## Setup

```python
from pyoutlineapi import AsyncOutlineClient

async with AsyncOutlineClient.from_env() as client:
    pass
```

## Use environment variables

```python
from pyoutlineapi import AsyncOutlineClient

# Secure - credentials not in code
async with AsyncOutlineClient.from_env() as client:
    pass

# Avoid embedding secrets in code
client = AsyncOutlineClient(
    api_url="https://...",
    cert_sha256="a" * 64,
)
```

## Always use context managers

```python
from pyoutlineapi import AsyncOutlineClient

async with AsyncOutlineClient.from_env() as client:
    await client.get_server_info()

client = AsyncOutlineClient.from_env()
await client.__aenter__()
try:
    await client.get_server_info()
finally:
    await client.shutdown()
```

## Handle specific exceptions

```python
from pyoutlineapi.exceptions import APIError

try:
    key = await client.get_access_key("key-id")
except APIError as e:
    if e.status_code == 404:
        print("Key not found")
    elif e.is_server_error:
        print("Server error - retry")
```

## Enable production features

```python
from pyoutlineapi import AsyncOutlineClient, DefaultAuditLogger, ProductionConfig

config = ProductionConfig.from_env(
    enable_circuit_breaker=True,
    circuit_failure_threshold=5,
    rate_limit=50,
)
audit = DefaultAuditLogger(enable_async=True, queue_size=5000)
client = AsyncOutlineClient(config, audit_logger=audit)
```

## Use batch operations for multiple items

```python
from pyoutlineapi.batch_operations import BatchOperations

batch = BatchOperations(client, max_concurrent=10)
configs = [{"name": f"User{i}"} for i in range(1, 101)]
result = await batch.create_multiple_keys(configs)

for i in range(1, 101):
    await client.create_access_key(name=f"User{i}")
```

## Monitor health & performance

```python
from pyoutlineapi.health_monitoring import HealthMonitor

monitor = HealthMonitor(client, cache_ttl=30)
health = await monitor.comprehensive_check()

if not health.healthy:
    logger.error(f"Service unhealthy: {health.failed_checks}")

monitor.record_request(success=True, duration=0.5)
metrics = monitor.get_metrics()
```
