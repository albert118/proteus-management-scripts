import utils as patient
import re


def describe_save_report_to_disk():
    def it_writes_to_file_with_contents_and_timestamp(tmp_path):
        report_file = tmp_path / "test-report.log"
        fake_content = "hello-world"
        # Matches [YYYYMMDD_HHMMSS]
        expected_timestamp_re = r"\[\d{8}_\d{6}\]"

        patient.save_report_to_disk(fake_content, report_file)

        assert report_file.exists()
        content = report_file.read_text(encoding="utf-8")

        assert re.match(expected_timestamp_re, content) is not None
        assert content.endswith(f"{fake_content}\n")

    def it_makes_parent_directories_if_missing(tmp_path):
        report_file = tmp_path / "grandparent/parent/test-report.log"
        fake_content = "hello-world"
        patient.save_report_to_disk(fake_content, report_file)
        assert report_file.exists()

    def it_allows_existing_directories(tmp_path):
        report_file = tmp_path / "test-report.log"
        fake_content = "hello-world"
        patient.save_report_to_disk(fake_content, report_file)

        patient.save_report_to_disk(fake_content, report_file)

        assert report_file.exists()
