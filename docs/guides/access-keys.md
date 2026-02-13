# Access Key Management

Practical guide for creating and managing access keys.

## Setup

```python
from pyoutlineapi import AsyncOutlineClient

async with AsyncOutlineClient.from_env() as client:
    pass
```

## Create keys

```python
from pyoutlineapi import AsyncOutlineClient
from pyoutlineapi.models import DataLimit

# Create key with data limit
key = await client.create_access_key(
    name="Alice",
    limit=DataLimit.from_gigabytes(10),
)

# Create with custom settings
key = await client.create_access_key(
    name="Bob",
    port=8388,
    method="chacha20-ietf-poly1305",
    password="custom-password",
)

# Create with specific ID
key = await client.create_access_key_with_id(
    key_id="user-001",
    name="Charlie",
)
```

## List and filter keys

```python
keys = await client.get_access_keys()
limited_keys = keys.filter_with_limits()
unlimited_keys = keys.filter_without_limits()
alice_keys = keys.get_by_name("Alice")
key = keys.get_by_id("1")
```

## Update and delete keys

```python
await client.rename_access_key("1", "Alice Smith")
await client.set_access_key_data_limit("1", DataLimit.from_gigabytes(5))
await client.remove_access_key_data_limit("1")
await client.delete_access_key("1")
```


