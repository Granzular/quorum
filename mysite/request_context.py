"""Request correlation shared by middleware and console logging."""

from contextlib import contextmanager
from contextvars import ContextVar


_request_id = ContextVar('quorum_request_id', default=None)


def get_request_id():
    """Return the active request ID, or None outside a request."""
    return _request_id.get()


@contextmanager
def bind_request_id(request_id):
    """Bind correlation for this execution context and restore it on exit."""
    token = _request_id.set(request_id)
    try:
        yield
    finally:
        _request_id.reset(token)
