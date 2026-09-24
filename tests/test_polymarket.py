import asyncio
import copy
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from eventtrader.market_data.polymarket import PolymarketReadOnlyClient, normalize_market
from eventtrader.market_data.provider import (
    InvalidResponse,
    MarketNotFound,
    ProviderUnavailable,
    RateLimited,
)
from eventtrader.settings import Settings


def test_contract_pagination_details_books_constraints(gamma_payload, book_payload):
    requests = []
    second = copy.deepcopy(gamma_payload)
    second["id"] = "703258"

    def handler(request):
        requests.append(request)
        assert request.method == "GET"
        assert "authorization" not in request.headers
        assert not any(key.startswith("poly_") for key in request.headers)
        assert request.headers["x-request-id"]
        if request.url.path == "/markets/keyset":
            if request.url.params.get("after_cursor") == "page2":
                return httpx.Response(200, json={"markets": [second]})
            return httpx.Response(200, json={"markets": [gamma_payload], "next_cursor": "page2"})
        if request.url.path.startswith("/markets/"):
            return httpx.Response(200, json=gamma_payload)
        assert request.url.path == "/book"
        assert request.url.params["token_id"] == book_payload["asset_id"]
        return httpx.Response(200, json=book_payload)

    async def run():
        async with PolymarketReadOnlyClient(
            Settings(provider_page_size=1), transport=httpx.MockTransport(handler)
        ) as client:
            markets = await client.discover_markets(2)
            assert [market.external_market_id for market in markets] == ["703257", "703258"]
            assert await client.get_market_details("703257")
            assert await client.get_market_details(gamma_payload["slug"], by_slug=True)
            book = await client.get_orderbook(book_payload["asset_id"])
            assert book.best_bid == Decimal("0.03")
            assert book.best_ask == Decimal("0.97")
            constraints = await client.get_market_constraints(markets[0], book)
            assert constraints.tick_size == Decimal("0.01")
            assert constraints.minimum_order_size == 5
            assert constraints.fee_schedule.rate == Decimal("0.04")
            assert book.provider_timestamp.tzinfo is not None

    asyncio.run(run())
    assert len(requests) == 5


@pytest.mark.parametrize(
    "status,error",
    [(404, MarketNotFound), (429, RateLimited), (503, ProviderUnavailable), (403, InvalidResponse)],
)
def test_normalized_errors_and_bounded_retries(status, error):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, text="secret-sentinel")

    async def run():
        async with PolymarketReadOnlyClient(
            Settings(provider_max_retries=2), transport=httpx.MockTransport(handler)
        ) as client:
            with pytest.raises(error) as raised:
                await client.get_market_details("703257")
            assert "secret-sentinel" not in str(raised.value)

    with patch("eventtrader.market_data.polymarket.asyncio.sleep", new_callable=AsyncMock) as sleep:
        asyncio.run(run())
    assert len(calls) == (3 if status in (429, 503) else 1)
    assert len({request.headers["x-request-id"] for request in calls}) == 1
    if len(calls) == 3:
        assert [call.args[0] for call in sleep.call_args_list] == [0.5, 1.0]


def test_retry_after_and_recovery(gamma_payload):
    responses = [
        httpx.Response(429, headers={"Retry-After": "2"}),
        httpx.Response(200, json=gamma_payload),
    ]

    async def run():
        async with PolymarketReadOnlyClient(
            Settings(), transport=httpx.MockTransport(lambda _: responses.pop(0))
        ) as client:
            return await client.get_market_details("703257")

    with patch("eventtrader.market_data.polymarket.asyncio.sleep", new_callable=AsyncMock) as sleep:
        assert asyncio.run(run()).external_market_id == "703257"
        sleep.assert_awaited_once_with(2.0)


def test_long_retry_after_fails_without_early_retry():
    async def run():
        async with PolymarketReadOnlyClient(
            Settings(),
            transport=httpx.MockTransport(
                lambda _: httpx.Response(429, headers={"Retry-After": "120"})
            ),
        ) as client:
            with pytest.raises(RateLimited):
                await client.get_market_details("703257")

    with patch("eventtrader.market_data.polymarket.asyncio.sleep", new_callable=AsyncMock) as sleep:
        asyncio.run(run())
        sleep.assert_not_called()


