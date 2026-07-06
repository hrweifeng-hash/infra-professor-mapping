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

            if key.startswith("conf/"):

                parts = key.split("/")

                if len(parts) >= 2:
                    conf = parts[1]
                    counter[conf] += 1

            # 释放内存
            elem.clear()

            while elem.getprevious() is not None:
                del elem.getparent()[0]

    print()
    print("=" * 80)
    print("Conference Keys in DBLP")
    print("=" * 80)

    for conf, count in sorted(counter.items()):
        print(f"{conf:25} {count}")


if __name__ == "__main__":
    main()