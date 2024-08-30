from typing import Optional, Type, Any

import requests
from pydantic import BaseModel, ValidationError as PydanticValidationError
from requests_toolbelt.adapters.fingerprint import FingerprintAdapter

from pyoutlineapi.exceptions import APIError, ValidationError, HTTPError
from pyoutlineapi.logger import setup_logger
from pyoutlineapi.models import (
    AccessKeyCreateRequest,
    Server,
    AccessKey,
    AccessKeyList,
    ServerPort,
    DataLimit,
    Metrics
)

# Set up logging
logger = setup_logger(__name__)

__all__ = [
    'PyOutlineWrapper'
]


class PyOutlineWrapper:
    """
    Class for interacting with the Outline VPN Server.

    This class provides methods for managing access keys, retrieving server
    information, updating server settings, and monitoring data usage.

    Attributes:
        _api_url (str): The base URL of the API.
        _cert_sha256 (str): SHA-256 fingerprint of the certificate for authenticity verification.
        _verify_tls (bool): Whether to verify the TLS certificate.
    """

    def __init__(self, api_url: str, cert_sha256: str, verify_tls: bool = True, json_format: Optional[bool] = False):
        """
        Initialize PyOutlineAPI.

        Args:
            api_url (str): The base URL of the API.
            cert_sha256 (str): SHA-256 fingerprint of the certificate.
            verify_tls (bool, optional): Whether to verify the TLS certificate. Defaults to True.
            json_format (bool, optional): Whether to return responses in JSON format. Defaults to False.
        """
        self._api_url = api_url
        self._cert_sha256 = cert_sha256
        self._verify_tls = verify_tls
        self._json_format = json_format
        self._session = requests.Session()
        self._session.mount(self._api_url, FingerprintAdapter(self._cert_sha256))

    def _request(self, method: str, endpoint: str, json_data=None) -> requests.Response:
        """
        Perform an HTTP request to the API.

        Args:
            method (str): HTTP method (GET, POST, PUT, DELETE).
            endpoint (str): API endpoint.
            json_data (Dict[str, Any], optional): Data to send in the request body.

        Returns:
            requests.Response: The HTTP response object.

        Raises:
            APIError: If the request fails.
        """
        url = f"{self._api_url}/{endpoint}"
        try:
            response = self._session.request(
                method,
                url,
                json=json_data,
                verify=self._verify_tls,
                timeout=15
            )
            response.raise_for_status()
            return response
        except (requests.RequestException, HTTPError) as exception:
            raise APIError(f"Request to {url} failed: {exception}")

    def _parse_response(self, response: requests.Response, model: Type[BaseModel]) -> Any:
        """
        Validate response data and optionally convert to JSON format.

        Args:
            response (requests.Response): The HTTP response object.
            model (Type[BaseModel]): The Pydantic model class for validation.

        Returns:
            Any: The validated and optionally JSON-formatted response data.

        Raises:
            ValidationError: If the response data is invalid.
        """
        try:
            data = model(**response.json())
            if self._json_format:
                return data.model_dump_json()
            return data
        except PydanticValidationError as e:
            raise ValidationError(f"Validation error: {e}")

    def get_server_info(self) -> Any:
        """
        Get information about the server.

        Returns:
            Any: An object containing server information, or JSON-formatted data if json_format is True.

        Raises:
            APIError: If the request fails.
            ValidationError: If the response data is invalid.

        Example:
            server_info = api.get_server_info()
        """
        try:
            response = self._request("GET", "server")
            return self._parse_response(response, Server)
        except PydanticValidationError as e:
            raise ValidationError(f"Failed to get server info: {e}")

    def create_access_key(self, name: Optional[str] = None, password: Optional[str] = None,
                          port: Optional[int] = None) -> Any:
        """
        Create a new access key.

        Args:
            name (Optional[str]): Name of the access key. Defaults to None.
            password (Optional[str]): Password for the access key. Defaults to None.
            port (Optional[int]): Port for the access key. Defaults to None.

        Returns:
            Any: An object containing information about the new access key, or JSON-formatted data if json_format is True.

        Raises:
            ValidationError: If the server response is not 201 or if there's an issue with the request.

        Example:
            access_key = api.create_access_key(name="User1", password="securepassword")
        """
        request_data = {
            "name": name,
            "password": password,
            "port": port,
        }
        request_data = {key: value for key, value in request_data.items() if value is not None}

        try:
            if request_data:
                request_data = AccessKeyCreateRequest(**request_data).model_dump(mode="json")
            else:
                request_data = None

            response = self._request("POST", "access-keys", json_data=request_data)

            if response.status_code == 201:
                return self._parse_response(response, AccessKey)
            else:
                raise ValidationError(f"Failed to create access key: {response.status_code} - {response.text}")

        except (PydanticValidationError, KeyError, requests.RequestException) as e:
            raise ValidationError(f"Failed to create access key: {e}")

    def get_access_keys(self) -> Any:
        """
        Get a list of all access keys.

        Returns:
            Any: An object containing a list of access keys, or JSON-formatted data if json_format is True.

        Raises:
            APIError: If the request fails.
            ValidationError: If the response data is invalid.

        Example:
            access_keys = api.get_access_keys()
        """
        try:
            response = self._request("GET", "access-keys")
            return self._parse_response(response, AccessKeyList)
        except PydanticValidationError as e:
            raise ValidationError(f"Failed to get access keys: {e}")

    def delete_access_key(self, key_id: str) -> bool:
        """
        Delete an access key by its ID.

        Args:
            key_id (str): The ID of the access key.

        Returns:
            bool: True if the access key was successfully deleted, False otherwise.

        Raises:
            APIError: If the request fails.

        Example:
            success = api.delete_access_key(key_id="some_key_id")
        """
        try:
            response = self._request("DELETE", f"access-keys/{key_id}")
            return response.status_code == 204
        except HTTPError as e:
            raise APIError(f"Failed to delete access key with ID {key_id}: {e}")

    def update_server_port(self, port: ServerPort | int) -> bool:
        """
        Update the port for new access keys.

        Args:
            port (ServerPort): The new port.

        Returns:
            bool: True if the server port was successfully updated, False otherwise.

        Raises:
            APIError: If the request fails.

        Example:
            success = api.update_server_port(port=12345)
        """
        try:
            response = self._request("PUT", "server/port-for-new-access-keys", {"port": port})
            if response.status_code == 409:
                raise APIError(f"Port {port} is already in use")
            return response.status_code == 204
        except (PydanticValidationError, APIError) as e:
            raise APIError(f"Failed to update server port: {e}")

    def set_access_key_data_limit(self, key_id: str, limit: DataLimit) -> bool:
        """
        Set the data limit for an access key.

        Args:
            key_id (str): The ID of the access key.
            limit (DataLimit): The data limit in bytes.

        Returns:
            bool: True if the data limit was successfully set, False otherwise.

        Raises:
            APIError: If the request fails.

        Example:
            success = api.set_access_key_data_limit(key_id="some_key_id", limit=DataLimit(bytes=1048576))
        """
        try:
            response = self._request("PUT", f"access-keys/{key_id}/data-limit", {"bytes": limit})
            return response.status_code == 204
        except (PydanticValidationError, APIError) as e:
            raise APIError(f"Failed to set data limit for access key with ID {key_id}: {e}")

    def get_metrics(self) -> Metrics:
        """
        Get metrics about data transfer.

        Returns:
            Metrics: An object containing data transfer metrics.

        Raises:
            APIError: If the request fails.
            ValidationError: If the response data is invalid.

        Example:
            metrics = api.get_metrics()
        """
        try:
            response = self._request("GET", "metrics/transfer")
            return self._parse_response(response, Metrics)
        except PydanticValidationError as e:
            raise ValidationError(f"Failed to get metrics: {e}")
