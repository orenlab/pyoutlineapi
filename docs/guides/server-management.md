# Server Management Guide

Complete guide to managing Outline VPN server configuration with PyOutlineAPI.

## Setup

```python
from pyoutlineapi import AsyncOutlineClient

async with AsyncOutlineClient.from_env() as client:
    pass
```

## Table of Contents

- [Server Information](#server-information)
- [Server Configuration](#server-configuration)
- [Network Settings](#network-settings)
- [Global Data Limits](#global-data-limits)
- [Metrics Management](#metrics-management)
- [Best Practices](#best-practices)

---

## Server Information

### Get Server Info

```python
from pyoutlineapi import AsyncOutlineClient
import asyncio


async def get_server_details():
    async with AsyncOutlineClient.from_env() as client:
        server = await client.get_server_info()

        print(f"Server Name: {server.name}")
        print(f"Server ID: {server.server_id}")
        print(f"Version: {server.version}")
        print(f"Port: {server.port_for_new_access_keys}")
        print(f"Hostname: {server.hostname_for_access_keys}")
        print(f"Metrics: {server.metrics_enabled}")
        print(f"Created: {server.created_timestamp_seconds}")


asyncio.run(get_server_details())
```

### Server Properties

```python
async def analyze_server():
    async with AsyncOutlineClient.from_env() as client:
        server = await client.get_server_info()

        # Check metrics status
        if server.metrics_enabled:
            print("✅ Metrics enabled")
        else:
            print("❌ Metrics disabled")

        # Check default port
        if server.port_for_new_access_keys == 443:
            print("✅ Using standard HTTPS port")
        else:
            print(f"ℹ️  Using custom port: {server.port_for_new_access_keys}")

        # Check hostname
        if server.hostname_for_access_keys:
            print(f"✅ Hostname configured: {server.hostname_for_access_keys}")
        else:
            print("⚠️  No hostname configured")


asyncio.run(analyze_server())
```

---

## Server Configuration

### Rename Server

```python
async def rename_server():
    async with AsyncOutlineClient.from_env() as client:
        # Update server name
        await client.rename_server("Production VPN Server")

        # Verify
        server = await client.get_server_info()
        print(f"Server renamed to: {server.name}")


asyncio.run(rename_server())
```

### Complete Server Setup

```python
async def setup_server():
    """Complete server configuration."""
    async with AsyncOutlineClient.from_env() as client:
        # Set server name
        await client.rename_server("Company VPN")
        print("✅ Server name set")

        # Configure hostname
        await client.set_hostname("vpn.company.com")
        print("✅ Hostname configured")

        # Set default port
        await client.set_default_port(443)
        print("✅ Port configured")

        # Enable metrics
        await client.set_metrics_status(True)
        print("✅ Metrics enabled")

        # Verify configuration
        server = await client.get_server_info()
        print(f"\n📋 Final configuration:")
        print(f"  Name: {server.name}")
        print(f"  Hostname: {server.hostname_for_access_keys}")
        print(f"  Port: {server.port_for_new_access_keys}")
        print(f"  Metrics: {server.metrics_enabled}")


asyncio.run(setup_server())
```

---

## Network Settings

### Set Hostname

```python
async def configure_hostname():
    async with AsyncOutlineClient.from_env() as client:
        # Set custom hostname
        await client.set_hostname("vpn.example.com")

        # Verify
        server = await client.get_server_info()
        print(f"Hostname: {server.hostname_for_access_keys}")


asyncio.run(configure_hostname())
```

### Set Default Port

```python
async def configure_port():
    async with AsyncOutlineClient.from_env() as client:
        # Change default port for new keys
        await client.set_default_port(443)

        # Verify
        server = await client.get_server_info()
        print(f"Default port: {server.port_for_new_access_keys}")


asyncio.run(configure_port())
```

### Update Port for Existing Keys

```python
async def update_all_ports():
    """Update port for all existing keys."""
    async with AsyncOutlineClient.from_env() as client:
        # Set new default port
        new_port = 8443
        await client.set_default_port(new_port)

        # Get all keys
        keys = await client.get_access_keys()

        # Note: Existing keys keep their ports
        # New keys will use the new default
        print(f"New default port: {new_port}")
        print(f"Existing keys: {keys.count}")
        print("Note: Existing keys retain their current ports")


asyncio.run(update_all_ports())
```

---

## Global Data Limits

### Set Global Limit

```python
from pyoutlineapi import AsyncOutlineClient
from pyoutlineapi.models import DataLimit


async def set_global_limit():
    async with AsyncOutlineClient.from_env() as client:
        # Set 100 GB global limit
        limit = DataLimit.from_gigabytes(100)
        await client.set_global_data_limit(limit)

        print(f"✅ Global limit set: 100 GB")
        print("This affects all keys without individual limits")


asyncio.run(set_global_limit())
```

### Remove Global Limit

```python
async def remove_global_limit():
    async with AsyncOutlineClient.from_env() as client:
        # Remove global data limit
        await client.remove_global_data_limit()

        print("✅ Global limit removed")
        print("Keys without individual limits are now unlimited")


asyncio.run(remove_global_limit())
```

### Check Global Limit Impact

```python
async def analyze_limit_impact():
    async with AsyncOutlineClient.from_env() as client:
        keys = await client.get_access_keys()

        # Count keys affected by global limit
        without_individual_limits = keys.filter_without_limits()
        with_limits = keys.filter_with_limits()

        print(f"Total keys: {keys.count}")
        print(f"Keys with individual limits: {len(with_limits)}")
        print(f"Keys affected by global limit: {len(without_individual_limits)}")


asyncio.run(analyze_limit_impact())
```

---

## Metrics Management

### Enable Metrics

```python
async def enable_metrics():
    async with AsyncOutlineClient.from_env() as client:
        # Enable metrics collection
        await client.set_metrics_status(True)

        # Verify
        status = await client.get_metrics_status()
        print(f"Metrics enabled: {status.metrics_enabled}")


asyncio.run(enable_metrics())
```

### Disable Metrics

```python
async def disable_metrics():
    async with AsyncOutlineClient.from_env() as client:
        # Disable metrics
        await client.set_metrics_status(False)

        # Verify
        status = await client.get_metrics_status()
        print(f"Metrics enabled: {status.metrics_enabled}")


asyncio.run(disable_metrics())
```

### Check Metrics Status

```python
async def check_metrics():
    async with AsyncOutlineClient.from_env() as client:
        status = await client.get_metrics_status()

        if status.metrics_enabled:
            print("✅ Metrics collection is enabled")
            print("You can view transfer metrics and analytics")
        else:
            print("❌ Metrics collection is disabled")
            print("Enable metrics to track usage")


asyncio.run(check_metrics())
```

---

## Best Practices

### 1. Use Descriptive Names

```python
# ❌ Bad: Generic name
await client.rename_server("Server1")

# ✅ Good: Descriptive name
await client.rename_server("US-East Production VPN")
```

### 2. Configure Hostname

```python
# Always set hostname for better user experience
await client.set_hostname("vpn.company.com")
```

### 3. Use Standard Ports

```python
# Prefer standard ports for better compatibility
await client.set_default_port(443)  # HTTPS
# or
await client.set_default_port(8080)  # Common alternative
```

### 4. Enable Metrics

```python
# Enable metrics for monitoring and analytics
await client.set_metrics_status(True)
```

### 5. Document Configuration

```python
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ServerConfig:
    """Server configuration snapshot."""
    name: str
    hostname: str
    port: int
    metrics_enabled: bool
    timestamp: datetime


async def save_config():
    """Save current configuration."""
    async with AsyncOutlineClient.from_env() as client:
        server = await client.get_server_info()

        config = ServerConfig(
            name=server.name,
            hostname=server.hostname_for_access_keys or "not-set",
            port=server.port_for_new_access_keys,
            metrics_enabled=server.metrics_enabled,
            timestamp=datetime.now()
        )

        # Save to file/database
        print(f"Configuration saved: {config}")


asyncio.run(save_config())
```

### 6. Validate Changes

```python
async def validate_server_config():
    """Validate server configuration."""
    async with AsyncOutlineClient.from_env() as client:
        server = await client.get_server_info()

        issues = []

        # Check name
        if not server.name or server.name == "My Outline Server":
            issues.append("Server name not customized")

        # Check hostname
        if not server.hostname_for_access_keys:
            issues.append("Hostname not configured")

        # Check port
        if server.port_for_new_access_keys not in [443, 8080, 8443]:
            issues.append(f"Non-standard port: {server.port_for_new_access_keys}")

        # Check metrics
        if not server.metrics_enabled:
            issues.append("Metrics disabled")

        if issues:
            print("⚠️  Configuration issues:")
            for issue in issues:
                print(f"  - {issue}")
        else:
            print("✅ Configuration looks good")


asyncio.run(validate_server_config())
```

### 7. Configuration Template

```python
from typing import TypedDict


class ServerTemplate(TypedDict):
    """Server configuration template."""
    name: str
    hostname: str
    port: int
    metrics_enabled: bool
    global_limit_gb: int | None


# Production template
PRODUCTION_CONFIG: ServerTemplate = {
    "name": "Production VPN",
    "hostname": "vpn.company.com",
    "port": 443,
    "metrics_enabled": True,
    "global_limit_gb": 100,
}

# Development template
DEVELOPMENT_CONFIG: ServerTemplate = {
    "name": "Development VPN",
    "hostname": "vpn-dev.company.com",
    "port": 8080,
    "metrics_enabled": True,
    "global_limit_gb": None,
}


async def apply_template(template: ServerTemplate):
    """Apply configuration template."""
    async with AsyncOutlineClient.from_env() as client:
        await client.rename_server(template["name"])
        await client.set_hostname(template["hostname"])
        await client.set_default_port(template["port"])
        await client.set_metrics_status(template["metrics_enabled"])

        if template["global_limit_gb"]:
            limit = DataLimit.from_gigabytes(template["global_limit_gb"])
            await client.set_global_data_limit(limit)
        else:
            await client.remove_global_data_limit()

        print(f"✅ Applied template: {template['name']}")


# Apply production configuration
asyncio.run(apply_template(PRODUCTION_CONFIG))
```

---

## Complete Example

```python
from pyoutlineapi import AsyncOutlineClient
from pyoutlineapi.models import DataLimit
from pyoutlineapi.exceptions import OutlineError
import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ServerManager:
    """Server configuration manager."""

    def __init__(self, client: AsyncOutlineClient):
        self.client = client

    async def initial_setup(
            self,
            name: str,
            hostname: str,
            port: int = 443,
            global_limit_gb: int | None = None,
    ):
        """Perform initial server setup."""
        try:
            # Configure server
            await self.client.rename_server(name)
            logger.info(f"✅ Server name: {name}")

            await self.client.set_hostname(hostname)
            logger.info(f"✅ Hostname: {hostname}")

            await self.client.set_default_port(port)
            logger.info(f"✅ Port: {port}")

            await self.client.set_metrics_status(True)
            logger.info("✅ Metrics enabled")

            # Set global limit if specified
            if global_limit_gb:
                limit = DataLimit.from_gigabytes(global_limit_gb)
                await self.client.set_global_data_limit(limit)
                logger.info(f"✅ Global limit: {global_limit_gb} GB")

            # Verify configuration
            server = await self.client.get_server_info()
            logger.info(f"\n📋 Server configured:")
            logger.info(f"  Name: {server.name}")
            logger.info(f"  Hostname: {server.hostname_for_access_keys}")
            logger.info(f"  Port: {server.port_for_new_access_keys}")
            logger.info(f"  Metrics: {server.metrics_enabled}")

            return True

        except OutlineError as e:
            logger.error(f"❌ Setup failed: {e}")
            return False

    async def get_status(self) -> dict:
        """Get comprehensive server status."""
        server = await self.client.get_server_info()
        keys = await self.client.get_access_keys()

        status = {
            "server": {
                "name": server.name,
                "version": server.version,
                "hostname": server.hostname_for_access_keys,
                "port": server.port_for_new_access_keys,
                "metrics_enabled": server.metrics_enabled,
            },
            "keys": {
                "total": keys.count,
                "with_limits": len(keys.filter_with_limits()),
                "without_limits": len(keys.filter_without_limits()),
            }
        }

        if server.metrics_enabled:
            metrics = await self.client.get_transfer_metrics()
            status["usage"] = {
                "total_gb": metrics.total_gigabytes,
                "active_keys": metrics.user_count,
            }

        return status


async def main():
    """Main setup flow."""
    async with AsyncOutlineClient.from_env() as client:
        manager = ServerManager(client)

        # Initial setup
        success = await manager.initial_setup(
            name="Company VPN Server",
            hostname="vpn.company.com",
            port=443,
            global_limit_gb=100
        )

        if success:
            # Get status
            status = await manager.get_status()
            logger.info(f"\n📊 Status: {status}")


if __name__ == "__main__":
    asyncio.run(main())
```

---

## See Also

- [Access Key Management](access-keys.md)
- [Metrics & Monitoring](metrics-monitoring.md)
- [Configuration Guide](../getting-started/configuration.md)

---

[← Back to Documentation](../README.md)
