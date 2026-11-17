"""Banned IP checker scripts"""

import os
import sys
import argparse
from pathlib import Path
from ip_tools import banned_ip_geostat
# from ip_tools import filter_ips # TODO: arg parser command to use this


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


def setup_argument_parser():
    """Set up and return the argument parser for the script."""
    parser = argparse.ArgumentParser(
        description='Banned IP checker scripts for use with frail2ban and IP Info <https://ipinfo.io/signup>.'
    )

    parser.add_argument(
        "--ip-file", default="ip_list.txt",
        type=Path,
        help="File of known IPs (one per line). New IPs are merged in and the file is updated. (default: ip_list.txt)",
    )
    parser.add_argument(
        "--no-banned-script", action="store_true",
        help=f"Skip running banned-ip (bash) scripts and process --ip-file as-is",
    )
    parser.add_argument(
        "--env-file", default=".env",
        type=Path,
        help="Path to .env file containing IPINFO_API_KEY (default: .env)",
    )
    parser.add_argument(
        "--country-file", default="country_count.txt",
        type=Path,
        help="Output file for country data (default: country_count.txt)",
    )
    parser.add_argument(
        "--org-file", default="org_count.txt",
        type=Path,
        help="Output file for org data (default: org_count.txt)",
    )
    parser.add_argument(
        "--city-file", default="city_count.txt",
        type=Path,
        help="Output file for city data (default: city_count.txt)",
    )
    parser.add_argument(
        "--org-ips-file", default="org_ips.txt",
        type=Path,
        help="Output file listing IPs grouped by organisation (default: org_ips.txt)",
    )
    parser.add_argument(
        "--api-key",
        help="IPInfo API key (overrides IPINFO_API_KEY from environment)",
    )

    return parser


def run(args) -> None:
    api_key = os.getenv("IPINFO_API_KEY")
    if not api_key:
        print("Error: IPINFO_API_KEY not set. Use --api-key or set it in .env.")
        sys.exit(1)

    ip_file = Path(args.ip_file)

    banned_ip_geostat.run(
        api_key=api_key,
        ip_file=ip_file,
        country_file=args.country_file,
        org_file=args.org_file,
        city_file=args.city_file,
        org_ips_file=args.org_ips_file,
        no_banned_script=args.no_banned_script
    )


def main() -> None:
    arg_parser = setup_argument_parser()
    args = arg_parser.parse_args()
    load_env(args.env_file)
    run(args)


if __name__ == "__main__":
    main()
