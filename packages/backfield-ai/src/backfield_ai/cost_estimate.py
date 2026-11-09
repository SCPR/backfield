"""LiteLLM-based estimated cost from provider responses."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import litellm

from backfield_ai.constants import (
    COST_ESTIMATE_SOURCE_CATALOG_PRICE,
    COST_ESTIMATE_SOURCE_LITELLM,
    COST_ESTIMATE_SOURCE_UNAVAILABLE,
    DEFAULT_AI_CURRENCY,
)

if TYPE_CHECKING:
    from backfield_ai.completion import LiteLLMCompletionResult


def litellm_estimated_cost_from_response(
    resp: Any | None,
    *,
    litellm_model: str | None = None,
) -> tuple[Decimal | None, bool, str, str]:
    """Return ``(estimated_cost, cost_estimate_incomplete, cost_estimate_source, currency)``."""
    if resp is None:
        return None, True, COST_ESTIMATE_SOURCE_UNAVAILABLE, DEFAULT_AI_CURRENCY
    try:
        kwargs: dict[str, Any] = {"completion_response": resp}
        if litellm_model:
            kwargs["model"] = litellm_model
        cost_val = litellm.completion_cost(**kwargs)
        if cost_val is not None:
            return Decimal(str(cost_val)), False, COST_ESTIMATE_SOURCE_LITELLM, DEFAULT_AI_CURRENCY
    except Exception:
        pass
    return None, True, COST_ESTIMATE_SOURCE_LITELLM, DEFAULT_AI_CURRENCY


def apply_catalog_token_prices(
    result: LiteLLMCompletionResult,
    *,
    input_price: Decimal | None,
    output_price: Decimal | None,
) -> LiteLLMCompletionResult:
    """Price a call from saved per-token catalog prices when LiteLLM could not.

    LiteLLM prices by model name, so routes it does not recognize (such as a Bedrock
    application inference profile ARN) come back unpriced, or as zero despite real usage.
    When the model config carries prices and the response reported token counts, use them.
    A LiteLLM price above zero is kept as-is.
    """
    if input_price is None and output_price is None:
        return result
    if result.estimated_cost is not None and result.estimated_cost > 0:
        return result
    pt, ct = result.prompt_tokens, result.completion_tokens
    if pt is None and ct is None:
        return result
    incomplete = (pt is None or input_price is None) or (ct is None or output_price is None)
    cost = Decimal(pt or 0) * (input_price or Decimal(0)) + Decimal(ct or 0) * (
        output_price or Decimal(0)
    )
    return replace(
        result,
        estimated_cost=cost,
        cost_estimate_incomplete=incomplete,
        cost_estimate_source=COST_ESTIMATE_SOURCE_CATALOG_PRICE,
    )
