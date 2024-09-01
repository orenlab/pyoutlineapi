from typing import Union, Optional, Type

import requests
from pydantic import BaseModel, ValidationError
from requests_toolbelt.adapters.fingerprint import FingerprintAdapter

from pyoutlineapi.exceptions import APIError
from pyoutlineapi.models import DataLimit, ServerPort, Metrics, AccessKeyList, AccessKey, AccessKeyCreateRequest, Server


class PyOutlineWrapper:
    """
    Class for interacting with the Outline VPN Server API.

    This class provides methods to interact with the Outline VPN Server, including:

    - Retrieving server information
    - Creating, listing, and deleting access keys
    - Updating server ports
    - Setting and removing data limits for access keys
    - Retrieving metrics

    The class uses the `requests` library for making HTTP requests and `pydantic` for data validation.
    Responses can be returned either as Pydantic models or in JSON format, depending on the `json_format` parameter.
    """

    def __init__(self, api_url: str, cert_sha256: str, verify_tls: bool = True, json_format: bool = True):
        """
        Initializes the PyOutlineWrapper with the given API URL, certificate fingerprint, and options for TLS verification
        and response format.

        Args:
            api_url (str): The base URL of the Outline VPN Server API.
            cert_sha256 (str): The SHA-256 fingerprint of the server's certificate.
            verify_tls (bool, optional): Whether to verify the server's TLS certificate. Defaults to True.
            json_format (bool, optional): Whether to return responses in JSON format. Defaults to True.
        """
        self._api_url = api_url
        self._cert_sha256 = cert_sha256
        self._verify_tls = verify_tls
        self._json_format = json_format
        self._session = requests.Session()
        self._session.mount(self._api_url, FingerprintAdapter(self._cert_sha256))

    def _request(self, method: str, endpoint: str, json_data=None) -> requests.Response:
        """
        Makes an HTTP request to the API.

        Args:
            method (str): The HTTP method to use (e.g., 'GET', 'POST', 'PUT', 'DELETE').
            endpoint (str): The API endpoint to call.
            json_data (optional): The JSON data to send with the request.

        Returns:
            requests.Response: The HTTP response object.

        Raises:
            APIError: If the request fails or the response status is not successful.
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
        except requests.RequestException as exception:
            raise APIError(f"Request to {url} failed: {exception}")

    def _parse_response(self, response: requests.Response, model: Type[BaseModel]) -> Union[BaseModel, str]:
        """
        Parses the response from the API.

        Args:
            response (requests.Response): The HTTP response object.
            model (Type[BaseModel]): The Pydantic model to validate the response data.

        Returns:
            Union[BaseModel, str]: The validated data as a Pydantic model or a JSON string, depending on the json_format parameter.

        Raises:
            ValidationError: If the response data does not match the Pydantic model.
        """
        try:
            json_data = response.json()
            data = model.model_validate(json_data)
            return data.model_dump_json() if self._json_format else data
        except ValidationError as e:
            raise ValidationError(f"Validation error: {e}")

    def get_server_info(self) -> Union[Server, str]:
        """
        Retrieves information about the Outline VPN server.

        Returns:
            Union[Server, str]: The server information as a Pydantic model or a JSON string.
        """
        response = self._request("GET", "server")
        return self._parse_response(response, Server)

    def create_access_key(self, name: Optional[str] = None, password: Optional[str] = None,
                          port: Optional[int] = None) -> Union[AccessKey, str]:
        """
        Creates a new access key.

        Args:
            name (Optional[str]): The name of the access key.
            password (Optional[str]): The password for the access key.
            port (Optional[int]): The port for the access key.

        Returns:
            Union[AccessKey, str]: The created access key as a Pydantic model or a JSON string.
        """
        request_data = {
            "name": name,
            "password": password,
            "port": port,
        }
        request_data = {key: value for key, value in request_data.items() if value is not None}

        if request_data:
            request_data = AccessKeyCreateRequest(**request_data).model_dump()

        response = self._request("POST", "access-keys", json_data=request_data)
        return self._parse_response(response, AccessKey)

    def get_access_keys(self) -> Union[AccessKeyList, str]:
        """
        Retrieves a list of all access keys.

        Returns:
            Union[AccessKeyList, str]: The list of access keys as a Pydantic model or a JSON string.
        """
        response = self._request("GET", "access-keys")
        return self._parse_response(response, AccessKeyList)

    def delete_access_key(self, key_id: str) -> bool:
        """
        Deletes an access key by its ID.

        Args:
            key_id (str): The ID of the access key to delete.

        Returns:
            bool: True if the access key was successfully deleted, False otherwise.
        """
        response = self._request("DELETE", f"access-keys/{key_id}")
        return response.status_code == 204

    def update_server_port(self, port: int) -> bool:
        """
        Updates the port for new access keys on the server.

        Args:
            port (int): The new port number.

        Returns:
            bool: True if the port was successfully updated, False otherwise.

        Raises:
            APIError: If the port is already in use.
        """
        verified_port = ServerPort(port=port)
        response = self._request("PUT", "server/port-for-new-access-keys", {"port": verified_port.port})
        if response.status_code == 409:
            raise APIError(f"Port {verified_port.port} is already in use")
        return response.status_code == 204

    def set_access_key_data_limit(self, key_id: str, limit: DataLimit) -> bool:
        """
        Sets a data limit for an access key.

        Args:
            key_id (str): The ID of the access key.
            limit (DataLimit): The data limit to set.

        Returns:
            bool: True if the data limit was successfully set, False otherwise.
        """
        response = self._request("PUT", f"access-keys/{key_id}/data-limit", {"bytes": limit.bytes})
        return response.status_code == 204

    def get_metrics(self) -> Union[Metrics, str]:
        """
        Retrieves transfer metrics from the server.

        Returns:
            Union[Metrics, str]: The metrics data as a Pydantic model or a JSON string.
        """
        response = self._request("GET", "metrics/transfer")
        return self._parse_response(response, Metrics)

    def remove_access_key_data_limit(self, key_id: str) -> bool:
        """
        Removes the data limit for an access key.

        Args:
            key_id (str): The ID of the access key.

        Returns:
            bool: True if the data limit was successfully removed, False otherwise.
        """
        response = self._request("DELETE", f"access-keys/{key_id}/data-limit")
        return response.status_code == 204


__all__ = ["PyOutlineWrapper"]
