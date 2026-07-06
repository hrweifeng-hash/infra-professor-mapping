import json
import time
import tracemalloc
from pathlib import Path

from pipeline.mapping_pipeline import MappingPipeline
from config.conferences import CONFERENCES

# Default years used by main.py
YEARS = [2021, 2022, 2023, 2024, 2025]

DATASET_PATH = Path('data/raw/dblp.xml.gz')
OUTPUT_PATH = Path('data/output/pipeline_report.json')

# Import ingestion normalizer
from crawler.ingestion import normalize_dataset
from utils.observability import stage_start, stage_end


def run():
    dataset_path = DATASET_PATH
    if not dataset_path.exists():
        print(f"Dataset not found: {dataset_path}")
        return 2

    # Guard against truncated or accidentally small dataset files
    if dataset_path.stat().st_size < 1024:
        print(f"Dataset file looks too small or corrupted: {dataset_path} ({dataset_path.stat().st_size} bytes)")
        print("Please restore the original DBLP dataset at data/raw/dblp.xml.gz and re-run.")
        return 4

    # Normalize dataset once and reuse the normalized file
    normalized_path = dataset_path.with_name("dblp_normalized.xml.gz")

    if normalized_path.exists():
        print(f"Using existing normalized dataset: {normalized_path}", flush=True)
    else:
        try:
            norm_start = stage_start("Normalization")
            print(f"Normalizing dataset to: {normalized_path}", flush=True)
            normalize_dataset(dataset_path, normalized_path)
            stage_end("Normalization", norm_start)
        except Exception as e:
            print("Failed to normalize dataset:", e, flush=True)
            return 3

    # Use the normalized dataset for the pipeline
    dataset_path = normalized_path

    mapper = MappingPipeline(dataset_path=str(dataset_path))

    start_time = time.time()
    tracemalloc.start()

    try:
        professors = mapper.run(conferences=list(CONFERENCES.values()), years=YEARS)
    except Exception as e:
        print("Pipeline execution error:", e)
        return 1

    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    elapsed = time.time() - start_time

    # normalize professors list
    if isinstance(professors, dict):
        professors = list(professors.values())

    # collect top 50
    ranked = sorted(
        professors,
        key=lambda p: getattr(getattr(p, 'intelligence', None), 'overall_score', 0),
        reverse=True,
    )

    top50 = []
    for p in ranked[:50]:
        author = getattr(getattr(p, 'author_profile', None), 'author', None)
        name = getattr(author, 'name', None) if author else None
        top50.append({
            'name': name,
            'pid': getattr(author, 'pid', None) if author else None,
            'pubs': getattr(p, 'intelligence').publication_count if getattr(p, 'intelligence', None) else None,
            'score': getattr(p, 'intelligence').overall_score if getattr(p, 'intelligence', None) else None,
        })

    # invariants
    violations = []
    for p in professors:
        key = getattr(getattr(p, 'author_profile', None), 'author', None)
        pid = key.pid if key else None
        name = key.name if key else None
        intelligence = getattr(p, 'intelligence', None)
        papers = getattr(getattr(p, 'author_profile', None), 'papers', [])
        pub_count = getattr(intelligence, 'publication_count', None) if intelligence else None

        actual = len(papers)
        if pub_count != actual:
            violations.append({'type': 'publication_count_mismatch', 'pid': pid, 'name': name, 'int_pub_count': pub_count, 'actual_papers': actual})

        # duplicate papers
        seen = set(); dup = []
        for paper in papers:
            keyp = getattr(paper, 'dblp_key', None) or getattr(paper, 'title', None)
            if keyp in seen:
                dup.append(keyp)
            seen.add(keyp)
        if dup:
            violations.append({'type': 'duplicate_papers', 'pid': pid, 'name': name, 'dups': dup})

        # venue distribution
        venue_dist = getattr(intelligence, 'venue_distribution', {}) if intelligence else {}
        if sum(venue_dist.values()) != actual:
            violations.append({'type': 'venue_distribution_mismatch', 'pid': pid, 'name': name, 'venue_sum': sum(venue_dist.values()), 'actual': actual})

        # yearly
        yearly = getattr(intelligence, 'yearly_publications', {}) if intelligence else {}
        if sum(yearly.values()) != actual:
            violations.append({'type': 'yearly_publications_mismatch', 'pid': pid, 'name': name, 'yearly_sum': sum(yearly.values()), 'actual': actual})

        # null fields
        nulls = [k for k, v in (intelligence.__dict__.items() if intelligence else {}).items() if v is None]
        if nulls:
            violations.append({'type': 'null_intelligence_fields', 'pid': pid, 'name': name, 'fields': nulls})

    report = {
        'timestamp': time.time(),
        'elapsed_seconds': elapsed,
        'tracemalloc_current_bytes': current,
        'tracemalloc_peak_bytes': peak,
        'registry_size': len(professors),
        'top_50': top50,
        'violations': violations,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open('w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)

    print(f"Wrote report to {OUTPUT_PATH}")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(run())
