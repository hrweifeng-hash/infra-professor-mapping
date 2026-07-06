from models.conference import Conference


CONFERENCES = {

    # ==========================
    # Operating Systems
    # ==========================

    "OSDI": Conference(
        name="OSDI",
        dblp_name="osdi",
        category="Operating Systems",
        start_year=1994,
    ),

    "SOSP": Conference(
        name="SOSP",
        dblp_name="sosp",
        category="Operating Systems",
        start_year=1967,
    ),

    "NSDI": Conference(
        name="NSDI",
        dblp_name="nsdi",
        category="Networking",
        start_year=2004,
    ),

    "USENIX ATC": Conference(
        name="USENIX ATC",
        dblp_name="usenix",
        category="Operating Systems",
        start_year=1993,
    ),

    "EuroSys": Conference(
        name="EuroSys",
        dblp_name="eurosys",
        category="Operating Systems",
        start_year=2006,
    ),

    "FAST": Conference(
        name="FAST",
        dblp_name="fast",
        category="Storage Systems",
        start_year=2002,
    ),

    # ==========================
    # Networking
    # ==========================

    "SIGCOMM": Conference(
        name="SIGCOMM",
        dblp_name="sigcomm",
        category="Networking",
        start_year=1983,
    ),

    # ==========================
    # Architecture
    # ==========================

    "ASPLOS": Conference(
        name="ASPLOS",
        dblp_name="asplos",
        category="Computer Architecture",
        start_year=1982,
    ),

    "ISCA": Conference(
        name="ISCA",
        dblp_name="isca",
        category="Computer Architecture",
        start_year=1973,
    ),

    "MICRO": Conference(
        name="MICRO",
        dblp_name="micro",
        category="Computer Architecture",
        start_year=1968,
    ),

    "HPCA": Conference(
        name="HPCA",
        dblp_name="hpca",
        category="Computer Architecture",
        start_year=1995,
    ),

    # ==========================
    # Programming Languages
    # ==========================

    "PLDI": Conference(
        name="PLDI",
        dblp_name="pldi",
        category="Programming Languages",
        start_year=1979,
    ),

    "CGO": Conference(
        name="CGO",
        dblp_name="cgo",
        category="Compiler",
        start_year=2003,
    ),

    "PPoPP": Conference(
        name="PPoPP",
        dblp_name="ppopp",
        category="Parallel Programming",
        start_year=1988,
    ),

    # ==========================
    # Database
    # ==========================

    "SIGMOD": Conference(
        name="SIGMOD Conference",
        dblp_name="sigmod",
        category="Database",
        start_year=1975,
    ),

    "VLDB": Conference(
        name="VLDB",
        dblp_name="vldb",
        category="Database",
        start_year=1975,
    ),

    # ==========================
    # Machine Learning
    # ==========================

    "NeurIPS": Conference(
        name="NeurIPS",
        dblp_name="nips",
        category="Machine Learning",
        start_year=1987,
    ),

    "ICML": Conference(
        name="ICML",
        dblp_name="icml",
        category="Machine Learning",
        start_year=1980,
    ),

    "ICLR": Conference(
        name="ICLR",
        dblp_name="iclr",
        category="Machine Learning",
        start_year=2013,
    ),
}