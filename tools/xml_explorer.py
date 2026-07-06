import gzip
from collections import Counter

from lxml import etree as ET


DATASET = "data/raw/dblp.xml.gz"


def main():

    counter = Counter()

    with gzip.open(DATASET, "rb") as f:

        context = ET.iterparse(
            f,
            events=("end",),
            tag="inproceedings",
            recover=True,
            huge_tree=True,
        )

        for _, elem in context:

            key = elem.get("key", "")

            prefix = key.split("/")[0] if key else "UNKNOWN"

            counter[prefix] += 1

            elem.clear()

            while elem.getprevious() is not None:
                del elem.getparent()[0]

            if sum(counter.values()) >= 5000:
                break

    print()
    print("=" * 80)
    print("Top prefixes (first 5000 inproceedings)")
    print("=" * 80)

    for prefix, count in counter.most_common():
        print(f"{prefix:20} {count}")


if __name__ == "__main__":
    main()