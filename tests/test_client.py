import unittest
from unittest.mock import patch, Mock

import requests

from pyoutlineapi.client import PyOutlineWrapper
from pyoutlineapi.exceptions import APIError
from pyoutlineapi.models import Server, DataLimit


class TestPyOutlineWrapper(unittest.TestCase):

    def setUp(self):
        self.api_url = "https://example.com"
        self.cert_sha256 = "dummy-sha256"
        self.wrapper = PyOutlineWrapper(api_url=self.api_url, cert_sha256=self.cert_sha256)

    @patch("pyoutlineapi.client.requests.Session.request")
    def test_request_success(self, mock_request):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_request.return_value = mock_response

        response = self.wrapper._request("GET", "test-endpoint")
        self.assertEqual(response.status_code, 200)

    @patch("pyoutlineapi.client.requests.Session.request")
    def test_request_failure(self, mock_request):
        mock_request.side_effect = requests.RequestException("Connection error")

        with self.assertRaises(APIError):
            self.wrapper._request("GET", "test-endpoint")

    @patch("pyoutlineapi.client.requests.Response.json")
    def test_parse_response_success(self, mock_json):
        mock_json.return_value = {
            "name": "Test Server",
            "serverId": "12345",
            "metricsEnabled": True,
            "createdTimestampMs": 1609459200000,
            "portForNewAccessKeys": 8080
        }

        response = Mock()
        response.json = mock_json

        result = self.wrapper._parse_response(response, Server)
        self.assertIsInstance(result, str)  # JSON format is True by default

    @patch.object(PyOutlineWrapper, '_request')
    def test_get_server_info(self, mock_request):
        mock_request.return_value.json.return_value = {
            "name": "Test Server",
            "serverId": "12345",
            "metricsEnabled": True,
            "createdTimestampMs": 1609459200000,
            "portForNewAccessKeys": 8080
        }

        result = self.wrapper.get_server_info()
        self.assertIsInstance(result, str)

    @patch.object(PyOutlineWrapper, '_request')
    def test_create_access_key(self, mock_request):
        mock_request.return_value.json.return_value = {
            "id": "test_id",
            "name": "Test Access Key",
            "password": "secret",
            "port": 8080,
            "method": "aes-256-gcm",
            "accessUrl": "ss://..."
        }

        result = self.wrapper.create_access_key(name="Test Access Key", password="secret", port=8080)
        self.assertIsInstance(result, str)

    @patch.object(PyOutlineWrapper, '_request')
    def test_get_access_keys(self, mock_request):
        mock_request.return_value.json.return_value = {
            "accessKeys": [{
                "id": "test_id",
                "name": "Test Access Key",
                "password": "secret",
                "port": 8080,
                "method": "aes-256-gcm",
                "accessUrl": "ss://..."
            }]
        }

        result = self.wrapper.get_access_keys()
        self.assertIsInstance(result, str)

    @patch.object(PyOutlineWrapper, '_request')
    def test_delete_access_key(self, mock_request):
        mock_request.return_value.status_code = 204

        result = self.wrapper.delete_access_key("test_id")
        self.assertTrue(result)

    @patch.object(PyOutlineWrapper, '_request')
    def test_update_server_port(self, mock_request):
        mock_request.return_value.status_code = 204

        result = self.wrapper.update_server_port(8080)
        self.assertTrue(result)

    @patch.object(PyOutlineWrapper, '_request')
    def test_set_access_key_data_limit(self, mock_request):
        mock_request.return_value.status_code = 204

        data_limit = DataLimit(bytes=1000000)
        result = self.wrapper.set_access_key_data_limit("test_id", data_limit)
        self.assertTrue(result)

    @patch.object(PyOutlineWrapper, '_request')
    def test_remove_access_key_data_limit(self, mock_request):
        mock_request.return_value.status_code = 204

        result = self.wrapper.remove_access_key_data_limit("test_id")
        self.assertTrue(result)

    @patch.object(PyOutlineWrapper, '_request')
    def test_get_metrics(self, mock_request):
        mock_request.return_value.json.return_value = {
            "bytesTransferredByUserId": {
                "user1": 1000,
                "user2": 2000
            }
        }

        result = self.wrapper.get_metrics()
        self.assertIsInstance(result, str)
