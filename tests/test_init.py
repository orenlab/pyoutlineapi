"""
Tests for PyOutlineAPI __init__ module.

PyOutlineAPI: A modern, async-first Python client for the Outline VPN Server API.

Copyright (c) 2025 Denis Rozhnovskiy <pytelemonbot@mail.ru>
All rights reserved.

This software is licensed under the MIT License.
You can find the full license text at:
    https://opensource.org/licenses/MIT

Source code repository:
    https://github.com/orenlab/pyoutlineapi
"""
from unittest import mock

import pytest

import pyoutlineapi
from pyoutlineapi import check_python_version


def test_check_python_version_raises():
    with mock.patch("sys.version_info", (3, 9)):
        with pytest.raises(RuntimeError, match="requires Python 3.10"):
            check_python_version()


def test_version_from_metadata():
    """Ensure __version__ is loaded correctly from metadata or fallback."""
    assert isinstance(pyoutlineapi.__version__, str)
    assert pyoutlineapi.__version__ != ""


def test_all_exports():
    """Check that __all__ contains expected public API symbols."""
    for name in pyoutlineapi.__all__:
        assert hasattr(pyoutlineapi, name)


def test_metadata_constants():
    assert pyoutlineapi.__author__ == "Denis Rozhnovskiy"
    assert pyoutlineapi.__email__ == "pytelemonbot@mail.ru"
    assert pyoutlineapi.__license__ == "MIT"
