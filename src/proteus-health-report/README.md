# Health Report Monitor Script

> [!note]
> This is run by a cron job usually but you can manually check the log files or run it in dry-mode to test it.

A small Python script that runs periodic system health checks (disk usage, service status, DNS resolution, and network bandwidth) and sends a formatted report to a Discord webhook.

## 📌 What it does

- Checks large directories (`/var/log`, `/var/cache`, `/tmp`) and warns if files exceed a threshold.
- Checks disk usage on `/dev/vda1` against a percentage threshold.
- Verifies that key services (nginx, ssh, fail2ban, wg-quick@wg0, ufw) are active.
- Verifies DNS resolution for `google.com` using `dig`.
- Fetches concise **monthly + daily** bandwidth stats per interface from `vnstat`.
- Checks the power profile of the server and how much time the server has spent power saving
- Monitors power (profile) usage.
- Sends a single Discord message with the results and writes a timestamped report file to `/var/log/proteus-health-reports/`.

## ✅ Requirements

- Python 3
- `requests` Python package
- `vnstat` (v2.x) installed and configured
- `dig` (from `dnsutils`/`bind9-dnsutils`)
- `power-profiles-daemon` (power profile management)

## 🛠️ Setup

1. Place the script somewhere, e.g.:

```sh
./script/proteus-health-monitor.py
```

2. Create a file containing your Discord webhook URL (one line):

```sh
echo "https://discord.com/api/webhooks/..." > ~/discord-webhook-url.txt
```

3. Make the script executable (optional):

```sh
chmod +x ./scripts/proteus-health-monitor.py
```

## Usage

```sh
python3 ./scripts/proteus-health-monitor.py --dry-run
```

## Useful flags

- `--dry-run` – print the report instead of sending it
- `--test-webhook` – send a test notification and exit
- `--webhook-file <path>` – path to the file containing the webhook URL
- `--file-size-threshold <size>` – threshold for `du` warnings (default `20M`)
- `--disk-threshold <percent>` – disk usage percent threshold (default `50`)
- `--services <list>` – space-separated list of services to check

## 🧮 Log output

Reports are saved under `/var/log/proteus-health-report.<timestamp>.log`.

The script includes a sample `logrotate` config block (commented at the top of the script) to avoid disk pollution.

## 🎯 Cron example

Add a cron job to run once per day (at 06:00am AEDT or 7pm UTC) with `crontab -e`:

```cron
# change the directories as needed
0 19 * * * /usr/bin/python3 ~/proteus-health-monitor.py --webhook-file ~/discord-webhook-url.txt
```

## ⚡️ Power Management and Testing

Use the health report to monitor how often the server is within the power-saving profile. Opt-in by enabling it within the config,

```yml
sections:
  # Power Saving stats
  power_saving_stats: true # <--
```

### Enabling the Profiling Daemon

1. copy the script to `/usr/local/bin/dynamic-power.sh`
2. setup a system daemon like so:

```sh
# /etc/systemd/system/dynamic-power.service
[Unit]
Description=Dynamic Power Profile Switcher  
After=power-profiles-daemon.service

[Service]
Type=simple
ExecStart=/usr/local/bin/dynamic-power.sh
Restart=always

[Install]
WantedBy=multi-user.target
```

3. configure logrotate for the audit logs `nano /etc/logrotate.d/dynamic-power`

```sh
# see /usr/bin/local/dynamic-power.sh
/var/log/power_profile_audit.log {
    su root root
    weekly
    rotate 26
    missingok
    notifempty
    compress
    delaycompress
    sharedscripts
    postrotate
        systemctl kill -s SIGUSR1 dynamic-power.service 2>/dev/null || true
    endscript
}
```

4. reload, enable, and startup the daemon

```sh
sudo systemctl daemon-reload
sudo systemctl enable dynamic-power
sudo systemctl start dynamic-power
sudo systemctl status dynamic-power
```

### Profiling/Verifying the Daemon

> This uses taskset + cpulimit to test on certain thresholds.

Test current profiles like so.

1. `tail -f /var/log/power_profile_audit.log` to view the logs
2. start a load on a single-core with `taskset -c 4 cpulimit -l 40 -- md5sum /dev/zero`

Verify that the logs change to balanced from power-saving after a few seconds. 

3. `killall md5sum` to stop the previous test
4. then test more cores for performance mode with `for i in {0..8}; do taskset -c $i sha256sum /dev/zero & done`
   
Verify that the logs change to performance.

5. `killall sha256sum` to stop the previous test
