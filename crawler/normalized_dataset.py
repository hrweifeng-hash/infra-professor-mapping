from pathlib import Path

from utils.observability import stage_start, stage_end
from crawler.ingestion import normalize_dataset


def resolve_normalized_path(dataset_path: Path) -> Path:
    """Return a path to a normalized copy of dataset_path, building it
    (once) if needed. If dataset_path already looks normalized, it is
    used as-is to avoid redundant work.

    Shared by DBLPDatasetScanner and DBLPWWWScanner so both streaming
    passes over dblp.xml.gz use the same cached, cleaned copy instead of
    each normalizing (or re-normalizing) independently.
    """

    name = dataset_path.name

    if "_normalized" in name:
        return dataset_path

    if name.endswith(".xml.gz"):
        normalized_name = name[: -len(".xml.gz")] + "_normalized.xml.gz"
    else:
        normalized_name = name + ".normalized.gz"

    normalized_path = dataset_path.with_name(normalized_name)

    if normalized_path.exists():
        print(
            f"[Normalize] Using cached normalized dataset: {normalized_path}",
            flush=True,
        )
        return normalized_path

    norm_start = stage_start("Dataset Normalization")
    print(
        f"[Normalize] Cleaning {dataset_path} -> {normalized_path} "
        "(one-time; cached for future runs)",
        flush=True,
    )
    normalize_dataset(dataset_path, normalized_path)
    stage_end("Dataset Normalization", norm_start)

    return normalized_path
