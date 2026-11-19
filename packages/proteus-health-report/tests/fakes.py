import subprocess
from types import SimpleNamespace

import requests

import proteus_health_report.ReportBuilder as report_builder_module


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


class FakeSubprocess:
    """
    Stand-in for subprocess.run. Responses are matched by substring against the shell command, first match wins.
    Unmatched commands return an empty successful result. Every command is recorded in `commands`.
    """

    def __init__(self):
        self.responses = []
        self.commands = []

    def respond(self, command_contains, stdout="", returncode=0):
        self.responses.append((command_contains, subprocess.CompletedProcess(
            args=command_contains, returncode=returncode, stdout=stdout, stderr="")))
        return self

    def __call__(self, command, *args, **kwargs):
        self.commands.append(command)
        for needle, result in self.responses:
            if needle in command:
                return result
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

    def commands_containing(self, needle):
        return [c for c in self.commands if needle in c]


def fake_subprocess(monkeypatch) -> FakeSubprocess:
    """Replaces subprocess.run as seen by ReportBuilder so no real shell command ever runs (portable to Windows)."""
    fake = FakeSubprocess()
    # swap the module's reference rather than subprocess.run itself, so nothing else in the process is affected
    monkeypatch.setattr(report_builder_module, "subprocess", SimpleNamespace(run=fake))
    return fake
