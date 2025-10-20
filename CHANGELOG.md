# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] - 2025-10-XX

### 🎯 Major Release - Enterprise-Grade Refactoring

Version 0.4.0 represents a complete architectural overhaul of PyOutlineAPI, transforming it from a basic API client into
a production-ready, enterprise-grade library with advanced resilience patterns, comprehensive monitoring, and
professional-grade code quality.

---

### ✨ Added

#### **Enterprise Features**

- **Circuit Breaker Pattern** (`circuit_breaker.py`)
    - Automatic failure detection and recovery with configurable thresholds
    - Three-state circuit (CLOSED, OPEN, HALF_OPEN) with smart transitions
    - Comprehensive metrics tracking (success rate, failure rate, state changes)
    - Timeout enforcement with exponential backoff
    - Thread-safe implementation with asyncio.Lock protection
    - Configurable via `CircuitConfig` with validation
    - Example: Protects against cascading failures in distributed systems

- **Audit Logging System** (`audit.py`)
    - Production-ready audit logger with async queue processing
    - Singleton pattern for global audit logger management
    - `@AuditDecorator` for automatic action logging
    - Sensitive data sanitization (passwords, tokens, secrets)
    - Structured logging with correlation IDs for request tracing
    - Support for both sync and async logging operations
    - Graceful shutdown with queue draining
    - `NoOpAuditLogger` for disabling audit without code changes

- **Health Monitoring** (`health_monitoring.py`)
    - `HealthMonitor` class with configurable caching (1-300 seconds TTL)
    - Quick health checks for fast connectivity testing
    - Comprehensive health checks with multiple dimensions
    - Custom health check registration support
    - Performance metrics tracking with EMA (Exponential Moving Average) smoothing
    - `wait_for_healthy()` method for graceful startup coordination
    - Immutable `HealthStatus` results for thread safety

- **Metrics Collection** (`metrics_collector.py`)
    - Advanced `MetricsCollector` with automatic periodic collection
    - Memory-efficient storage using SortedList (binary search optimized)
    - Prometheus export format with extensive metrics:
        - Traffic metrics (bytes, megabytes, gigabytes transferred)
        - Rate metrics (bytes/second, megabytes/second)
        - Peak metrics and active key tracking
        - Location-based metrics from experimental API
        - Bandwidth metrics (current, peak with timestamps)
        - Collection metadata (uptime, interval, snapshot count)
    - Per-key usage statistics with temporal queries
    - Configurable history limits (1-100,000 snapshots)
    - Size validation to prevent memory exhaustion (max 10MB per snapshot)
    - Context manager support for automatic lifecycle management

- **Batch Operations** (`batch_operations.py`)
    - Generic `BatchProcessor` with concurrency control
    - Type-safe batch operations for multiple operations:
        - `create_multiple_keys()` - Bulk key creation
        - `delete_multiple_keys()` - Bulk key deletion
        - `rename_multiple_keys()` - Bulk key renaming
        - `set_multiple_data_limits()` - Bulk limit configuration
        - `fetch_multiple_keys()` - Parallel key retrieval
        - `execute_custom_operations()` - Generic batch executor
    - Comprehensive validation with detailed error reporting
    - `fail_fast` mode for error handling strategy
    - Immutable `BatchResult` with rich statistics:
        - Success/failure counts and rates
        - Validation error tracking
        - Type-safe result extraction methods
    - Dynamic concurrency adjustment during runtime

#### **Configuration System**

- **Enhanced Configuration** (`config.py`)
    - `OutlineClientConfig` with Pydantic validation
    - Environment-based configuration with `.env` file support
    - Preset configurations:
        - `DevelopmentConfig` - Relaxed security for local development
        - `ProductionConfig` - Strict security enforcement
    - `SecretStr` type for sensitive data protection
    - Automatic circuit breaker timeout adjustment
    - Immutable configuration snapshots with `model_copy_immutable()`
    - `get_sanitized_config()` for safe logging
    - `create_env_template()` utility for quick setup
    - Factory methods: `from_env()`, `create_minimal()`

#### **Type System & Validation**

