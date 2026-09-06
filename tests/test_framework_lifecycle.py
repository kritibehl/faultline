import pytest

from faultline.lifecycle import RunLifecycle


class RecordingLifecycle(RunLifecycle):
    def __init__(self) -> None:
        self.cleanup_calls = 0

    def cleanup(self) -> None:
        self.cleanup_calls += 1


def test_lifecycle_cleans_up_on_success():
    lifecycle = RecordingLifecycle()

    with lifecycle:
        pass

    assert lifecycle.cleanup_calls == 1


def test_lifecycle_cleans_up_and_preserves_exception():
    lifecycle = RecordingLifecycle()

    with pytest.raises(RuntimeError, match="boom"):
        with lifecycle:
            raise RuntimeError("boom")

    assert lifecycle.cleanup_calls == 1
