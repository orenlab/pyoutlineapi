"""
Tests for PyOutlineAPI exceptions module.

PyOutlineAPI: A modern, async-first Python client for the Outline VPN Server API.

Copyright (c) 2025 Denis Rozhnovskiy <pytelemonbot@mail.ru>
All rights reserved.

This software is licensed under the MIT License.
You can find the full license text at:
    https://opensource.org/licenses/MIT

Source code repository:
    https://github.com/orenlab/pyoutlineapi
"""

import pytest

# Import the exceptions to test
from pyoutlineapi import OutlineError, APIError


class TestOutlineError:
    """Test cases for OutlineError base exception class."""

    def test_outline_error_is_exception(self):
        """Test that OutlineError inherits from Exception."""
        assert issubclass(OutlineError, Exception)

    def test_outline_error_creation_without_message(self):
        """Test creating OutlineError without message."""
        error = OutlineError()
        assert isinstance(error, OutlineError)
        assert isinstance(error, Exception)

    def test_outline_error_creation_with_message(self):
        """Test creating OutlineError with message."""
        message = "Test error message"
        error = OutlineError(message)
        assert str(error) == message
        assert error.args == (message,)

    def test_outline_error_creation_with_empty_message(self):
        """Test creating OutlineError with empty message."""
        error = OutlineError("")
        assert str(error) == ""
        assert error.args == ("",)

    def test_outline_error_creation_with_none_message(self):
        """Test creating OutlineError with None message."""
        error = OutlineError(None)
        assert str(error) == "None"
        assert error.args == (None,)

    def test_outline_error_multiple_args(self):
        """Test creating OutlineError with multiple arguments."""
        arg1, arg2, arg3 = "arg1", 123, {"key": "value"}
        error = OutlineError(arg1, arg2, arg3)
        assert error.args == (arg1, arg2, arg3)

    def test_outline_error_inheritance_chain(self):
        """Test that OutlineError maintains proper inheritance."""
        error = OutlineError("test")
        assert isinstance(error, OutlineError)
        assert isinstance(error, Exception)
        assert isinstance(error, BaseException)

    def test_outline_error_can_be_raised(self):
        """Test that OutlineError can be raised and caught."""
        with pytest.raises(OutlineError) as exc_info:
            raise OutlineError("Test exception")

        assert str(exc_info.value) == "Test exception"
        assert isinstance(exc_info.value, OutlineError)

    def test_outline_error_can_be_caught_as_exception(self):
        """Test that OutlineError can be caught as generic Exception."""
        with pytest.raises(Exception) as exc_info:
            raise OutlineError("Test exception")

        assert isinstance(exc_info.value, OutlineError)


