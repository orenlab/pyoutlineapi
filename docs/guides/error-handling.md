# Error Handling

## Setup

```python
from pyoutlineapi import AsyncOutlineClient

async with AsyncOutlineClient.from_env() as client:
    pass
```

## Exception hierarchy

```python
from pyoutlineapi.exceptions import (
    OutlineError,
    APIError,
    CircuitOpenError,
    ConfigurationError,
    ValidationError,
    ConnectionError,
    TimeoutError,
)
```

## Comprehensive handling

```python
from pyoutlineapi import AsyncOutlineClient
from pyoutlineapi.exceptions import (
    CircuitOpenError,
    APIError,
    ConnectionError,
    TimeoutError,
    get_retry_delay,
    is_retryable,
    get_safe_error_dict,
)

async with AsyncOutlineClient.from_env() as client:
    try:
        server = await client.get_server_info()

    except CircuitOpenError as e:
        print(f"Service failing - retry after {e.retry_after}s")
        await asyncio.sleep(e.retry_after)

    except APIError as e:
        print(f"Status: {e.status_code}")
        print(f"Endpoint: {e.endpoint}")

        if e.is_client_error:
            print("Client error - check request")
        elif e.is_server_error:
            print("Server error - retry may help")
        elif e.is_rate_limit_error:
            print("Rate limited")

        if e.is_retryable:
            delay = get_retry_delay(e)
            await asyncio.sleep(delay)

    except ConnectionError as e:
        print(f"Failed to connect to {e.host}:{e.port}")

    except TimeoutError as e:
        print(f"Timeout after {e.timeout}s on {e.operation}")

    except OutlineError as e:
        safe_dict = get_safe_error_dict(e)
        logger.error(f"Error: {safe_dict}")
```

## Retry strategy

```python
import asyncio

from pyoutlineapi import AsyncOutlineClient
from pyoutlineapi.exceptions import APIError, is_retryable, get_retry_delay


async def robust_operation(max_attempts: int = 3):
    for attempt in range(max_attempts):
        try:
            async with AsyncOutlineClient.from_env() as client:
                return await client.get_server_info()

        except APIError as e:
            if not is_retryable(e) or attempt == max_attempts - 1:
                raise

            delay = get_retry_delay(e) or 1.0
            backoff_delay = delay * (2 ** attempt)

            print(f"Attempt {attempt + 1} failed, retrying in {backoff_delay}s")
            await asyncio.sleep(backoff_delay)
```
