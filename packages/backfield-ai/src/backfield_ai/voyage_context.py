"""Voyage contextualized chunk embeddings (``voyage-context-*``) over plain HTTP.

LiteLLM only speaks Voyage's ``/v1/embeddings`` endpoint. Context models live on
``/v1/contextualizedembeddings``, which embeds each chunk with the rest of its document in
view and can split documents itself (``enable_auto_chunking``), returning each chunk's text
with its vector. Search queries go to the same endpoint as one-element documents with
``input_type="query"``.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx

VOYAGE_CONTEXT_PATH = "/v1/contextualizedembeddings"
VOYAGE_DEFAULT_API_BASE = "https://api.voyageai.com"
VOYAGE_CONTEXT_MODEL_PREFIX = "voyage-context-"

# Documented per-request limits: 1,000 inputs, 120K tokens with auto-chunking, 16K chunks.
MAX_INPUTS_PER_REQUEST = 1000
MAX_TOKENS_PER_REQUEST = 120_000
# Batch on a conservative character estimate (about three characters per token for news
# copy) so a request never trips the token limit; Voyage counts the real tokens.
CHARS_PER_TOKEN_ESTIMATE = 3
BATCH_TOKEN_BUDGET = 90_000
# One document can't exceed the request budget; longer articles are cut (rare for news).
MAX_DOCUMENT_CHARS = BATCH_TOKEN_BUDGET * CHARS_PER_TOKEN_ESTIMATE

_RETRY_STATUS = {429, 500, 502, 503, 504}


class VoyageContextError(RuntimeError):
    """The contextualized embeddings call failed or returned an unexpected shape."""


def voyage_context_model_name(litellm_model: str) -> str | None:
    """``voyage/voyage-context-4`` -> ``voyage-context-4``; None for any other model."""
    lm = (litellm_model or "").strip()
    provider, _, rest = lm.partition("/")
    if provider.lower() != "voyage" or not rest.startswith(VOYAGE_CONTEXT_MODEL_PREFIX):
        return None
    return rest


def is_voyage_context_model(litellm_model: str) -> bool:
    return voyage_context_model_name(litellm_model) is not None


@dataclass(frozen=True)
class ContextChunk:
    text: str | None
    vector: list[float]


@dataclass(frozen=True)
class ContextEmbedResponse:
    documents: list[list[ContextChunk]]
    total_tokens: int | None
    latency_ms: int


def _endpoint(api_base: str | None) -> str:
    base = (api_base or "").strip().rstrip("/") or VOYAGE_DEFAULT_API_BASE
    if base.endswith("/v1"):
        base = base[: -len("/v1")]
    return base + VOYAGE_CONTEXT_PATH


def _parse_response(payload: Any, *, expected_documents: int) -> list[list[ContextChunk]]:
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list) or len(data) != expected_documents:
        raise VoyageContextError(
            f"Voyage returned {len(data) if isinstance(data, list) else 'no'} results for "
            f"{expected_documents} input(s)."
        )
    documents: list[list[ContextChunk]] = [[] for _ in range(expected_documents)]
    for pos, doc in enumerate(data):
        doc_index = doc.get("index", pos) if isinstance(doc, dict) else pos
        chunks = doc.get("data") if isinstance(doc, dict) else None
        if not isinstance(chunks, list) or not chunks:
            raise VoyageContextError(f"Voyage result {doc_index} has no chunk embeddings.")
        ordered = sorted(chunks, key=lambda c: int(c.get("index", 0)))
        out: list[ContextChunk] = []
        for chunk in ordered:
            vec = chunk.get("embedding")
            if not isinstance(vec, list) or not vec:
                raise VoyageContextError(f"Voyage result {doc_index} has an empty embedding.")
            text = chunk.get("text")
            out.append(
                ContextChunk(
                    text=text if isinstance(text, str) else None,
                    vector=[float(x) for x in vec],
                )
            )
        documents[int(doc_index)] = out
    return documents


def contextualized_embed(
    *,
    api_key: str,
    model: str,
    inputs: list[str] | list[list[str]],
    input_type: str | None,
    output_dimension: int | None = None,
    auto_chunk: bool = False,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    api_base: str | None = None,
    timeout: float = 120.0,
    max_attempts: int = 4,
    client: httpx.Client | None = None,
) -> ContextEmbedResponse:
    """One ``/v1/contextualizedembeddings`` request, retrying rate limits and 5xx.

    With ``auto_chunk`` the inputs are whole documents (strings) and ``input_type`` must be
    ``document``; otherwise each input is a list of chunks (a query is ``[[query]]``).
    """
    if not inputs:
        raise VoyageContextError("At least one input is required.")
    if len(inputs) > MAX_INPUTS_PER_REQUEST:
        raise VoyageContextError(f"At most {MAX_INPUTS_PER_REQUEST} inputs per request.")
    body: dict[str, Any] = {"inputs": inputs, "model": model, "input_type": input_type}
    if output_dimension:
        body["output_dimension"] = int(output_dimension)
    if auto_chunk:
        if input_type != "document":
            raise VoyageContextError('Auto-chunking requires input_type="document".')
        body["enable_auto_chunking"] = True
        if chunk_size:
            body["chunk_size"] = int(chunk_size)
        if chunk_overlap:
            body["chunk_overlap"] = int(chunk_overlap)

    headers = {"Authorization": f"Bearer {api_key}", "content-type": "application/json"}
    url = _endpoint(api_base)
    owned = client is None
    http = client or httpx.Client(timeout=timeout)
    t0 = time.perf_counter()
    try:
        last_error = ""
        for attempt in range(1, max_attempts + 1):
            try:
                resp = http.post(url, json=body, headers=headers, timeout=timeout)
            except httpx.HTTPError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            else:
                if resp.status_code == 200:
                    payload = resp.json()
                    usage = payload.get("usage") if isinstance(payload, dict) else None
                    tokens = usage.get("total_tokens") if isinstance(usage, dict) else None
                    return ContextEmbedResponse(
                        documents=_parse_response(payload, expected_documents=len(inputs)),
                        total_tokens=int(tokens) if tokens is not None else None,
                        latency_ms=int((time.perf_counter() - t0) * 1000),
                    )
                detail = resp.text[:500]
                last_error = f"HTTP {resp.status_code}: {detail}"
                if resp.status_code not in _RETRY_STATUS:
                    break
            if attempt < max_attempts:
                time.sleep(min(2 ** attempt, 20))
        raise VoyageContextError(f"Voyage contextualized embeddings failed: {last_error}")
    finally:
        if owned:
            http.close()


def estimated_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN_ESTIMATE)


def document_batches(
    documents: list[str],
    *,
    token_budget: int = BATCH_TOKEN_BUDGET,
    max_inputs: int = MAX_INPUTS_PER_REQUEST,
) -> Iterator[list[int]]:
    """Yield index batches whose estimated tokens fit one auto-chunking request."""
    batch: list[int] = []
    used = 0
    for i, doc in enumerate(documents):
        cost = estimated_tokens(doc)
        if batch and (used + cost > token_budget or len(batch) >= max_inputs):
            yield batch
            batch, used = [], 0
        batch.append(i)
        used += cost
    if batch:
        yield batch


def voyage_token_cost(litellm_model: str, tokens: int | None) -> Decimal | None:
    """Price ``tokens`` with LiteLLM's model cost map (None when the model isn't listed)."""
    if tokens is None:
        return None
    import litellm

    entry = litellm.model_cost.get(litellm_model) or litellm.model_cost.get(
        litellm_model.partition("/")[2]
    )
    if not isinstance(entry, dict) or entry.get("input_cost_per_token") is None:
        return None
    return Decimal(str(entry["input_cost_per_token"])) * Decimal(int(tokens))
