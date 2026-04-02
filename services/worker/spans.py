from contextlib import contextmanager

@contextmanager
def start_span(*args, **kwargs):
    yield

@contextmanager
def start_job_span_from_payload(*args, **kwargs):
    yield
