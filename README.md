# pyoutlineapi

`pyoutlineapi` is a Python package designed to interact with the Outline VPN Server API, providing robust data
validation through Pydantic models. This ensures reliable and secure API interactions.

Whether you're building a Telegram bot or another application that requires accurate and secure API communication,
`pyoutlineapi` offers comprehensive validation for both incoming and outgoing data. This makes it an excellent choice
for integrating with bots and other automated systems.

[![Security Rating](https://sonarcloud.io/api/project_badges/measure?project=orenlab_pyoutlineapi&metric=security_rating)](https://sonarcloud.io/summary/new_code?id=orenlab_pyoutlineapi)
[![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=orenlab_pyoutlineapi&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=orenlab_pyoutlineapi)
[![Vulnerabilities](https://sonarcloud.io/api/project_badges/measure?project=orenlab_pyoutlineapi&metric=vulnerabilities)](https://sonarcloud.io/summary/new_code?id=orenlab_pyoutlineapi)
[![tests](https://github.com/orenlab/pyoutlineapi/actions/workflows/python_tests.yml/badge.svg)](https://github.com/orenlab/pyoutlineapi/actions/workflows/python_tests.yml)

## Features

- **Server Management**: Retrieve server information, update hostnames, manage ports, and more.
- **Access Key Management**: Create, list, rename, and delete access keys, as well as set data limits.
- **Metrics**: Enable or disable metrics sharing and retrieve data transfer metrics.
- **Experimental Endpoints**: Access and manage experimental features of the Outline Server API.

## Installation

You can install PyOutlineAPI via [PyPI](https://pypi.org/project/pyoutlineapi/) using pip:

```bash
pip install pyoutlineapi
```

Or via [Poetry](https://python-poetry.org/):

```bash
poetry add pyoutlineapi
```

## Usage

Initialize the Client:

To get started, you need to initialize the PyOutlineWrapper client with your Outline VPN server URL and certificate
fingerprint:

```python
from pyoutlineapi.client import PyOutlineWrapper

api_url = "https://your-outline-url.com"
cert_sha256 = "your-cert-sha256-fingerprint"
# If a self-signed certificate is used, set "verify_tls" to False.
api_client = PyOutlineWrapper(api_url=api_url, cert_sha256=cert_sha256, verify_tls=False)

# Retrieve Server Information
from pyoutlineapi.models import Server

server_info: Server = api_client.get_server_info()
print("Server Information:", server_info)

# Create a New Access Key:
from pyoutlineapi.models import AccessKey

new_access_key: AccessKey = api_client.create_access_key(name="my_access_key", password="secure_password", port=8080)
print("New Access Key:", new_access_key)

# List All Access Keys:
from pyoutlineapi.models import AccessKeyList

access_key_list: AccessKeyList = api_client.get_access_keys()
print("Access Key List:")
for access_key in access_key_list.accessKeys:
    print(f"- ID: {access_key.id}, Name: {access_key.name}, Port: {access_key.port}")

# Delete Access Key:
api_client.delete_access_key("your-key-id")
print("Access Key Deleted Successfully")

# Update Server Port:
update_success: bool = api_client.update_server_port(9090)
print("Server Port Updated:", update_success)

# Set Data Limit for Access Key:
from pyoutlineapi.models import DataLimit

data_limit: bool = api_client.set_access_key_data_limit("your-key-id", DataLimit(bytes=50000000))
print("Data Limit Set:", data_limit)

# Retrieve Metrics:
from pyoutlineapi.models import Metrics

metrics_data: Metrics = api_client.get_metrics()
print("Metrics Data:")
for user_id, bytes_transferred in metrics_data.bytesTransferredByUserId.items():
    print(f"- User ID: {user_id}, Bytes Transferred: {bytes_transferred}")
```

## Contributing

We welcome contributions to PyOutlineAPI! Please follow the guidelines outlined in
the [CONTRIBUTING.md](https://github.com/orenlab/pyoutlineapi/blob/main/CONTRIBUTING.md) file.

## License

PyOutlineAPI is licensed under the MIT [License](https://github.com/orenlab/pyoutlineapi/blob/main/LICENSE). See the
LICENSE file for more details.
