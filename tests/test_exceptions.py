"""
Copyright (c) 2024 Denis Rozhnovskiy <pytelemonbot@mail.ru>

This file is part of the PyOutlineAPI project.

PyOutlineAPI is a Python package for interacting with the Outline VPN Server.

Licensed under the MIT License. See the LICENSE file for more details.

"""

import unittest
from pyoutlineapi.exceptions import APIError, HTTPError, RequestError, ValidationError

class TestAPIError(unittest.TestCase):
    def test_api_error_initialization(self):
        """Test initialization of APIError."""
        error = APIError("Test API Error")
        self.assertEqual(str(error), "Test API Error")
        self.assertEqual(error.message, "Test API Error")

class TestHTTPError(unittest.TestCase):
    def test_http_error_initialization(self):
        """Test initialization of HTTPError."""
        error = HTTPError(404, "Not Found")
        self.assertEqual(str(error), "HTTP error occurred: 404 - Not Found")
        self.assertEqual(error.status_code, 404)
        self.assertEqual(error.message, "Not Found")

class TestRequestError(unittest.TestCase):
    def test_request_error_initialization(self):
        """Test initialization of RequestError."""
        error = RequestError("Connection failed")
        self.assertEqual(str(error), "An error occurred while requesting data: Connection failed")

class TestValidationError(unittest.TestCase):
    def test_validation_error_initialization(self):
        """Test initialization of ValidationError."""
        error = ValidationError("Invalid data format")
        self.assertEqual(str(error), "Validation error occurred: Invalid data format")

if __name__ == '__main__':
    unittest.main()