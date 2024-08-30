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
from pyoutlineapi.models import DataLimit

# Initialize the API client
api_url = "https://your-outline-url.com"
cert_sha256 = "your-cert-sha256-fingerprint"
# If using a self-signed certificate, set "verify_tls" to False.
# If answers need to be returned in JSON format, set "json_format" to True. 
# Defaults to False - Pydantic models will be returned.
api_client = PyOutlineWrapper(api_url=api_url, cert_sha256=cert_sha256, verify_tls=False, json_format=True)

# Retrieve server information
try:
    server_info = api_client.get_server_info()
    print("Server Information:", server_info)
    if isinstance(server_info, str):  # Check for JSON format
        print("JSON Format Server Information:", server_info)
    else:
        print("Server Name:", server_info.name)
        print("Server ID:", server_info.serverId)
        print("Metrics Enabled:", server_info.metricsEnabled)
        print("Created Timestamp (ms):", server_info.createdTimestampMs)
        print("Port for New Access Keys:", server_info.portForNewAccessKeys)
except Exception as e:
    print(f"An error occurred: {e}")

# Create a new access key
try:
    new_access_key = api_client.create_access_key(name="my_access_key", password="secure_password", port=8080)
    print("New Access Key:", new_access_key)
    if isinstance(new_access_key, str):  # Check for JSON format
        print("JSON Format New Access Key:", new_access_key)
    else:
        print("Access Key ID:", new_access_key.id)
        print("Access Key Name:", new_access_key.name)
        print("Access Key Port:", new_access_key.port)
except Exception as e:
    print(f"An error occurred: {e}")

# Retrieve a list of all access keys
try:
    access_key_list = api_client.get_access_keys()
    print("Access Key List:")
    if isinstance(access_key_list, str):  # Check for JSON format
        print("JSON Format Access Key List:", access_key_list)
    else:
        for access_key in access_key_list.accessKeys:
            print(f"- ID: {access_key.id}, Name: {access_key.name}, Port: {access_key.port}")
except Exception as e:
    print(f"An error occurred: {e}")

# Delete an access key
try:
    success = api_client.delete_access_key("example-key-id")
    print("Access Key Deleted Successfully" if success else "Failed to Delete Access Key")
except Exception as e:
    print(f"An error occurred: {e}")

# Update the server port
try:
    update_success = api_client.update_server_port(9090)
    print("Server Port Updated:", update_success)
except Exception as e:
    print(f"An error occurred: {e}")

# Set data limit for an access key
try:
    data_limit = api_client.set_access_key_data_limit("example-key-id", DataLimit(bytes=50000000))
    print("Data Limit Set:", data_limit)
except Exception as e:
    print(f"An error occurred: {e}")

# Retrieve metrics
try:
    metrics_data = api_client.get_metrics()
    print("Metrics Data:")
    if isinstance(metrics_data, str):  # Check for JSON format
        print("JSON Format Metrics Data:", metrics_data)
    else:
        for user_id, bytes_transferred in metrics_data.bytesTransferredByUserId.items():
            print(f"- User ID: {user_id}, Bytes Transferred: {bytes_transferred}")
except Exception as e:
    print(f"An error occurred: {e}")
```

## Contributing

We welcome contributions to PyOutlineAPI! Please follow the guidelines outlined in
the [CONTRIBUTING.md](https://github.com/orenlab/pyoutlineapi/blob/main/CONTRIBUTING.md) file.

## License

PyOutlineAPI is licensed under the MIT [License](https://github.com/orenlab/pyoutlineapi/blob/main/LICENSE). See the
LICENSE file for more details.
