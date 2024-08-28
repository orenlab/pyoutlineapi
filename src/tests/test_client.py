"""
Copyright (c) 2024 Denis Rozhnovskiy <pytelemonbot@mail.ru>

This file is part of the PyOutline project.

PyOutline is a Python package for interacting with the Outline VPN Server.

Licensed under the MIT License. See the LICENSE file for more details.

"""

import unittest
from unittest.mock import patch, Mock

import requests

from src.pyoutlineapi import models as models, client as pyoutline_client, exceptions as exceptions


class TestPyOutline(unittest.TestCase):
    def setUp(self):
        """Setup for test cases."""
        self.api_url = "https://api.example.com"
        self.cert_sha256 = "dummy_cert_sha256"
        self.api = pyoutline_client.PyOutlineWrapper(self.api_url, self.cert_sha256)

    @patch('client.requests.Session.request')
    def test_get_server_info(self, mock_request):
        """Test the get_server_info method."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "name": "Test Server",
            "serverId": "123",
            "metricsEnabled": True,
            "createdTimestampMs": 123456789,
            "portForNewAccessKeys": 8080
        }
        mock_request.return_value = mock_response

        server_info = self.api.get_server_info()
        self.assertIsInstance(server_info, models.Server)
        self.assertEqual(server_info.name, "Test Server")
        self.assertEqual(server_info.serverId, "123")
        self.assertTrue(server_info.metricsEnabled)
        self.assertEqual(server_info.createdTimestampMs, 123456789)
        self.assertEqual(server_info.portForNewAccessKeys, 8080)
        mock_request.assert_called_once_with("GET", f"{self.api_url}/server", json=None, verify=True)

    @patch('client.requests.Session.request')
    def test_create_access_key(self, mock_request):
        """Test the create_access_key method."""
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

        access_key = self.api.create_access_key()
        self.assertIsInstance(access_key, models.AccessKey)
        self.assertEqual(access_key.id, "key_id")
        self.assertEqual(access_key.name, "Test Key")
        self.assertEqual(access_key.password.get_secret_value(), "secret_password")
        self.assertEqual(access_key.port, 1234)
        self.assertEqual(access_key.method, "method")
        self.assertEqual(access_key.accessUrl.get_secret_value(), "https://example.com")
        mock_request.assert_called_once_with("POST", f"{self.api_url}/access-keys", json=None, verify=True)

    @patch('client.requests.Session.request')
    def test_get_access_keys(self, mock_request):
        """Test the get_access_keys method."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "accessKeys": [
                {
                    "id": "key_id1",
                    "name": "Test Key 1",
                    "password": "secret_password_1",
                    "port": 1234,
                    "method": "method1",
                    "accessUrl": "https://example1.com"
                },
                {
                    "id": "key_id2",
                    "name": "Test Key 2",
                    "password": "secret_password_2",
                    "port": 5678,
                    "method": "method2",
                    "accessUrl": "https://example2.com"
                }
            ]
        }
        mock_request.return_value = mock_response

        access_key_list = self.api.get_access_keys()
        self.assertIsInstance(access_key_list, models.AccessKeyList)
        self.assertEqual(len(access_key_list.accessKeys), 2)
        self.assertEqual(access_key_list.accessKeys[0].id, "key_id1")
        self.assertEqual(access_key_list.accessKeys[1].id, "key_id2")
        mock_request.assert_called_once_with("GET", f"{self.api_url}/access-keys", json=None, verify=True)

    @patch('client.requests.Session.request')
    def test_delete_access_key(self, mock_request):
        """Test the delete_access_key method."""
        mock_response = Mock()
        mock_response.status_code = 204
        mock_request.return_value = mock_response

        self.api.delete_access_key("key_id")
        mock_request.assert_called_once_with("DELETE", f"{self.api_url}/access-keys/key_id", json=None, verify=True)

    @patch('client.requests.Session.request')
    def test_update_server_port(self, mock_request):
        """Test the update_server_port method."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"port": 1234}
        mock_request.return_value = mock_response

        server_port = self.api.update_server_port(1234)
        self.assertIsInstance(server_port, models.ServerPort)
        self.assertEqual(server_port.port, 1234)
        mock_request.assert_called_once_with("PUT", f"{self.api_url}/server/port-for-new-access-keys",
                                             json={"port": 1234}, verify=True)

    @patch('client.requests.Session.request')
    def test_set_access_key_data_limit(self, mock_request):
        """Test the set_access_key_data_limit method."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"bytes": 1000000}
        mock_request.return_value = mock_response

        data_limit = self.api.set_access_key_data_limit("key_id", 1000000)
        self.assertIsInstance(data_limit, models.DataLimit)
        self.assertEqual(data_limit.bytes, 1000000)
        mock_request.assert_called_once_with("PUT", f"{self.api_url}/access-keys/key_id/data-limit",
                                             json={"bytes": 1000000}, verify=True)

    @patch('client.requests.Session.request')
    def test_set_metrics_enabled(self, mock_request):
        """Test the set_metrics_enabled method."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"enabled": True}
        mock_request.return_value = mock_response

        metrics_enabled = self.api.set_metrics_enabled(True)
        self.assertIsInstance(metrics_enabled, models.MetricsEnabled)
        self.assertTrue(metrics_enabled.enabled)
        mock_request.assert_called_once_with("PUT", f"{self.api_url}/server/metrics/enabled", json={"enabled": True},
                                             verify=True)

    @patch('client.requests.Session.request')
    def test_get_metrics(self, mock_request):
        """Test the get_metrics method."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "bytesTransferredByUserId": {
                "0": 3353820783,
                "1": 12827443528
            }
        }
        mock_request.return_value = mock_response

        metrics = self.api.get_metrics()
        self.assertIsInstance(metrics, models.Metrics)
        self.assertEqual(metrics.bytesTransferredByUserId, {"0": 3353820783, "1": 12827443528})
        mock_request.assert_called_once_with("GET", f"{self.api_url}/metrics/transfer", json=None, verify=True)

    @patch('client.requests.Session.request')
    def test_request_error_handling(self, mock_request):
        """Test the error handling in _request method."""
        mock_request.side_effect = requests.RequestException("Test exception")

        with self.assertRaises(exceptions.APIError):
            self.api._request("GET", "server")

    @patch('client.requests.Session.request')
    def test_get_server_info_invalid_data(self, mock_request):
        """Test handling of invalid data from get_server_info."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "unexpectedField": "unexpectedValue"
        }
        mock_request.return_value = mock_response

        with self.assertRaises(ValueError):
            self.api.get_server_info()

    @patch('client.requests.Session.request')
    def test_create_access_key_invalid_data(self, mock_request):
        """Test handling of invalid data from create_access_key."""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": "key_id",
            "name": "Test Key",
            "password": "secret_password",
            "port": 1234,
            "method": "method"
            # Missing 'accessUrl'
        }
        mock_request.return_value = mock_response

        with self.assertRaises(ValueError):
            self.api.create_access_key()


if __name__ == '__main__':
    unittest.main()
