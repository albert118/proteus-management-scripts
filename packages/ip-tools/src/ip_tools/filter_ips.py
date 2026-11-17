import os
from pathlib import Path


def filter(ips: list[str], output_file_name: Path):
    existing = set()
    if os.path.exists(output_file_name):
        with open(output_file_name, "r") as f:
            existing = {line.strip() for line in f if line.strip()}

    distinct = sorted(existing | set(ips))

    with open(output_file_name, "w") as f:
        f.write("\n".join(distinct) + "\n")


# if __name__ == "__main__":
#     parser = argparse.ArgumentParser(
#         description="Create a distinct set of IPs given new and existing IPs. Writes to the output (newline-separated).")
#     parser.add_argument(
#         "ips", nargs="+", help="New IP addresses separated by whitespace")
#     parser.add_argument("-o", "--output", default="ip_list.txt",
#                         help="Output filename (default: ip_list.txt)")
#     args = parser.parse_args()
#     main(args)
