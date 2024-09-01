# PyOutlineAPI

`pyoutlineapi` is a Python package designed to interact with the Outline VPN Server API, providing robust data
validation through Pydantic models. This ensures reliable and secure API interactions, making it an excellent choice for
integrating with bots and other automated systems that require accurate and secure communication.

[![Security Rating](https://sonarcloud.io/api/project_badges/measure?project=orenlab_pyoutlineapi&metric=security_rating)](https://sonarcloud.io/summary/new_code?id=orenlab_pyoutlineapi)
[![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=orenlab_pyoutlineapi&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=orenlab_pyoutlineapi)
[![Vulnerabilities](https://sonarcloud.io/api/project_badges/measure?project=orenlab_pyoutlineapi&metric=vulnerabilities)](https://sonarcloud.io/summary/new_code?id=orenlab_pyoutlineapi)
[![tests](https://github.com/orenlab/pyoutlineapi/actions/workflows/python_tests.yml/badge.svg)](https://github.com/orenlab/pyoutlineapi/actions/workflows/python_tests.yml)

## Features

- **Server Management**: Retrieve server information, update hostnames, manage ports, and more.
- **Access Key Management**: Create, list, rename, and delete access keys, as well as set data limits.
- **Metrics**: Enable or disable metrics sharing and retrieve data transfer metrics.
- **Experimental Endpoints**: Access and manage experimental features of the Outline Server API.

## Quick Start

To get started with `pyoutlineapi`, follow these steps:

1. Install the package using pip or Poetry.
2. Initialize the `PyOutlineWrapper` client with your Outline VPN server URL and certificate fingerprint.
3. Use the provided methods to interact with the server and access keys.

See the examples below for more detailed information.

## Installation

You can install PyOutlineAPI via [PyPI](https://pypi.org/project/pyoutlineapi/) using pip:

```bash
pip install pyoutlineapi
```

Or via [Poetry](https://python-poetry.org/):

```bash
poetry add pyoutlineapi
```

## Basic Operations

### Initialize the Client

```python
from pyoutlineapi.client import PyOutlineWrapper
from pyoutlineapi.models import DataLimit

# Initialize the API client
api_url = "https://your-outline-url.com"
cert_sha256 = "your-cert-sha256-fingerprint"
# Set "verify_tls" to False if using a self-signed certificate.
# Set "json_format" to True if answers need to be returned in JSON format. Defaults to False - Pydantic models will be returned.
api_client = PyOutlineWrapper(api_url=api_url, cert_sha256=cert_sha256, verify_tls=False, json_format=True)
```

### Retrieve Server Information

```python
server_info = api_client.get_server_info()
print("Server Information:", server_info)
```

### Create a New Access Key

```python
# Create a new access key with default values
new_access_key = api_client.create_access_key()
# Create a new access key with custom values
new_access_key = api_client.create_access_key(name="my_access_key", password="secure_password", port=8080)

print("New Access Key:", new_access_key)
```

### Delete Access Key

```python
success = api_client.delete_access_key("example-key-id")
print("Access Key Deleted Successfully" if success else "Failed to Delete Access Key")
```

## Additional Functions

### Update Server Port

```python
update_success = api_client.update_server_port(9090)
print("Server Port Updated:", update_success)
```

### Set Data Limit for an Access Key

```python
data_limit = api_client.set_access_key_data_limit("example-key-id", DataLimit(bytes=50000000))
print("Data Limit Set:", data_limit)
```

### Retrieve Metrics

```python
metrics_data = api_client.get_metrics()
print("Metrics Data:", metrics_data)
```

## Contributing

We welcome contributions to PyOutlineAPI! Please follow the guidelines outlined in
the [CONTRIBUTING.md](https://github.com/orenlab/pyoutlineapi/blob/main/CONTRIBUTING.md) file.

## License

PyOutlineAPI is licensed under the MIT [License](https://github.com/orenlab/pyoutlineapi/blob/main/LICENSE). See the
LICENSE file for more details.

## Frequently Asked Questions (FAQ)

___
**How to use self-signed certificates?**

Set the `verify_tls` parameter to `False` when initializing the client.
___
___
**How to change the response format to Pydantic models?**

Set the `json_format` parameter to `False` when initializing the client if you need to receive responses in Pydantic
models.
___