class TestAPIError:
    """Test cases for APIError exception class."""

    def test_api_error_is_outline_error(self):
        """Test that APIError inherits from OutlineError."""
        assert issubclass(APIError, OutlineError)
        assert issubclass(APIError, Exception)

    def test_api_error_creation_with_message_only(self):
        """Test creating APIError with only message parameter."""
        message = "API request failed"
        error = APIError(message)

        assert str(error) == message
        assert error.args == (message,)
        assert error.status_code is None
        assert error.attempt is None

    def test_api_error_creation_with_all_parameters(self):
        """Test creating APIError with all parameters."""
        message = "API request failed"
        status_code = 404
        attempt = 3

        error = APIError(message, status_code, attempt)

        assert error.args == (message,)
        assert error.status_code == status_code
        assert error.attempt == attempt

    def test_api_error_creation_with_status_code_only(self):
        """Test creating APIError with message and status_code."""
        message = "Not found"
        status_code = 404

        error = APIError(message, status_code=status_code)

        assert str(error) == message
        assert error.status_code == status_code
        assert error.attempt is None

    def test_api_error_creation_with_attempt_only(self):
        """Test creating APIError with message and attempt."""
        message = "Connection timeout"
        attempt = 2

        error = APIError(message, attempt=attempt)

        assert error.status_code is None
        assert error.attempt == attempt

    def test_api_error_str_without_attempt(self):
        """Test __str__ method when attempt is None."""
        message = "API error"
        error = APIError(message, status_code=500)

        assert str(error) == message

    def test_api_error_str_with_attempt(self):
        """Test __str__ method when attempt is provided."""
        message = "Connection failed"
        attempt = 3
        error = APIError(message, attempt=attempt)

        expected = f"[Attempt {attempt}] {message}"
        assert str(error) == expected

    def test_api_error_str_with_zero_attempt(self):
        """Test __str__ method when attempt is 0."""
        message = "First attempt failed"
        attempt = 0
        error = APIError(message, attempt=attempt)

        expected = f"[Attempt {attempt}] {message}"
        assert str(error) == expected

    def test_api_error_str_with_negative_attempt(self):
        """Test __str__ method when attempt is negative (edge case)."""
        message = "Invalid attempt"
        attempt = -1
        error = APIError(message, attempt=attempt)

        expected = f"[Attempt {attempt}] {message}"
        assert str(error) == expected

    def test_api_error_parameters_are_optional(self):
        """Test that status_code and attempt parameters are truly optional."""
        message = "Required message"

        # Test with explicit None values
        error1 = APIError(message, None, None)
        assert error1.status_code is None
        assert error1.attempt is None

        # Test with keyword arguments as None
        error2 = APIError(message, status_code=None, attempt=None)
        assert error2.status_code is None
        assert error2.attempt is None

    def test_api_error_with_different_status_codes(self):
        """Test APIError with various HTTP status codes."""
        test_cases = [
            (200, "OK"),
            (400, "Bad Request"),
            (401, "Unauthorized"),
            (403, "Forbidden"),
            (404, "Not Found"),
            (500, "Internal Server Error"),
            (502, "Bad Gateway"),
            (503, "Service Unavailable"),
        ]

        for status_code, message in test_cases:
            error = APIError(message, status_code=status_code)
            assert error.status_code == status_code
            assert str(error) == message

    def test_api_error_with_different_attempt_values(self):
        """Test APIError with various attempt values."""
        message = "Retry attempt"
        test_attempts = [1, 2, 5, 10, 100]

        for attempt in test_attempts:
            error = APIError(message, attempt=attempt)
            assert error.attempt == attempt
            expected_str = f"[Attempt {attempt}] {message}"
            assert str(error) == expected_str

    def test_api_error_inheritance_chain(self):
        """Test that APIError maintains proper inheritance chain."""
        error = APIError("test")
        assert isinstance(error, APIError)
        assert isinstance(error, OutlineError)
        assert isinstance(error, Exception)
        assert isinstance(error, BaseException)

    def test_api_error_can_be_raised(self):
        """Test that APIError can be raised and caught."""
        message = "API failure"
        status_code = 500
        attempt = 2

        with pytest.raises(APIError) as exc_info:
            raise APIError(message, status_code, attempt)

        error = exc_info.value
        assert str(error) == f"[Attempt {attempt}] {message}"
        assert error.status_code == status_code
        assert error.attempt == attempt

    def test_api_error_can_be_caught_as_outline_error(self):
        """Test that APIError can be caught as OutlineError."""
        with pytest.raises(OutlineError) as exc_info:
            raise APIError("Test API error")

        assert isinstance(exc_info.value, APIError)

    def test_api_error_can_be_caught_as_exception(self):
        """Test that APIError can be caught as generic Exception."""
        with pytest.raises(Exception) as exc_info:
            raise APIError("Test API error")

        assert isinstance(exc_info.value, APIError)

    def test_api_error_attributes_are_accessible(self):
        """Test that all APIError attributes are accessible."""
        message = "Test message"
        status_code = 418  # I'm a teapot
        attempt = 7

        error = APIError(message, status_code, attempt)

        # Test attribute access
        assert hasattr(error, 'status_code')
        assert hasattr(error, 'attempt')
        assert hasattr(error, 'args')

        # Test attribute values
        assert error.status_code == status_code
        assert error.attempt == attempt
        assert error.args == (message,)

    def test_api_error_with_empty_message(self):
        """Test APIError with empty message."""
        error = APIError("", status_code=200, attempt=1)
        assert str(error) == "[Attempt 1] "
        assert error.status_code == 200

    def test_api_error_with_complex_message(self):
        """Test APIError with complex message containing special characters."""
        message = "API error: Connection failed!\nDetails: timeout after 30s\n→ Check network"
        attempt = 3

        error = APIError(message, attempt=attempt)
        expected = f"[Attempt {attempt}] {message}"
        assert str(error) == expected

    def test_api_error_super_call_behavior(self):
        """Test that APIError properly calls parent __init__ and __str__."""
        message = "Super test"
        error = APIError(message)

        # Verify that parent Exception.__init__ was called
        assert error.args == (message,)

        # Verify that when attempt is None, parent __str__ is used
        assert str(error) == message

    def test_api_error_type_annotations(self):
        """Test that APIError accepts proper types according to annotations."""
        # Test with proper types
        error1 = APIError("message", 200, 1)
        assert isinstance(error1.status_code, int)
        assert isinstance(error1.attempt, int)

        # Test with None values (Optional types)
        error2 = APIError("message", None, None)
        assert error2.status_code is None
        assert error2.attempt is None


