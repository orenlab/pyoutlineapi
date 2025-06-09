# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] - 2025-0X-0X

### Added

- **Documentation**:
    - Safety guide `SECURITY.md`

## [0.3.0] - 2025-06-09

### Added

- **New API methods**:
    - `create_access_key_with_id()` - Create access key with specific custom ID
    - `get_experimental_metrics(since)` - Get detailed experimental server metrics (requires mandatory `since`
      parameter)
    - `set_global_data_limit()` - Set global data transfer limit for all access keys
    - `remove_global_data_limit()` - Remove global data transfer limit
- **Enhanced models and validation**:
    - New request models: `AccessKeyNameRequest`, `DataLimitRequest`, `HostnameRequest`, `MetricsEnabledRequest`,
      `PortRequest`, `ServerNameRequest`
    - `ExperimentalMetrics` model for detailed server analytics
    - Better type safety with dedicated request/response models
- **Improved error handling**:
    - Separated exceptions into dedicated module (`exceptions.py`)
    - Enhanced error messages with more context
    - Better exception hierarchy
- **Retry mechanism enhancements**:
    - Configurable retry attempts via constructor parameter
    - Robust retry logic with exponential backoff
    - Automatic retry for transient failures (HTTP 408, 429, 500, 502, 503, 504)
    - Enhanced error tracking with attempt numbers
- **Constants and configuration**:
    - `MIN_PORT` and `MAX_PORT` constants for port validation
    - `DEFAULT_RETRY_ATTEMPTS`, `DEFAULT_RETRY_DELAY` for retry configuration
    - `RETRY_STATUS_CODES` set for retriable HTTP status codes

### Changed

- **Breaking changes**:
    - Default `json_format` parameter changed from `True` to `False` (now returns Pydantic models by default)
    - Default timeout reduced from 30 to 10 seconds for better responsiveness
    - Access key ID parameters changed from `int` to `str` type for better API compatibility
    - Method signatures updated to use dedicated request models instead of raw dictionaries
- **API improvements**:
    - All request methods now use proper Pydantic models with `by_alias=True` serialization
    - Better handling of optional parameters with `exclude_none=True`
    - Improved type annotations throughout the codebase
    - Enhanced method documentation with updated examples
- **Internal optimizations**:
    - Refactored request handling with separate `_make_request` and `_retry_request` methods
    - Better session management and connection handling
    - More efficient error handling and response parsing
    - Improved SSL context creation and certificate validation

### Fixed

- **Metrics handling**:
    - Removed deprecated `MetricsPeriod` parameter from `get_transfer_metrics()` (API doesn't support period filtering)
    - Fixed metrics status response parsing
    - **Documentation**: Corrected examples for `get_experimental_metrics()` to show that `since` parameter is mandatory
- **Data validation**:
    - Better handling of API response formats
    - Improved error messages for validation failures
    - Fixed SSL certificate fingerprint validation
- **Connection stability**:
    - More robust handling of connection failures and timeouts
    - Better cleanup of resources during session closure
    - Improved retry logic for transient network issues

### Removed

- **Deprecated features**:
    - `MetricsPeriod` enum and period parameter from `get_transfer_metrics()`
    - Direct dictionary usage in API requests (replaced with proper models)
- **Simplified API**:
    - Removed redundant parameter validation (now handled by Pydantic models)
    - Cleaned up internal helper methods

### Migration Guide

For users upgrading from v0.2.0:

1. **Default behavior change**: The client now returns Pydantic models by default instead of JSON dictionaries. To
   maintain old behavior, set `json_format=True` in the constructor.

2. **Access key IDs**: Change access key ID parameters from integers to strings:
   ```python
   # Old
   await client.get_access_key(1)
   
   # New  
   await client.get_access_key("1")
   ```

3. **Metrics API**: Remove period parameter from `get_transfer_metrics()`:
   ```python
   # Old
   await client.get_transfer_metrics(MetricsPeriod.MONTHLY)
   
   # New
   await client.get_transfer_metrics()
   ```

4. **Error handling**: Update exception handling to use the new exception hierarchy from `exceptions` module.

## [0.2.0] - 2024-01-10

### Added

- New asynchronous client `AsyncOutlineClient` using `aiohttp`
- Comprehensive type hints and overloads for better IDE support
- New methods for server management:
    - `rename_server()` - Change server name
    - `set_hostname()` - Configure server hostname
    - `get_metrics_status()` - Check metrics collection status
    - `set_metrics_status()` - Enable/disable metrics collection
- Support for different metrics periods (DAILY, WEEKLY, MONTHLY)
- Extended options for access key creation (method, encryption settings)
- Improved error handling with detailed error messages
- Context manager support with async `__aenter__` and `__aexit__`

### Changed

- Complete rewrite of the client to support asynchronous operations
- Enhanced error hierarchy with `OutlineError` base class
- Improved request handling with automatic session management
- More flexible SSL/TLS certificate verification
- Better JSON response parsing and validation
- Updated type annotations to use modern Python typing features

### Removed

- Synchronous client implementation (migrated to async)
- Direct requests-based HTTP handling

## [0.1.2] - 2024-01-09

### Added

- Initial release with synchronous client
- Basic Outline VPN server management features:
    - Server information retrieval
    - Access key management (create, list, delete)
    - Data limit management
    - Server port configuration
    - Basic metrics retrieval
- Pydantic models for data validation
- Support for custom certificate verification
- Optional JSON response format

[0.3.0]: https://github.com/orenlab/pyoutlineapi/compare/v0.2.0...v0.3.0

[0.2.0]: https://github.com/orenlab/pyoutlineapi/compare/v0.1.2...v0.2.0

[0.1.2]: https://github.com/orenlab/pyoutlineapi/releases/tag/v0.1.2