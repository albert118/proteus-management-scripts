import argparse
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import ipaddress
import os

from dotenv import load_dotenv

retry_strategy = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[500, 502, 503, 504],
    allowed_methods=["HEAD", "GET", "OPTIONS", "POST", "PUT"],
)

# Apply retries to session
adapter = HTTPAdapter(max_retries=retry_strategy)
session = requests.Session()
session.mount("https://", adapter)
session.mount("http://", adapter)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Refresh a Cloudflare DNS A record when your public IP changes."
    )
    parser.add_argument("--zone-id", required=True, help="Cloudflare zone ID.")
    parser.add_argument("--dns-record-id", help="Cloudflare DNS record ID.")
    parser.add_argument(
        "--dns-record-name",
        help="DNS record name (for example: home.example.com).",
    )
    parser.add_argument(
        "--last-ip-fn",
        default='last-known-ip.txt',
        help="Path to file that stores the last known IP address.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned DNS changes without sending a PUT request.",
    )
    parser.add_argument(
        "--list-records",
        action="store_true",
        help="List available DNS records for the zone and exit.",
    )
    return parser.parse_args(argv)


def _parse_ip_address(raw):
    candidate = raw.strip()
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        print(f'❌ Unexpected response while fetching current public IP address: {candidate[:64]!r}')
        return None
    return candidate


def get_current_public_ip_address():
    url = 'https://api.ipify.org'
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        return _parse_ip_address(response.text)
    except requests.exceptions.Timeout:
        print('❌ Timed out while fetching current public IP address')
        return None
    except requests.exceptions.RequestException as err:
        print(f'❌ Failed to fetch current public IP address: {err}')
        return None


def get_last_public_ip_address(fn):
    if os.path.exists(fn):
        with open(fn, 'r') as f:
            last_ip = f.read().strip()
            return last_ip
    else:
        print(f'Creating a new file to track the last known IP address: {fn}')
        with open(fn, 'w') as f:
            f.write('')
        return None


def save_ip_address(ip, fn):
    with open(fn, 'w') as f:
        f.write(ip)


def get_dns_records(zone_id, api_token):
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records"
    headers = {
        "Authorization": f"Bearer {api_token}"
    }

    try:
        response = session.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        # Cloudflare API result will include errors, messages, a success flag, and a result object
        data = response.json()
    except requests.exceptions.Timeout:
        print('❌ Timed out while getting Cloudflare DNS records')
        return []
    except requests.exceptions.RequestException as err:
        print(f'❌ Failed to get Cloudflare DNS records: {err}')
        return []

    if data.get("success"):
        return data.get("result", [])

    if data.get("errors") and len(data["errors"]) > 0:
        print('⚠️ Errors were returned from Cloudflare.')
        for error in data["errors"]:
            print(error)

    return []


def put_dns_update(zone_id, dns_record_id, dns_record_name, ip_address, api_token) -> dict:
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records/{dns_record_id}"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "type": "A",
        "name": dns_record_name,
        "content": ip_address,
        # 1 hour TTL
        "ttl": 3600,
        # unproxied to avoid Cloudflare bandwidth limitations
        # also to avoid issues with their T&S
        "proxied": False,
    }

    try:
        response = session.put(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        # Cloudflare API result will include errors, messages, a success flag, and a result object
        data = response.json()
    except requests.exceptions.Timeout:
        print('❌ Timed out while updating Cloudflare DNS record')
        return None
    except requests.exceptions.RequestException as err:
        print(f'❌ Failed to update Cloudflare DNS record: {err}')
        return None

    print(f"☁️ Cloudflare response success: {data.get('success')}")
    if data.get("success"):
        return data

    if data.get("errors") and len(data["errors"]) > 0:
        print('⚠️ Errors were returned from Cloudflare.')
        for error in data["errors"]:
            print(error)

    return data


def init_env_variables(args):
    load_dotenv()

    cloudflare_api_token = os.getenv("CLOUDFLARE_API_TOKEN")
    if not cloudflare_api_token:
        raise ValueError("CLOUDFLARE_API_TOKEN is not set")

    dns_record_name = args.dns_record_name
    cloudflare_zone_id = args.zone_id
    cloudflare_dns_record_id = args.dns_record_id
    last_ip_fn = args.last_ip_fn

    return {
        "CLOUDFLARE_API_TOKEN": cloudflare_api_token,
        "DNS_RECORD_NAME": dns_record_name,
        "CLOUDFLARE_ZONE_ID": cloudflare_zone_id,
        "CLOUDFLARE_DNS_RECORD_ID": cloudflare_dns_record_id,
        "LAST_IP_FN": last_ip_fn,
    }


def main(argv=None):
    args = parse_args(argv)
    env = init_env_variables(args)

    if args.list_records:
        records = get_dns_records(
            zone_id=env["CLOUDFLARE_ZONE_ID"],
            api_token=env["CLOUDFLARE_API_TOKEN"],
        )
        if not records:
            print('No DNS records found (or request failed).')
            raise SystemExit(0)

        print(f"Found {len(records)} DNS record(s):")
        for record in records:
            print(
                f"- {record.get('id')} | {record.get('type')} | "
                f"{record.get('name')} -> {record.get('content')}"
            )
        raise SystemExit(0)

    if not args.dns_record_id or not args.dns_record_name:
        raise ValueError("--dns-record-id and --dns-record-name are required unless --list-records is used")

    curr_ip = get_current_public_ip_address()
    if (curr_ip is None):
        raise ValueError('⚠️ The current IP was not resolved - aborting')

    last_ip = get_last_public_ip_address(fn=env["LAST_IP_FN"])

    if last_ip == curr_ip:
        print('✅ Last known IP is the same, exiting now')
    else:
        print(f'🆕 New address found. Updating Cloudflare record with: {curr_ip}')
        if args.dry_run:
            print('🧪 Dry-run mode enabled. No request was sent to Cloudflare.')
            print(
                f"Would update zone '{env['CLOUDFLARE_ZONE_ID']}', "
                f"record '{args.dns_record_id}' "
                f"({args.dns_record_name}) to IP '{curr_ip}'."
            )
            raise SystemExit(0)

        result = put_dns_update(
            zone_id=env["CLOUDFLARE_ZONE_ID"],
            dns_record_id=args.dns_record_id,
            dns_record_name=args.dns_record_name,
            ip_address=curr_ip,
            api_token=env["CLOUDFLARE_API_TOKEN"],
        )
        # persist the last known address only if we can update the DNS record
        if result is not None and result.get('success'):
            save_ip_address(curr_ip, fn=env["LAST_IP_FN"])
            print(f'📃 DNS record updated. Persisted last known IP to file: {env["LAST_IP_FN"]}')


if __name__ == "__main__":
    main()
