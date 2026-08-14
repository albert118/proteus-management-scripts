import pytest
import requests


@pytest.fixture(scope="session", autouse=True)
def disable_network_requests():
    """Globally block all requests library outbound traffic using pytest monkeypatch."""
    def block_send(*args, **kwargs):
        raise RuntimeError(
            "External network call blocked! Use pytest-mock or responses to mock it.")

    with pytest.MonkeyPatch().context() as mp:
        # Patching 'send' catches get, post, put, delete, and active Sessions
        mp.setattr(requests.Session, "send", block_send)
        yield