- **Common Types Module** (`common_types.py`)
    - Extensive type aliases for better IDE support:
        - `Port`, `Bytes`, `TimestampMs`, `TimestampSec`
        - `JsonDict`, `JsonList`, `JsonPayload`, `ResponseData`
        - `AuditDetails`, `MetricsTags`, `QueryParams`
    - `Constants` class with security limits and defaults
    - Enhanced `Validators` utility class with DRY optimizations
    - Security utilities: `secure_compare()`, `mask_sensitive_data()`
    - `ConfigOverrides` and `ClientDependencies` TypedDict for type safety
    - Comprehensive sensitive key detection (32+ patterns)

- **Enhanced Exception Hierarchy** (`exceptions.py`)
    - Rich error context with separate internal/safe details
    - Message length limits to prevent DoS attacks
    - Retry guidance with `is_retryable` and `get_retry_delay()`
    - Specific exception types:
        - `CircuitOpenError` - With retry_after information
        - `ConfigurationError` - With field and security_issue flags
        - `ValidationError` - With field and model context
        - `ConnectionError` - With host and port details
        - `TimeoutError` - With timeout value and operation name
    - Helper functions: `get_safe_error_dict()`, `format_error_chain()`

#### **API Client Enhancements**

- **Modular Architecture** (`api_mixins.py`)
    - `ServerMixin` - Server management operations
    - `AccessKeyMixin` - Access key CRUD operations
    - `DataLimitMixin` - Global data limit management
    - `MetricsMixin` - Metrics collection operations
    - `HTTPClientProtocol` - Runtime-checkable protocol
    - `AuditableMixin` - Automatic audit logger access
    - `JsonFormattingMixin` - JSON format preference resolution

- **Response Parser** (`response_parser.py`)
    - Type-safe response parsing with overloads
    - Comprehensive validation error logging (max 10 errors)
    - `parse_simple()` for boolean success responses
    - `validate_response_structure()` for lightweight pre-validation
    - `extract_error_message()` with fallback strategies
    - `is_error_response()` for error detection

- **Base HTTP Client** (`base_client.py`)
    - Enhanced `BaseHTTPClient` with enterprise features:
        - Correlation ID tracking with `ContextVar`
        - Cryptographically secure ID generation
        - Rate limiting with dynamic adjustment
        - Graceful shutdown with active request tracking
        - Metrics collection integration
        - Certificate pinning via SHA-256 fingerprint
        - Connection pooling with configurable limits
        - Request/response logging with sanitization
    - `RateLimiter` class with thread-safe operations
    - `RetryHelper` for DRY retry logic with jitter
    - `NoOpMetrics` for optional metrics collection

#### **Model Enhancements**

- **Extended Models** (`models.py`)
    - DRY mixins: `ByteConversionMixin`, `TimeConversionMixin`
    - Factory methods: `DataLimit.from_kilobytes/megabytes/gigabytes()`
    - Utility methods:
        - `AccessKey.has_data_limit`, `display_name`
        - `AccessKeyList.get_by_id()`, `get_by_name()`, filtering methods
        - `Server.has_global_limit`, `created_timestamp_seconds`
        - `ServerMetrics.get_top_consumers()`, `get_usage_for_key()`
    - Enhanced experimental metrics models with proper validation
    - `HealthCheckResult` and `ServerSummary` for monitoring

#### **Developer Experience**

- **Enhanced Package Interface** (`__init__.py`)
    - `quick_setup()` - Interactive configuration wizard
    - `print_type_info()` - Type alias documentation
    - `get_version()` - Version information
    - Better error messages for common mistakes
    - Interactive help in REPL mode
    - Comprehensive `__all__` export list (60+ symbols)

---

### 🔄 Changed

#### **Breaking Changes**

- **Client Constructor Signature**:
  ```python
  # Old (v0.3.0)
  client = AsyncOutlineClient(api_url, cert_sha256, json_format=True)
  
  # New (v0.4.0)
  client = AsyncOutlineClient(
      api_url=api_url,
      cert_sha256=cert_sha256,
      timeout=10,
      enable_logging=True
  )
  # Or use configuration object
  config = OutlineClientConfig.from_env()
  client = AsyncOutlineClient(config)
  ```

