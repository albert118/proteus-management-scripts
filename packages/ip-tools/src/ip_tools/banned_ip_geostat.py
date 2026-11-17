"""IP geolocation statistics tool using IPInfo API."""

import ipaddress
import json
import subprocess
import sys
import urllib.request
import urllib.error
from collections import Counter, defaultdict
from pathlib import Path

BANNED_IPS_SCRIPT = Path("~/scripts/check-banned-ips.sh").expanduser()


def fetch_banned_ips() -> list[str]:
    """Run check-banned-ips.sh and return the space-delimited IPs it emits."""
    if not BANNED_IPS_SCRIPT.exists():
        print(f"Error: banned-IPs script '{BANNED_IPS_SCRIPT}' not found.")
        sys.exit(1)

    result = subprocess.run(
        ["bash", str(BANNED_IPS_SCRIPT)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(
            f"Error running '{BANNED_IPS_SCRIPT}' (exit {result.returncode}):\n{result.stderr}")
        sys.exit(1)

    ips = [token for token in result.stdout.split() if _is_ip(token)]
    print(f"Retrieved {len(ips)} banned IP(s) from {BANNED_IPS_SCRIPT}")
    return ips


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def merge_ips(new_ips: list[str], ip_file: Path) -> list[str]:
    """Merge new IPs with any previously recorded in ip_file, deduplicate, and sort."""
    existing: set[str] = set()
    if ip_file.exists():
        existing = {line.strip()
                    for line in ip_file.read_text().splitlines() if line.strip()}

    merged = sorted(existing | set(new_ips))
    ip_file.write_text("\n".join(merged) + "\n")

    added = len(merged) - len(existing)
    print(f"{added} new IP(s) added; {len(merged)} distinct IP(s) total")
    return merged


def preflight(api_key: str) -> None:
    print("Beginning preflight")
    req = urllib.request.Request(
        "https://api.ipinfo.io/lite/8.8.8.8",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(req) as response:
            print(response.read().decode())
        print("Preflight valid, continuing")
    except urllib.error.URLError as e:
        print(
            f"Cannot access IP Info API: {e}\nCheck the environment and network.")
        sys.exit(1)


def get_ip_info(ip: str, api_key: str) -> dict:
    req = urllib.request.Request(
        f"https://ipinfo.io/{ip}?token={api_key}",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode())


def print_stats(label: str, counter: Counter) -> None:
    print(f"\nStatistics by {label}:")
    for item, count in counter.most_common():
        print(f"{count:6}  {item}")


def write_org_ips(org_ips: dict[str, list[str]], output_file: Path) -> None:
    lines: list[str] = []
    for org in sorted(org_ips):
        lines.append(org)
        for ip in sorted(org_ips[org]):
            lines.append(f"  {ip}")
    output_file.write_text("\n".join(lines) + "\n")


def print_org_ips(org_ips: dict[str, list[str]]) -> None:
    print("\nIPs by organisation:")
    for org in sorted(org_ips):
        print(f"  {org}")
        for ip in sorted(org_ips[org]):
            print(f"    {ip}")


def run(api_key: str, ip_file: Path, country_file: Path, org_file: Path, city_file: Path, org_ips_file: Path, no_banned_script: bool) -> None:
    if no_banned_script:
        if not ip_file.exists():
            print(f"File {ip_file} not found.")
            sys.exit(1)
        ips = [line.strip()
               for line in ip_file.read_text().splitlines() if line.strip()]
    else:
        new_ips = fetch_banned_ips()
        ips = merge_ips(new_ips, ip_file)

    preflight(api_key)

    country_counter: Counter[str] = Counter()
    org_counter: Counter[str] = Counter()
    city_counter: Counter[str] = Counter()
    org_ips: dict[str, list[str]] = defaultdict(list)

    country_lines: list[str] = []
    org_lines: list[str] = []
    city_lines: list[str] = []

    for ip in ips:
        print(f"Processing {ip}...")
        try:
            info = get_ip_info(ip, api_key)
            country = info.get("country", "unknown")
            org = info.get("org", "unknown")
            city = info.get("city", "unknown")

            country_counter[country] += 1
            org_counter[org] += 1
            city_counter[city] += 1
            org_ips[org].append(ip)

            country_lines.append(country)
            org_lines.append(org)
            city_lines.append(city)
        except urllib.error.URLError as e:
            print(f"  Warning: failed to get info for {ip}: {e}")

    Path(country_file).write_text("\n".join(country_lines) + "\n")
    Path(org_file).write_text("\n".join(org_lines) + "\n")
    Path(city_file).write_text("\n".join(city_lines) + "\n")
    write_org_ips(org_ips, Path(org_ips_file))

    print_stats("country code", country_counter)
    print_stats("organization", org_counter)
    print_stats("city", city_counter)
    print_org_ips(org_ips)
