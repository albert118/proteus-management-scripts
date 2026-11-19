from unittest.mock import MagicMock

import pytest
import requests

from ddns_refresher import main as ddns

ZONE = "zone-1"
RECORD_ID = "rec-1"
RECORD_NAME = "home.example.com"
TOKEN = "test-token"


def make_response(text="", json_data=None, status_error=None):
    response = MagicMock()
    response.text = text
    response.json.return_value = json_data
    if status_error is not None:
        response.raise_for_status.side_effect = status_error
    return response


@pytest.fixture
def session(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr(ddns, "session", fake)
    return fake


def describe_parse_args():
    def it_applies_defaults():
        args = ddns.parse_args(["--zone-id", ZONE])

        assert args.zone_id == ZONE
        assert args.dns_record_id is None
        assert args.dns_record_name is None
        assert args.last_ip_fn == "last-known-ip.txt"
        assert args.dry_run is False
        assert args.list_records is False

    def it_requires_zone_id():
        with pytest.raises(SystemExit) as exc:
            ddns.parse_args([])

        assert exc.value.code == 2

    def it_reads_flags():
        args = ddns.parse_args(
            ["--zone-id", ZONE, "--dry-run", "--list-records", "--last-ip-fn", "x.txt"]
        )

        assert args.dry_run is True
        assert args.list_records is True
        assert args.last_ip_fn == "x.txt"


def describe_get_current_public_ip_address():
    def it_returns_the_ip(session):
        session.get.return_value = make_response(text="203.0.113.7")

        assert ddns.get_current_public_ip_address() == "203.0.113.7"

    def it_strips_a_trailing_newline(session):
        session.get.return_value = make_response(text="203.0.113.7\n")

        assert ddns.get_current_public_ip_address() == "203.0.113.7"

    def it_accepts_ipv6(session):
        session.get.return_value = make_response(text="2001:db8::1\n")

        assert ddns.get_current_public_ip_address() == "2001:db8::1"

    @pytest.mark.parametrize("body", ["", "  \n", "<html>error</html>", "not an ip"])
    def it_rejects_a_non_ip_body(session, body, capsys):
        session.get.return_value = make_response(text=body)

        assert ddns.get_current_public_ip_address() is None
        assert "Unexpected response" in capsys.readouterr().out

    def it_returns_none_on_timeout(session, capsys):
        session.get.side_effect = requests.exceptions.Timeout()

        assert ddns.get_current_public_ip_address() is None
        assert "Timed out" in capsys.readouterr().out

    def it_returns_none_on_request_exception(session, capsys):
        session.get.side_effect = requests.exceptions.ConnectionError("boom")

        assert ddns.get_current_public_ip_address() is None
        assert "Failed to fetch" in capsys.readouterr().out

    def it_returns_none_on_http_error(session):
        session.get.return_value = make_response(
            status_error=requests.exceptions.HTTPError("503")
        )

        assert ddns.get_current_public_ip_address() is None


def describe_ip_cache():
    def it_creates_the_file_and_returns_none_when_missing(tmp_path):
        fn = tmp_path / "ip.txt"

        assert ddns.get_last_public_ip_address(str(fn)) is None
        assert fn.read_text() == ""

    def it_returns_the_stored_ip_stripped(tmp_path):
        fn = tmp_path / "ip.txt"
        fn.write_text("198.51.100.4\n")

        assert ddns.get_last_public_ip_address(str(fn)) == "198.51.100.4"

    def it_returns_empty_string_for_an_existing_empty_file(tmp_path):
        fn = tmp_path / "ip.txt"
        fn.write_text("")

        assert ddns.get_last_public_ip_address(str(fn)) == ""

    def it_round_trips_a_saved_ip(tmp_path):
        fn = str(tmp_path / "ip.txt")

        ddns.save_ip_address("203.0.113.7", fn)

        assert ddns.get_last_public_ip_address(fn) == "203.0.113.7"


def describe_get_dns_records():
    def it_returns_the_result_on_success(session):
        records = [{"id": "a"}, {"id": "b"}]
        session.get.return_value = make_response(
            json_data={"success": True, "result": records}
        )

        assert ddns.get_dns_records(ZONE, TOKEN) == records
        assert session.get.call_args.kwargs["headers"] == {"Authorization": f"Bearer {TOKEN}"}
        assert session.get.call_args.args[0].endswith(f"/zones/{ZONE}/dns_records")

    def it_returns_empty_and_prints_errors_when_success_is_false(session, capsys):
        session.get.return_value = make_response(
            json_data={"success": False, "errors": [{"code": 9109, "message": "bad token"}]}
        )

        assert ddns.get_dns_records(ZONE, TOKEN) == []
        out = capsys.readouterr().out
        assert "Errors were returned from Cloudflare" in out
        assert "bad token" in out

    def it_reports_a_network_failure_differently_from_an_api_error(session, capsys):
        session.get.side_effect = requests.exceptions.ConnectionError("down")

        assert ddns.get_dns_records(ZONE, TOKEN) == []
        out = capsys.readouterr().out
        assert "Failed to get Cloudflare DNS records" in out
        assert "Errors were returned from Cloudflare" not in out

    def it_reports_a_timeout(session, capsys):
        session.get.side_effect = requests.exceptions.Timeout()

        assert ddns.get_dns_records(ZONE, TOKEN) == []
        assert "Timed out" in capsys.readouterr().out


def describe_put_dns_update():
    def it_sends_the_expected_payload(session):
        session.put.return_value = make_response(json_data={"success": True})

        result = ddns.put_dns_update(ZONE, RECORD_ID, RECORD_NAME, "203.0.113.7", TOKEN)

        assert result == {"success": True}
        args, kwargs = session.put.call_args
        assert args[0].endswith(f"/zones/{ZONE}/dns_records/{RECORD_ID}")
        assert kwargs["headers"]["Authorization"] == f"Bearer {TOKEN}"
        assert kwargs["json"] == {
            "type": "A",
            "name": RECORD_NAME,
            "content": "203.0.113.7",
            "ttl": 3600,
            "proxied": False,
        }

    def it_returns_the_body_when_cloudflare_reports_failure(session, capsys):
        body = {"success": False, "errors": [{"code": 1, "message": "nope"}]}
        session.put.return_value = make_response(json_data=body)

        assert ddns.put_dns_update(ZONE, RECORD_ID, RECORD_NAME, "203.0.113.7", TOKEN) == body
        assert "nope" in capsys.readouterr().out

    @pytest.mark.parametrize(
        "error", [requests.exceptions.Timeout(), requests.exceptions.ConnectionError("x")]
    )
    def it_returns_none_on_network_failure(session, error):
        session.put.side_effect = error

        assert ddns.put_dns_update(ZONE, RECORD_ID, RECORD_NAME, "203.0.113.7", TOKEN) is None


def describe_init_env_variables():
    def it_raises_when_the_token_is_missing():
        args = ddns.parse_args(["--zone-id", ZONE])

        with pytest.raises(ValueError, match="CLOUDFLARE_API_TOKEN"):
            ddns.init_env_variables(args)

    def it_raises_when_the_token_is_empty(monkeypatch):
        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "")
        args = ddns.parse_args(["--zone-id", ZONE])

        with pytest.raises(ValueError, match="CLOUDFLARE_API_TOKEN"):
            ddns.init_env_variables(args)

    def it_maps_args_and_token(monkeypatch):
        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", TOKEN)
        args = ddns.parse_args(
            ["--zone-id", ZONE, "--dns-record-id", RECORD_ID,
             "--dns-record-name", RECORD_NAME, "--last-ip-fn", "x.txt"]
        )

        assert ddns.init_env_variables(args) == {
            "CLOUDFLARE_API_TOKEN": TOKEN,
            "DNS_RECORD_NAME": RECORD_NAME,
            "CLOUDFLARE_ZONE_ID": ZONE,
            "CLOUDFLARE_DNS_RECORD_ID": RECORD_ID,
            "LAST_IP_FN": "x.txt",
        }