- **Default Values**:
    - `timeout`: Changed from 30s to 10s for better responsiveness
    - `retry_attempts`: Changed from 3 to 2 for faster failure detection
    - `json_format`: Remains `False` (returns Pydantic models by default)

- **Parameter Names**:
    - `cert_sha256` now expects `SecretStr` in config (automatic in constructor)
    - `user_agent` default changed to include version number

#### **API Improvements**

- **Method Enhancements**:
    - All methods now support `as_json` parameter for runtime format selection
    - Better type hints with overloads for precise return types
    - Consistent error handling across all operations
    - Improved parameter validation with descriptive error messages

- **Client Architecture**:
    - Split into mixin-based architecture for better code organization
    - Separated concerns: HTTP client, API mixins, configuration
    - Protocol-based design for better testability
    - Enhanced session management with proper cleanup

#### **Internal Optimizations**

- **Performance**:
    - Lazy initialization of expensive resources
    - Connection pooling with keep-alive
    - Efficient retry logic with exponential backoff + jitter
    - Memory-optimized data structures (SortedList, __slots__)

- **Code Quality**:
    - DRY principles applied throughout (extracted 20+ helper methods)
    - Type safety with runtime_checkable protocols
    - Immutable data structures where appropriate
    - Comprehensive docstrings with examples

---

### 🐛 Fixed

- **Validation Issues**:
    - Fixed empty name handling in `AccessKey` validation
    - Improved port validation with clear error messages
    - Better certificate fingerprint format validation
    - Fixed URL validation edge cases

- **Connection Stability**:
    - Proper session cleanup on errors
    - Fixed race conditions in session initialization
    - Better handling of connection timeouts
    - Improved SSL context creation error handling

- **Error Handling**:
    - More descriptive error messages with context
    - Proper error chain preservation
    - Better handling of API error responses
    - Fixed validation error logging

- **Memory Management**:
    - Fixed potential memory leaks in metrics collection
    - Proper cleanup of background tasks
    - Limited history size with automatic trimming
    - Snapshot size validation

---

### 🗑️ Removed

- **Deprecated Features**:
    - Removed direct dictionary usage in internal methods
    - Removed redundant validation code (now in Validators class)
    - Removed hardcoded retry values (now configurable)

- **Simplified API**:
    - Removed internal helper methods now covered by mixins
    - Consolidated duplicate code into DRY utilities

---

### 📦 Dependencies

- **New Dependencies**:
    - `sortedcontainers` - For efficient metrics storage
    - `pydantic-settings` - For configuration management

- **Updated Dependencies**:
    - `pydantic` - Now requires v2.0+
    - `aiohttp` - Updated for better async support

---

### 🔧 Technical Improvements

#### **Code Organization**

- Modular architecture with clear separation of concerns
- 14 specialized modules vs. 3 in v0.3.0
- Over 5,000 lines of production-ready code
- Comprehensive inline documentation

#### **Testing & Quality**

- Type hints coverage: ~100%
- Docstring coverage: ~95%
- Protocol-based design for easy mocking
- Immutable data structures for thread safety

#### **Security**

- Automatic sensitive data masking
- Secure comparison for certificates
- Rate limiting to prevent abuse
- Certificate pinning for TLS connections
- No secrets in logs or string representations

#### **Observability**

- Structured logging with correlation IDs
- Comprehensive metrics collection
- Health check framework
- Audit trail for all operations
- Prometheus export format

---

### 📚 Documentation

- Enhanced docstrings with type information
- Comprehensive examples in each method
- Updated README with new features
- Configuration guide with best practices
- Migration guide from v0.3.0

---

### 🚀 Migration Guide (v0.3.0 → v0.4.0)

#### **1. Python Version**

```bash
# Ensure Python 3.10+
python --version  # Should be 3.10 or higher
```

#### **2. Installation**

```bash
# Install new version
pip install --upgrade pyoutlineapi

# Or with optional dependencies
pip install pyoutlineapi[dev]
```

#### **3. Basic Client Usage**