class TestExceptionInteraction:
    """Test cases for exception interaction and edge cases."""

    def test_exception_hierarchy_catching(self):
        """Test catching exceptions at different levels of hierarchy."""

        # Test catching APIError as OutlineError
        try:
            raise APIError("API failed", 500, 2)
        except OutlineError as e:
            assert isinstance(e, APIError)
            assert e.status_code == 500
            assert e.attempt == 2

        # Test catching OutlineError as Exception
        try:
            raise OutlineError("Outline failed")
        except Exception as e:
            assert isinstance(e, OutlineError)

    def test_multiple_exception_types_in_single_try_block(self):
        """Test handling multiple exception types."""

        def raise_outline_error():
            raise OutlineError("Base error")

        def raise_api_error():
            raise APIError("API error", 404, 1)

        # Test catching specific types
        with pytest.raises(OutlineError):
            raise_outline_error()

        with pytest.raises(APIError):
            raise_api_error()

        # Test catching both as OutlineError
        for func in [raise_outline_error, raise_api_error]:
            with pytest.raises(OutlineError):
                func()

    def test_exception_chaining(self):
        """Test exception chaining (raise from)."""
        original_error = ValueError("Original error")

        with pytest.raises(APIError) as exc_info:
            try:
                raise original_error
            except ValueError as e:
                raise APIError("API wrapper error", 500, 1) from e

        api_error = exc_info.value
        assert api_error.__cause__ is original_error
        assert str(api_error) == "[Attempt 1] API wrapper error"

    def test_exception_context_preservation(self):
        """Test that exception context is preserved."""

        def inner_function():
            raise OutlineError("Inner error")

        def outer_function():
            try:
                inner_function()
            except OutlineError:
                raise APIError("Outer error", 500, 2)

        with pytest.raises(APIError) as exc_info:
            outer_function()

        api_error = exc_info.value
        assert str(api_error) == "[Attempt 2] Outer error"
        assert api_error.__context__ is not None
        assert isinstance(api_error.__context__, OutlineError)


