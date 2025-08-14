# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] - 2025-08-XX

### Added

- **Circuit Breaker Pattern**:
    - Full circuit breaker implementation with `AsyncCircuitBreaker` class
    - Three states: CLOSED, OPEN, HALF_OPEN with automatic transitions
    - Configurable failure thresholds, recovery timeouts, and success thresholds
    - Sliding window failure rate calculation with exponential backoff
    - Event callbacks for state changes and call results monitoring
    - Health checker integration for automatic recovery detection
    - Background monitoring tasks for health checks and metrics cleanup

- **Advanced Health Monitoring**:
    - `HealthMonitoringMixin` for comprehensive health tracking
    - `OutlineHealthChecker` with cached health verification
    - `PerformanceMetrics` for detailed performance tracking
    - Real-time metrics collection: success rates, response times, circuit trips
    - Comprehensive health checks with individual component status
    - `health_check()` method with detailed metrics and circuit breaker status

- **Enhanced Configuration Management**:
    - `OutlineClientConfig` dataclass for immutable configuration
    - Environment variable loading with `from_env()` factory method
    - `.env` file support with automatic template generation
    - Comprehensive validation for all configuration parameters
    - `create_env_template()` utility for setup assistance
    - Configuration validation with detailed error messages

- **Batch Operations**:
    - `BatchOperationsMixin` with generic batch processor
    - `batch_create_access_keys()` for multiple key creation
    - `batch_delete_access_keys()` for bulk key deletion
    - `batch_rename_access_keys()` for mass key renaming
    - `batch_operations_with_resilience()` for custom batch operations
    - Configurable concurrency control and fail-fast options

- **Advanced Error Handling**:
    - Enhanced `ResponseParser` with detailed validation error formatting
    - Helpful error suggestions and context for common issues
    - Safe parsing with fallback to raw JSON on validation errors
    - Improved error messages with field paths and input values
    - Graceful handling of empty names and missing fields from API

- **Modular Architecture**:
    - Mixin-based design for clean separation of concerns
    - `ServerManagementMixin`, `MetricsMixin`, `AccessKeyMixin`, `DataLimitMixin`
    - Protocol-based type safety with `HTTPClientProtocol`
    - Enhanced type annotations with proper generic support

- **Enhanced Client Features**:
    - `create_resilient_client()` factory with conservative settings
    - `get_server_summary()` for comprehensive server overview
    - `wait_for_healthy_state()` for health state monitoring
    - Dynamic circuit breaker reconfiguration
    - Connection info and detailed status properties

- **Utility Functions**:
    - `quick_setup()` for interactive development setup
    - `get_version_info()` for package information
    - `create_config_template()` convenience wrapper
    - Interactive help display when imported in Python REPL
    - Comprehensive masking of sensitive data in logs

### Changed

- **Breaking Changes**:
    - Version bumped to 0.4.0 to reflect major feature additions
    - Client constructor now accepts many new parameters for circuit breaker and health monitoring
    - Default user agent updated to "PyOutlineAPI/0.4.0"
    - Enhanced error handling may change exception types in some edge cases

- **Enhanced Base Client**:
    - `BaseHTTPClient` now includes circuit breaker integration
    - Comprehensive logging setup without duplication
    - Enhanced session management with proper SSL context handling
    - Improved retry logic with circuit breaker awareness
    - Rate limiting support with configurable delays

- **Improved Type Safety**:
    - Better protocol definitions for HTTP client capabilities
    - Enhanced type hints with proper generic constraints
    - Improved overloads for response parsing methods
    - Stronger validation with `CommonValidators` utilities

- **Better Resource Management**:
    - Proper async context manager support throughout
    - Background task management in circuit breaker
    - Cleanup tasks for old metrics and call history
    - Enhanced session lifecycle management

- **Configuration Enhancements**:
    - All configuration now validated at initialization
    - Support for multiple environment variable prefixes
    - Comprehensive default values for all optional settings
    - Better error messages for configuration issues

### Fixed

- **Response Parsing**:
    - Better handling of empty name fields from Outline API
    - Improved validation error messages with actionable suggestions
    - Graceful fallback for unexpected response formats
    - Fixed handling of edge cases in metric responses

- **Connection Stability**:
    - Enhanced SSL certificate validation with proper error handling
    - Better handling of connection timeouts and retries
    - Improved cleanup of resources during failures
    - More robust session management

- **Logging**:
    - Eliminated duplicate log messages
    - Proper logger hierarchy setup
    - Configurable logging levels and formats
    - Performance-aware logging with conditional execution

- **Memory Management**:
    - Proper cleanup of circuit breaker background tasks
    - Sliding window size limits for call history
    - Weak references for callback management
    - Better resource cleanup in error scenarios

### Enhanced

- **Documentation**:
    - Comprehensive docstrings with usage examples
    - Better type annotations for IDE support
    - Enhanced error messages with troubleshooting hints
    - Interactive help and setup assistance

- **Developer Experience**:
    - Interactive setup with `quick_setup()` function
    - Automatic environment template creation
    - Better error messages for common configuration issues
    - Enhanced debugging capabilities with detailed metrics

- **Monitoring and Observability**:
    - Comprehensive performance metrics collection
    - Circuit breaker state monitoring with callbacks
    - Health check results with individual component status
    - Request/response time tracking and analysis

### Migration Guide

For users upgrading from v0.3.0:

1. **Enhanced Constructor**: The client constructor now accepts many new optional parameters. Existing code will
   continue to work with defaults:
   ```python
   # Old - still works
   client = AsyncOutlineClient(api_url, cert_sha256)
   
   # New - with enhanced features
   client = AsyncOutlineClient(
       api_url, cert_sha256,
       circuit_breaker_enabled=True,
       enable_health_monitoring=True,
       enable_metrics_collection=True
   )
   ```

2. **Environment Configuration**: Consider using the new configuration system:
   ```python
   # New approach
   client = AsyncOutlineClient.from_env()
   # or
   config = OutlineClientConfig.from_env()
   client = AsyncOutlineClient.from_config(config)
   ```

3. **Health Monitoring**: New health check methods are available:
   ```python
   # Get comprehensive health status
   health = await client.health_check(include_detailed_metrics=True)
   
   # Get performance metrics
   metrics = client.get_performance_metrics()
   
   # Get circuit breaker status
   cb_status = await client.get_circuit_breaker_status()
   ```

4. **Batch Operations**: Use new batch methods for better performance:
   ```python
   # Create multiple keys efficiently
   configs = [{"name": "User1"}, {"name": "User2"}]
   results = await client.batch_create_access_keys(configs)
   ```

5. **Setup Assistance**: Use new setup utilities:
   ```python
   import pyoutlineapi
   pyoutlineapi.quick_setup()  # Creates .env.example and shows usage
   ```

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

[0.4.0]: https://github.com/orenlab/pyoutlineapi/compare/v0.3.0...v0.4.0

[0.3.0]: https://github.com/orenlab/pyoutlineapi/compare/v0.2.0...v0.3.0

[0.2.0]: https://github.com/orenlab/pyoutlineapi/compare/v0.1.2...v0.2.0

[0.1.2]: https://github.com/orenlab/pyoutlineapi/releases/tag/v0.1.2