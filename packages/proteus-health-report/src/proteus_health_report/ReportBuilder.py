import subprocess

from proteus_health_report.Configuration import ProteusHealthConfig


class ReportBuilder():
    def __init__(self, config: ProteusHealthConfig):
        self.config = config

        self.logs_size_warnings = []
        self.caches_size_warnings = []
        self.tmps_size_warnings = []
        self.disk_usage_warning = []
        self.service_statuses = []
        self.dns_status = []
        self.net_stats = []
        self.docker_containers = []
        self.power_saving_stats = None

    def check_directory_size(self, paths, threshold):
        """Check directory sizes for the given paths list and threshold."""
        results = []
        for path in paths:
            command = f"du -sh -t {threshold} {path} | sort -hr | head -5"
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                shell=True,
                check=True
            )

            if result.returncode != 0:
                raise RuntimeError(f"Error asserting disk size of {path} (exit {result.returncode}):\n{result.stderr}")

            entries = [entry for entry in result.stdout.splitlines()]
            results.extend(entries)

        return results

    def with_logs_size_warnings(self) -> 'ReportBuilder':
        if not self.config.sections.logs_warnings:
            return self

        logs_size_warnings = self.check_directory_size(
            self.config.file_reporting.logs_directories,
            self.config.file_reporting.file_size
        )
        return self

    def with_caches_size_warnings(self) -> 'ReportBuilder':
        """
        For now, caches_warnings uses the same directories from config.
        In the future, this could be separated into cache-specific directories.
        """
        if not self.config.sections.caches_warnings:
            return self

        self.caches_size_warnings = self.check_directory_size(
            [d for d in self.config.file_reporting.cache_directories if 'cache' in d],
            self.config.file_reporting.file_size
        )
        return self

    def with_tmps_size_warnings(self) -> 'ReportBuilder':
        if not self.config.sections.temp_warnings:
            return self

        tmps_size_warnings = self.check_directory_size(
            [d for d in self.config.file_reporting.temp_directories],
            self.config.file_reporting.file_size
        )
        return self

    def with_disk_warnings(self) -> 'ReportBuilder':
        """Check disk usage on the specified device against threshold."""
        if not self.config.sections.disk_warnings:
            return self

        command = f"df -hlP {self.config.file_reporting.disk_device} | awk -v thr=\"{self.config.file_reporting.disk_percent}\" 'NR==1 {{ print; next }} {{ sub(/%/, \"\", $5); if ($5+0 > thr+0) print }}'"

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            shell=True,
            check=True
        )

        if result.returncode != 0:
            raise RuntimeError(f"Error asserting disk usage (exit {result.returncode}):\n{result.stderr}")

        self.disk_usage_warning = [entry for entry in result.stdout.splitlines()]

        return self

    def with_service_statuses(self) -> 'ReportBuilder':
        if not self.config.sections.service_statuses:
            return self

        for service in self.config.report.services_to_monitor:
            command = f"systemctl -q is-active {service}"
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                shell=True
            )
            status = "active" if result.returncode == 0 else "inactive"
            self.service_statuses.append(f"{service}: {status}")

        return self

    def with_dns_status(self) -> 'ReportBuilder':
        """
        Check DNS resolution by attempting to resolve the given domain.
        For now, only resolve the first option to keep it simple.
        """
        if not self.config.sections.dns_resolution:
            return self

        # For now, only resolve the first option to keep it simple.
        command = f"dig +short {self.config.networking_reporting.dns_test_domain[0]} | head -1"
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            shell=True
        )

        if result.returncode == 0 and result.stdout.strip():
            ip_address = result.stdout.strip()
            self.dns_status = [f"DNS Resolution: OK ({ip_address})"]
        else:
            self.dns_status = ["DNS Resolution: FAILED"]

        return self

    def with_net_stats(self) -> 'ReportBuilder':
        """Run vnstat for chosen interfaces and return ASCII-formatted stats lines."""
        if not self.config.sections.net_stats:
            return self

        all_lines = []
        for iface in self.config.networking_reporting.network_interfaces:
            command = f"vnstat -i {iface} -d | head -8"
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                shell=True
            )
            if result.returncode == 0 and result.stdout.strip():
                lines = [line.rstrip()
                         for line in result.stdout.splitlines() if line.strip()]
                all_lines.extend(lines)
        if not all_lines:
            self.net_stats = ["Network stats unavailable (vnstat failed or not installed)"]

        self.net_stats = all_lines
        return self

    def with_docker_containers(self) -> 'ReportBuilder':
        """Get list of exited docker containers in table format."""
        if not self.config.sections.docker_containers:
            return self

        command = "docker ps -f 'status=exited' --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'"
        table = subprocess.run(
            command,
            capture_output=True,
            text=True,
            shell=True
        )

        if table.returncode != 0:
            self.docker_containers = ["Docker unavailable or no containers running"]
            return self

        lines = [line.rstrip() for line in table.stdout.splitlines() if line.strip()]

        if not lines or (len(lines) == 1 and "NAMES" in lines[0]):
            self.docker_containers = ["✅️ No inactive docker containers"]
            return self

        self.docker_containers = lines
        return self

    def with_power_saving_stats(self) -> 'ReportBuilder':
        if not self.config.sections.power_saving_stats:
            return self

        """Parses the audit log file of the power saving script output. Calculates several stats and reports some stats."""
        command = "/home/albertferguson/git/proteus-management-scripts/check-power-usage.sh"
        stats = subprocess.run(
            command,
            capture_output=True,
            text=True,
            shell=True
        )

        self.power_saving_stats = stats.stdout.strip()
        return self

    def build(self) -> str:
        # execute the report builder steps...
        (self.with_logs_size_warnings()
         .with_caches_size_warnings()
         .with_tmps_size_warnings()
         .with_tmps_size_warnings()
         .with_disk_warnings()
         .with_service_statuses()
         .with_dns_status()
         .with_net_stats()
         .with_docker_containers()
         .with_power_saving_stats())

        # ...then build the report as a string

        report_sections = [f"**{self.config.report.hostname.title()} Health Report**"]

        if len(self.logs_size_warnings) > 0:
            logs_formatted = "\n".join(f"  • {entry}" for entry in self.logs_size_warnings)
            report_sections.append(f"**🗂️ Logs Size Warnings:**\n{logs_formatted}")

        if len(self.caches_size_warnings) > 0:
            caches_formatted = "\n".join(f"  • {entry}" for entry in self.caches_size_warnings)
            report_sections.append(f"**🧹 Caches Size Warnings:**\n{caches_formatted}")

        if len(self.tmps_size_warnings) > 0:
            tmps_formatted = "\n".join(f"  • {entry}" for entry in self.tmps_size_warnings)
            report_sections.append(f"**♨️ Temp Size Warnings:**\n{tmps_formatted}")

        # ie. has header row + data (length of 2 expected)
        if len(self.disk_usage_warning) > 1:
            disk_formatted = "\n".join(f"  • {entry}" for entry in self.disk_usage_warning)
            report_sections.append(f"**💽 Disk Usage Warning:**\n{disk_formatted}")

        if len(self.service_statuses) > 0:
            service_formatted = "\n".join(f"  • {status}" for status in self.service_statuses)
            report_sections.append(f"**🛠️ Service Statuses:**\n{service_formatted}")

        if len(self.dns_status) > 0:
            dns_formatted = "\n".join(f"  • {status}" for status in self.dns_status)
            report_sections.append(f"**🌐 DNS Resolution:**\n{dns_formatted}")

        if len(self.docker_containers) > 0:
            containers_formatted = "\n".join(self.docker_containers)
            report_sections.append(f"**🐳 Active Docker Containers:**\n```\n{containers_formatted}\n```")

        if self.power_saving_stats:
            report_sections.append(f"**⚡️ Power Saving Stats:**\n```\n{self.power_saving_stats}\n```")

        if len(self.net_stats) > 0:
            if isinstance(self.net_stats, list):
                self.net_stats = "\n".join(self.net_stats)
            report_sections.append(f"**📶 Network Stats (vnstat):**\n```\n{self.net_stats}\n```")

        report_message = "\n\n".join(report_sections)

        # Check if the message length is greater than the webhook limit and truncate if necessary
        max_length = 2000
        if len(report_message) > max_length:
            # Reserve space for truncation warning
            warning = "\n\n⚠️ **Message truncated** - Report exceeded 2K char limit!"
            available_length = max_length - len(warning)
            report_message = report_message[:available_length] + warning

        return report_message