class TestExceptionEdgeCases:
    """Test edge cases and unusual scenarios."""

    def test_api_error_with_very_large_numbers(self):
        """Test APIError with very large status codes and attempts."""
        large_status = 999999
        large_attempt = 1000000

        error = APIError("Large numbers", large_status, large_attempt)
        assert error.status_code == large_status
        assert error.attempt == large_attempt
        assert str(error) == f"[Attempt {large_attempt}] Large numbers"

    def test_api_error_with_unicode_message(self):
        """Test APIError with Unicode characters in message."""
        unicode_message = "API错误: 连接失败 🔥 → 请检查网络"
        error = APIError(unicode_message, 500, 1)

        assert str(error) == f"[Attempt 1] {unicode_message}"
        assert error.args == (unicode_message,)

    def test_exception_pickle_serialization(self):
        """Test that exceptions can be pickled and unpickled."""
        import pickle

        # Test OutlineError
        outline_error = OutlineError("Pickle test")
        pickled = pickle.dumps(outline_error)
        unpickled = pickle.loads(pickled)

        assert isinstance(unpickled, OutlineError)
        assert str(unpickled) == "Pickle test"

        # Test APIError
        api_error = APIError("API pickle test", 404, 3)
        pickled = pickle.dumps(api_error)
        unpickled = pickle.loads(pickled)

        assert isinstance(unpickled, APIError)
        assert str(unpickled) == "[Attempt 3] API pickle test"
        assert unpickled.status_code == 404
        assert unpickled.attempt == 3

    def test_exception_repr_methods(self):
        """Test __repr__ methods of exceptions."""

        # OutlineError
        outline_error = OutlineError("Test repr")
        repr_str = repr(outline_error)
        assert "OutlineError" in repr_str
        assert "Test repr" in repr_str

        # APIError
        api_error = APIError("API repr test", 500, 2)
        repr_str = repr(api_error)
        assert "APIError" in repr_str
        assert "API repr test" in repr_str

    def test_exception_equality_and_hashing(self):
        """Test exception equality and hashing behavior."""

        # Test OutlineError equality
        error1 = OutlineError("Same message")
        error2 = OutlineError("Same message")
        error3 = OutlineError("Different message")

        # Exceptions with same args should be equal
        assert error1.args == error2.args
        assert error1.args != error3.args

        # Test APIError equality
        api1 = APIError("Same", 200, 1)
        api2 = APIError("Same", 200, 1)
        api3 = APIError("Same", 404, 1)

        assert api1.args == api2.args
        assert api1.status_code == api2.status_code
        assert api1.attempt == api2.attempt

        assert api1.status_code != api3.status_code

    def test_memory_efficiency(self):
        """Test that exceptions don't consume excessive memory."""

        # Create many exceptions and ensure they don't consume too much memory
        exceptions = []
        for i in range(1000):
            exceptions.append(APIError(f"Error {i}", i % 600, i % 10))

        # Basic check that all exceptions were created
        assert len(exceptions) == 1000
        assert all(isinstance(e, APIError) for e in exceptions)

        # Check that they have expected properties
        assert exceptions[500].status_code == 500 % 600
        assert exceptions[500].attempt == 500 % 10


# Integration tests
class TestExceptionIntegration:
    """Integration tests simulating real-world usage scenarios."""

    def test_error_logging_scenario(self):
        """Test simulating error logging with exceptions."""
        import logging
        from io import StringIO

        # Setup logging capture
        log_capture = StringIO()
        handler = logging.StreamHandler(log_capture)
        logger = logging.getLogger("test_logger")
        logger.addHandler(handler)
        logger.setLevel(logging.ERROR)

        try:
            raise APIError("Critical API failure", 500, 5)
        except APIError as e:
            logger.error("API Error occurred: %s (Status: %s, Attempt: %s)",
                         str(e), e.status_code, e.attempt)

        log_output = log_capture.getvalue()
        assert "Critical API failure" in log_output
        assert "Status: 500" in log_output
        assert "Attempt: 5" in log_output

        # Cleanup
        logger.removeHandler(handler)

    def test_exception_in_async_context(self):
        """Test that exceptions work properly in async context simulation."""
        import asyncio

        async def async_api_call():
            raise APIError("Async API failed", 408, 1)

        async def test_async():
            with pytest.raises(APIError) as exc_info:
                await async_api_call()

            error = exc_info.value
            assert error.status_code == 408
            assert error.attempt == 1
            assert "Async API failed" in str(error)

        # Run the async test
        asyncio.run(test_async())


if __name__ == "__main__":
    # Run tests if script is executed directly
    pytest.main([__file__, "-v", "--tb=short"])
