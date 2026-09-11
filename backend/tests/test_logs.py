"""Log response handling."""

from __future__ import annotations

from kubernetes.client.exceptions import ApiException

from app.api.v1.events import _bad_request_detail, _decode


def test_bytes_are_decoded_not_stringified() -> None:
    """str(bytes) renders the whole log as a Python repr on one line.

    That is what the client returns by default, and it is unreadable; the route
    asks for the raw response and decodes it here instead.
    """
    raw = b"line one\nline two\n"
    assert _decode(raw) == "line one\nline two\n"
    assert not _decode(raw).startswith("b'")


def test_undecodable_bytes_do_not_fail_the_request() -> None:
    # A log with odd bytes in it should still be readable.
    assert _decode(b"ok \xff\xfe done") == "ok �� done"


def test_empty_and_str_inputs() -> None:
    assert _decode(None) == ""
    assert _decode("already text") == "already text"


def _api_exception(body: str) -> ApiException:
    exc = ApiException(status=400, reason="Bad Request")
    exc.body = body
    return exc


def test_multi_container_error_is_explained() -> None:
    detail = _bad_request_detail(
        _api_exception("a container name must be specified, choose one of: [api proxy]")
    )
    assert "several containers" in detail


def test_missing_previous_log_is_explained() -> None:
    detail = _bad_request_detail(_api_exception('previous terminated container "api" not found'))
    assert "not terminated before" in detail


def test_unknown_bad_request_falls_back() -> None:
    assert "rejected" in _bad_request_detail(_api_exception("something else"))
