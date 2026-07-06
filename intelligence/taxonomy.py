from intelligence.models.research_category import ResearchCategory

"""
Infrastructure Research Taxonomy.

This file defines the knowledge base used by the
Intelligence Engine.

Analyzer MUST NOT hard-code any keywords or venues.
Everything should come from this taxonomy.
"""


INFRASTRUCTURE_TAXONOMY = [

    ResearchCategory(
        name="Operating Systems",
        parent="Infrastructure",
        keywords=[
            "kernel",
            "scheduler",
            "filesystem",
            "file system",
            "virtual memory",
            "memory management",
            "process",
            "thread",
            "microkernel",
            "operating system",
            "os",
        ],
        venues=[
            "SOSP",
            "OSDI",
            "EuroSys",
        ],
    ),

    ResearchCategory(
        name="Distributed Systems",
        parent="Infrastructure",
        keywords=[
            "distributed",
            "consensus",
            "replication",
            "replicated",
            "raft",
            "paxos",
            "fault tolerance",
            "distributed transaction",
            "cluster",
            "coordination",
        ],
        venues=[
            "SOSP",
            "OSDI",
            "NSDI",
            "EuroSys",
        ],
    ),

    ResearchCategory(
        name="Storage",
        parent="Infrastructure",
        keywords=[
            "storage",
            "ssd",
            "flash",
            "nvme",
            "persistent memory",
            "pmem",
            "log structured",
            "filesystem",
            "file system",
        ],
        venues=[
            "FAST",
            "OSDI",
            "SOSP",
        ],
    ),

    ResearchCategory(
        name="Networking",
        parent="Infrastructure",
        keywords=[
            "network",
            "networking",
            "tcp",
            "udp",
            "rdma",
            "routing",
            "switch",
            "datacenter network",
            "congestion",
        ],
        venues=[
            "SIGCOMM",
            "NSDI",
        ],
    ),

    ResearchCategory(
        name="Cloud Computing",
        parent="Infrastructure",
        keywords=[
            "cloud",
            "container",
            "kubernetes",
            "docker",
            "virtual machine",
            "resource management",
            "cluster management",
            "serverless",
        ],
        venues=[
            "SoCC",
            "EuroSys",
            "OSDI",
        ],
    ),

    ResearchCategory(
        name="Database Systems",
        parent="Infrastructure",
        keywords=[
            "database",
            "sql",
            "query",
            "index",
            "join",
            "transaction",
            "oltp",
            "olap",
        ],
        venues=[
            "SIGMOD",
            "VLDB",
            "ICDE",
        ],
    ),

    ResearchCategory(
        name="ML Systems",
        parent="Infrastructure",
        keywords=[
            "llm",
            "language model",
            "transformer",
            "gpu",
            "cuda",
            "training",
            "inference",
            "serving",
            "parameter server",
            "pipeline parallelism",
        ],
        venues=[
            "MLSys",
            "NeurIPS",
            "ICML",
        ],
    ),

]