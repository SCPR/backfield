"""Provider normalization tests for address discovery search."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from agate_utils.search import (
    EXA_SEARCH_URL,
    brave_place_search,
    brave_web_search,
    exa_search,
)


def test_brave_web_search_keeps_oakland_station_address_evidence() -> None:
    payload = {
        "type": "search",
        "web": {
            "results": [
                {
                    "title": "Oakland Station - 1428 105th Ave Oakland, CA 94603",
                    "url": "https://www.apartments.com/oakland-station/",
                    "description": "Oakland Station is an apartment community.",
                    "extra_snippets": [
                        "Oakland Station is located at 1428 105th Ave in Oakland, CA."
                    ],
                },
                {
                    "title": "Contact Us - Oakland Station",
                    "url": "https://www.oaklandstationapts.com/contact_us/",
                    "description": "1428 105th Avenue Oakland, CA 94603",
                    "location": {
                        "postal_address": {
                            "streetAddress": "1428 105th Avenue",
                            "addressLocality": "Oakland",
                            "addressRegion": "CA",
                            "postalCode": "94603",
                            "country": "US",
                        }
                    },
                },
            ]
        },
        "locations": {"results": []},
        "infobox": {"results": []},
    }
    with patch("agate_utils.search.brave_web_search_raw", return_value=payload):
        response = brave_web_search(
            "brave-key",
            q="Oakland Station 105th Avenue Oakland CA address",
        )

    assert response.success is True
    assert len(response.results) == 2
    evidence = "\n".join(result.snippet for result in response.results)
    assert "1428 105th Ave" in evidence
    assert "Postal address: 1428 105th Avenue, Oakland, CA, 94603, US" in evidence


def test_brave_web_search_deduplicates_mixed_result_groups() -> None:
    row = {
        "title": "Oakland Station",
        "url": "https://example.com/oakland-station",
        "description": "1428 105th Avenue, Oakland, CA 94603",
    }
    payload = {
        "web": {"results": [row]},
        "locations": {"results": [row]},
        "infobox": {"results": []},
    }
    with patch("agate_utils.search.brave_web_search_raw", return_value=payload):
        response = brave_web_search("brave-key", q="Oakland Station address")

    assert len(response.results) == 1


def test_brave_place_search_keeps_description_and_postal_address() -> None:
    payload = {
        "results": [
            {
                "title": "Oakland Station",
                "url": "https://example.com/oakland-station",
                "description": "Affordable apartment community",
                "postal_address": {
                    "displayAddress": "1428 105th Avenue, Oakland, CA 94603"
                },
            }
        ]
    }
    with patch("agate_utils.search.brave_place_search_raw", return_value=payload):
        response = brave_place_search(
            "brave-key",
            q="Oakland Station address",
            location="Oakland CA US",
        )

    assert response.success is True
    assert response.results[0].snippet == (
        "Affordable apartment community\n"
        "Postal address: 1428 105th Avenue, Oakland, CA 94603"
    )


def test_exa_search_sends_recommended_request_and_maps_highlights() -> None:
    reply = MagicMock()
    reply.json.return_value = {
        "requestId": "r1",
        "results": [
            {
                "title": "Red Lion Tavern",
                "url": "https://redliontavern.net/",
                "highlights": ["Red Lion Tavern, 2366 Glendale Blvd, Los Angeles, CA 90039"],
            },
            {"title": "No content", "url": "https://example.com/"},
        ],
        "costDollars": {"total": 0.007},
    }
    with patch("agate_utils.search.requests.post", return_value=reply) as post:
        response = exa_search(
            "exa-key",
            query="Red Lion Tavern Silver Lake address",
            objective="Find the street address of Red Lion Tavern in Los Angeles, CA.",
            user_location="us",
        )

    args, kwargs = post.call_args
    assert args == (EXA_SEARCH_URL,)
    assert kwargs["headers"]["x-api-key"] == "exa-key"
    assert kwargs["json"] == {
        "query": "Red Lion Tavern Silver Lake address",
        "type": "auto",
        "contents": {"highlights": True},
        "objective": "Find the street address of Red Lion Tavern in Los Angeles, CA.",
        "userLocation": "US",
    }
    assert response.success is True
    assert [r.url for r in response.results] == [
        "https://redliontavern.net/",
        "https://example.com/",
    ]
    assert "2366 Glendale Blvd" in response.results[0].snippet


def test_exa_search_without_key_or_on_error_fails_softly() -> None:
    assert exa_search("", query="x").success is False
    with patch("agate_utils.search.requests.post", side_effect=OSError("boom")):
        out = exa_search("exa-key", query="x")
    assert out.success is False
    assert "boom" in (out.error or "")
