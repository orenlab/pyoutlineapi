# Security Policy

## Table of Contents

- [Reporting Security Vulnerabilities](#reporting-security-vulnerabilities)
- [Security Best Practices](#security-best-practices)
- [Secure Configuration](#secure-configuration)
- [Certificate Verification](#certificate-verification)
- [API Key Management](#api-key-management)
- [Network Security](#network-security)
- [Data Protection](#data-protection)
- [Logging and Monitoring](#logging-and-monitoring)
- [Deployment Security](#deployment-security)
- [Dependencies and Updates](#dependencies-and-updates)
- [Security Checklist](#security-checklist)

## Reporting Security Vulnerabilities

We take security seriously. If you discover a security vulnerability in PyOutlineAPI, please report it responsibly.

### How to Report

**DO NOT** create a public GitHub issue for security vulnerabilities.

Instead, please:

1. **Email us directly**: Send details to `pytelemonbot@mail.ru` with the subject line "SECURITY: PyOutlineAPI
   Vulnerability Report"

2. **Include the following information**:
    - Description of the vulnerability
    - Steps to reproduce the issue
    - Potential impact assessment
    - Suggested fix (if you have one)
    - Your contact information

3. **Response timeline**:
    - **24 hours**: Initial acknowledgment
    - **72 hours**: Preliminary assessment
    - **7 days**: Detailed response with timeline
    - **30 days**: Target resolution (may vary based on complexity)

### Responsible Disclosure

- Allow us reasonable time to investigate and fix the issue
- Do not publicly disclose the vulnerability until we've released a fix
- We will credit you in the security advisory (unless you prefer to remain anonymous)

## Security Best Practices

### 1. Certificate Verification

**Always verify TLS certificates** to prevent man-in-the-middle attacks:

```python
from pyoutlineapi import AsyncOutlineClient

# ✅ SECURE: Always provide certificate fingerprint
async with AsyncOutlineClient(
        api_url="https://your-server:port/path",
        cert_sha256="your-certificate-fingerprint",  # Required!
) as client:
    server = await client.get_server_info()

# ❌ INSECURE: Never skip certificate verification
# This would be vulnerable to MITM attacks
```

#### How to Get Certificate Fingerprint

```bash
# Method 1: Using OpenSSL
echo | openssl s_client -connect your-server:port 2>/dev/null | \
    openssl x509 -fingerprint -sha256 -noout | \
    cut -d'=' -f2 | tr -d ':'

# Method 2: Using curl and OpenSSL
curl -k https://your-server:port 2>/dev/null | \
    openssl x509 -fingerprint -sha256 -noout

# Method 3: From Outline Manager
# The certificate fingerprint is displayed in Outline Manager
# when you set up your server
```

### 2. Secure URL Handling

**Protect API URLs** as they contain sensitive authentication information:

```python
import os
from urllib.parse import urlparse

# ✅ SECURE: Store in environment variables
api_url = os.getenv("OUTLINE_API_URL")
cert_fingerprint = os.getenv("OUTLINE_CERT_SHA256")

if not api_url or not cert_fingerprint:
    raise ValueError("Missing required security credentials")

# ✅ SECURE: Validate URL format
parsed_url = urlparse(api_url)
if parsed_url.scheme != 'https':
    raise ValueError("API URL must use HTTPS")

async with AsyncOutlineClient(
        api_url=api_url,
        cert_sha256=cert_fingerprint
) as client:
    # Your code here
    pass
```

**Never hardcode credentials**:

```python
# ❌ INSECURE: Hardcoded credentials
client = AsyncOutlineClient(
    api_url="https://server:8080/secret-key-here",  # Don't do this!
    cert_sha256="abc123..."
)

# ❌ INSECURE: Credentials in version control
API_URL = "https://production-server/secret"  # Don't commit this!
```

### 3. Environment Variables

Use secure environment variable practices:

```python
import os
from pathlib import Path


# ✅ SECURE: Load from .env file (not in version control)
def load_secure_config():
    """Load configuration from secure sources."""

    # Check for required environment variables
    required_vars = ['OUTLINE_API_URL', 'OUTLINE_CERT_SHA256']
    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        raise ValueError(f"Missing required environment variables: {missing_vars}")

    return {
        'api_url': os.getenv('OUTLINE_API_URL'),
        'cert_sha256': os.getenv('OUTLINE_CERT_SHA256'),
    }


# Example .env file (add to .gitignore!)
"""
OUTLINE_API_URL=https://your-server:port/secret-path
OUTLINE_CERT_SHA256=your-certificate-fingerprint
"""
```

## Secure Configuration

### Connection Security

```python
from pyoutlineapi import AsyncOutlineClient

# ✅ SECURE: Recommended secure configuration
async with AsyncOutlineClient(
        api_url=os.getenv("OUTLINE_API_URL"),
        cert_sha256=os.getenv("OUTLINE_CERT_SHA256"),

        # Security settings
        timeout=30,  # Reasonable timeout
        retry_attempts=3,  # Limited retry attempts
        rate_limit_delay=0.1,  # Prevent rate limiting issues

        # Disable logging in production (avoid credential leaks)
        enable_logging=False,

        # Custom user agent (optional, for monitoring)
        user_agent="MySecureApp/1.0"
) as client:
    # Your secure operations
    pass
```

### Production vs Development

```python
import os


def create_secure_client():
    """Create client with environment-appropriate security settings."""

    is_production = os.getenv('ENVIRONMENT') == 'production'

    return AsyncOutlineClient(
        api_url=os.getenv("OUTLINE_API_URL"),
        cert_sha256=os.getenv("OUTLINE_CERT_SHA256"),

        # More restrictive settings in production
        timeout=30 if is_production else 60,
        retry_attempts=2 if is_production else 5,
        enable_logging=not is_production,  # No logging in production

        # Production-specific settings
        max_connections=5 if is_production else 10,
        rate_limit_delay=0.2 if is_production else 0.1,
    )
```

## Certificate Verification

### Understanding Certificate Pinning

PyOutlineAPI uses certificate pinning to prevent MITM attacks:

```python
# Certificate fingerprint verification process:
# 1. Client connects to server
# 2. Server presents TLS certificate
# 3. Client calculates SHA-256 fingerprint
# 4. Client compares with provided fingerprint
# 5. Connection proceeds only if fingerprints match

async def secure_connection_example():
    try:
        async with AsyncOutlineClient(
                api_url="https://your-server:port/path",
                cert_sha256="expected-fingerprint"
        ) as client:
            # Connection successful - certificate verified
            server = await client.get_server_info()
            return server

    except Exception as e:
        # Certificate mismatch or other security error
        print(f"Security error: {e}")
        raise
```

### Certificate Rotation

When your Outline server certificate changes:

```python
import asyncio
from pyoutlineapi import AsyncOutlineClient, APIError


async def handle_certificate_rotation():
    """Handle certificate changes gracefully."""

    primary_cert = os.getenv("OUTLINE_CERT_PRIMARY")
    backup_cert = os.getenv("OUTLINE_CERT_BACKUP")  # New certificate

    # Try primary certificate first
    try:
        async with AsyncOutlineClient(
                api_url=os.getenv("OUTLINE_API_URL"),
                cert_sha256=primary_cert
        ) as client:
            return await client.get_server_info()

    except APIError as e:
        if "certificate" in str(e).lower():
            # Certificate might have changed, try backup
            async with AsyncOutlineClient(
                    api_url=os.getenv("OUTLINE_API_URL"),
                    cert_sha256=backup_cert
            ) as client:
                return await client.get_server_info()
        else:
            raise
```

## API Key Management

### Access Key Security

```python
from pyoutlineapi import AsyncOutlineClient, DataLimit
import secrets
import string


async def secure_key_management():
    """Demonstrate secure access key management practices."""

    async with AsyncOutlineClient(...) as client:
        # ✅ SECURE: Use strong, unique names
        def generate_secure_key_name():
            """Generate secure, unique key identifier."""
            return f"user_{secrets.token_hex(8)}"

        # ✅ SECURE: Set appropriate data limits
        key = await client.create_access_key(
            name=generate_secure_key_name(),
            limit=DataLimit(bytes=10 * 1024 ** 3),  # 10 GB limit
        )

        # ✅ SECURE: Use custom encryption methods when needed
        secure_key = await client.create_access_key(
            name=generate_secure_key_name(),
            method="chacha20-ietf-poly1305",  # Strong encryption
            limit=DataLimit(bytes=5 * 1024 ** 3)
        )

        return [key, secure_key]


# ❌ INSECURE: Predictable key names
await client.create_access_key(name="user1")  # Too predictable
await client.create_access_key(name="admin")  # Reveals purpose

# ❌ INSECURE: No data limits
await client.create_access_key(name="unlimited")  # No usage control
```

### Key Lifecycle Management

```python
async def secure_key_lifecycle():
    """Manage access keys securely throughout their lifecycle."""

    async with AsyncOutlineClient(...) as client:

        # Create key with appropriate limits
        key = await client.create_access_key(
            name=f"temp_user_{secrets.token_hex(4)}",
            limit=DataLimit(bytes=1024 ** 3)  # 1 GB
        )

        try:
            # Use the key...
            yield key.access_url

        finally:
            # ✅ SECURE: Always clean up temporary keys
            await client.delete_access_key(key.id)
            print(f"Key {key.id} securely deleted")


# ✅ SECURE: Monitor key usage
async def monitor_key_usage():
    """Monitor access key usage for security purposes."""

    async with AsyncOutlineClient(...) as client:
        metrics = await client.get_transfer_metrics()

        # Check for unusual usage patterns
        for key_id, bytes_used in metrics.bytes_transferred_by_user_id.items():
            gb_used = bytes_used / 1024 ** 3

            if gb_used > 50:  # Threshold for investigation
                print(f"WARNING: Key {key_id} used {gb_used:.2f} GB")

                # Consider implementing automated responses:
                # - Reduce data limit
                # - Temporarily disable key
                # - Send alert to administrators
```

## Network Security

### Secure Connection Practices

```python
import ssl
import aiohttp
from pyoutlineapi import AsyncOutlineClient


async def network_security_example():
    """Demonstrate network security best practices."""

    # ✅ SECURE: Use proper SSL context if needed for custom configurations
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = True
    ssl_context.verify_mode = ssl.CERT_REQUIRED

    connector = aiohttp.TCPConnector(
        ssl=ssl_context,
        limit=10,  # Connection pool limit
        limit_per_host=5,  # Per-host connection limit
        ttl_dns_cache=300,  # DNS cache TTL
        use_dns_cache=True,
    )

    # Note: PyOutlineAPI handles SSL verification internally
    # This is just an example of additional security measures

    async with AsyncOutlineClient(
            api_url=os.getenv("OUTLINE_API_URL"),
            cert_sha256=os.getenv("OUTLINE_CERT_SHA256"),
            timeout=30,  # Reasonable timeout
            max_connections=5,  # Limit concurrent connections
    ) as client:
        # Verify server health before operations
        if not await client.health_check():
            raise ConnectionError("Server health check failed")

        return await client.get_server_info()
```

### Firewall and Network Configuration

```python
async def network_hardening_checks():
    """Check network security configuration."""

    async with AsyncOutlineClient(...) as client:
        # Get server info to check configuration
        server = await client.get_server_info()

        # ✅ SECURE: Verify server configuration
        security_checks = {
            'has_name': bool(server.name),
            'version_recent': server.version >= "1.8.0",
            'port_configured': server.port_for_new_access_keys is not None,
        }

        # Check metrics status (disable in high-security environments)
        metrics_status = await client.get_metrics_status()
        security_checks['metrics_disabled'] = not metrics_status.metrics_enabled

        # Report security status
        for check, status in security_checks.items():
            print(f"Security check {check}: {'✅' if status else '❌'}")

        return all(security_checks.values())
```

## Data Protection

### Sensitive Data Handling

```python
import json
from typing import Any, Dict


class SecureDataHandler:
    """Handle sensitive data securely."""

    @staticmethod
    def sanitize_for_logging(data: Dict[str, Any]) -> Dict[str, Any]:
        """Remove sensitive information from data before logging."""

        sensitive_keys = {
            'access_url', 'password', 'secret', 'key', 'token',
            'cert', 'fingerprint', 'api_url'
        }

        sanitized = {}
        for key, value in data.items():
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                sanitized[key] = "[REDACTED]"
            elif isinstance(value, str) and len(value) > 50:
                # Truncate long strings that might contain secrets
                sanitized[key] = value[:20] + "...[TRUNCATED]"
            else:
                sanitized[key] = value

        return sanitized

    @staticmethod
    def secure_logging_example():
        """Example of secure logging practices."""

        # ❌ INSECURE: Logging sensitive data
        # logger.info(f"Created key: {key.access_url}")

        # ✅ SECURE: Log without sensitive information
        # logger.info(f"Created key with ID: {key.id}")


async def secure_data_operations():
    """Demonstrate secure data handling."""

    async with AsyncOutlineClient(
            api_url=os.getenv("OUTLINE_API_URL"),
            cert_sha256=os.getenv("OUTLINE_CERT_SHA256"),
            enable_logging=False  # Disable to prevent credential leaks
    ) as client:
        # Create access key
        key = await client.create_access_key(name="secure_user")

        # ✅ SECURE: Store only necessary information
        key_info = {
            'id': key.id,
            'name': key.name,
            'created_at': key.id,  # Use ID as creation timestamp
            # Don't store access_url in logs or databases
        }

        # ✅ SECURE: Provide access_url securely to end user
        # (e.g., through encrypted channel, secure API response, etc.)
        return {
            'key_id': key.id,
            'access_url': key.access_url,  # Only in direct response
            'status': 'created'
        }
```

### Memory Security

```python
import gc
from typing import Optional


class SecurityAwareClient:
    """Client wrapper with security-focused memory management."""

    def __init__(self, api_url: str, cert_sha256: str):
        self._api_url = api_url
        self._cert_sha256 = cert_sha256
        self._client: Optional[AsyncOutlineClient] = None

    async def __aenter__(self):
        self._client = AsyncOutlineClient(
            api_url=self._api_url,
            cert_sha256=self._cert_sha256,
            enable_logging=False
        )
        return await self._client.__aenter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            result = await self._client.__aexit__(exc_type, exc_val, exc_tb)

            # ✅ SECURE: Clear sensitive data from memory
            self._api_url = None
            self._cert_sha256 = None
            self._client = None

            # Force garbage collection to clear sensitive data
            gc.collect()

            return result
```

## Logging and Monitoring

### Security-Conscious Logging

```python
import logging
import re
from typing import Any


class SecureFormatter(logging.Formatter):
    """Custom formatter that redacts sensitive information."""

    # Patterns that might contain sensitive data
    SENSITIVE_PATTERNS = [
        r'(access_url["\']?\s*[:=]\s*["\']?)([^"\'\\s]+)',
        r'(password["\']?\s*[:=]\s*["\']?)([^"\'\\s]+)',
        r'(secret["\']?\s*[:=]\s*["\']?)([^"\'\\s]+)',
        r'(cert_sha256["\']?\s*[:=]\s*["\']?)([^"\'\\s]+)',
        r'(api_url["\']?\s*[:=]\s*["\']?)([^"\'\\s]+)',
    ]

    def format(self, record: logging.LogRecord) -> str:
        # Format the record normally first
        formatted = super().format(record)

        # Redact sensitive information
        for pattern in self.SENSITIVE_PATTERNS:
            formatted = re.sub(pattern, r'\1[REDACTED]', formatted, flags=re.IGNORECASE)

        return formatted


def setup_secure_logging():
    """Set up logging with security considerations."""

    # Create secure formatter
    formatter = SecureFormatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Configure handler
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    # Configure logger
    logger = logging.getLogger('pyoutlineapi')
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)  # Don't use DEBUG in production

    return logger


async def secure_logging_example():
    """Example of secure logging practices."""

    logger = setup_secure_logging()

    async with AsyncOutlineClient(
            api_url=os.getenv("OUTLINE_API_URL"),
            cert_sha256=os.getenv("OUTLINE_CERT_SHA256"),
            enable_logging=True  # Now safe with secure formatter
    ) as client:
        # Log operations without sensitive data
        logger.info("Attempting to connect to Outline server")

        server = await client.get_server_info()
        logger.info(f"Connected to server: {server.name}")

        # ✅ SECURE: Log events without sensitive information
        key = await client.create_access_key(name="user123")
        logger.info(f"Created access key with ID: {key.id}")

        # ❌ INSECURE: Don't log the access URL
        # logger.info(f"Access URL: {key.access_url}")
```

### Security Monitoring

```python
import time
from collections import defaultdict
from typing import Dict, List


class SecurityMonitor:
    """Monitor for suspicious activities."""

    def __init__(self):
        self.request_counts: Dict[str, List[float]] = defaultdict(list)
        self.failed_requests: Dict[str, int] = defaultdict(int)

    def log_request(self, endpoint: str, success: bool):
        """Log API request for monitoring."""
        current_time = time.time()

        # Track request frequency
        self.request_counts[endpoint].append(current_time)

        # Clean old entries (keep last hour)
        hour_ago = current_time - 3600
        self.request_counts[endpoint] = [
            t for t in self.request_counts[endpoint] if t > hour_ago
        ]

        # Track failures
        if not success:
            self.failed_requests[endpoint] += 1

    def check_rate_limits(self, endpoint: str, max_per_hour: int = 1000) -> bool:
        """Check if request rate is suspicious."""
        return len(self.request_counts[endpoint]) > max_per_hour

    def check_failure_rate(self, endpoint: str, max_failures: int = 10) -> bool:
        """Check if failure rate is suspicious."""
        return self.failed_requests[endpoint] > max_failures


async def monitored_operations():
    """Example of security monitoring in practice."""

    monitor = SecurityMonitor()

    async with AsyncOutlineClient(...) as client:

        try:
            # Monitor server access
            monitor.log_request("get_server_info", True)
            server = await client.get_server_info()

            # Check for suspicious activity
            if monitor.check_rate_limits("get_server_info"):
                print("WARNING: High request rate detected")

            if monitor.check_failure_rate("get_server_info"):
                print("WARNING: High failure rate detected")

        except Exception as e:
            monitor.log_request("get_server_info", False)
            raise
```

## Deployment Security

### Container Security

```dockerfile
# Dockerfile security best practices
FROM python:3.13-alpine

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser

# Set work directory
WORKDIR /app

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Switch to non-root user
USER appuser

# Set secure environment
ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Run application
CMD ["python", "app.py"]
```

```yaml
# docker-compose.yml security considerations
version: '3.8'
services:
  pyoutlineapi-app:
    build: .
    environment:
      - OUTLINE_API_URL_FILE=/run/secrets/outline_api_url
      - OUTLINE_CERT_SHA256_FILE=/run/secrets/outline_cert
    secrets:
      - outline_api_url
      - outline_cert
    networks:
      - internal
    restart: unless-stopped

    # Security constraints
    read_only: true
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true

secrets:
  outline_api_url:
    external: true
  outline_cert:
    external: true

networks:
  internal:
    driver: bridge
```

### Environment Security

```python
# secure_config.py
import os
from pathlib import Path
from typing import Optional


class SecureConfig:
    """Secure configuration management."""

    @staticmethod
    def load_from_file(file_path: str) -> Optional[str]:
        """Load secret from file (for Docker secrets)."""
        try:
            return Path(file_path).read_text().strip()
        except (FileNotFoundError, PermissionError):
            return None

    @classmethod
    def get_outline_config(cls) -> dict:
        """Get Outline configuration from secure sources."""

        # Try Docker secrets first
        api_url = cls.load_from_file('/run/secrets/outline_api_url')
        cert_sha256 = cls.load_from_file('/run/secrets/outline_cert')

        # Fall back to environment variables
        if not api_url:
            api_url = os.getenv('OUTLINE_API_URL')
        if not cert_sha256:
            cert_sha256 = os.getenv('OUTLINE_CERT_SHA256')

        if not api_url or not cert_sha256:
            raise ValueError("Missing required Outline configuration")

        return {
            'api_url': api_url,
            'cert_sha256': cert_sha256
        }


# Usage in application
async def secure_app_startup():
    """Start application with secure configuration."""

    try:
        config = SecureConfig.get_outline_config()

        async with AsyncOutlineClient(
                api_url=config['api_url'],
                cert_sha256=config['cert_sha256'],
                enable_logging=False  # Disable in production
        ) as client:

            # Verify connection security
            if not await client.health_check():
                raise ConnectionError("Failed to establish secure connection")

            return client

    except Exception as e:
        # Log security errors (without sensitive details)
        print(f"Security configuration error: {type(e).__name__}")
        raise
```

## Dependencies and Updates

### Dependency Security

```bash
# Check for known vulnerabilities
pip install safety
safety check

# Check for outdated packages
pip install pip-audit
pip-audit

# Use pip-tools for reproducible builds
pip install pip-tools
pip-compile --generate-hashes requirements.in
```

### Update Management

```python
# version_check.py
import aiohttp
import asyncio
from packaging import version


async def check_pyoutlineapi_version():
    """Check if PyOutlineAPI version is up to date."""

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('https://pypi.org/pypi/pyoutlineapi/json') as resp:
                data = await resp.json()
                latest_version = data['info']['version']

                # Compare with current version
                import pyoutlineapi
                current_version = pyoutlineapi.__version__

                if version.parse(current_version) < version.parse(latest_version):
                    print(f"WARNING: PyOutlineAPI {latest_version} available (current: {current_version})")
                    print("Consider updating for latest security fixes")
                    return False

                return True

    except Exception as e:
        print(f"Could not check for updates: {e}")
        return None


# Run version check
if __name__ == "__main__":
    asyncio.run(check_pyoutlineapi_version())
```

## Security Checklist

### Pre-Deployment Checklist

- [ ] **Certificate Verification**
    - [ ] Certificate fingerprint is correctly configured
    - [ ] No hardcoded certificates in code
    - [ ] Certificate rotation process is documented

- [ ] **Credential Management**
    - [ ] API URLs stored securely (environment variables/secrets)
    - [ ] No credentials in version control
    - [ ] Secrets management system in place

- [ ] **Network Security**
    - [ ] HTTPS-only connections enforced
    - [ ] Proper firewall rules configured
    - [ ] Rate limiting implemented

- [ ] **Access Control**
    - [ ] Appropriate data limits set on access keys
    - [ ] Key naming conventions follow security guidelines
    - [ ] Regular key rotation schedule established

- [ ] **Monitoring and Logging**
    - [ ] Security logging configured
    - [ ] Sensitive data redaction implemented
    - [ ] Monitoring for suspicious activities

- [ ] **Code Security**
    - [ ] Static analysis tools run (bandit, safety)
    - [ ] Dependencies audited for vulnerabilities
    - [ ] Security tests included in CI/CD

### Runtime Security Checklist

- [ ] **Connection Security**
    - [ ] Health checks passing
    - [ ] Certificate validation working
    - [ ] No connection errors or timeouts

- [ ] **Access Key Management**
    - [ ] Regular usage monitoring
    - [ ] Cleanup of unused keys
    - [ ] Data limit enforcement

- [ ] **System Security**
    - [ ] Log monitoring active
    - [ ] No sensitive data in logs
    - [ ] Error handling not exposing internals

### Incident Response

If you suspect a security incident:

1. **Immediate Actions**:
    - Rotate API credentials
    - Check access logs for suspicious activity
    - Disable affected access keys
    - Document the incident

2. **Investigation**:
    - Review server metrics for unusual patterns
    - Check for unauthorized access key creation/modification
    - Analyze network traffic logs

3. **Recovery**:
    - Update credentials and certificates
    - Implement additional security measures
    - Update incident response procedures

4. **Reporting**:
    - Report security incidents to `pytelemonbot@mail.ru`
    - Document lessons learned
    - Update security procedures

---

## Additional Resources

- [OWASP Security Guidelines](https://owasp.org/)
- [Python Security Best Practices](https://python-security.readthedocs.io/)
- [Outline Server Security](https://github.com/Jigsaw-Code/outline-server/blob/main/docs/security.md)
- [TLS Certificate Pinning](https://owasp.org/www-community/controls/Certificate_and_Public_Key_Pinning)