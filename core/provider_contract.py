"""Shared result/error contract for provider adapters."""
from dataclasses import dataclass

@dataclass(frozen=True)
class ModelResponse:
    text: str
    latency_seconds: float
    input_tokens: int | None
    output_tokens: int | None
    thought_tokens: int | None
    cost_credits: float | None = None
    response_id: str | None = None
    returned_model: str | None = None
    upstream_provider: str | None = None

class ProviderError(RuntimeError):
    def __init__(self, code: int, message: str):
        self.code = code
        super().__init__(message)
