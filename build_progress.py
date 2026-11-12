"""Per-build progress callbacks stay isolated between worker threads."""
from contextlib import contextmanager
from contextvars import ContextVar

_listener = ContextVar('build_progress', default=None)


@contextmanager
def observe_build(callback):
    token = _listener.set(callback)
    try:
        yield
    finally:
        _listener.reset(token)


def stage(name, message):
    callback = _listener.get()
    if callback:
        callback(name, message)
