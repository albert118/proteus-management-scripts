from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class ReportSection:
    hostname: str
    webhook_file: str
    report_file_location: Path
    services_to_monitor: List[str]


@dataclass
class SectionsSection:
    logs_warnings: bool
    caches_warnings: bool
    temp_warnings: bool
    disk_warnings: bool
    service_statuses: bool
    dns_resolution: bool
    net_stats: bool
    docker_containers: bool
    power_saving_stats: bool


@dataclass
class NetworkingReportingSection:
    network_interfaces: List[str]
    dns_test_domain: List[str]


@dataclass
class FileReportingSection:
    disk_percent: int
    file_size: str
    disk_device: str
    logs_directories: List[str]
    cache_directories: List[str]
    temp_directories: List[str]


@dataclass
class ServicesSection:
    to_monitor: List[str]

# ==============================================================================


@dataclass
class ProteusHealthConfig:
    report: ReportSection
    sections: SectionsSection
    networking_reporting: NetworkingReportingSection
    file_reporting: FileReportingSection
    services: ServicesSection  # Handles '[services]:' as configparser drops the colon
