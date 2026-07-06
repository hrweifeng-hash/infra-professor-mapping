from lxml import etree

from models.author_detail import AuthorDetail


class AuthorParser:

    def parse(
        self,
        xml: str,
    ) -> AuthorDetail:

        root = etree.fromstring(xml.encode())

        person = root.find("person")

        pid = person.attrib["pid"]

        name = person.findtext("author")

        homepage = None
        affiliation = None
        orcid = None

        for url in person.findall("url"):

            text = url.text

            if text:

                homepage = text

                break

        return AuthorDetail(
            pid=pid,
            name=name,
            homepage=homepage,
            affiliation=affiliation,
            orcid=orcid,
        )