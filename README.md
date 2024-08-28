# pyoutline

`pyoutlineapi` is a Python package to interact with the Outline VPN Server API. The package includes Pydantic-based
data validation, ensuring robust and reliable API interactions.

## Features

- **Server Management**: Retrieve server information, update hostnames, manage ports, and more.
- **Access Key Management**: Create, list, rename, and delete access keys, as well as set data limits.
- **Metrics**: Enable or disable metrics sharing and retrieve data transfer metrics.
- **Experimental Endpoints**: Access and manage experimental features of the Outline Server API.

## Installation

You can install PyOutline via [PyPI](https://pypi.org/project/pyoutline/) using pip:

```bash
pip install pyoutlineapi
```

Or via [Poetry](https://python-poetry.org/):

```bash
poetry add pyoutlineapi
```

## Usage

Initialize the Client:

```python
from pyoutlineapi.client import PyOutlineWrapper

api_url = "https://your-outline-url.com"
cert_sha256 = "your-cert-sha256-fingerprint"
# If a self-signed certificate is used to operate the outline server, 
# the "verify_tls" parameter must be set to "False".
api_client = PyOutlineWrapper(api_url=api_url, cert_sha256=cert_sha256, verify_tls=False)

# Get Server Information:
server_info = api_client.get_server_info()
print(server_info)

# Create a New Access Key:
new_access_key = api_client.create_access_key()
print(new_access_key)

# Get List of Access Keys:
access_key_list = api_client.get_access_keys()
print(access_key_list)

# Delete Access Key:
api_client.delete_access_key("your-key-id")

# Update Server Port:
new_port = api_client.update_server_port(8080)
print(new_port)

# Set Data Limit for Access Key:
data_limit = api_client.set_access_key_data_limit("your-key-id", 50000000)
print(data_limit)

# Enable or Disable Metrics:
metrics_status = api_client.set_metrics_enabled(True)
print(metrics_status)

# Get Metrics:
metrics_data = api_client.get_metrics()
print(metrics_data)
```

## Contributing

We welcome contributions to PyOutlineAPI! Please follow the guidelines outlined in the CONTRIBUTING.md file.

## License

PyOutlineAPI is licensed under the MIT [License](LICENSE). See the LICENSE file for more details.