def test_transport_timeout():
    def handler(request):
        raise httpx.ReadTimeout("secret-sentinel", request=request)

    async def run():
        async with PolymarketReadOnlyClient(
            Settings(provider_max_retries=0), transport=httpx.MockTransport(handler)
        ) as client:
            with pytest.raises(ProviderUnavailable, match="provider_transport_error"):
                await client.get_market_details("703257")

    asyncio.run(run())


@pytest.mark.parametrize(
    "change",
    [
        {"outcomes": "bad-json"},
        {"clobTokenIds": '["1"]'},
        {"clobTokenIds": '["1","1"]'},
        {"volume": "NaN"},
        {"endDate": "2027-01-01T00:00:00"},
    ],
)
def test_invalid_markets_are_rejected(gamma_payload, change):
    gamma_payload.update(change)
    with pytest.raises(InvalidResponse):
        normalize_market(gamma_payload, "test-request")


def test_unknown_fields_and_missing_metadata(gamma_payload):
    gamma_payload["futureField"] = "ignored"
    market = normalize_market(gamma_payload, "test")
    assert market.category is None
    assert market.resolved_at is None
    assert market.liquidity is None
    assert len(market.outcomes) == 2


def test_repeated_cursor_fails(gamma_payload):
    async def run():
        transport = httpx.MockTransport(
            lambda _: httpx.Response(200, json={"markets": [gamma_payload], "next_cursor": "same"})
        )
        async with PolymarketReadOnlyClient(
            Settings(provider_page_size=1), transport=transport
        ) as client:
            with pytest.raises(InvalidResponse, match="pagination_not_advancing"):
                await client.discover_markets(3)

    asyncio.run(run())


@pytest.mark.parametrize(
    "change",
    [
        {"asset_id": "123"},
        {"bids": [{"price": "1.1", "size": "1"}]},
        {"bids": [{"price": "0.99", "size": "1"}]},
    ],
)
def test_invalid_books(book_payload, change):
    token_id = book_payload["asset_id"]
    book_payload.update(change)

    async def run():
        async with PolymarketReadOnlyClient(
            Settings(),
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=book_payload)),
        ) as client:
            with pytest.raises(InvalidResponse):
                await client.get_orderbook(token_id)

    asyncio.run(run())


def test_empty_book_is_not_a_zero_price(book_payload):
    book_payload.update(bids=[], asks=[])

    async def run():
        async with PolymarketReadOnlyClient(
            Settings(),
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=book_payload)),
        ) as client:
            book = await client.get_orderbook(book_payload["asset_id"])
            assert book.best_bid is None and book.best_ask is None

    asyncio.run(run())


def test_invalid_json_is_not_retried():
    async def run():
        async with PolymarketReadOnlyClient(
            Settings(),
            transport=httpx.MockTransport(lambda _: httpx.Response(200, text="not json")),
        ) as client:
            with pytest.raises(InvalidResponse, match="invalid_json"):
                await client.get_market_details("703257")

    asyncio.run(run())


def test_resolution_contract_accepts_only_unambiguous_final_payout():
    condition_id = "0xresolved"

    def handler(request):
        assert request.url.path == "/v2/resolutions"
        assert dict(request.url.params) == {"condition": condition_id}
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "condition_id": condition_id,
                        "status": "resolved",
                        "payouts": ["1", "0"],
                        "resolved_at": "2026-09-24T00:00:00Z",
                        "resolution_source": "https://example.org/final",
                    }
                ]
            },
        )

    async def run():
        async with PolymarketReadOnlyClient(
            Settings(), transport=httpx.MockTransport(handler)
        ) as client:
            resolution = await client.get_resolution(condition_id, 2)
            assert resolution is not None
            assert resolution.payouts == [Decimal("1"), Decimal("0")]
            assert resolution.source == "https://example.org/final"

    asyncio.run(run())


@pytest.mark.parametrize("payouts", [["0.5", "0.5"], ["1", "1"], ["1"]])
def test_resolution_contract_abstains_on_ambiguous_payout(payouts):
    condition_id = "0xambiguous"
    payload = {
        "data": [
            {
                "condition_id": condition_id,
                "status": "resolved",
                "payouts": payouts,
                "resolved_at": "2026-09-24T00:00:00Z",
            }
        ]
    }

    async def run():
        async with PolymarketReadOnlyClient(
            Settings(),
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)),
        ) as client:
            assert await client.get_resolution(condition_id, 2) is None

    asyncio.run(run())
