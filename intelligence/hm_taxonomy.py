"""
HM Capability Taxonomy

This taxonomy maps research capabilities to each Hiring Manager (HM).

Unlike intelligence.taxonomy, which models academic research areas,
this file models ByteDance recruiting directions.

HM Matching Analyzer should ONLY depend on this file.
"""

HM_TRACKS = {

    "Huazheng Zhang": [
        "Distributed Training",
        "Training Infrastructure",
        "GPU Cluster",
        "GPU Runtime",
        "RDMA",
        "High Performance Computing",
        "Distributed Systems",
        "Cluster Scheduling",
        "Resource Management",
        "Fault Tolerance",
        "Reliability",
        "World Model",
        "Video Generation",
        "RL Infrastructure",
    ],

    "Yang Hua": [
        "LLM Training Framework",
        "Training Runtime",
        "Megatron",
        "DeepSpeed",
        "FSDP",
        "MoE",
        "FP8",
        "Low Precision",
        "Mixed Precision",
        "Attention Optimization",
        "Communication Optimization",
        "Gradient Checkpointing",
        "Large Scale Training",
    ],

    "Liu Bo": [
        "LLM Algorithm",
        "Distributed Training",
        "Training Runtime",
        "Mixed Precision",
        "FP8",
        "MoE",
        "Optimization",
        "Scaling Law",
        "Training Infrastructure",
    ],

    "Liwen Chang": [
        "Compiler",
        "Code Generation",
        "ML Compiler",
        "Runtime",
        "Inference Runtime",
        "LLM Inference",
        "Serving",
        "TVM",
        "Triton",
        "TorchInductor",
        "TensorRT",
        "CUDA",
        "Kernel Optimization",
        "KV Cache",
        "Operator Fusion",
        "Graph Optimization",
    ],

    "Chundian Liu": [
        "Agent",
        "Agent Infrastructure",
        "Agent Runtime",
        "Platform Backend",
        "Evaluation Harness",
        "Memory System",
        "Tool Calling",
        "Workflow",
        "Serving Backend",
        "Monitoring",
        "Observability",
        "Orchestration",
        "Browser Agent",
        "Multi-Agent",
    ],
}