"""Backend-only Gemini REST client with bounded retries and strict JSON parsing."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any, Literal

import httpx

GEMINI_API_ROOT = "https://generativelanguage.googleapis.com"


class GeminiProviderError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 502,
        retryable: bool = False,
    ) -> None:
        self.status_code = status_code
        self.retryable = retryable
        super().__init__(message)


class GeminiClient:
    """Small synchronous client that never places the API key in a URL."""

    def __init__(
        self,
        *,
        api_key: str,
        generation_model: str = "gemini-3.5-flash-lite",
        embedding_model: str = "gemini-embedding-2",
        embedding_dimensions: int = 384,
        timeout_seconds: float = 45.0,
        max_retries: int = 3,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key.strip():
            raise ValueError("A Gemini API key is required")
        if not 128 <= embedding_dimensions <= 3072:
            raise ValueError("Gemini embedding dimensions must be between 128 and 3072")
        self.generation_model = generation_model
        self.embedding_model = embedding_model
        self.embedding_dimensions = embedding_dimensions
        self._max_retries = max_retries
        self._sleep = sleep
        self._client = httpx.Client(
            base_url=GEMINI_API_ROOT,
            headers={
                "x-goog-api-key": api_key,
                "Content-Type": "application/json",
            },
            timeout=timeout_seconds,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> GeminiClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
            if isinstance(payload, dict):
                error = payload.get("error")
                if isinstance(error, dict) and error.get("message"):
                    return str(error["message"])
        except ValueError:
            pass
        return f"Gemini request failed with HTTP {response.status_code}"

    def _post(self, path: str, payload: dict[str, object]) -> dict[str, Any]:
        last_error: GeminiProviderError | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.post(path, json=payload)
            except httpx.RequestError as exc:
                last_error = GeminiProviderError(
                    "Gemini could not be reached.",
                    retryable=True,
                )
                if attempt >= self._max_retries:
                    raise last_error from exc
            else:
                if not response.is_error:
                    parsed = response.json()
                    if not isinstance(parsed, dict):
                        raise GeminiProviderError("Gemini returned an invalid response.")
                    return parsed
                retryable = response.status_code == 429 or response.status_code >= 500
                last_error = GeminiProviderError(
                    self._error_message(response),
                    status_code=response.status_code,
                    retryable=retryable,
                )
                if not retryable or attempt >= self._max_retries:
                    raise last_error
            self._sleep(min(8.0, 0.5 * (2**attempt)))
        raise last_error or GeminiProviderError("Gemini request failed.")

    def generate_json(
        self,
        *,
        system_instruction: str,
        prompt: str,
        response_schema: dict[str, object],
    ) -> dict[str, Any]:
        payload = self._post(
            f"/v1beta/models/{self.generation_model}:generateContent",
            {
                "systemInstruction": {"parts": [{"text": system_instruction}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseJsonSchema": response_schema,
                },
            },
        )
        try:
            parts = payload["candidates"][0]["content"]["parts"]
            text = "".join(
                str(part.get("text", ""))
                for part in parts
                if isinstance(part, dict)
            )
            parsed = json.loads(text)
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise GeminiProviderError("Gemini returned malformed structured output.") from exc
        if not isinstance(parsed, dict):
            raise GeminiProviderError("Gemini structured output must be a JSON object.")
        return parsed

    def embed(
        self,
        text: str,
        *,
        task_type: Literal["RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"],
    ) -> list[float]:
        if not text.strip():
            raise ValueError("Embedding input cannot be empty")
        payload = self._post(
            f"/v1beta/models/{self.embedding_model}:embedContent",
            {
                "model": f"models/{self.embedding_model}",
                "content": {"parts": [{"text": text}]},
                "taskType": task_type,
                "outputDimensionality": self.embedding_dimensions,
            },
        )
        try:
            values = payload["embedding"]["values"]
            vector = [float(value) for value in values]
        except (KeyError, TypeError, ValueError) as exc:
            raise GeminiProviderError("Gemini returned an invalid embedding.") from exc
        if len(vector) != self.embedding_dimensions:
            raise GeminiProviderError(
                f"Expected {self.embedding_dimensions} embedding values, got {len(vector)}."
            )
        return vector
