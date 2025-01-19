# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - work-in-progress

### Added

- Advanced rate limiting system with Token Bucket algorithm
    - Integer-based implementation for better performance
    - Configurable rate and burst parameters per endpoint
    - Decorator-based rate limiting for API methods
    - Async-safe implementation with proper locking
    - Nanosecond precision for token calculations
- New classes for rate limiting:
    - `TokenBucket`: Core rate limiting implementation
    - `TokenBucketConfig`: Immutable configuration storage
    - `RateLimiter`: High-level rate limiting manager
- Constants for request retry configuration:
    - `DEFAULT_RETRY_ATTEMPTS`: Default number of retry attempts
    - `DEFAULT_RETRY_DELAY`: Base delay between retries
    - `RETRY_STATUS_CODES`: Set of HTTP status codes eligible for retry
- Constants for port range validation:
    - `MIN_PORT`: Minimum allowed port number (1025)
    - `MAX_PORT`: Maximum allowed port number (65535)
- Robust request retry mechanism for handling transient failures
    - New configurable retry attempts parameter (default: 3 attempts)
    - Automatic retry for specific HTTP status codes (408, 429, 500, 502, 503, 504)
    - Exponential backoff delay between retry attempts
- Enhanced error tracking with attempt number in error messages
- Extended API error information including retry attempt count

### Changed

- Improved memory efficiency with extensive use of `__slots__`
- Enhanced type safety with stricter type annotations
- Integer-based calculations instead of floating-point for rate limiting
- Improved error handling with more detailed error messages
- Refactored request handling into separate `_make_request` and `_retry_request` methods
- Enhanced type annotations throughout the codebase
- Modified port validation to use constant values
- Updated error messages to include retry attempt information
- Optimized session handling and connection management
- Default timeout reduced from 30.0 to 10 seconds for better responsiveness

### Fixed

- More robust handling of connection failures and timeouts
- Better cleanup of resources during session closure
- Improved validation of API responses
- More consistent error handling across all API methods

### Internal

- Added immutable configuration objects for rate limiting
- Implemented nanosecond-precision timing for rate limiting
- Added comprehensive input validation for rate limiting parameters
- Enhanced error handling for rate limiting edge cases
- Reorganized code structure for better maintainability
- Added detailed type annotations for internal methods
- Improved documentation and code examples
- Enhanced error hierarchy for better error handling

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

[0.2.0]: https://github.com/username/repo/compare/v0.1.2...v0.2.0

[0.1.2]: https://github.com/username/repo/releases/tag/v0.1.2