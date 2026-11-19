import requests


class FakeSuccessResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code

    def json(self):
        return {"data": "success"}

    def raise_for_status(self):
        # Simulate requests behaviour: raise HTTPError for 4xx or 5xx codes
        if 400 <= self.status_code < 600:
            raise requests.exceptions.HTTPError(
                f"{self.status_code} Client/Server Error")


def fake_webhook_call(monkeypatch, status_code):
    def fake_post(self, url, *args, **kwargs):
        return FakeSuccessResponse(status_code)

    # production posts via a requests.Session (retry adapter), not requests.post
    monkeypatch.setattr(requests.Session, "post", fake_post)
