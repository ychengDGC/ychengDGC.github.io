"""Fetch a validated citation snapshot without replacing data on fetch failure."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile


def is_count(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def fetch_snapshot(scholar_id):
    from scholarly import scholarly

    author = scholarly.search_author_id(scholar_id)
    author = scholarly.fill(author, sections=["basics", "indices", "counts", "publications"])
    if author.get("scholar_id") != scholar_id:
        raise ValueError("The returned Scholar profile does not match the configured ID.")
    if not is_count(author.get("citedby")):
        raise ValueError("Scholar did not return a valid citation count.")
    publications = author.get("publications")
    if not isinstance(publications, list):
        raise ValueError("Scholar did not return a valid publication list.")
    if author["citedby"] > 0 and not publications:
        raise ValueError("Scholar returned an incomplete profile without publications.")

    snapshot = {
        "google_scholar_id": scholar_id,
        "name": author.get("name", ""),
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "publications": {},
    }
    for key in ("citedby", "hindex", "i10index", "citedby5", "hindex5", "i10index5"):
        if is_count(author.get(key)):
            snapshot[key] = author[key]
    for publication in publications:
        paper_id = publication.get("author_pub_id", "")
        citations = publication.get("num_citations")
        if paper_id.startswith(scholar_id + ":") and is_count(citations):
            snapshot["publications"][paper_id] = {"num_citations": citations}
    return snapshot


def save_snapshot(snapshot, output_dir):
    payloads = {
        "gs_data.json": snapshot,
        "gs_data_shieldsio.json": {
            "schemaVersion": 1,
            "label": "citations",
            "message": str(snapshot["citedby"]),
        },
    }
    # Serialize everything before replacing either existing result file.
    serialized = {
        name: json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        for name, value in payloads.items()
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output_dir) as temporary_dir:
        for name, content in serialized.items():
            Path(temporary_dir, name).write_text(content, encoding="utf-8")
        for name in serialized:
            os.replace(Path(temporary_dir, name), output_dir / name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path, default=Path(__file__).resolve().parent / "results"
    )
    args = parser.parse_args()
    scholar_id = os.environ.get("GOOGLE_SCHOLAR_ID", "").strip()
    if not scholar_id:
        print("Skipped: set GOOGLE_SCHOLAR_ID to enable citation updates.")
        return 0
    try:
        snapshot = fetch_snapshot(scholar_id)
        save_snapshot(snapshot, args.output_dir)
    except Exception as error:
        print(f"Citation update failed; previously published data is unchanged: {error}", file=sys.stderr)
        return 1
    print(f"Saved citation data for {snapshot['name']} ({len(snapshot['publications'])} publications).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
