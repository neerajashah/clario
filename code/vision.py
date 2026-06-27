"""Gemini vision wrapper for structured claim-review calls (google-genai SDK)."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from PIL import Image

from data_loader import ClaimRecord, EvidenceRequirement, UserHistoryRecord
from prompts import (
    SINGLE_CALL_SCHEMA,
    build_single_call_prompt,
    get_system_instruction,
)

DEFAULT_MODEL = "gemini-2.5-flash"
ACCEPTED_FINISH_REASONS = {
    "STOP",
    "MAX_TOKENS",
    "FINISH_REASON_UNSPECIFIED",
    "",
}


class VisionAPIError(RuntimeError):
    """Raised when Gemini returns an unusable or blocked response."""


@dataclass
class UsageStats:
    model_calls: int = 0
    images_sent: int = 0
    prompt_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    retries: int = 0

    def record_response(self, response: Any, images_sent: int = 0) -> None:
        self.model_calls += 1
        self.images_sent += images_sent
        usage = getattr(response, "usage_metadata", None)
        if usage is None:
            return
        prompt = int(getattr(usage, "prompt_token_count", 0) or 0)
        output = int(getattr(usage, "candidates_token_count", 0) or 0)
        total = int(getattr(usage, "total_token_count", 0) or 0)
        self.prompt_tokens += prompt
        self.output_tokens += output
        self.total_tokens += total or (prompt + output)


@dataclass
class GeminiVisionClient:
    """Call Gemini once per claim with all images and return structured JSON."""

    api_key: str | None = None
    model_name: str = DEFAULT_MODEL
    temperature: float = 0.1
    max_retries: int = 4
    base_retry_delay: float = 2.0
    repo_root: Path | None = None
    stats: UsageStats = field(default_factory=UsageStats)
    _client: Any = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        key = self.api_key or os.getenv("GEMINI_API_KEY")
        if not key:
            raise ValueError("GEMINI_API_KEY is not set")
        self.api_key = key
        self.model_name = self.model_name or os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
        self._client = genai.Client(api_key=self.api_key)

    @classmethod
    def from_env(cls, env_path: Path | str | None = None, **kwargs: Any) -> GeminiVisionClient:
        if env_path is not None:
            load_dotenv(env_path)
        else:
            load_dotenv()
        model_name = kwargs.pop("model_name", None) or os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
        return cls(
            api_key=os.getenv("GEMINI_API_KEY"),
            model_name=model_name,
            **kwargs,
        )

    def review_claim(
        self,
        claim: ClaimRecord,
        requirements: list[EvidenceRequirement],
        history: UserHistoryRecord | None,
    ) -> dict[str, Any]:
        """Single API call: all images + context → complete verdict JSON."""
        prompt = build_single_call_prompt(claim, requirements, history)
        images = load_claim_images(claim)
        return self.generate_json(prompt, SINGLE_CALL_SCHEMA, images=images)

    def generate_json(
        self,
        prompt: str,
        schema: dict[str, Any],
        images: list[Image.Image] | None = None,
    ) -> dict[str, Any]:
        images = images or []
        contents: list[Any] = [prompt, *images]
        response = self._generate_with_retry(contents, schema)
        self.stats.record_response(response, images_sent=len(images))
        text = _response_text(response)
        return parse_json_response(text)

    def _generate_with_retry(self, contents: list[Any], schema: dict[str, Any]) -> Any:
        last_error: Exception | None = None
        config = types.GenerateContentConfig(
            system_instruction=get_system_instruction(),
            temperature=self.temperature,
            response_mime_type="application/json",
            response_json_schema=schema,
        )
        for attempt in range(self.max_retries + 1):
            try:
                return self._client.models.generate_content(
                    model=self.model_name,
                    contents=contents,
                    config=config,
                )
            except (genai_errors.ClientError, genai_errors.ServerError) as exc:
                last_error = exc
                if not _is_retryable(exc) or attempt >= self.max_retries:
                    break
                self.stats.retries += 1
                delay = _retry_delay_seconds(exc, attempt, self.base_retry_delay)
                time.sleep(delay)
        raise VisionAPIError(
            f"Gemini request failed after {self.max_retries + 1} attempts: {last_error}"
        ) from last_error


def load_image(path: Path | str) -> Image.Image:
    image_path = Path(path)
    if not image_path.is_file():
        raise FileNotFoundError(f"Image not found: {image_path}")
    with Image.open(image_path) as img:
        return img.convert("RGB")


def load_claim_images(claim: ClaimRecord) -> list[Image.Image]:
    images: list[Image.Image] = []
    for image_ref in claim.images:
        if image_ref.exists:
            images.append(load_image(image_ref.absolute_path))
    return images


def parse_json_response(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise VisionAPIError(f"Model returned invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise VisionAPIError("Model JSON response must be an object")
    return parsed


def _response_text(response: Any) -> str:
    if not getattr(response, "candidates", None):
        raise VisionAPIError("Gemini returned no candidates")
    candidate = response.candidates[0]
    finish_reason = getattr(candidate, "finish_reason", None)
    if finish_reason is not None:
        reason_value = str(getattr(finish_reason, "value", finish_reason)).upper()
        if reason_value not in ACCEPTED_FINISH_REASONS:
            raise VisionAPIError(f"Gemini stopped early: finish_reason={finish_reason}")
    text = getattr(response, "text", None)
    if not text:
        raise VisionAPIError("Gemini response contained no text")
    return text


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, genai_errors.ServerError):
        return True
    if isinstance(exc, genai_errors.ClientError):
        code = getattr(exc, "code", None)
        return code in {408, 429}
    return False


def _retry_delay_seconds(exc: Exception, attempt: int, base_delay: float) -> float:
    match = re.search(r"Please retry in ([\d.]+)s", str(exc))
    if match:
        return max(float(match.group(1)), base_delay)
    retry_delay = getattr(exc, "retry_delay", None)
    if retry_delay is not None:
        seconds = getattr(retry_delay, "seconds", None)
        if seconds is not None:
            return max(float(seconds), base_delay)
    return base_delay * (2**attempt)


if __name__ == "__main__":
    from data_loader import find_repo_root, load_claims, load_user_history, requirements_for_claim

    root = find_repo_root()
    claim = load_claims(repo_root=root)[0]
    history = load_user_history(repo_root=root).get(claim.user_id)
    requirements = requirements_for_claim(claim.claim_object, repo_root=root)

    print("=== Local checks (no API) ===")
    images = load_claim_images(claim)
    print(f"loaded {len(images)} image(s) for claim")
    sample = parse_json_response('{"ok": true, "value": 1}')
    print(f"json parse: {sample}")

    if not os.getenv("GEMINI_API_KEY"):
        load_dotenv(root / ".env")

    if os.getenv("GEMINI_API_KEY"):
        model_name = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
        print(f"\n=== Live single-call review (model={model_name}) ===")
        client = GeminiVisionClient.from_env(root / ".env")
        try:
            verdict = client.review_claim(claim, requirements, history)
            print(json.dumps(verdict, indent=2)[:800], "...")
            print(
                f"stats: calls={client.stats.model_calls}, "
                f"images={client.stats.images_sent}, "
                f"retries={client.stats.retries}, "
                f"tokens={client.stats.total_tokens}"
            )
        except VisionAPIError as exc:
            print(f"Live API skipped/failed: {exc}")
    else:
        print("\nGEMINI_API_KEY not set; skipped live API test.")
