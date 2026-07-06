import gzip

from lxml import etree as ET


DATASET = "data/raw/dblp.xml.gz"


def main():

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

            if key.startswith("conf/osdi/"):

                print("=" * 100)
                print(key)
                print("=" * 100)

                print(
                    ET.tostring(
                        elem,
                        pretty_print=True,
                        encoding="unicode",
                    )
                )

                break

            elem.clear()

            while elem.getprevious() is not None:
                del elem.getparent()[0]


if __name__ == "__main__":
    main()