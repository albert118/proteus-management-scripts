# Python DDNS Refresher

A script to help check and update public IP addresses. If it's found, it pushes the updated address to Cloudflare using their API.

This service uses <https://api.ipify.org> to resolve the current network's public facing IP address. This is quite a nice service, as it is free and allows millions of RPS without issue. See their docs [here | ipify.com](https://www.ipify.org/) for more.

> [!note]
> This will fail with an SSL error if using services such as Cloudflare WARP, as this interferes with the certificate chain.

## Requirements

- A Cloudflare API token with DNS edit permissions for your zone

## Setup

```sh
uv tool install .
cp .env.example .env
chmod 600 .env  # copy in your webhook URL
```

If you need to, resolve the target DNS record ID using this request to show all available records in a zone,

```sh
python main.py --zone-id <cloudflare_zone_id> --list-records
```

## Usage

Run the script with required CLI arguments:

```sh
python main.py \
    --zone-id <cloudflare_zone_id> \
    --dns-record-id <cloudflare_dns_record_id> \
    --dns-record-name <record_name> \
    --last-ip-fn <path_to_ip_cache_file>
```

### Required arguments

- `--zone-id`: Cloudflare zone ID
- `--dns-record-id`: Cloudflare DNS record ID
- `--dns-record-name`: DNS A record name (example: `home.example.com`)

### Optional arguments

- `--last-ip-fn`: File used to store the previously known public IP (defaults to `last-known-ip.txt`)
- `--dry-run`: Print what would change without sending a Cloudflare update request
- `--list-records`: List available DNS records in the zone and exit early (only `--zone-id` is required)

### Dry run example

```bash
python main.py \
    --zone-id <cloudflare_zone_id> \
    --dns-record-id <cloudflare_dns_record_id> \
    --dns-record-name <record_name> \
    --dry-run
```

## Scheduling

Run this script on an interval (for example every 5 minutes) using your scheduler of choice:

- Linux/macOS: `cron`
- Windows: Task Scheduler