```python
# Old way (v0.3.0)
from pyoutlineapi import AsyncOutlineClient

client = AsyncOutlineClient(
    "https://server.com/path",
    "abc123...",
    json_format=False,
    timeout=30
)

# New way (v0.4.0) - Option 1: Direct instantiation
client = AsyncOutlineClient(
    api_url="https://server.com/path",
    cert_sha256="abc123...",
    timeout=10,
    enable_logging=True,
    rate_limit=50
)

# New way (v0.4.0) - Option 2: Configuration object
from pyoutlineapi import OutlineClientConfig

config = OutlineClientConfig.create_minimal(
    api_url="https://server.com/path",
    cert_sha256="abc123...",
    timeout=10,
    enable_logging=True
)
client = AsyncOutlineClient(config)

# New way (v0.4.0) - Option 3: Environment variables
# Create .env file first
client = AsyncOutlineClient.from_env()
```

#### **4. Using New Features**

```python
# Circuit breaker (automatic protection)
async with AsyncOutlineClient.create(
        api_url=url,
        cert_sha256=cert,
        enable_circuit_breaker=True,
        circuit_failure_threshold=5
) as client:
    # Automatically protected against cascading failures
    await client.get_server_info()

# Health monitoring
from pyoutlineapi.health_monitoring import HealthMonitor

monitor = HealthMonitor(client, cache_ttl=30)
health = await monitor.comprehensive_check()
print(f"Healthy: {health.healthy}")
print(f"Failed checks: {health.failed_checks}")

# Metrics collection
from pyoutlineapi.metrics_collector import MetricsCollector

async with MetricsCollector(client, interval=60) as collector:
    await collector.start()
    # ... your code ...
    stats = collector.get_usage_stats(period_minutes=60)
    print(f"Total GB: {stats.gigabytes_transferred:.2f}")

# Batch operations
from pyoutlineapi.batch_operations import BatchOperations

batch = BatchOperations(client, max_concurrent=5)
configs = [
    {"name": "User1", "port": 8388},
    {"name": "User2", "port": 8389},
]
result = await batch.create_multiple_keys(configs)
print(f"Success rate: {result.success_rate:.1%}")

# Audit logging
from pyoutlineapi import DefaultAuditLogger

audit = DefaultAuditLogger(enable_async=True)
client = AsyncOutlineClient(config, audit_logger=audit)
# All operations are now automatically audited
```

#### **5. Configuration Migration**

```python
# Old: Hardcoded values
client = AsyncOutlineClient(url, cert, timeout=30)

# New: Configuration object with validation
from pyoutlineapi import DevelopmentConfig, ProductionConfig

# Development
dev_config = DevelopmentConfig(
    api_url=url,
    cert_sha256=cert,
    enable_logging=True
)

# Production
prod_config = ProductionConfig.from_env(".env.prod")
```

---

### 🎯 Use Cases

#### **Enterprise Production Deployment**

```python
from pyoutlineapi import (
    AsyncOutlineClient,
    ProductionConfig,
    DefaultAuditLogger,
)

# Load production config with strict validation
config = ProductionConfig.from_env(
    ".env.prod",
    enable_circuit_breaker=True,
    circuit_failure_threshold=3,
    rate_limit=50
)

# Initialize with audit logging
audit_logger = DefaultAuditLogger(
    enable_async=True,
    queue_size=1000
)

async with AsyncOutlineClient(
        config,
        audit_logger=audit_logger
) as client:
    # All operations are protected and audited
    health = await client.health_check()
    if health:
        keys = await client.get_access_keys()
```

#### **Development & Testing**

```python
from pyoutlineapi import DevelopmentConfig

config = DevelopmentConfig(
    api_url="http://localhost:8080/secret",
    cert_sha256="0" * 64,  # Dev cert
    enable_logging=True,
    enable_circuit_breaker=False
)

async with AsyncOutlineClient(config) as client:
    # Development with detailed logging
    pass
```

---

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

### Migration Guide (v0.3.0)

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

---

[0.4.0]: https://github.com/orenlab/pyoutlineapi/compare/v0.3.0...v0.4.0

[0.3.0]: https://github.com/orenlab/pyoutlineapi/compare/v0.2.0...v0.3.0

[0.2.0]: https://github.com/orenlab/pyoutlineapi/compare/v0.1.2...v0.2.0

[0.1.2]: https://github.com/orenlab/pyoutlineapi/releases/tag/v0.1.2