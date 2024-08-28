"""
Copyright (c) 2024 Denis Rozhnovskiy <pytelemonbot@mail.ru>

This file is part of the PyOutline project.

PyOutline is a Python package for interacting with the Outline VPN Server.

Licensed under the MIT License. See the LICENSE file for more details.

"""

import requests
from requests_toolbelt.adapters.fingerprint import FingerprintAdapter

from src.pyoutlineapi.exceptions import APIError, ValidationError
from src.pyoutlineapi.logger import setup_logger
from src.pyoutlineapi.models import (
    Server,
    AccessKey,
    AccessKeyList,
    ServerPort,
    DataLimit,
    MetricsEnabled,
    Metrics
)

# Set up logging
logger = setup_logger(__name__)


class PyOutlineWrapper:
    """
    Class for interacting with the Outline VPN Server.

    Attributes:
        api_url (str): The base URL of the API.
        cert_sha256 (str): SHA-256 fingerprint of the certificate for authenticity verification.
    """

    def __init__(self, api_url: str, cert_sha256: str, verify_tls: bool = True):
        """
        Initialize PyOutlineAPI.

        Args:
            api_url (str): The base URL of the API.
            cert_sha256 (str): SHA-256 fingerprint of the certificate.
        """
        self.api_url = api_url
        self.cert_sha256 = cert_sha256
        self.verify_tls = verify_tls
        self.session = requests.Session()
        self.session.mount(self.api_url, FingerprintAdapter(self.cert_sha256))

    def _request(self, method: str, endpoint: str, json_data=None) -> requests.Response:
        """
        Perform an HTTP request to the API.

        Args:
            method (str): HTTP method (GET, POST, PUT, DELETE).
            endpoint (str): API endpoint.
            json_data (dict, optional): Data to send in the request body.

        Returns:
            requests.Response: The HTTP response object.

        Raises:
            APIError: If the request fails.
        """
        url = f"{self.api_url}/{endpoint}"
        try:
            logger.debug(f"Making {method} request to {url} with data: {json_data}")
            response = self.session.request(method, url, json=json_data, verify=self.verify_tls)
            response.raise_for_status()
            logger.debug(f"Response from {url}: {response.status_code}")
            return response
        except requests.RequestException as e:
            raise APIError(f"Request to {url} failed: {e}")

    def get_server_info(self) -> Server:
        """
        Get information about the server.

        Returns:
            Server: An object containing server information.
        """
        try:
            response = self._request("GET", "server")
            return Server(**response.json())
        except ValidationError as e:
            raise ValidationError(f"Failed to get server info: {e}")

    def create_access_key(self) -> AccessKey:
        """
        Create a new access key.

        Returns:
            AccessKey: An object containing information about the new access key.
        """
        try:
            response = self._request("POST", "access-keys")
            return AccessKey(**response.json())
        except ValidationError as e:
            raise ValidationError(f"Failed to create access key: {e}")

    def get_access_keys(self) -> AccessKeyList:
        """
        Get a list of all access keys.

        Returns:
            AccessKeyList: An object containing a list of access keys.
        """
        try:
            response = self._request("GET", "access-keys")
            return AccessKeyList(**response.json())
        except ValidationError as e:
            raise ValidationError(f"Failed to get access keys: {e}")

    def delete_access_key(self, key_id: str):
        """
        Delete an access key by its ID.

        Args:
            key_id (str): The ID of the access key.

        Raises:
            APIError: If the request fails.
        """
        try:
            self._request("DELETE", f"access-keys/{key_id}")
        except ValidationError as e:
            raise ValidationError(f"Failed to delete access key with ID {key_id}: {e}")

    def update_server_port(self, port: int) -> ServerPort:
        """
        Update the port for new access keys.

        Args:
            port (int): The new port.

        Returns:
            ServerPort: An object containing the updated port information.
        """
        try:
            response = self._request("PUT", "server/port-for-new-access-keys", {"port": port})
            return ServerPort(**response.json())
        except ValidationError as e:
            raise ValidationError(f"Failed to update server port: {e}")

    def set_access_key_data_limit(self, key_id: str, limit: int) -> DataLimit:
        """
        Set the data limit for an access key.

        Args:
            key_id (str): The ID of the access key.
            limit (int): The data limit in bytes.

        Returns:
            DataLimit: An object containing the set data limit.
        """
        try:
            response = self._request("PUT", f"access-keys/{key_id}/data-limit", {"bytes": limit})
            return DataLimit(**response.json())
        except ValidationError as e:
            raise ValidationError(f"Failed to set data limit for access key with ID {key_id}: {e}")

    def set_metrics_enabled(self, enabled: bool) -> MetricsEnabled:
        """
        Enable or disable metrics on the server.

        Args:
            enabled (bool): The state of metrics (enabled/disabled).

        Returns:
            MetricsEnabled: An object containing the metrics state information.
        """
        try:
            response = self._request("PUT", "server/metrics/enabled", {"enabled": enabled})
            return MetricsEnabled(**response.json())
        except ValidationError as e:
            raise ValidationError(f"Failed to set metrics enabled state: {e}")

    def get_metrics(self) -> Metrics:
        """
        Get metrics about data transfer.

        Returns:
            Metrics: An object containing data transfer metrics.
        """
        try:
            response = self._request("GET", "metrics/transfer")
            return Metrics(**response.json())
        except ValidationError as e:
            raise ValidationError(f"Failed to get metrics: {e}")
