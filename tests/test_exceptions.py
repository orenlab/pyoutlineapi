from pyoutlineapi.exceptions import APIError


def test_api_error():
    error = APIError("Resource not found", status_code=404)
    assert str(error) == "Resource not found"
    assert error.status_code == 404

    error_with_attempt = APIError("Rate limit exceeded", status_code=429, attempt=3)
    assert str(error_with_attempt) == "[Attempt 3] Rate limit exceeded"
