# banned-ip-geostat

Fetches geolocation data for banned IPs and reports statistics by country, organisation, and city using the [IPInfo](https://ipinfo.io) API.

## 📌 How it works

1. Runs `~/scripts/check-banned-ips.sh` to retrieve currently jailed IPs from fail2ban
2. Merges them with any previously seen IPs in `ip_list.txt`, deduplicates, and sorts the list
3. Performs a preflight check against the IPInfo API
4. Looks up each IP and writes raw results to `country_count.txt`, `org_count.txt`, and `city_count.txt`
5. Prints ranked statistics by country code, organisation, and city

The raw per-IP values are also written to the output files for further processing.

| Option               | Default              | Description                                                        |
|----------------------|----------------------|--------------------------------------------------------------------|
| `--ip-file`          | `ip_list.txt`        | Cumulative IP list; merged, deduplicated and updated on each run   |
| `--no-banned-script` | _(flag)_             | Skip fail2ban script; process `--ip-file` as-is                   |
| `--env-file`         | `.env`               | Path to file containing `IPINFO_API_KEY`                           |
| `--country-file`     | `country_count.txt`  | Output file for raw country results                                |
| `--org-file`         | `org_count.txt`      | Output file for raw organisation results                           |
| `--city-file`        | `city_count.txt`     | Output file for raw city results                                   |
| `--org-ips-file`     | `org_ips.txt`        | Output file listing IPs grouped by organisation                    |
| `--api-key`          | _(env)_              | IPInfo API key; overrides `IPINFO_API_KEY`                         |

## ✅ Requirements

- Python 3.12+
- An [IPInfo API key](https://ipinfo.io/signup)
- `~/scripts/check-banned-ips.sh` present and executable (unless using `--no-banned-script`)

## 🛠️ Configuration

Create a `.env` file in the working directory:

```env
IPINFO_API_KEY=your_api_key_here
```

Alternatively, pass --api-key on the command line.

## 🌏️ Execution Examples

```sh
# Standard run — fetch new banned IPs and look them up
python banned-ip-geostat.py

# Use a specific API key without a .env file
python banned-ip-geostat.py --api-key sk_abc123

# Skip fail2ban and analyse a manually curated IP list
python banned-ip-geostat.py --no-banned-script --ip-file my_ips.txt
```

## 🌏️ Output Sample

```sh
Statistics by country code:
   142  CN
    87  RU
    34  US
    ...

Statistics by organization:
    56  AS4134 Chinanet
    ...

Statistics by city:
    61  Beijing
    ...
```
