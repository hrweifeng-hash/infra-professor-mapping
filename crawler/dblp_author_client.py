import requests


class DBLPAuthorClient:

    BASE_URL = "https://dblp.org/pid"

    def get_author_xml(self, pid: str) -> str:
        """
        Download one author's DBLP XML.
        Example:
        https://dblp.org/pid/31/6601-1.xml
        """

        url = f"{self.BASE_URL}/{pid}.xml"

        print(f"Downloading Author: {url}")

        response = requests.get(
            url,
            timeout=30,
            headers={
                "User-Agent": "Mozilla/5.0"
            },
        )

        response.raise_for_status()

        return response.text