import unittest
from unittest.mock import patch, Mock

import requests
from pydantic import SecretStr

from pyoutlineapi.client import PyOutlineWrapper
from pyoutlineapi.exceptions import ValidationError, APIError
from pyoutlineapi.models import (
    Server,
    AccessKey,
    AccessKeyList,
    ServerPort,
    DataLimit,
    Metrics
)


class TestPyOutlineWrapper(unittest.TestCase):
    def setUp(self):
        self.api_url = "https://api.example.com"
        self.cert_sha256 = "dummy_sha256"
        self.wrapper = PyOutlineWrapper(self.api_url, self.cert_sha256)

    @patch('pyoutlineapi.client.requests.Session.request')
    def test_get_server_info(self, mock_request):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "name": "Test Server",
            "serverId": "server_id",
            "metricsEnabled": True,
            "createdTimestampMs": 1234567890,
            "portForNewAccessKeys": 443
        }
        mock_request.return_value = mock_response

        server = self.wrapper.get_server_info()
        self.assertIsInstance(server, Server)
        self.assertEqual(server.name, "Test Server")
        self.assertEqual(server.serverId, "server_id")

    @patch('pyoutlineapi.client.requests.Session.request')
    def test_create_access_key(self, mock_request):
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": "key_id",
            "name": "Test Key",
            "password": "secret_password",
            "port": 1234,
            "method": "method",
            "accessUrl": "https://example.com"
        }
        mock_request.return_value = mock_response

        access_key = self.wrapper.create_access_key(name="Test Key", password="secret_password", port=1234)
        self.assertIsInstance(access_key, AccessKey)
        self.assertEqual(access_key.id, "key_id")
        self.assertEqual(access_key.name, "Test Key")
        self.assertEqual(access_key.password.get_secret_value(), "secret_password")
        self.assertEqual(access_key.port, 1234)
        self.assertEqual(access_key.method, "method")
        self.assertEqual(access_key.accessUrl.get_secret_value(), "https://example.com")

    @patch('pyoutlineapi.client.requests.Session.request')
    def test_create_access_key_invalid_data(self, mock_request):
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = 'Invalid request'
        mock_request.return_value = mock_response

        with self.assertRaises(ValidationError):
            self.wrapper.create_access_key(name="Test Key")

    @patch('pyoutlineapi.client.requests.Session.request')
    def test_create_access_key_password_hidden(self, mock_request):
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": "key123",
            "name": "Test Key",
            "password": "test_password",
            "port": 12345,
            "method": "aes-256-cfb",
            "accessUrl": "outline://accessurl"
        }
        mock_request.return_value = mock_response

        access_key = self.wrapper.create_access_key(name="Test Key", password="test_password", port=12345)
        self.assertTrue(isinstance(access_key.password, SecretStr))
        self.assertEqual(access_key.password.get_secret_value(), "test_password")

    @patch('pyoutlineapi.client.requests.Session.request')
    def test_get_server_info_invalid_data(self, mock_request):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"unexpectedField": "unexpectedValue"}
        mock_request.return_value = mock_response

        with self.assertRaises(ValidationError):
            self.wrapper.get_server_info()

    @patch('pyoutlineapi.client.requests.Session.request')
    def test_delete_access_key(self, mock_request):
        mock_response = Mock()
        mock_response.status_code = 204
        mock_request.return_value = mock_response

        result = self.wrapper.delete_access_key("key_id")
        self.assertTrue(result)

    @patch('pyoutlineapi.client.requests.Session.request')
    def test_delete_access_key_error(self, mock_request):
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError('Not Found')
        mock_request.return_value = mock_response

        with self.assertRaises(APIError):
            self.wrapper.delete_access_key("key_id")

    @patch('pyoutlineapi.client.requests.Session.request')
    def test_update_server_port(self, mock_request):
        mock_response = Mock()
        mock_response.status_code = 204
        mock_request.return_value = mock_response

        result = self.wrapper.update_server_port(ServerPort(port=1234))
        self.assertTrue(result)

    @patch('pyoutlineapi.client.requests.Session.request')
    def test_update_server_port_conflict(self, mock_request):
        mock_response = Mock()
        mock_response.status_code = 409
        mock_response.text = 'Conflict'
        mock_request.return_value = mock_response

        with self.assertRaises(APIError):
            self.wrapper.update_server_port(ServerPort(port=1234))

    @patch('pyoutlineapi.client.requests.Session.request')
    def test_set_access_key_data_limit(self, mock_request):
        mock_response = Mock()
        mock_response.status_code = 204
        mock_request.return_value = mock_response

        result = self.wrapper.set_access_key_data_limit("key_id", DataLimit(bytes=1000))
        self.assertTrue(result)

    @patch('pyoutlineapi.client.requests.Session.request')
    def test_get_metrics(self, mock_request):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "bytesTransferredByUserId": {"user1": 12345}
        }
        mock_request.return_value = mock_response

        metrics = self.wrapper.get_metrics()
        self.assertIsInstance(metrics, Metrics)
        self.assertEqual(metrics.bytesTransferredByUserId, {"user1": 12345})

    @patch('pyoutlineapi.client.requests.Session.request')
    def test_get_metrics_invalid_data(self, mock_request):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"unexpectedField": "unexpectedValue"}
        mock_request.return_value = mock_response

        with self.assertRaises(ValidationError):
            self.wrapper.get_metrics()

    @patch('pyoutlineapi.client.requests.Session.request')
    def test_get_access_keys_empty(self, mock_request):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"accessKeys": []}
        mock_request.return_value = mock_response

        access_keys = self.wrapper.get_access_keys()
        self.assertIsInstance(access_keys, AccessKeyList)
        self.assertEqual(len(access_keys.accessKeys), 0)

    @patch('pyoutlineapi.client.requests.Session.request')
    def test_handle_api_error(self, mock_request):
        mock_request.side_effect = requests.exceptions.HTTPError("500 Internal Server Error")
        with self.assertRaises(APIError):
            self.wrapper.get_server_info()


if __name__ == '__main__':
    unittest.main()
