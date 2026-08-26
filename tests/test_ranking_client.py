from uuid import UUID

import httpx
import pytest

from app.ranking_client import (
    RankingBackendError,
    RankingFeedClient,
    RankingUnavailableDataError,
    RankingUserNotFoundError,
)

USER_ID = UUID("11111111-1111-4111-8111-111111111111")


def test_client_calls_configured_ranking_endpoint(monkeypatch):
    seen = {}

    def fake_get(url, **kwargs):
        seen.update(url=url, **kwargs)
        return httpx.Response(
            200,
            json={
                "user_id": str(USER_ID),
                "total_candidates": 0,
                "items": [],
                "neutral_signals": [],
            },
        )

    monkeypatch.setattr("app.ranking_client.httpx.get", fake_get)
    client = RankingFeedClient("http://ranking.test/", timeout_seconds=1.5)

    result = client.get_feed(USER_ID, [("limit", "20")])

    assert result.user_id == USER_ID
    assert seen == {
        "url": f"http://ranking.test/ranking/feed/{USER_ID}",
        "params": [("limit", "20")],
        "timeout": 1.5,
        "follow_redirects": False,
    }


def test_client_maps_not_found_without_leaking_response(monkeypatch):
    monkeypatch.setattr(
        "app.ranking_client.httpx.get", lambda *args, **kwargs: httpx.Response(404)
    )

    with pytest.raises(RankingUserNotFoundError):
        RankingFeedClient().get_feed(USER_ID, [])


def test_client_rejects_malformed_success_payload(monkeypatch):
    monkeypatch.setattr(
        "app.ranking_client.httpx.get",
        lambda *args, **kwargs: httpx.Response(200, json={"unexpected": True}),
    )

    with pytest.raises(RankingUnavailableDataError):
        RankingFeedClient().get_feed(USER_ID, [])


def test_client_maps_network_errors(monkeypatch):
    def fail(*args, **kwargs):
        raise httpx.ConnectError(
            "offline", request=httpx.Request("GET", "http://ranking")
        )

    monkeypatch.setattr("app.ranking_client.httpx.get", fail)

    with pytest.raises(RankingBackendError):
        RankingFeedClient().get_feed(USER_ID, [])
