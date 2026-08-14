class FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def create_fake_dotenv(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "# comment",
                "IPINFO_API_KEY='key1'",
                "OTHER = \"val2\"",
                "EMPTY=",
            ]
        ),
        encoding="utf-8",
    )
    return env_file


def create_dummy_args(tmp_path):
    # Exercise the `not args.no_banned_script` branch.
    ip_file = tmp_path / "ip_list.txt"
    country_file = tmp_path / "country_count.txt"
    org_file = tmp_path / "org_count.txt"
    city_file = tmp_path / "city_count.txt"
    org_ips_file = tmp_path / "org_ips.txt"

    args_dict = {
        "ip_file": str(ip_file),
        "no_banned_script": False,
        "env_file": str(tmp_path / ".env"),
        "country_file": str(country_file),
        "org_file": str(org_file),
        "city_file": str(city_file),
        "org_ips_file": str(org_ips_file),
        "api_key": "tok",
    }

    return args_dict, ip_file, country_file, org_file, city_file, org_ips_file


def fake_api_interaction(patient, monkeypatch):
    """Avoid network: return deterministic info."""
    monkeypatch.setattr(
        patient,
        "get_ip_info",
        lambda ip, api_key: {"country": "US",
                             "org": "OrgX", "city": "NYC"},
    )
