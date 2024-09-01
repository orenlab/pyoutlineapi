"""
Copyright (c) 2024 Denis Rozhnovskiy <pytelemonbot@mail.ru>

This file is part of the PyOutlineAPI project.

PyOutlineAPI is a Python package for interacting with the Outline VPN Server.

Licensed under the MIT License. See the LICENSE file for more details.
"""

import unittest

from pydantic import ValidationError

from pyoutlineapi.models import Server, ServerPort, DataLimit, AccessKey, Metrics


class TestPyOutlineModels(unittest.TestCase):

    def test_server_model_invalid_timestamp(self):
        """Test that Server model raises ValidationError for invalid timestamp."""
        with self.assertRaises(ValidationError):
            Server(
                name="Test Server",
                serverId="server-id",
                metricsEnabled=True,
                createdTimestampMs=-1609459200000,  # Invalid negative timestamp
                portForNewAccessKeys=12345
            )

    def test_server_port_invalid_range(self):
        """Test that ServerPort model raises ValidationError for port out of range."""
        with self.assertRaises(ValidationError):
            ServerPort(port=70000)  # Port number out of valid range

    def test_data_limit_negative_bytes(self):
        """Test that DataLimit model raises ValidationError for negative bytes."""
        with self.assertRaises(ValidationError):
            DataLimit(bytes=-1)  # Negative value not allowed

    def test_access_key_invalid_port(self):
        """Test that AccessKey model raises ValidationError for invalid port."""
        with self.assertRaises(ValidationError):
            AccessKey(
                id="access-key-id",
                name="test-key",
                password="test-password",
                port=70000,  # Invalid port number
                method="aes-256-cfb",
                accessUrl="ss://example"
            )

    def test_metrics_invalid_data(self):
        """Test that Metrics model raises ValidationError for invalid dictionary data."""
        with self.assertRaises(ValidationError):
            Metrics(bytesTransferredByUserId={"user1": -100})  # Negative bytes transferred

    def test_access_key_empty_password(self):
        """Test that AccessKey model raises ValidationError for empty password."""
        with self.assertRaises(ValidationError):
            AccessKey(
                id="access-key-id",
                name="test-key",
                password="",  # Empty password
                port=12345,
                method="aes-256-cfb",
                accessUrl="ss://example"
            )

    def test_access_key_invalid_url(self):
        """Test that AccessKey model raises ValidationError for invalid accessUrl."""
        with self.assertRaises(ValidationError):
            AccessKey(
                id="access-key-id",
                name="test-key",
                password="test-password",
                port=12345,
                method="aes-256-cfb",
                accessUrl=""  # Invalid access URL
            )


if __name__ == "__main__":
    unittest.main()
