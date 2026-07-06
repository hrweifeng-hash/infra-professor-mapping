# DATA_SOURCE.md

## Primary dataset

The pipeline is built around the official DBLP XML dump, **not** per-conference
downloads.

- Download: https://dblp.org/xml/release/
- File: `dblp.xml.gz` (the full dump; several GB, grows over time)
- DBLP also publishes a matching `.dtd` — not required at runtime, only
  useful if you want to validate the file yourself.

## Where it goes

```
data/raw/dblp.xml.gz
```

`DatasetPipeline` / `DBLPDatasetScanner` default to this path
(`pipeline/dataset_pipeline.py`, `crawler/dblp_dataset_scanner.py`). Pass a
different path via `MappingPipeline(dataset_path=...)` if you keep it
elsewhere.

## Refreshing the dataset

DBLP updates the dump periodically (roughly weekly). Re-download and replace
`data/raw/dblp.xml.gz` to pick up new publications — no code changes needed.
The scanner streams the file (`lxml.etree.iterparse`), so it does not load
the whole dump into memory regardless of file size.

## Malformed XML

DBLP's dump occasionally contains stray unescaped entities that make lxml's
strict parser abort mid-stream (you'll see an `XMLSyntaxError` partway
through, often after several million records). `DBLPDatasetScanner`
handles this automatically: on first use it normalizes `dblp.xml.gz`
via `crawler/ingestion.py`'s `normalize_dataset()`, caching the cleaned
copy as `dblp_normalized.xml.gz` next to the original. Subsequent runs
detect the cached file and skip re-normalizing. Delete the
`*_normalized.xml.gz` file to force a re-clean (e.g. after replacing
`dblp.xml.gz` with a fresh download).

## Secondary source: per-author enrichment

`ProfessorEnrichmentBuilder` (`builders/professor_enrichment_builder.py`)
fetches individual author pages from DBLP to get fields not present in the
bulk dump — homepage, affiliation:

```
https://dblp.org/pid/<pid>.xml
```

This is a **live, rate-limited network call per professor** and is only run
against the top-N ranked professors (see `MappingPipeline(identity_top_n=...)`),
never the full professor universe. Run with `--no-enrich` (see `main.py`)
to skip it entirely, e.g. for a fast smoke test of the dataset pipeline.
