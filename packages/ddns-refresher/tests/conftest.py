import pytest
import requests


@pytest.fixture(scope="session", autouse=True)
def disable_network_requests():
    """Globally block all requests library outbound traffic using pytest monkeypatch."""
    def block_send(*args, **kwargs):
        raise RuntimeError(
            "External network call blocked! Mock the module session instead.")

    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(requests.Session, "send", block_send)
        yield


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    """Stop tests reading a developer's real .env or token."""
    monkeypatch.setattr("ddns_refresher.main.load_dotenv", lambda *a, **k: False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
