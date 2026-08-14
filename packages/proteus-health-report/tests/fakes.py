from pathlib import Path
import requests


def build_fake_config():
    """Fake configuration source for testing"""
    return {
        "hostname": 'Fake Test Host',
        "sections": {
            "logs_warnings": True,
            "caches_warnings": True,
            "temp_warnings": True,
            "disk_warnings": True,
            "service_statuses": True,
            "dns_resolution": True,
            "net_stats": True,
            "power_saving_stats": True,
            "docker_containers": True,
        },
        "network_interfaces": [],
        "thresholds": {
            "disk_percent": "1",
            "file_size": "1M"
        },
        "paths": {
            "disk_device": "/fake/fakedev01",
            "logs_directories": [],
            "cache_directories": [],
            "temp_directories": [],
            "webhook_file": "fake-webhook-url.txt",
            "report_file_location": "/fake/fake-health-reports/fake-report.log",
        },
        "services": {
            "to_monitor": []
        },
        "dns": {
            "test_domain": "fake.lan"
        }
    }


def build_empty_report():
    """Build a fake report request."""
    return {
        "config": build_fake_config(),
        "logs_warnings": [],
        "caches_warnings": [],
        "tmps_warnings": [],
        "disk_warnings": [],
        "service_statuses": [],
        "dns_status": [],
        "net_stats": [],
        "docker_containers": [],
        "power_saving_stats": None,
        "dry_run": True
    }


def build_report_with_sections():
    """Build a fake report request with some fake data included."""
    return {
        "config": build_fake_config(),
        "logs_warnings": ["log1", "log2"],
        "caches_warnings": ["cache1"],
        "tmps_warnings": ["tmpfake"],
        "disk_warnings": ["hdr", "diskwarn"],
        "service_statuses": ["nginx: active", "fake-service: inactive"],
        "dns_status": ["Fake DNS Resolution: OK (1.2.3.4)"],
        "net_stats": ["fake_eth0 (monthly): rx 1, tx 2, total 3"],
        "docker_containers": ["mycontainer", "testcontainer", "anothercontainer"],
        "power_saving_stats": "Some stats for power stuff",
        "dry_run": True
    }


def get_fake_config_yaml():
    return """
hostname: 'Fake Test YAML Config'
sections:
  logs_warnings: true
  caches_warnings: true
  temp_warnings: true
  disk_warnings: true
  service_statuses: true
  dns_resolution: true
  net_stats: true
  docker_containers: true
  power_saving_stats: true
network_interfaces: []
thresholds:
    file_size: 0
    disk_percent: 0
paths:
  disk_device: ""
  logs_directories: []
  cache_directories: []
  temp_directories: []
  webhook_file: "__WEBHOOK_FILE__"
  report_file_location: "__REPORT_FILE__"
services:
  to_monitor: []
dns:
  test_domain: "fake.lan"
    """


def get_fake_user_config_yaml():
    return """
hostname: 'Different hostname!!'
sections:
  logs_warnings: false
    """


class FakeWebHookFile:
    """Create a dummy object that mimics a file context manager with a fake webhook URL"""

    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self): return "https://fake.lan"


def patch_fake_webhook(monkeypatch):
    monkeypatch.setattr("builtins.open", lambda *args,
                        **kwargs: FakeWebHookFile())


def fake_path(expected_path, contents):
    real_path_class = Path

    def faked_path(current_path):
        p_str = str(current_path)
        if p_str.startswith(expected_path):
            return contents

        return real_path_class(p_str)

    return faked_path

# The test using monkeypatch


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
    def fake_post(url, json, headers):
        return FakeSuccessResponse(status_code)

    monkeypatch.setattr(requests, "post", fake_post)
