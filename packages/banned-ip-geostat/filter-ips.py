import argparse
import os


def main():
    parser = argparse.ArgumentParser(
        description="Create a distinct set of IPs given new and existing IPs. Writes to the output (newline-separated).")
    parser.add_argument(
        "ips", nargs="+", help="New IP addresses separated by whitespace")
    parser.add_argument("-o", "--output", default="ip_list.txt",
                        help="Output filename (default: ip_list.txt)")
    args = parser.parse_args()

    existing = set()
    if os.path.exists(args.output):
        with open(args.output, "r") as f:
            existing = {line.strip() for line in f if line.strip()}

    distinct = sorted(existing | set(args.ips))

    with open(args.output, "w") as f:
        f.write("\n".join(distinct) + "\n")


if __name__ == "__main__":
    main()
