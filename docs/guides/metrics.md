# Metrics

Guide to metrics management and transfer statistics.

## Setup

```python
from pyoutlineapi import AsyncOutlineClient

async with AsyncOutlineClient.from_env() as client:
    pass
```

## Enable / disable metrics

```python
from pyoutlineapi import AsyncOutlineClient

await client.set_metrics_status(True)
status = await client.get_metrics_status()
```

## Transfer metrics

```python
from pyoutlineapi import AsyncOutlineClient

metrics = await client.get_transfer_metrics()
print(f"Total: {metrics.total_gigabytes:.2f} GB")
print(f"Active keys: {metrics.user_count}")

for key_id, bytes_used in metrics.top_users(5):
    print(f"{key_id}: {bytes_used / 1024 ** 3:.2f} GB")

usage = metrics.get_user_bytes("key-123")
print(f"Key 123: {usage / 1024 ** 3:.2f} GB")
```

## Experimental metrics

```python
from pyoutlineapi import AsyncOutlineClient

exp = await client.get_experimental_metrics("24h")
print(f"Server tunnel time: {exp.server.tunnel_time.hours:.1f} hours")
print(f"Server traffic: {exp.server.data_transferred.gigabytes:.2f} GB")
print(f"Peak bandwidth: {exp.server.bandwidth.peak.data.bytes} bytes")
print(f"Locations: {len(exp.server.locations)}")

key_metric = exp.get_key_metric("key-123")
if key_metric:
    print(f"Key tunnel time: {key_metric.tunnel_time.minutes:.1f} min")
```
