from ip_tools import filter_ips as patient


def it_filter_ips_writes_distinct_sorted_ips(tmp_path):
    out = tmp_path / "ip_list.txt"
    out.write_text("2.2.2.2\n1.1.1.1\n", encoding="utf-8")

    patient.filter(["3.3.3.3", "2.2.2.2", "4.4.4.4"], str(out))

    result = out.read_text(encoding="utf-8")
    assert result == "1.1.1.1\n2.2.2.2\n3.3.3.3\n4.4.4.4\n"


def it_filter_ips_creates_output_when_it_does_not_exist(tmp_path):
    out = tmp_path / "ip_list.txt"

    patient.filter(["2.2.2.2", "1.1.1.1", "2.2.2.2"], out)

    assert out.read_text(encoding="utf-8") == "1.1.1.1\n2.2.2.2\n"


def it_filter_ips_keeps_existing_ips_when_given_an_empty_list(tmp_path):
    out = tmp_path / "ip_list.txt"
    out.write_text("2.2.2.2\n1.1.1.1\n", encoding="utf-8")

    patient.filter([], out)

    assert out.read_text(encoding="utf-8") == "1.1.1.1\n2.2.2.2\n"


def it_filter_ips_writes_only_a_newline_for_empty_list_and_missing_output(tmp_path):
    out = tmp_path / "ip_list.txt"

    patient.filter([], out)

    assert out.read_text(encoding="utf-8") == "\n"


def it_filter_ips_handles_an_empty_existing_file(tmp_path):
    out = tmp_path / "ip_list.txt"
    out.write_text("", encoding="utf-8")

    patient.filter(["2.2.2.2", "1.1.1.1"], out)

    assert out.read_text(encoding="utf-8") == "1.1.1.1\n2.2.2.2\n"


def it_filter_ips_ignores_blank_and_whitespace_lines_in_existing_file(tmp_path):
    out = tmp_path / "ip_list.txt"
    out.write_text("\n  \n 2.2.2.2 \n\t\n1.1.1.1\n", encoding="utf-8")

    patient.filter(["3.3.3.3"], out)

    assert out.read_text(encoding="utf-8") == "1.1.1.1\n2.2.2.2\n3.3.3.3\n"
