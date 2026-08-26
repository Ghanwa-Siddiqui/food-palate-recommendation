"""Batch-process reviews.csv with Ollama and optionally attach local embeddings."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from review_intelligence.src.embeddings import ReviewEmbedder
from review_intelligence.src.extractor import ExtractionError, ReviewExtractor

DATA_DIR = ROOT / "review_intelligence" / "data"
REQUIRED_COLUMNS = {"review_id", "dish_id", "text", "rating", "timestamp"}


def process_reviews(input_path: Path, output_path: Path, with_embeddings: bool = False) -> tuple[int, int]:
    if not input_path.exists():
        raise FileNotFoundError(f"Reviews file not found: {input_path}")
    with input_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not REQUIRED_COLUMNS.issubset(reader.fieldnames):
            missing = REQUIRED_COLUMNS.difference(reader.fieldnames or [])
            raise ValueError(f"Input CSV missing required columns: {', '.join(sorted(missing))}")
        rows = list(reader)
    extractor, embedder = ReviewExtractor(), ReviewEmbedder() if with_embeddings else None
    output_rows, failures = [], 0
    for row in rows:
        try:
            features = extractor.extract(row["text"])
            result = {**row, **features.to_dict()}
            result["flavor_tags"] = json.dumps(features.flavor_tags)
            if embedder:
                result["embedding"] = json.dumps(embedder.embed(row["text"]))
            output_rows.append(result)
        except (ExtractionError, KeyError, ValueError) as exc:
            failures += 1
            print(f"Skipping review {row.get('review_id', '<unknown>')}: {exc}", file=sys.stderr)
    fields = ["review_id", "dish_id", "text", "rating", "timestamp", "sentiment", "spice_level", "oiliness", "flavor_tags"]
    if with_embeddings:
        fields.append("embedding")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output_rows)
    return len(output_rows), failures


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DATA_DIR / "reviews.csv")
    parser.add_argument("--output", type=Path, default=DATA_DIR / "review_features.csv")
    parser.add_argument("--with-embeddings", action="store_true", help="Generate local Sentence Transformer vectors")
    args = parser.parse_args()
    processed, failed = process_reviews(args.input, args.output, args.with_embeddings)
    print(f"Processed {processed} reviews; skipped {failed}. Wrote {args.output}")


if __name__ == "__main__":
    main()
