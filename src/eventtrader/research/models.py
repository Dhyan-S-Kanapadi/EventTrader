"""Explicit model routing with metered deterministic mock and LiteLLM adapters."""

import json
import time
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError


@dataclass(frozen=True)
class ModelCall:
    value: BaseModel | None
    provider: str
    model_name: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    estimated_cost_usd: Decimal
    success: bool
    error_code: str | None = None
    prior_attempts: tuple["ModelCall", ...] = ()


class StructuredModelProvider(Protocol):
    async def call(
        self,
        *,
        role: str,
        model_name: str,
        fallback_model: str,
        schema: type[BaseModel],
        system: str,
        user: str,
        expected_cost_usd: Decimal,
        timeout: float,
    ) -> ModelCall: ...


class DisabledModelProvider:
    async def call(self, **kwargs: Any) -> ModelCall:
        return ModelCall(
            value=None,
            provider="none",
            model_name=str(kwargs.get("model_name", "")),
            input_tokens=0,
            output_tokens=0,
            latency_ms=0,
            estimated_cost_usd=Decimal("0"),
            success=False,
            error_code="RESEARCH_UNAVAILABLE",
        )


class MockModelProvider:
    """Deterministic no-key development provider; responses must be supplied by tests/app."""

    def __init__(self, responses: dict[str, dict[str, object]]):
        self.responses = responses
        self.calls: list[str] = []

    async def call(
        self,
        *,
        role: str,
        model_name: str,
        fallback_model: str,
        schema: type[BaseModel],
        system: str,
        user: str,
        expected_cost_usd: Decimal,
        timeout: float,
    ) -> ModelCall:
        del fallback_model, system, timeout
        self.calls.append(role)
        started = time.perf_counter()
        try:
            value = schema.model_validate(self.responses[role])
        except (KeyError, ValidationError):
            return ModelCall(
                value=None,
                provider="mock",
                model_name=model_name or f"mock-{role}",
                input_tokens=len(user.split()),
                output_tokens=0,
                latency_ms=int((time.perf_counter() - started) * 1000),
                estimated_cost_usd=expected_cost_usd,
                success=False,
                error_code="INVALID_MODEL_RESPONSE",
            )
        return ModelCall(
            value=value,
            provider="mock",
            model_name=model_name or f"mock-{role}",
            input_tokens=len(user.split()),
            output_tokens=len(value.model_dump_json().split()),
            latency_ms=int((time.perf_counter() - started) * 1000),
            estimated_cost_usd=expected_cost_usd,
            success=True,
        )


class LiteLLMModelProvider:
    async def call(
        self,
        *,
        role: str,
        model_name: str,
        fallback_model: str,
        schema: type[BaseModel],
        system: str,
        user: str,
        expected_cost_usd: Decimal,
        timeout: float,
    ) -> ModelCall:
        if not model_name:
            return ModelCall(
                None, "litellm", "", 0, 0, 0, Decimal("0"), False, "MODEL_NOT_CONFIGURED"
            )
        first = await self._attempt(
            role, model_name, schema, system, user, expected_cost_usd, timeout
        )
        # Invalid structured output is a completed provider response, not a provider failure.
        if first.success or first.error_code == "INVALID_MODEL_RESPONSE" or not fallback_model:
            return first
        fallback = await self._attempt(
            role, fallback_model, schema, system, user, expected_cost_usd, timeout
        )
        return replace(fallback, prior_attempts=(first, *fallback.prior_attempts))

    async def _attempt(
        self,
        role: str,
        model_name: str,
        schema: type[BaseModel],
        system: str,
        user: str,
        expected_cost_usd: Decimal,
        timeout: float,
    ) -> ModelCall:
        del role
        import litellm

        started = time.perf_counter()
        try:
            response = await litellm.acompletion(
                model=model_name,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0,
                timeout=timeout,
            )
        except Exception as exc:
            error_code = type(exc).__name__.upper()[:64]
            return ModelCall(
                None,
                "litellm",
                model_name,
                0,
                0,
                int((time.perf_counter() - started) * 1000),
                Decimal("0"),
                False,
                error_code,
            )
        usage = response.usage
        content = response.choices[0].message.content or ""
        try:
            payload = json.loads(content)
            value = schema.model_validate(payload)
        except (json.JSONDecodeError, ValidationError, TypeError):
            return ModelCall(
                None,
                "litellm",
                model_name,
                int(usage.prompt_tokens or 0),
                int(usage.completion_tokens or 0),
                int((time.perf_counter() - started) * 1000),
                expected_cost_usd,
                False,
                "INVALID_MODEL_RESPONSE",
            )
        hidden = getattr(response, "_hidden_params", {}) or {}
        cost = Decimal(str(hidden.get("response_cost") or expected_cost_usd))
        return ModelCall(
            value,
            "litellm",
            model_name,
            int(usage.prompt_tokens or 0),
            int(usage.completion_tokens or 0),
            int((time.perf_counter() - started) * 1000),
            cost,
            True,
        )
