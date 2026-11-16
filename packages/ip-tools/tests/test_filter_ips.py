import filter_ips as patient
from types import SimpleNamespace


def it_filter_ips_writes_distinct_sorted_ips(tmp_path):
    out = tmp_path / "ip_list.txt"
    out.write_text("2.2.2.2\n1.1.1.1\n", encoding="utf-8")

    args_dict = {
        "ips": ["3.3.3.3", "2.2.2.2", "4.4.4.4"],
        "output": str(out)
    }

    patient.main(SimpleNamespace(**args_dict))

    result = out.read_text(encoding="utf-8")
    assert result == "1.1.1.1\n2.2.2.2\n3.3.3.3\n4.4.4.4\n"
