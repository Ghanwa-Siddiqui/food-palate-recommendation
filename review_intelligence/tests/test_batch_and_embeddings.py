import csv
import json

from review_intelligence.scripts import process_reviews as processor
from review_intelligence.src.embeddings import ReviewEmbedder
from review_intelligence.src.models import ReviewFeatures


def test_batch_processing_preserves_input_and_writes_json_tags(tmp_path, monkeypatch):
    source = tmp_path / "reviews.csv"
    target = tmp_path / "review_features.csv"
    source.write_text(
        "review_id,dish_id,text,rating,timestamp\nR1,D001,Great karahi,5,2026-08-25\n",
        encoding="utf-8",
    )

    class FakeExtractor:
        def extract(self, text):
            assert text == "Great karahi"
            return ReviewFeatures(0.9, 0.8, 0.4, ["spicy", "tender"])

    monkeypatch.setattr(processor, "ReviewExtractor", FakeExtractor)
    processed, failures = processor.process_reviews(source, target)
    with target.open(encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert (processed, failures) == (1, 0)
    assert row["review_id"] == "R1"
    assert json.loads(row["flavor_tags"]) == ["spicy", "tender"]


def test_embedding_model_is_reused_with_injected_encoder():
    class FakeModel:
        def __init__(self):
            self.calls = 0

        def encode(self, sentences, **kwargs):
            self.calls += 1
            return [[0.1, 0.2]]

    model = FakeModel()
    embedder = ReviewEmbedder(model=model)
    assert embedder.embed("first review") == [0.1, 0.2]
    assert embedder.embed("second review") == [0.1, 0.2]
    assert model.calls == 2
