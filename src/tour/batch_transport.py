"""Batch API transport for the durable certification workflow.

Wraps the Anthropic Message Batches endpoint for 50% cost reduction on
certification compose and review calls. The synchronous certification
provider (certification_provider.py) remains the authority for the
receipt shape and response parsing; this module handles only submission,
polling, and result mapping.

Never edit tour_batch_candidate.py — its own SHA is sealed into plans.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .certification_provider import PhysicalProviderResponse, _response_text, _usage


@dataclass(frozen=True)
class BatchUnitResult:
    """One unit's outcome from a batch, before mapping into the certification receipt."""
    custom_id: str
    result_type: str  # "succeeded" | "errored" | "canceled" | "expired"
    response: PhysicalProviderResponse | None  # None for non-succeeded
    batch_id: str
    error_message: str | None = None


def batch_client() -> Any:
    import anthropic

    return anthropic.Anthropic(max_retries=2)


def submit_batch(
    requests: list[tuple[str, Mapping[str, object]]],
    *,
    client: object | None = None,
) -> Any:
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    if client is None:
        client = batch_client()
    batch_requests = [
        Request(
            custom_id=custom_id,
            params=MessageCreateParamsNonStreaming(**dict(sdk_request)),
        )
        for custom_id, sdk_request in requests
    ]
    return client.messages.batches.create(requests=batch_requests)


def poll_batch(
    batch_id: str,
    *,
    client: object | None = None,
    poll_interval_s: float = 10,
    max_poll_s: float = 3600,
) -> Any:
    if client is None:
        client = batch_client()
    deadline = time.monotonic() + max_poll_s
    while True:
        batch = client.messages.batches.retrieve(batch_id)
        if batch.processing_status == "ended":
            return batch
        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"batch {batch_id} did not reach 'ended' within {max_poll_s}s; "
                f"last processing_status was {batch.processing_status!r}"
            )
        time.sleep(poll_interval_s)


def collect_results(
    batch_id: str,
    *,
    client: object | None = None,
) -> dict[str, BatchUnitResult]:
    if client is None:
        client = batch_client()
    collected: dict[str, BatchUnitResult] = {}
    for individual in client.messages.batches.results(batch_id):
        outcome = individual.result
        if outcome.type == "succeeded":
            message = outcome.message
            text = _response_text(message)
            input_tokens, output_tokens, cache_creation, cache_read = _usage(message)
            response = PhysicalProviderResponse(
                body=text.encode("utf-8"),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=0,
                model=message.model,
                provider_request_id=message.id,
                stop_reason=message.stop_reason,
                cache_creation_input_tokens=cache_creation,
                cache_read_input_tokens=cache_read,
            )
            collected[individual.custom_id] = BatchUnitResult(
                custom_id=individual.custom_id,
                result_type=outcome.type,
                response=response,
                batch_id=batch_id,
                error_message=None,
            )
            continue
        error_message: str | None = None
        if outcome.type == "errored":
            error_message = f"{outcome.error.error.type}: {outcome.error.error.message}"
        collected[individual.custom_id] = BatchUnitResult(
            custom_id=individual.custom_id,
            result_type=outcome.type,
            response=None,
            batch_id=batch_id,
            error_message=error_message,
        )
    return collected


__all__ = [
    "BatchUnitResult",
    "batch_client",
    "collect_results",
    "poll_batch",
    "submit_batch",
]
