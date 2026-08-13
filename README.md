# Proteus Management Scripts

These are various scripts I use to manage the server.

- [⚡️ Power Management and Testing](#️-power-management-and-testing)
  - [Enabling the Profiling Daemon](#enabling-the-profiling-daemon)
  - [Profiling/Verifying the Daemon](#profilingverifying-the-daemon)

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
