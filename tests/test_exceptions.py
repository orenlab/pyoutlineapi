"""
Copyright (c) 2024 Denis Rozhnovskiy <pytelemonbot@mail.ru>

This file is part of the PyOutline project.

PyOutline is a Python package for interacting with the Outline VPN Server.

Licensed under the MIT License. See the LICENSE file for more details.

"""

from pyoutlineapi import exceptions as e


def test_api_error():
    error = e.APIError("API general error")
    assert str(error) == "API general error"
    assert isinstance(error, Exception)


def test_request_error():
    error = e.RequestError("Connection failed")
    assert str(error) == "An error occurred while requesting data: Connection failed"
    assert isinstance(error, e.APIError)
    assert isinstance(error, Exception)


def test_validation_error():
    error = e.ValidationError("Invalid data format")
    assert str(error) == "Validation error occurred: Invalid data format"
    assert isinstance(error, e.APIError)
    assert isinstance(error, Exception)
