#!/usr/bin/env python3
"""IP geolocation statistics tool using IPInfo API."""

import argparse
import ipaddress
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error
from collections import Counter, defaultdict
from pathlib import Path

BANNED_IPS_SCRIPT = Path("~/scripts/check-banned-ips.sh").expanduser()


def load_env(env_file: str) -> None:
    env_path = Path(env_file)
    if not env_path.exists():
        return
    with env_path.open() as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(
                    key.strip(), value.strip().strip('"').strip("'"))


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch IP geolocation data and display statistics."
    )
    parser.add_argument(
        "--ip-file", default="ip_list.txt",
        help="File of known IPs (one per line). New IPs are merged in and the file is updated. (default: ip_list.txt)",
    )
    parser.add_argument(
        "--no-banned-script", action="store_true",
        help=f"Skip running {BANNED_IPS_SCRIPT} and process --ip-file as-is",
    )
    parser.add_argument(
        "--env-file", default=".env",
        help="Path to .env file containing IPINFO_API_KEY (default: .env)",
    )
    parser.add_argument(
        "--country-file", default="country_count.txt",
        help="Output file for country data (default: country_count.txt)",
    )
    parser.add_argument(
        "--org-file", default="org_count.txt",
        help="Output file for org data (default: org_count.txt)",
    )
    parser.add_argument(
        "--city-file", default="city_count.txt",
        help="Output file for city data (default: city_count.txt)",
    )
    parser.add_argument(
        "--org-ips-file", default="org_ips.txt",
        help="Output file listing IPs grouped by organisation (default: org_ips.txt)",
    )
    parser.add_argument(
        "--api-key",
        help="IPInfo API key (overrides IPINFO_API_KEY from environment)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_env(args.env_file)

    api_key = args.api_key or os.getenv("IPINFO_API_KEY")
    if not api_key:
        print("Error: IPINFO_API_KEY not set. Use --api-key or set it in .env.")
        sys.exit(1)

    ip_file = Path(args.ip_file)

    if not args.no_banned_script:
        new_ips = fetch_banned_ips()
        ips = merge_ips(new_ips, ip_file)
    else:
        if not ip_file.exists():
            print(f"File {ip_file} not found.")
            sys.exit(1)
        ips = [line.strip()
               for line in ip_file.read_text().splitlines() if line.strip()]

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

    Path(args.country_file).write_text("\n".join(country_lines) + "\n")
    Path(args.org_file).write_text("\n".join(org_lines) + "\n")
    Path(args.city_file).write_text("\n".join(city_lines) + "\n")
    write_org_ips(org_ips, Path(args.org_ips_file))

    print_stats("country code", country_counter)
    print_stats("organization", org_counter)
    print_stats("city", city_counter)
    print_org_ips(org_ips)


if __name__ == "__main__":
    main()
