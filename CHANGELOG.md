# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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