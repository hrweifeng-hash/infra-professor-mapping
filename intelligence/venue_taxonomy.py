"""
Venue -> Research Category mapping.

Venue evidence usually has a higher confidence than keyword matching.
"""

VENUE_WEIGHTS = {

    "OSDI": {
        "Operating Systems": 5.0,
        "Distributed Systems": 3.0,
        "Cloud Computing": 2.0,
        "Storage": 2.0,
    },

    "SOSP": {
        "Operating Systems": 5.0,
        "Distributed Systems": 4.0,
        "Storage": 2.0,
    },

    "EuroSys": {
        "Operating Systems": 4.0,
        "Distributed Systems": 4.0,
        "Cloud Computing": 2.0,
    },

    "FAST": {
        "Storage": 5.0,
        "Operating Systems": 2.0,
    },

    "NSDI": {
        "Networking": 5.0,
        "Distributed Systems": 3.0,
    },

    "SIGCOMM": {
        "Networking": 5.0,
    },

    "SIGMOD": {
        "Database Systems": 5.0,
    },

    "VLDB": {
        "Database Systems": 5.0,
    },

    "ICDE": {
        "Database Systems": 4.0,
    },

    "SoCC": {
        "Cloud Computing": 5.0,
        "Distributed Systems": 2.0,
    },

    "MLSys": {
        "ML Systems": 5.0,
    },

    "NeurIPS": {
        "ML Systems": 3.0,
    },

    "ICML": {
        "ML Systems": 3.0,
    },

}