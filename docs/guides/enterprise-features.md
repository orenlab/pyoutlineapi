# Enterprise Features

Production-grade patterns: circuit breaker, health monitoring, batch operations, metrics collection, and audit logging.

## Setup

```python
from pyoutlineapi import AsyncOutlineClient

async with AsyncOutlineClient.from_env() as client:
    pass
```

## Circuit breaker

```python
from pyoutlineapi import AsyncOutlineClient, CircuitOpenError

async with AsyncOutlineClient.from_env(
    enable_circuit_breaker=True,
    circuit_failure_threshold=5,
    circuit_recovery_timeout=60.0,
    circuit_success_threshold=2,
) as client:
    try:
        await client.get_server_info()
    except CircuitOpenError as e:
        print(f"Circuit open - retry after {e.retry_after}s")

    metrics = client.get_circuit_metrics()
    if metrics:
        print(f"State: {metrics['state']}")
        print(f"Success rate: {metrics['success_rate']:.2%}")
        print(f"Total calls: {metrics['total_calls']}")
        print(f"Failed calls: {metrics['failed_calls']}")

    await client.reset_circuit_breaker()
```

Circuit states:
- CLOSED: normal operation
- OPEN: failures exceeded threshold
- HALF_OPEN: recovery probing

## Health monitoring

```python
from pyoutlineapi import AsyncOutlineClient
from pyoutlineapi.health_monitoring import HealthMonitor

async with AsyncOutlineClient.from_env() as client:
    monitor = HealthMonitor(client, cache_ttl=30.0)

    is_healthy = await monitor.quick_check()
    print(f"Quick check: {is_healthy}")

    health = await monitor.comprehensive_check()
    print(f"Overall health: {health.healthy}")
    print(f"Total checks: {health.total_checks}")
    print(f"Passed: {health.passed_checks}")
    print(f"Degraded: {health.is_degraded}")

    for check_name, result in health.checks.items():
        print(f"{check_name}: {result['status']}")
        if "message" in result:
            print(f"  → {result['message']}")

    if not health.healthy:
        print(f"Failed: {health.failed_checks}")
        print(f"Warnings: {health.warning_checks}")

    print(f"Connectivity time: {health.metrics.get('connectivity_time', 0):.3f}s")
    print(f"Success rate: {health.metrics.get('success_rate', 0):.2%}")

    async def check_disk_space(client):
        return {"status": "healthy", "message": "Disk space OK"}

    monitor.add_custom_check("disk_space", check_disk_space)
    health = await monitor.comprehensive_check(force_refresh=True)

    if await monitor.wait_for_healthy(timeout=120, check_interval=5):
        print("Service recovered!")
    else:
        print("Service still unhealthy after 120s")

    monitor.record_request(success=True, duration=0.5)
    monitor.record_request(success=False, duration=5.0)

    metrics = monitor.get_metrics()
    print(f"Total requests: {metrics['total_requests']}")
    print(f"Avg response time: {metrics['avg_response_time']:.3f}s")
    print(f"Uptime: {metrics['uptime']:.1f}s")
```

## Batch operations

```python
from pyoutlineapi import AsyncOutlineClient
from pyoutlineapi.batch_operations import BatchOperations
from pyoutlineapi.models import DataLimit

async with AsyncOutlineClient.from_env() as client:
    batch = BatchOperations(client, max_concurrent=10)

    configs = [
        {"name": f"User{i}", "limit": DataLimit.from_gigabytes(5)}
        for i in range(1, 101)
    ]
    result = await batch.create_multiple_keys(configs, fail_fast=False)

    print(f"Created: {result.successful}/{result.total}")
    print(f"Failed: {result.failed}")
    print(f"Success rate: {result.success_rate:.2%}")

    keys = result.get_successful_results()

    if result.has_validation_errors:
        print(f"Validation errors: {result.validation_errors}")

    pairs = [(key.id, f"User-{i}") for i, key in enumerate(keys, 1)]
    await batch.rename_multiple_keys(pairs)

    limits = [(key.id, DataLimit.from_gigabytes(10).bytes) for key in keys]
    await batch.set_multiple_data_limits(limits)

    key_ids = [key.id for key in keys]
    await batch.delete_multiple_keys(key_ids)

    operations = [
        lambda: client.get_access_key(key_id)
        for key_id in key_ids
    ]
    await batch.execute_custom_operations(operations)

    await batch.set_concurrency(20)
```

