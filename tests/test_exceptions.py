from pyoutlineapi.exceptions import OutlineError, APIError


def test_outline_error_is_base_exception():
    err = OutlineError("Something went wrong")
    assert isinstance(err, Exception)
    assert isinstance(err, OutlineError)
    assert str(err) == "Something went wrong"


def test_api_error_without_optional_args():
    err = APIError("API failure")
    assert isinstance(err, APIError)
    assert isinstance(err, OutlineError)
    assert err.status_code is None
    assert err.attempt is None
    assert str(err) == "API failure"


def test_api_error_with_all_args():
    err = APIError("Request failed", status_code=500, attempt=3)
    assert err.status_code == 500
    assert err.attempt == 3
    assert str(err) == "[Attempt 3] Request failed"
