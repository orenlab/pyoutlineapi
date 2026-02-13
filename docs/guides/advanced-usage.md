# Advanced Usage

## Setup

```python
from pyoutlineapi import AsyncOutlineClient

async with AsyncOutlineClient.from_env() as client:
    pass
```

## Rate limiting & connection pooling

```python
from pyoutlineapi import AsyncOutlineClient, OutlineClientConfig

config = OutlineClientConfig.from_env(
    rate_limit=50,
    max_connections=20,
)

async with AsyncOutlineClient(config) as client:
    stats = client.get_rate_limiter_stats()
    print(f"Active: {stats['active']}/{stats['limit']}")
    print(f"Available: {stats['available']}")

    await client.set_rate_limit(100)
    print(f"Active requests: {client.active_requests}")
    print(f"Available slots: {client.available_slots}")
```

## Health checks & summary

```python
async with AsyncOutlineClient.from_env() as client:
    health = await client.health_check()
    print(f"Healthy: {health['healthy']}")
    print(f"Response time: {health.get('response_time_ms')}ms")
    print(f"Circuit: {health['circuit_state']}")

    summary = await client.get_server_summary()
    print(f"Server: {summary['server']['name']}")
    print(f"Keys: {summary['access_keys_count']}")
    print(f"Metrics enabled: {summary['server'].get('metricsEnabled')}")

    if summary.get("transfer_metrics"):
        print(f"Total traffic: {summary['transfer_metrics']}")

    status = client.get_status()
    print(f"Connected: {status['connected']}")
    print(f"Circuit state: {status['circuit_state']}")
    print(f"Active requests: {status['active_requests']}")
    print(f"Rate limit: {status['rate_limit']}")
```

## JSON format

```python
config = OutlineClientConfig.from_env(json_format=True)
async with AsyncOutlineClient(config) as client:
    server_dict = await client.get_server_info()
    print(server_dict["name"])

async with AsyncOutlineClient.from_env() as client:
    server_dict = await client.get_server_info(as_json=True)
    server_model = await client.get_server_info(as_json=False)
```

## Custom metrics collector

```python
from pyoutlineapi.base_client import MetricsCollector


class PrometheusMetrics:
    def increment(self, metric: str, *, tags: dict | None = None) -> None:
        pass

    def timing(self, metric: str, value: float, *, tags: dict | None = None) -> None:
        pass

    def gauge(self, metric: str, value: float, *, tags: dict | None = None) -> None:
        pass


metrics = PrometheusMetrics()
async with AsyncOutlineClient.from_env(metrics=metrics) as client:
    await client.get_server_info()
```