## Metrics collection

```python
from pyoutlineapi import AsyncOutlineClient
from pyoutlineapi.metrics_collector import MetricsCollector
import asyncio
import time

async with AsyncOutlineClient.from_env() as client:
    collector = MetricsCollector(
        client,
        interval=60,
        max_history=1440,
    )

    await collector.start()
    await asyncio.sleep(3600)

    snapshot = collector.get_latest_snapshot()
    if snapshot:
        print(f"Keys: {snapshot.key_count}")
        print(f"Total traffic: {snapshot.total_bytes_transferred}")

    stats = collector.get_usage_stats(period_minutes=60)
    print(f"Period: {stats.duration:.1f}s")
    print(f"Total: {stats.gigabytes_transferred:.2f} GB")
    print(f"Rate: {stats.bytes_per_second / 1024:.2f} KB/s")
    print(f"Peak: {stats.peak_bytes / 1024 ** 3:.2f} GB")
    print(f"Active keys: {len(stats.active_keys)}")
    print(f"Snapshots: {stats.snapshots_count}")

    key_usage = collector.get_key_usage("key-123", period_minutes=60)
    print(f"Key 123 traffic: {key_usage['total_bytes'] / 1024 ** 3:.2f} GB")
    print(f"Key 123 rate: {key_usage['bytes_per_second'] / 1024:.2f} KB/s")

    cutoff = time.time() - 3600
    recent_snapshots = collector.get_snapshots_after(cutoff)

    data = collector.export_to_dict()
    print(f"Collection duration: {data['collection_end'] - data['collection_start']:.1f}s")
    print(f"Snapshots: {data['snapshots_count']}")

    prometheus = collector.export_prometheus_format(include_per_key=True)
    print(prometheus)

    summary = collector.export_prometheus_summary()
    print(summary)

    print(f"Running: {collector.is_running}")
    print(f"Uptime: {collector.uptime:.1f}s")
    print(f"Snapshots collected: {collector.snapshots_count}")

    await collector.stop()

async with AsyncOutlineClient.from_env() as client:
    async with MetricsCollector(client, interval=60) as collector:
        await asyncio.sleep(3600)
        stats = collector.get_usage_stats()
```

## Audit logging

```python
from pyoutlineapi import AsyncOutlineClient, DefaultAuditLogger, set_default_audit_logger
from pyoutlineapi import NoOpAuditLogger

# Default audit logger (built-in)
audit_logger = DefaultAuditLogger(
    enable_async=True,
    queue_size=5000,
)

async with AsyncOutlineClient.from_env(audit_logger=audit_logger) as client:
    key = await client.create_access_key(name="Alice")
    await client.rename_access_key(key.id, "Alice Smith")
    await client.delete_access_key(key.id)

    try:
        await client.delete_access_key("non-existent")
    except Exception:
        pass


class CustomAuditLogger:
    def log_action(self, action: str, resource: str, **kwargs) -> None:
        print(f"AUDIT: {action} on {resource} - {kwargs}")

    async def alog_action(self, action: str, resource: str, **kwargs) -> None:
        self.log_action(action, resource, **kwargs)

    async def shutdown(self) -> None:
        pass


set_default_audit_logger(DefaultAuditLogger(enable_async=True))

async with AsyncOutlineClient.from_env() as client1:
    await client1.create_access_key(name="User1")

async with AsyncOutlineClient.from_env() as client2:
    await client2.create_access_key(name="User2")

async with AsyncOutlineClient.from_env(audit_logger=NoOpAuditLogger()) as client:
    await client.create_access_key(name="Test")
```

Audited operations:
- Access keys: create, delete, rename, set/remove data limit
- Server: rename, set hostname, set default port
- Data limits: set/remove global data limit
- Metrics: set metrics status