def describe_main():
    @pytest.fixture(autouse=True)
    def token(monkeypatch):
        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", TOKEN)

    @pytest.fixture
    def ip_file(tmp_path):
        return tmp_path / "ip.txt"

    def _base_argv(ip_file, *extra):
        return ["--zone-id", ZONE, "--dns-record-id", RECORD_ID,
                "--dns-record-name", RECORD_NAME, "--last-ip-fn", str(ip_file), *extra]

    def it_lists_records_and_exits_without_touching_the_ip_flow(session, ip_file, capsys):
        session.get.return_value = make_response(
            json_data={"success": True, "result": [
                {"id": "r1", "type": "A", "name": RECORD_NAME, "content": "1.2.3.4"}]}
        )

        with pytest.raises(SystemExit) as exc:
            ddns.main(["--zone-id", ZONE, "--list-records", "--last-ip-fn", str(ip_file)])

        assert exc.value.code == 0
        assert "r1 | A | home.example.com -> 1.2.3.4" in capsys.readouterr().out
        assert session.get.call_count == 1
        assert "cloudflare" in session.get.call_args.args[0]
        assert not ip_file.exists()
        session.put.assert_not_called()

    def it_exits_cleanly_when_no_records_are_found(session, capsys):
        session.get.return_value = make_response(json_data={"success": True, "result": []})

        with pytest.raises(SystemExit) as exc:
            ddns.main(["--zone-id", ZONE, "--list-records"])

        assert exc.value.code == 0
        assert "No DNS records found" in capsys.readouterr().out

    def it_requires_record_id_and_name_unless_listing(session, ip_file):
        with pytest.raises(ValueError, match="--dns-record-id"):
            ddns.main(["--zone-id", ZONE, "--last-ip-fn", str(ip_file)])

    def it_aborts_when_the_current_ip_cannot_be_resolved(session, ip_file):
        session.get.side_effect = requests.exceptions.Timeout()

        with pytest.raises(ValueError, match="not resolved"):
            ddns.main(_base_argv(ip_file))

        session.put.assert_not_called()

    def it_skips_the_update_when_the_ip_is_unchanged_despite_a_trailing_newline(
        session, ip_file, capsys
    ):
        ip_file.write_text("203.0.113.7")
        session.get.return_value = make_response(text="203.0.113.7\n")

        ddns.main(_base_argv(ip_file))

        session.put.assert_not_called()
        assert "Last known IP is the same" in capsys.readouterr().out

    def it_updates_and_persists_a_changed_ip(session, ip_file):
        ip_file.write_text("198.51.100.4")
        session.get.return_value = make_response(text="203.0.113.7\n")
        session.put.return_value = make_response(json_data={"success": True})

        ddns.main(_base_argv(ip_file))

        assert session.put.call_count == 1
        assert session.put.call_args.kwargs["json"]["content"] == "203.0.113.7"
        assert ip_file.read_text() == "203.0.113.7"

    def it_does_not_persist_when_cloudflare_rejects_the_update(session, ip_file):
        ip_file.write_text("198.51.100.4")
        session.get.return_value = make_response(text="203.0.113.7")
        session.put.return_value = make_response(
            json_data={"success": False, "errors": [{"message": "no"}]}
        )

        ddns.main(_base_argv(ip_file))

        assert ip_file.read_text() == "198.51.100.4"

    def it_does_not_persist_when_the_put_fails(session, ip_file):
        ip_file.write_text("198.51.100.4")
        session.get.return_value = make_response(text="203.0.113.7")
        session.put.side_effect = requests.exceptions.ConnectionError("x")

        ddns.main(_base_argv(ip_file))

        assert ip_file.read_text() == "198.51.100.4"

    def it_sends_no_put_in_dry_run_mode(session, ip_file, capsys):
        ip_file.write_text("198.51.100.4")
        session.get.return_value = make_response(text="203.0.113.7")

        with pytest.raises(SystemExit) as exc:
            ddns.main(_base_argv(ip_file, "--dry-run"))

        assert exc.value.code == 0
        session.put.assert_not_called()
        assert ip_file.read_text() == "198.51.100.4"
        assert "Dry-run mode enabled" in capsys.readouterr().out
