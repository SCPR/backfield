"""Catalog per-token prices fill in cost when LiteLLM cannot price a route."""

from __future__ import annotations

from decimal import Decimal

from backfield_ai.completion import LiteLLMCompletionResult
from backfield_ai.constants import (
    COST_ESTIMATE_SOURCE_CATALOG_PRICE,
    COST_ESTIMATE_SOURCE_LITELLM,
)
from backfield_ai.cost_estimate import apply_catalog_token_prices

ARN = "arn:aws:bedrock:us-west-2:123456789012:application-inference-profile/abc123"


def _result(*, cost: Decimal | None, pt: int | None = 1000, ct: int | None = 200):
    return LiteLLMCompletionResult(
        text="{}",
        provider="bedrock",
        provider_model_id=ARN,
        prompt_tokens=pt,
        completion_tokens=ct,
        total_tokens=None if pt is None and ct is None else (pt or 0) + (ct or 0),
        estimated_cost=cost,
        currency="USD",
        cost_estimate_incomplete=cost is None,
        cost_estimate_source=COST_ESTIMATE_SOURCE_LITELLM,
        latency_ms=10,
    )


IN = Decimal("0.000002")
OUT = Decimal("0.00001")


def test_prices_unpriced_call_from_catalog() -> None:
    out = apply_catalog_token_prices(_result(cost=None), input_price=IN, output_price=OUT)
    assert out.estimated_cost == Decimal("0.004")  # 1000*2e-6 + 200*1e-5
    assert out.cost_estimate_incomplete is False
    assert out.cost_estimate_source == COST_ESTIMATE_SOURCE_CATALOG_PRICE


def test_zero_litellm_cost_with_usage_is_repriced() -> None:
    out = apply_catalog_token_prices(_result(cost=Decimal(0)), input_price=IN, output_price=OUT)
    assert out.estimated_cost == Decimal("0.004")


def test_positive_litellm_cost_is_kept() -> None:
    original = _result(cost=Decimal("0.5"))
    assert apply_catalog_token_prices(original, input_price=IN, output_price=OUT) is original


def test_no_catalog_prices_leaves_result_unchanged() -> None:
    original = _result(cost=None)
    assert apply_catalog_token_prices(original, input_price=None, output_price=None) is original


def test_missing_output_price_is_marked_incomplete() -> None:
    out = apply_catalog_token_prices(_result(cost=None), input_price=IN, output_price=None)
    assert out.estimated_cost == Decimal("0.002")
    assert out.cost_estimate_incomplete is True


def test_no_usage_leaves_result_unchanged() -> None:
    original = _result(cost=None, pt=None, ct=None)
    assert apply_catalog_token_prices(original, input_price=IN, output_price=OUT) is original
