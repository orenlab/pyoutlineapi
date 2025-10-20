# Security Policy

## Table of Contents

- [Reporting Security Vulnerabilities](#reporting-security-vulnerabilities)
- [Security Architecture](#security-architecture)
- [Secure Configuration](#secure-configuration)
- [Certificate Pinning](#certificate-pinning)
- [Credential Management](#credential-management)
- [Network Security](#network-security)
- [Data Protection](#data-protection)
- [Audit Logging](#audit-logging)
- [Circuit Breaker Security](#circuit-breaker-security)
- [Deployment Security](#deployment-security)
- [Dependencies and Updates](#dependencies-and-updates)
- [Security Checklist](#security-checklist)
- [Incident Response](#incident-response)

---

## Reporting Security Vulnerabilities

We take security seriously. If you discover a security vulnerability in PyOutlineAPI, please report it responsibly.

### How to Report

**DO NOT** create a public GitHub issue for security vulnerabilities.

Instead, please:

1. **Email us directly**: `pytelemonbot@mail.ru`
    - Subject: `[SECURITY] PyOutlineAPI Vulnerability Report`
    - Include: Description, reproduction steps, impact assessment, suggested fix

2. **Response Timeline**:
    - ✅ **24 hours**: Initial acknowledgment
    - ⚡ **72 hours**: Preliminary assessment and severity classification
    - 📋 **7 days**: Detailed response with remediation timeline
    - 🔧 **30 days**: Target resolution (varies by complexity and severity)

3. **Responsible Disclosure**:
    - Allow reasonable time to investigate and fix (minimum 90 days)
    - Do not publicly disclose until patch is released
    - We will credit you in security advisory (unless you prefer anonymity)
    - Coordinated disclosure with CVE assignment for critical issues

### Security Advisory Process

When a vulnerability is confirmed:

1. **Assessment**: Severity classification (Critical/High/Medium/Low)
2. **Patch Development**: Fix created and tested
3. **Security Advisory**: Published on GitHub Security Advisories
4. **CVE Assignment**: For vulnerabilities with CVSS score ≥ 4.0
5. **Release**: Patched version published to PyPI
6. **Notification**: Security advisory sent to users

---

## Security Architecture

### Defense in Depth

PyOutlineAPI v0.4.0 implements multiple security layers:

```
┌─────────────────────────────────────────┐
│  Application Layer                      │
│  • Input Validation (Pydantic v2)       │
│  • Output Sanitization                  │
│  • Audit Logging                        │
└─────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────┐
│  Client Layer                           │
│  • Circuit Breaker (Failure Protection) │
│  • Rate Limiting (DoS Protection)       │
│  • Request Timeout Enforcement          │
│  • Correlation ID Tracking              │
└─────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────┐
│  Transport Layer                        │
│  • TLS 1.2+ Enforcement                 │
│  • Certificate Pinning (SHA-256)        │
│  • Connection Pool Management           │
│  • Secure Headers                       │
└─────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────┐
│  Data Layer                             │
│  • SecretStr for Credentials            │
│  • Sensitive Data Masking               │
│  • Memory Security (gc clearing)        │
│  • No Secrets in Logs                   │
└─────────────────────────────────────────┘
```

### Security Features Summary

| Feature                 | Protection Against      | Implementation                              |
|-------------------------|-------------------------|---------------------------------------------|
| **Certificate Pinning** | MITM attacks            | SHA-256 fingerprint verification            |
| **SecretStr**           | Credential exposure     | Pydantic SecretStr type                     |
| **Audit Logging**       | Unauthorized actions    | Async queue with sanitization               |
| **Circuit Breaker**     | Service degradation     | 3-state circuit with metrics                |
| **Rate Limiting**       | DoS/resource exhaustion | Semaphore-based concurrency control         |
| **Input Validation**    | Injection attacks       | Pydantic models with strict validation      |
| **Output Sanitization** | Information disclosure  | Automatic masking of 32+ sensitive patterns |
| **Correlation IDs**     | Request tracking/replay | Cryptographically secure tokens             |

---

## Secure Configuration

### Configuration Security Hierarchy (Best to Worst)

```python
from pyoutlineapi import AsyncOutlineClient, ProductionConfig
from pydantic import SecretStr

# ✅ BEST: Production config with environment variables
config = ProductionConfig.from_env()
# - Enforces HTTPS
# - Enables circuit breaker
# - Validates all settings
# - Secrets never in code

async with AsyncOutlineClient(config) as client:
    await client.get_server_info()

# ✅ GOOD: Environment variables with overrides
async with AsyncOutlineClient.from_env(
        enable_circuit_breaker=True,
        circuit_failure_threshold=5,
        enable_logging=False  # Disable in production
) as client:
    await client.get_server_info()

# ⚠️ ACCEPTABLE: Direct config with SecretStr
config = OutlineClientConfig(
    api_url="https://server.com/path",
    cert_sha256=SecretStr("abc123..."),  # SecretStr protects from accidental exposure
    enable_circuit_breaker=True
)

# ❌ DANGEROUS: Hardcoded credentials
client = AsyncOutlineClient(
    api_url="https://server.com/secret",  # Secret visible in code!
    cert_sha256="abc123...",  # String instead of SecretStr
    enable_circuit_breaker=False  # No protection
)
```

### Environment Variable Configuration

**Recommended `.env` structure:**

```bash
# === Required Security Settings ===
OUTLINE_API_URL=https://your-server.com:12345/your-secret-path
OUTLINE_CERT_SHA256=your-64-character-sha256-fingerprint

# === Security Features (Production Defaults) ===
OUTLINE_ENABLE_CIRCUIT_BREAKER=true
OUTLINE_CIRCUIT_FAILURE_THRESHOLD=5
OUTLINE_CIRCUIT_RECOVERY_TIMEOUT=60.0
OUTLINE_ENABLE_LOGGING=false  # CRITICAL: Disable in production

# === Connection Security ===
OUTLINE_TIMEOUT=10
OUTLINE_RETRY_ATTEMPTS=2
OUTLINE_MAX_CONNECTIONS=10
OUTLINE_RATE_LIMIT=50

# === Optional Security Hardening ===
OUTLINE_USER_AGENT=MySecureApp/1.0
OUTLINE_JSON_FORMAT=false
```

**Critical Security Rules:**

1. ✅ **Always add `.env` to `.gitignore`**
2. ✅ **Use different credentials per environment**
3. ✅ **Rotate credentials regularly (every 90 days)**
4. ✅ **Use read-only environment variables in production**
5. ❌ **Never commit `.env` files to version control**

### Configuration Validation

```python
from pyoutlineapi import OutlineClientConfig, ConfigurationError


def validate_production_config():
    """Validate configuration meets security requirements."""
    try:
        config = OutlineClientConfig.from_env()

        # Security checks
        checks = {
            "HTTPS Enforced": config.api_url.startswith("https://"),
            "Circuit Breaker Enabled": config.enable_circuit_breaker,
            "Logging Disabled": not config.enable_logging,
            "Reasonable Timeout": 5 <= config.timeout <= 30,
            "Rate Limited": config.rate_limit <= 100,
        }

        failed = [name for name, passed in checks.items() if not passed]

        if failed:
            raise ConfigurationError(
                f"Security validation failed: {', '.join(failed)}"
            )

        return config

    except ConfigurationError as e:
        print(f"❌ Configuration error: {e}")
        raise
```

---

## Certificate Pinning

### Understanding Certificate Pinning

PyOutlineAPI uses **SHA-256 certificate pinning** to prevent man-in-the-middle (MITM) attacks:

```python
# How it works:
# 1. Client extracts server's TLS certificate
# 2. Calculates SHA-256 fingerprint
# 3. Compares with configured fingerprint
# 4. Connection ONLY proceeds if they match
# 5. Any mismatch = immediate connection failure

from pyoutlineapi import AsyncOutlineClient

async with AsyncOutlineClient.from_env() as client:
    # Certificate automatically verified on every request
    server = await client.get_server_info()
```

### Obtaining Certificate Fingerprint

**Method 1: OpenSSL (Recommended)**

```bash
# Extract SHA-256 fingerprint
echo | openssl s_client -connect your-server.com:12345 2>/dev/null | \
    openssl x509 -fingerprint -sha256 -noout | \
    cut -d'=' -f2 | tr -d ':' | tr '[:upper:]' '[:lower:]'

# Output: abc123def456... (64 characters)
```

**Method 2: Outline Manager**

The certificate fingerprint is displayed in Outline Manager when you add a server.

**Method 3: Python Script**

```python
import ssl
import hashlib
import socket


def get_certificate_fingerprint(hostname: str, port: int) -> str:
    """Extract SHA-256 fingerprint from server certificate."""
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    with socket.create_connection((hostname, port)) as sock:
        with context.wrap_socket(sock, server_hostname=hostname) as ssock:
            cert_der = ssock.getpeercert(binary_form=True)
            fingerprint = hashlib.sha256(cert_der).hexdigest()
            return fingerprint


# Usage
fingerprint = get_certificate_fingerprint("your-server.com", 12345)
print(f"Certificate SHA-256: {fingerprint}")
```

### Certificate Rotation

**When server certificate changes:**

```python
from pyoutlineapi import AsyncOutlineClient, ConnectionError
import asyncio


async def handle_certificate_rotation():
    """Gracefully handle certificate updates."""

    # Strategy 1: Dual certificate support (recommended)
    certificates = [
        os.getenv("OUTLINE_CERT_PRIMARY"),  # Current cert
        os.getenv("OUTLINE_CERT_BACKUP"),  # New cert (during rotation)
    ]

    for cert in certificates:
        try:
            async with AsyncOutlineClient.from_env(
                    cert_sha256=cert
            ) as client:
                await client.get_server_info()
                print(f"✅ Connected with certificate: {cert[:16]}...")
                return client

        except ConnectionError as e:
            if "certificate" in str(e).lower():
                print(f"⚠️ Certificate mismatch: {cert[:16]}...")
                continue
            raise

    raise ConnectionError("All certificates failed validation")


# Strategy 2: Automated certificate monitoring
async def monitor_certificate_expiry():
    """Monitor certificate expiration and alert."""
    import ssl
    import datetime

    # This would be implemented based on your certificate source
    # Alert 30 days before expiration
    pass
```

**Certificate Rotation Best Practices:**

1. ✅ Test new certificate in staging first
2. ✅ Deploy new certificate to client before server rotation
3. ✅ Maintain both old and new certificates during transition (24-48h)
4. ✅ Monitor connection failures during rotation window
5. ✅ Document rotation procedure and schedule

---

## Credential Management

### Secure Credential Storage

```python
from pyoutlineapi import AsyncOutlineClient
from pydantic import SecretStr
import os
from pathlib import Path


# ✅ BEST: Docker Secrets (Orchestrated environments)
def load_from_docker_secret(secret_name: str) -> str:
    """Load credential from Docker secret."""
    secret_path = Path(f"/run/secrets/{secret_name}")
    if not secret_path.exists():
        raise ValueError(f"Secret not found: {secret_name}")

    # Secrets are read-only, owned by root
    return secret_path.read_text().strip()


async with AsyncOutlineClient(
        api_url=load_from_docker_secret("outline_api_url"),
        cert_sha256=load_from_docker_secret("outline_cert_sha256")
) as client:
    pass


# ✅ GOOD: Environment Variables with Validation
def load_from_env_secure() -> dict:
    """Load and validate credentials from environment."""
    api_url = os.getenv("OUTLINE_API_URL")
    cert = os.getenv("OUTLINE_CERT_SHA256")

    if not api_url or not cert:
        raise ValueError("Missing required credentials")

    # Validate format
    if not api_url.startswith("https://"):
        raise ValueError("API URL must use HTTPS")

    if len(cert) != 64 or not all(c in "0123456789abcdef" for c in cert.lower()):
        raise ValueError("Invalid certificate fingerprint format")

    return {"api_url": api_url, "cert_sha256": cert}


# ✅ ACCEPTABLE: Vault/KMS Integration
async def load_from_vault():
    """Load credentials from HashiCorp Vault or AWS Secrets Manager."""
    # Example with hvac (HashiCorp Vault client)
    import hvac

    client = hvac.Client(url=os.getenv("VAULT_ADDR"))
    client.auth.approle.login(
        role_id=os.getenv("VAULT_ROLE_ID"),
        secret_id=os.getenv("VAULT_SECRET_ID")
    )

    secret = client.secrets.kv.v2.read_secret_version(
        path="outline/production"
    )

    return {
        "api_url": secret["data"]["data"]["api_url"],
        "cert_sha256": secret["data"]["data"]["cert_sha256"]
    }


# ❌ NEVER: Hardcoded Credentials
API_URL = "https://prod.example.com/secret123"  # NEVER DO THIS!
CERT = "abc123..."  # NEVER DO THIS!
```

### Credential Rotation

```python
import asyncio
from datetime import datetime, timedelta


class CredentialRotator:
    """Automated credential rotation handler."""

    def __init__(self, rotation_interval_days: int = 90):
        self.rotation_interval = timedelta(days=rotation_interval_days)
        self.last_rotation = datetime.now()

    async def check_rotation_needed(self) -> bool:
        """Check if credentials need rotation."""
        time_since_rotation = datetime.now() - self.last_rotation
        return time_since_rotation >= self.rotation_interval

    async def rotate_credentials(self):
        """Rotate credentials with zero downtime."""
        # 1. Generate new credentials
        new_creds = await self.generate_new_credentials()

        # 2. Update service with new credentials
        await self.update_service_credentials(new_creds)

        # 3. Wait for propagation (grace period)
        await asyncio.sleep(60)

        # 4. Test new credentials
        if await self.test_credentials(new_creds):
            # 5. Update environment/secrets manager
            await self.update_stored_credentials(new_creds)

            # 6. Mark rotation complete
            self.last_rotation = datetime.now()
            return True

        # Rollback if test fails
        await self.rollback_credentials()
        return False
```

### Access Key Security

```python
from pyoutlineapi import AsyncOutlineClient
from pyoutlineapi.models import DataLimit
import secrets
import hashlib


async def create_secure_access_key():
    """Create access key with security best practices."""

    async with AsyncOutlineClient.from_env() as client:
        # ✅ SECURE: Generate cryptographically secure key name
        key_name = hashlib.sha256(
            secrets.token_bytes(32)
        ).hexdigest()[:16]

        # ✅ SECURE: Set appropriate data limit
        key = await client.create_access_key(
            name=f"user_{key_name}",
            method="chacha20-ietf-poly1305",  # Strong encryption
            limit=DataLimit.from_gigabytes(10)  # Enforce limits
        )

        # ✅ SECURE: Log creation without sensitive data
        from pyoutlineapi import get_default_audit_logger
        logger = get_default_audit_logger()
        logger.log_action(
            action="create_key",
            resource=key.id,
            details={"name": key.name, "has_limit": True}
        )

        return key


# ❌ INSECURE: Predictable patterns
await client.create_access_key(name="user1")  # Sequential
await client.create_access_key(name="admin")  # Reveals purpose
await client.create_access_key(name="test123")  # Predictable

# ❌ INSECURE: No limits
await client.create_access_key(name="unlimited")  # Can exhaust resources
```

---

## Network Security

### TLS Configuration

```python
from pyoutlineapi import OutlineClientConfig, AsyncOutlineClient
from pydantic import SecretStr

# ✅ SECURE: Enforce TLS 1.2+ (automatic in PyOutlineAPI)
config = OutlineClientConfig(
    api_url="https://server.com/path",  # HTTPS enforced
    cert_sha256=SecretStr("abc123..."),
    timeout=10,  # Prevent slowloris attacks
    max_connections=10,  # Limit resource usage
    rate_limit=50,  # Prevent DoS
)

# Production config automatically enforces HTTPS
from pyoutlineapi import ProductionConfig

prod_config = ProductionConfig.from_env()
# - Raises error if HTTP is used
# - Enforces certificate pinning
# - Enables circuit breaker
```

### Rate Limiting (DoS Protection)

```python
from pyoutlineapi import AsyncOutlineClient

async with AsyncOutlineClient.from_env(
        rate_limit=50,  # Max 50 concurrent requests
        max_connections=20,  # Connection pool limit
) as client:
    # Check rate limiter status
    stats = client.get_rate_limiter_stats()
    print(f"Active: {stats['active']}/{stats['limit']}")
    print(f"Available: {stats['available']}")

    # Dynamic adjustment based on load
    if stats['available'] < 5:
        await client.set_rate_limit(100)  # Increase temporarily

    # Monitor for abuse
    if client.active_requests > stats['limit'] * 0.9:
        print("⚠️ WARNING: High request rate detected")
```

### Request Timeout Protection

```python
from pyoutlineapi import AsyncOutlineClient, TimeoutError


async def timeout_protected_operation():
    """Demonstrate timeout protection."""

    async with AsyncOutlineClient.from_env(timeout=10) as client:
        try:
            # Operation automatically times out after 10s
            server = await client.get_server_info()

        except TimeoutError as e:
            print(f"Operation timed out after {e.timeout}s")
            print(f"Operation: {e.operation}")
            # Implement retry or fallback logic
```

### Network Isolation

```yaml
# docker-compose.yml with network security
version: '3.8'

services:
  outline-manager:
    image: myapp:latest
    networks:
      - internal
      - outline_net
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 512M

networks:
  internal:
    driver: bridge
    internal: true  # No external access

  outline_net:
    driver: bridge
    ipam:
      config:
        - subnet: 172.28.0.0/16
```

---

## Data Protection

### Sensitive Data Handling

```python
from pyoutlineapi.common_types import mask_sensitive_data, DEFAULT_SENSITIVE_KEYS

# Automatic sensitive data masking
sensitive_data = {
    "name": "Alice",
    "password": "secret123",
    "api_url": "https://server.com/secret",
    "cert_sha256": "abc123...",
    "user_id": "12345"
}

# ✅ SECURE: Mask before logging
safe_data = mask_sensitive_data(sensitive_data)
print(safe_data)
# {
#     "name": "Alice",
#     "password": "***MASKED***",
#     "api_url": "***MASKED***",
#     "cert_sha256": "***MASKED***",
#     "user_id": "12345"
# }

# 32+ sensitive patterns automatically detected:
# password, passwd, pwd, secret, api_key, token, cert, private_key, etc.
```

### Memory Security

```python
import gc
from pyoutlineapi import AsyncOutlineClient


async def memory_secure_operation():
    """Ensure sensitive data is cleared from memory."""

    api_url = os.getenv("OUTLINE_API_URL")
    cert = os.getenv("OUTLINE_CERT_SHA256")

    try:
        async with AsyncOutlineClient(
                api_url=api_url,
                cert_sha256=cert
        ) as client:
            result = await client.get_server_info()
            return result

    finally:
        # ✅ SECURE: Clear sensitive variables
        api_url = None
        cert = None

        # Force garbage collection
        gc.collect()
```

### Output Sanitization

```python
from pyoutlineapi import AsyncOutlineClient


async def sanitized_output_example():
    """Demonstrate automatic output sanitization."""

    async with AsyncOutlineClient.from_env() as client:
        key = await client.create_access_key(name="Alice")

        # ✅ SECURE: Get sanitized config for logging
        safe_config = client.get_sanitized_config()
        logger.info(f"Using config: {safe_config}")
        # Output: {'api_url': 'https://server.com/***', 'cert_sha256': '***MASKED***', ...}

        # ✅ SECURE: Safe string representation
        print(client)
        # Output: AsyncOutlineClient(host=https://server.com, status=connected)

        # ❌ NEVER: Log full key object
        # logger.info(f"Created key: {key}")  # Would expose access_url!

        # ✅ SECURE: Log only safe fields
        logger.info(f"Created key ID: {key.id}, name: {key.name}")
```

---

## Audit Logging

### Production Audit Logging

```python
from pyoutlineapi import DefaultAuditLogger, AsyncOutlineClient

# ✅ PRODUCTION: Async audit logger with queue
audit_logger = DefaultAuditLogger(
    enable_async=True,  # Non-blocking queue processing
    queue_size=5000  # Large queue for high throughput
)

async with AsyncOutlineClient.from_env(audit_logger=audit_logger) as client:
    # All operations automatically audited
    key = await client.create_access_key(name="Alice")
    # 📝 [AUDIT] create_access_key on {key.id} | {'name': 'Alice', 'success': True}

    await client.rename_access_key(key.id, "Alice Smith")
    # 📝 [AUDIT] rename_access_key on {key.id} | {'new_name': 'Alice Smith', 'success': True}

    try:
        await client.delete_access_key("invalid-id")
    except Exception:
        pass
    # 📝 [AUDIT] delete_access_key on invalid-id | {'success': False, 'error': '...'}

# Graceful shutdown with queue draining
await audit_logger.shutdown(timeout=5.0)
```

### Custom Audit Logger (SIEM Integration)

```python
from pyoutlineapi import AuditLogger
import json
import asyncio
import aiohttp


class SIEMauditLogger:
    """Send audit logs to SIEM system."""

    def __init__(self, siem_endpoint: str, api_key: str):
        self.siem_endpoint = siem_endpoint
        self.api_key = api_key
        self.session = None

    def log_action(self, action: str, resource: str, **kwargs) -> None:
        """Synchronous logging (for compatibility)."""
        asyncio.create_task(self.alog_action(action, resource, **kwargs))

    async def alog_action(self, action: str, resource: str, **kwargs) -> None:
        """Async logging to SIEM."""
        if not self.session:
            self.session = aiohttp.ClientSession()

        event = {
            "timestamp": time.time(),
            "service": "pyoutlineapi",
            "action": action,
            "resource": resource,
            "severity": "INFO" if kwargs.get("success") else "WARNING",
            **kwargs
        }

        try:
            async with self.session.post(
                    self.siem_endpoint,
                    json=event,
                    headers={"Authorization": f"Bearer {self.api_key}"}
            ) as resp:
                if resp.status != 200:
                    print(f"SIEM logging failed: {resp.status}")

        except Exception as e:
            print(f"SIEM logging error: {e}")

    async def shutdown(self) -> None:
        """Cleanup."""
        if self.session:
            await self.session.close()


# Usage
siem_logger = SIEMauditLogger(
    siem_endpoint="https://siem.company.com/events",
    api_key=os.getenv("SIEM_API_KEY")
)

async with AsyncOutlineClient.from_env(audit_logger=siem_logger) as client:
    await client.create_access_key(name="User")
```

### Audit Log Security

```python
# ✅ SECURE: Sensitive data automatically filtered
key = await client.create_access_key(
    name="Alice",
    password="secret123"  # Automatically masked in audit logs
)
# Audit log: {'name': 'Alice', 'password': '***REDACTED***', 'success': True}

# ✅ SECURE: Correlation IDs for request tracking
from pyoutlineapi.base_client import correlation_id

correlation_id.set("request-abc-123")
await client.create_access_key(name="Bob")
# Audit log includes correlation ID for tracing

# ✅ SECURE: Failed operations logged
try:
    await client.delete_access_key("non-existent")
except Exception:
    pass
# Audit log: {'success': False, 'error': 'Key not found', 'error_type': 'APIError'}
```

---

## Circuit Breaker Security

### Preventing Cascading Failures

```python
from pyoutlineapi import AsyncOutlineClient, CircuitOpenError

# ✅ PRODUCTION: Enable circuit breaker
async with AsyncOutlineClient.from_env(
        enable_circuit_breaker=True,
        circuit_failure_threshold=5,  # Open after 5 failures
        circuit_recovery_timeout=60.0,  # Test recovery after 60s
        circuit_success_threshold=2,  # Close after 2 successes
        circuit_call_timeout=10.0  # Individual call timeout
) as client:
    try:
        await client.get_server_info()

    except CircuitOpenError as e:
        # ✅ SECURE: Circuit prevents hammering failing service
        print(f"Circuit open - service degraded")
        print(f"Retry after: {e.retry_after}s")

        # Implement fallback or alert
        await notify_operations_team(
            "Outline service circuit breaker opened"
        )

        # Wait before retry
        await asyncio.sleep(e.retry_after)

    # Monitor circuit health
    metrics = client.get_circuit_metrics()
    if metrics:
        if metrics['state'] == 'OPEN':
            print("⚠️ CRITICAL: Circuit breaker is OPEN")
        elif metrics['state'] == 'HALF_OPEN':
            print("⚠️ WARNING: Circuit breaker testing recovery")

        if metrics['success_rate'] < 0.5:
            print("⚠️ WARNING: Low success rate detected")
```

### Circuit Breaker Monitoring

```python
async def monitor_circuit_breaker(client: AsyncOutlineClient):
    """Monitor circuit breaker for security incidents."""

    while True:
        metrics = client.get_circuit_metrics()

        if not metrics:
            await asyncio.sleep(10)
            continue

        # Security alerts
        if metrics['state'] == 'OPEN':
            await send_alert(
                severity="HIGH",
                message="Circuit breaker opened - service degraded",
                metrics=metrics
            )

        if metrics['failed_calls'] > 100:
            await send_alert(
                severity="MEDIUM",
                message=f"High failure count: {metrics['failed_calls']}",
                metrics=metrics
            )

        if metrics['success_rate'] < 0.5:
            await send_alert(
                severity="MEDIUM",
                message=f"Low success rate: {metrics['success_rate']:.2%}",
                metrics=metrics
            )

        await asyncio.sleep(30)
```

---

## Deployment Security

### Docker Security

**Secure Dockerfile:**

```dockerfile
# Use specific version (not 'latest')
FROM python:3.12-slim-bookworm

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Set secure working directory
WORKDIR /app

# Install dependencies as root
COPY requirements.txt .
RUN pip install --no-cache-dir --require-hashes -r requirements.txt

# Copy application
COPY --chown=appuser:appuser . .

# Switch to non-root user
USER appuser

# Security hardening
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONH

ASHSEED=random

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import asyncio; from app import health_check; exit(0 if asyncio.run(health_check()) else 1)"

# Run application
CMD ["python", "-u", "app.py"]
```

**Secure docker-compose.yml:**

```yaml
version: '3.8'

services:
  outline-manager:
    build: .

    # Use secrets (not environment variables)
    secrets:
      - outline_api_url
      - outline_cert_sha256

    environment:
      - OUTLINE_API_URL_FILE=/run/secrets/outline_api_url
      - OUTLINE_CERT_SHA256_FILE=/run/secrets/outline_cert_sha256
      - OUTLINE_ENABLE_CIRCUIT_BREAKER=true
      - OUTLINE_ENABLE_LOGGING=false

    # Security constraints
    read_only: true
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    tmpfs:
      - /tmp:noexec,nosuid,size=100M
    # Resource limits (prevent DoS)
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 512M
        reservations:
          cpus: '0.25'
          memory: 128M

    # Network isolation
    networks:
      - internal

    # Restart policy
    restart: unless-stopped

    # Health check
    healthcheck:
      test: [ "CMD", "python", "-c", "import asyncio; from app import health_check; exit(0 if asyncio.run(health_check()) else 1)" ]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s

    # Logging
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
        labels: "service,environment"

secrets:
  outline_api_url:
    external: true
  outline_cert_sha256:
    external: true

networks:
  internal:
    driver: bridge
    internal: false
    ipam:
      config:
        - subnet: 172.28.0.0/16
```

### Kubernetes Security

**Secure Kubernetes Deployment:**

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: outline-credentials
type: Opaque
stringData:
  api-url: "https://your-server.com:12345/path"
  cert-sha256: "your-certificate-fingerprint"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: outline-manager
  labels:
    app: outline-manager
spec:
  replicas: 2
  selector:
    matchLabels:
      app: outline-manager
  template:
    metadata:
      labels:
        app: outline-manager
    spec:
      # Security context
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        fsGroup: 1000
        seccompProfile:
          type: RuntimeDefault

      containers:
        - name: outline-manager
          image: myregistry/outline-manager:1.0.0
          imagePullPolicy: Always

          # Security context for container
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            runAsNonRoot: true
            runAsUser: 1000
            capabilities:
              drop:
                - ALL

          # Environment from secrets
          env:
            - name: OUTLINE_API_URL
              valueFrom:
                secretKeyRef:
                  name: outline-credentials
                  key: api-url
            - name: OUTLINE_CERT_SHA256
              valueFrom:
                secretKeyRef:
                  name: outline-credentials
                  key: cert-sha256
            - name: OUTLINE_ENABLE_CIRCUIT_BREAKER
              value: "true"
            - name: OUTLINE_ENABLE_LOGGING
              value: "false"

          # Resource limits
          resources:
            limits:
              cpu: "500m"
              memory: "512Mi"
            requests:
              cpu: "100m"
              memory: "128Mi"

          # Health checks
          livenessProbe:
            httpGet:
              path: /health
              port: 8080
            initialDelaySeconds: 10
            periodSeconds: 30
            timeoutSeconds: 5
            failureThreshold: 3

          readinessProbe:
            httpGet:
              path: /ready
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 10
            timeoutSeconds: 3
            failureThreshold: 2

          # Volume mounts for tmp
          volumeMounts:
            - name: tmp
              mountPath: /tmp

      volumes:
        - name: tmp
          emptyDir:
            sizeLimit: 100Mi

      # Pod security
      automountServiceAccountToken: false
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: outline-manager-pdb
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: outline-manager
---
apiVersion: v1
kind: Service
metadata:
  name: outline-manager
spec:
  type: ClusterIP
  selector:
    app: outline-manager
  ports:
    - port: 8080
      targetPort: 8080
```

### Secrets Management

**HashiCorp Vault Integration:**

```python
import hvac
from pyoutlineapi import AsyncOutlineClient


class VaultSecretLoader:
    """Load secrets from HashiCorp Vault."""

    def __init__(self, vault_addr: str, vault_token: str):
        self.client = hvac.Client(url=vault_addr, token=vault_token)

    def get_outline_credentials(self, path: str) -> dict:
        """Retrieve Outline credentials from Vault."""
        try:
            secret = self.client.secrets.kv.v2.read_secret_version(path=path)
            data = secret['data']['data']

            return {
                'api_url': data['api_url'],
                'cert_sha256': data['cert_sha256']
            }
        except Exception as e:
            raise ValueError(f"Failed to load secrets from Vault: {e}")


# Usage
vault = VaultSecretLoader(
    vault_addr=os.getenv("VAULT_ADDR"),
    vault_token=os.getenv("VAULT_TOKEN")
)

creds = vault.get_outline_credentials("secret/outline/production")

async with AsyncOutlineClient(
        api_url=creds['api_url'],
        cert_sha256=creds['cert_sha256']
) as client:
    await client.get_server_info()
```

**AWS Secrets Manager Integration:**

```python
import boto3
import json
from pyoutlineapi import AsyncOutlineClient


class AWSSecretLoader:
    """Load secrets from AWS Secrets Manager."""

    def __init__(self, region: str = 'us-east-1'):
        self.client = boto3.client('secretsmanager', region_name=region)

    def get_outline_credentials(self, secret_name: str) -> dict:
        """Retrieve Outline credentials from AWS Secrets Manager."""
        try:
            response = self.client.get_secret_value(SecretId=secret_name)
            secret = json.loads(response['SecretString'])

            return {
                'api_url': secret['api_url'],
                'cert_sha256': secret['cert_sha256']
            }
        except Exception as e:
            raise ValueError(f"Failed to load secrets from AWS: {e}")


# Usage
aws_secrets = AWSSecretLoader(region='us-east-1')
creds = aws_secrets.get_outline_credentials("outline/production/credentials")

async with AsyncOutlineClient(
        api_url=creds['api_url'],
        cert_sha256=creds['cert_sha256']
) as client:
    await client.get_server_info()
```

---

## Dependencies and Updates

### Dependency Security Scanning

```bash
# Install security tools
pip install safety pip-audit bandit

# Check for known vulnerabilities
safety check --json

# Audit dependencies
pip-audit --desc

# Security linting
bandit -r pyoutlineapi/ -f json

# Generate SBOM (Software Bill of Materials)
pip install cyclonedx-bom
cyclonedx-py requirements.txt -o sbom.json
```

**Automated Security Scanning in CI/CD:**

```yaml
# .github/workflows/security.yml
name: Security Scan

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]
  schedule:
    - cron: '0 0 * * 0'  # Weekly

jobs:
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: |
          pip install safety pip-audit bandit
          pip install -r requirements.txt

      - name: Run Safety check
        run: safety check --json

      - name: Run pip-audit
        run: pip-audit --desc

      - name: Run Bandit
        run: bandit -r pyoutlineapi/ -f json -o bandit-report.json

      - name: Upload security reports
        uses: actions/upload-artifact@v4
        with:
          name: security-reports
          path: |
            bandit-report.json
            safety-report.json
```

### Update Management

```python
# check_updates.py
import aiohttp
import asyncio
from packaging import version
import pyoutlineapi


async def check_pyoutlineapi_updates():
    """Check for security updates."""

    async with aiohttp.ClientSession() as session:
        async with session.get('https://pypi.org/pypi/pyoutlineapi/json') as resp:
            if resp.status != 200:
                print("❌ Failed to check for updates")
                return

            data = await resp.json()
            latest = data['info']['version']
            current = pyoutlineapi.__version__

            if version.parse(current) < version.parse(latest):
                print(f"⚠️ Update available: {latest} (current: {current})")

                # Check for security releases
                releases = data['releases'].get(latest, [])
                for release in releases:
                    if 'security' in release.get('comment_text', '').lower():
                        print("🚨 SECURITY UPDATE - Update immediately!")
                        return True

                print("ℹ️ Regular update available")
                return True

            print(f"✅ Up to date: {current}")
            return False


# Run check
if __name__ == "__main__":
    asyncio.run(check_pyoutlineapi_updates())
```

### Dependency Pinning

**requirements.txt with hashes:**

```text
# requirements.txt
# Generated with: pip-compile --generate-hashes requirements.in

pyoutlineapi==0.4.0 \
    --hash=sha256:abc123... \
    --hash=sha256:def456...

aiohttp==3.9.1 \
    --hash=sha256:123abc... \
    --hash=sha256:456def...

pydantic==2.5.3 \
    --hash=sha256:789ghi... \
    --hash=sha256:012jkl...

# Verify with: pip install --require-hashes -r requirements.txt
```

---

## Security Checklist

### Pre-Deployment Security Checklist

#### Configuration Security

- [ ] ✅ Environment variables configured (no hardcoded credentials)
- [ ] ✅ `.env` file added to `.gitignore`
- [ ] ✅ Production config uses `ProductionConfig` preset
- [ ] ✅ HTTPS enforced (no HTTP connections)
- [ ] ✅ Certificate fingerprint verified and correct
- [ ] ✅ Logging disabled in production (`enable_logging=false`)
- [ ] ✅ Circuit breaker enabled (`enable_circuit_breaker=true`)
- [ ] ✅ Reasonable timeouts configured (5-30 seconds)
- [ ] ✅ Rate limiting configured (≤100 concurrent requests)

#### Credential Management

- [ ] ✅ Credentials stored in secrets manager (Vault/AWS/Docker secrets)
- [ ] ✅ Credentials rotated within last 90 days
- [ ] ✅ Separate credentials for each environment (dev/staging/prod)
- [ ] ✅ Credential rotation procedure documented
- [ ] ✅ Emergency credential revocation process in place

#### Network Security

- [ ] ✅ TLS 1.2+ enforced
- [ ] ✅ Certificate pinning enabled
- [ ] ✅ Firewall rules configured (allowlist only)
- [ ] ✅ Network isolation implemented (internal networks)
- [ ] ✅ DDoS protection configured (rate limiting)

#### Access Control

- [ ] ✅ Access keys have appropriate data limits
- [ ] ✅ Key naming conventions follow security guidelines
- [ ] ✅ Regular key rotation schedule established
- [ ] ✅ Unused keys identified and removed
- [ ] ✅ Key usage monitoring enabled

#### Audit & Monitoring

- [ ] ✅ Audit logging enabled in production
- [ ] ✅ Audit logs sent to SIEM/centralized logging
- [ ] ✅ Sensitive data filtering active
- [ ] ✅ Correlation IDs tracked for requests
- [ ] ✅ Security alerts configured
- [ ] ✅ Health monitoring enabled
- [ ] ✅ Circuit breaker metrics tracked

#### Code Security

- [ ] ✅ Dependencies scanned for vulnerabilities (`safety check`)
- [ ] ✅ Static analysis passed (`bandit -r pyoutlineapi/`)
- [ ] ✅ No secrets in code or version control
- [ ] ✅ Input validation enabled (automatic with Pydantic)
- [ ] ✅ Output sanitization enabled (automatic)
- [ ] ✅ Security tests in CI/CD pipeline

#### Container/Deployment Security

- [ ] ✅ Running as non-root user
- [ ] ✅ Read-only filesystem enabled
- [ ] ✅ Capabilities dropped (`cap_drop: ALL`)
- [ ] ✅ Security options configured (`no-new-privileges`)
- [ ] ✅ Resource limits set (CPU/memory)
- [ ] ✅ Health checks configured
- [ ] ✅ Secrets mounted securely (not in environment)

### Runtime Security Checklist

#### Connection Health

- [ ] ✅ Health checks passing consistently
- [ ] ✅ Certificate validation successful
- [ ] ✅ No connection timeouts or errors
- [ ] ✅ Circuit breaker in CLOSED state
- [ ] ✅ Success rate >95%

#### Access Key Management

- [ ] ✅ Regular usage monitoring active
- [ ] ✅ Unused keys cleaned up monthly
- [ ] ✅ Data limits enforced
- [ ] ✅ No keys with unlimited access
- [ ] ✅ Key creation/deletion audited

#### Monitoring & Alerting

- [ ] ✅ Log monitoring active
- [ ] ✅ No sensitive data in logs
- [ ] ✅ Security alerts configured
- [ ] ✅ Anomaly detection enabled
- [ ] ✅ On-call rotation established

#### Compliance

- [ ] ✅ Audit logs retained per policy (90+ days)
- [ ] ✅ Access reviews completed quarterly
- [ ] ✅ Security training current
- [ ] ✅ Incident response plan tested
- [ ] ✅ Compliance certifications current

---

## Incident Response

### Incident Classification

| Severity          | Description             | Response Time | Examples                           |
|-------------------|-------------------------|---------------|------------------------------------|
| **P0 - Critical** | Active security breach  | Immediate     | Credential compromise, data breach |
| **P1 - High**     | Potential security risk | < 4 hours     | Suspicious activity, failed logins |
| **P2 - Medium**   | Security concern        | < 24 hours    | Configuration drift, outdated deps |
| **P3 - Low**      | Minor security issue    | < 7 days      | Best practice violations           |

### Security Incident Response Plan

**Phase 1: Detection & Assessment (0-15 minutes)**

```python
async def detect_security_incident(client: AsyncOutlineClient):
    """Automated security incident detection."""

    # Check circuit breaker state
    metrics = client.get_circuit_metrics()
    if metrics and metrics['state'] == 'OPEN':
        await alert_security_team(
            severity="HIGH",
            message="Circuit breaker opened - possible DoS or service failure"
        )

    # Check for unusual key creation patterns
    keys = await client.get_access_keys()
    recent_keys = [k for k in keys.access_keys
                   if is_recently_created(k, hours=1)]

    if len(recent_keys) > 10:  # Threshold
        await alert_security_team(
            severity="HIGH",
            message=f"Unusual key creation: {len(recent_keys)} keys in last hour"
        )

    # Check for excessive data usage
    if client.is_connected:
        metrics = await client.get_transfer_metrics()
        for key_id, bytes_used in metrics.bytes_transferred_by_user_id.items():
            if bytes_used > 100 * 1024 ** 3:  # 100 GB threshold
                await alert_security_team(
                    severity="MEDIUM",
                    message=f"High data usage detected: Key {key_id}"
                )
```

**Phase 2: Containment (15-60 minutes)**

```python
async def contain_security_incident(client: AsyncOutlineClient):
    """Immediate containment actions."""

    # 1. Rotate credentials
    print("Step 1: Rotating credentials...")
    await rotate_outline_credentials()

    # 2. Disable suspicious keys
    print("Step 2: Disabling suspicious access keys...")
    suspicious_keys = await identify_suspicious_keys(client)
    for key_id in suspicious_keys:
        await client.delete_access_key(key_id)
        print(f"  ✅ Disabled key: {key_id}")

    # 3. Enable additional monitoring
    print("Step 3: Enhanced monitoring enabled...")
    await enable_enhanced_monitoring()

    # 4. Notify stakeholders
    print("Step 4: Notifying stakeholders...")
    await notify_security_team({
        "incident": "Security incident contained",
        "actions_taken": [
            "Credentials rotated",
            f"Disabled {len(suspicious_keys)} suspicious keys",
            "Enhanced monitoring enabled"
        ]
    })
```

**Phase 3: Eradication (1-24 hours)**

```python
async def eradicate_threat(client: AsyncOutlineClient):
    """Remove threat completely."""

    # 1. Full audit of all access keys
    print("Conducting full access key audit...")
    keys = await client.get_access_keys()

    audit_results = []
    for key in keys.access_keys:
        status = await audit_access_key(key)
        audit_results.append(status)

        if status['risk_level'] == 'HIGH':
            await client.delete_access_key(key.id)
            print(f"  ⚠️ Removed high-risk key: {key.id}")

    # 2. Review and update security policies
    await update_security_policies()

    # 3. Patch vulnerabilities
    await apply_security_patches()

    # 4. Verify system integrity
    integrity_check = await verify_system_integrity(client)
    if not integrity_check:
        raise SecurityError("System integrity compromised")
```

**Phase 4: Recovery (24-72 hours)**

```python
async def recover_from_incident():
    """Restore normal operations securely."""

    # 1. Restore from clean backup if needed
    if backup_required:
        await restore_from_backup()

    # 2. Recreate legitimate access keys
    print("Recreating legitimate access keys...")
    await recreate_access_keys_from_approved_list()

    # 3. Update documentation
    await update_security_documentation()

    # 4. Conduct post-incident review
    await schedule_post_incident_review()
```

**Phase 5: Lessons Learned (7 days)**

```markdown
## Post-Incident Review Template

### Incident Summary

- **Date/Time**:
- **Duration**:
- **Severity**:
- **Impact**:

### Timeline

- **Detection**:
- **Containment**:
- **Eradication**:
- **Recovery**:

### Root Cause Analysis

1. What happened?
2. Why did it happen?
3. How was it detected?

### Actions Taken

- [ ] Immediate response
- [ ] Containment measures
- [ ] System recovery

### Lessons Learned

1. What worked well?
2. What could be improved?
3. What should we do differently?

### Action Items

- [ ] Update security policies
- [ ] Implement additional monitoring
- [ ] Security training
- [ ] Tool/process improvements

### Follow-up

- **Review Date**:
- **Owner**:
- **Status**: 
```

### Emergency Contacts

**Security Team Contacts:**

```python
SECURITY_CONTACTS = {
    "primary": {
        "email": "security@company.com",
        "phone": "+1-XXX-XXX-XXXX",
        "pagerduty": "security-team"
    },
    "escalation": {
        "email": "ciso@company.com",
        "phone": "+1-XXX-XXX-XXXX"
    },
    "vendor": {
        "email": "pytelemonbot@mail.ru",
        "github": "https://github.com/orenlab/pyoutlineapi/security"
    }
}
```

### Incident Communication Template

```python
async def send_security_incident_notification(
        severity: str,
        title: str,
        description: str,
        actions_taken: list[str]
):
    """Send standardized security incident notification."""

    message = f"""
🚨 SECURITY INCIDENT - {severity}

Title: {title}
Time: {datetime.now().isoformat()}
Severity: {severity}

Description:
{description}

Actions Taken:
{chr(10).join(f"- {action}" for action in actions_taken)}

Status: Under Investigation

Contact: security@company.com
Incident ID: INC-{datetime.now().strftime('%Y%m%d-%H%M%S')}
    """

    # Send via multiple channels
    await send_email(to=SECURITY_CONTACTS['primary']['email'], body=message)
    await send_slack_alert(channel='#security-incidents', message=message)
    await create_pagerduty_incident(severity=severity, message=message)
```

---

## Additional Resources

### Security Standards & Frameworks

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [NIST Cybersecurity Framework](https://www.nist.gov/cyberframework)
- [CIS Controls](https://www.cisecurity.org/controls)
- [ISO 27001](https://www.iso.org/isoiec-27001-information-security.html)

### Python Security

- [Python Security Best Practices](https://python-security.readthedocs.io/)
- [Bandit Security Linter](https://bandit.readthedocs.io/)
- [Safety - Dependency Scanner](https://pyup.io/safety/)
- [OWASP Python Security Project](https://owasp.org/www-project-python-security/)

### TLS & Certificate Security

- [TLS Best Practices](https://wiki.mozilla.org/Security/Server_Side_TLS)
- [Certificate Pinning Guide](https://owasp.org/www-community/controls/Certificate_and_Public_Key_Pinning)
- [Let's Encrypt Documentation](https://letsencrypt.org/docs/)

### Outline VPN Security

- [Outline Server Security](https://github.com/Jigsaw-Code/outline-server/blob/master/docs/security.md)
- [Outline Documentation](https://getoutline.org/support/)

### Container Security

- [Docker Security Best Practices](https://docs.docker.com/engine/security/)
- [Kubernetes Security Best Practices](https://kubernetes.io/docs/concepts/security/)
- [CIS Docker Benchmark](https://www.cisecurity.org/benchmark/docker)

### Secrets Management

- [HashiCorp Vault](https://www.vaultproject.io/)
- [AWS Secrets Manager](https://aws.amazon.com/secrets-manager/)
- [Docker Secrets](https://docs.docker.com/engine/swarm/secrets/)
- [Kubernetes Secrets](https://kubernetes.io/docs/concepts/configuration/secret/)

---

## Version History

| Version | Date       | Changes                            |
|---------|------------|------------------------------------|
| 1.0.0   | 2025-10-20 | Initial security policy for v0.4.0 |

---

**Last Updated**: 2025-10-20  
**Next Review**: 2026-01-20 (Quarterly review)

For security questions or to report vulnerabilities, contact: `pytelemonbot@mail.ru`

---

**Made with 🔒 by the PyOutlineAPI Security Team**

*Protecting your Outline VPN infrastructure with enterprise-grade security*