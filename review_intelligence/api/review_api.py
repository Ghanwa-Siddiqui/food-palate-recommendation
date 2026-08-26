"""FastAPI application exposing the shared dish review-summary contract."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException

from review_intelligence.src.aggregator import aggregate_reviews, load_feature_rows

DEFAULT_FEATURES_PATH = Path(__file__).resolve().parents[1] / "data" / "review_features.csv"


def create_app(features_path: str | Path = DEFAULT_FEATURES_PATH) -> FastAPI:
    app = FastAPI(title="Namak Review Intelligence", version="1.0.0")

    @app.get("/reviews/{dish_id}/summary")
    def review_summary(dish_id: str) -> dict:
        try:
            summaries = aggregate_reviews(load_feature_rows(features_path))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if dish_id not in summaries:
            raise HTTPException(status_code=404, detail=f"No review summary found for dish_id `{dish_id}`")
        return summaries[dish_id].to_dict()

    return app


app = create_app()
