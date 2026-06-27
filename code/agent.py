"""Orchestrate single-call claim review and format output rows."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from data_loader import (
    INPUT_COLUMNS,
    ISSUE_TYPES,
    OUTPUT_COLUMNS,
    RISK_FLAGS,
    SEVERITY_LEVELS,
    ClaimRecord,
    EvidenceRequirement,
    UserHistoryRecord,
    find_repo_root,
    load_claims,
    load_evidence_requirements,
    load_user_history,
    parse_semicolon_list,
    requirements_for_claim,
)
from prompts import object_parts_for
from vision import GeminiVisionClient, VisionAPIError, UsageStats

OUTPUT_ROW_COLUMNS = INPUT_COLUMNS + OUTPUT_COLUMNS
CONFIDENCE_REVIEW_THRESHOLD = 0.65
ALLOWED_RISK_FLAGS = set(RISK_FLAGS)
ALLOWED_ISSUE_TYPES = set(ISSUE_TYPES)
ALLOWED_SEVERITIES = set(SEVERITY_LEVELS)
ALLOWED_CLAIM_STATUSES = {"supported", "contradicted", "not_enough_information"}


@dataclass
class ClaimReviewAgent:
    """Run one Gemini call per claim and normalize the response."""

    client: GeminiVisionClient
    user_history: dict[str, UserHistoryRecord]
    requirements: list[EvidenceRequirement]
    repo_root: Path

    @classmethod
    def from_env(cls, repo_root: Path | str | None = None, **client_kwargs: Any) -> ClaimReviewAgent:
        root = Path(repo_root).resolve() if repo_root else find_repo_root()
        load_dotenv(root / ".env")
        model_name = client_kwargs.pop("model_name", None) or os.getenv(
            "GEMINI_MODEL", "gemini-2.5-flash"
        )
        return cls(
            client=GeminiVisionClient.from_env(
                root / ".env",
                repo_root=root,
                model_name=model_name,
                **client_kwargs,
            ),
            user_history=load_user_history(repo_root=root),
            requirements=load_evidence_requirements(repo_root=root),
            repo_root=root,
        )

    @property
    def stats(self) -> UsageStats:
        return self.client.stats

    def review_claim(self, claim: ClaimRecord) -> dict[str, str]:
        history = self.user_history.get(claim.user_id)
        requirements = requirements_for_claim(claim.claim_object, self.requirements)

        try:
            verdict = self.client.review_claim(claim, requirements, history)
        except VisionAPIError as exc:
            verdict = fallback_verdict(
                claim,
                reason=_short_error_message(exc),
                history=history,
            )
            return format_output_row(claim, verdict)

        verdict = normalize_verdict(verdict, claim, history)
        return format_output_row(claim, verdict)

    def review_claims(self, claims: list[ClaimRecord]) -> list[dict[str, str]]:
        return [self.review_claim(claim) for claim in claims]


def review_claim(
    claim: ClaimRecord,
    agent: ClaimReviewAgent | None = None,
    repo_root: Path | str | None = None,
) -> dict[str, str]:
    reviewer = agent or ClaimReviewAgent.from_env(repo_root=repo_root)
    return reviewer.review_claim(claim)


def format_output_row(claim: ClaimRecord, verdict: dict[str, Any]) -> dict[str, str]:
    risk_flags = verdict.get("risk_flags", ["none"])
    supporting_ids = verdict.get("supporting_image_ids", [])

    return {
        "user_id": claim.user_id,
        "image_paths": claim.image_paths,
        "user_claim": claim.user_claim,
        "claim_object": claim.claim_object,
        "evidence_standard_met": format_bool(verdict.get("evidence_standard_met", False)),
        "evidence_standard_met_reason": str(
            verdict.get("evidence_standard_met_reason", "Insufficient evidence to evaluate.")
        ),
        "risk_flags": format_risk_flags(risk_flags),
        "issue_type": str(verdict.get("issue_type", "unknown")),
        "object_part": str(verdict.get("object_part", "unknown")),
        "claim_status": str(verdict.get("claim_status", "not_enough_information")),
        "claim_status_justification": str(
            verdict.get(
                "claim_status_justification",
                "Unable to determine claim status from available evidence.",
            )
        ),
        "supporting_image_ids": format_supporting_ids(supporting_ids),
        "valid_image": format_bool(verdict.get("valid_image", False)),
        "severity": str(verdict.get("severity", "unknown")),
    }


def normalize_verdict(
    verdict: dict[str, Any],
    claim: ClaimRecord,
    history: UserHistoryRecord | None,
) -> dict[str, Any]:
    allowed_parts = set(object_parts_for(claim.claim_object))
    normalized = dict(verdict)

    normalized["issue_type"] = coerce_enum(
        normalized.get("issue_type"),
        ALLOWED_ISSUE_TYPES,
        default="unknown",
    )
    normalized["object_part"] = coerce_enum(
        normalized.get("object_part"),
        allowed_parts,
        default="unknown",
    )
    normalized["severity"] = coerce_enum(
        normalized.get("severity"),
        ALLOWED_SEVERITIES,
        default="unknown",
    )
    normalized["claim_status"] = coerce_enum(
        normalized.get("claim_status"),
        ALLOWED_CLAIM_STATUSES,
        default="not_enough_information",
    )
    normalized["evidence_standard_met"] = to_bool(
        normalized.get("evidence_standard_met", False)
    )
    normalized["valid_image"] = to_bool(normalized.get("valid_image", False))
    normalized["supporting_image_ids"] = normalize_id_list(
        normalized.get("supporting_image_ids"),
        claim.image_ids,
    )

    per_image_flags = _per_image_risk_flags(normalized.get("per_image_assessments"))
    risk_flags = collect_risk_flags(
        normalized.get("risk_flags"),
        normalized,
        history,
        extra_flags=per_image_flags,
        confidence=normalized.get("confidence"),
    )
    normalized["risk_flags"] = risk_flags
    return normalized


def _per_image_risk_flags(per_image_assessments: Any) -> list[str]:
    if not isinstance(per_image_assessments, list):
        return []
    flags: list[str] = []
    for row in per_image_assessments:
        if not isinstance(row, dict):
            continue
        row_flags = row.get("risk_flags", [])
        if isinstance(row_flags, list):
            flags.extend(str(flag) for flag in row_flags)
    return flags


def collect_risk_flags(
    model_flags: Any,
    verdict: dict[str, Any],
    history: UserHistoryRecord | None,
    extra_flags: list[str] | None = None,
    confidence: Any = None,
) -> list[str]:
    flags: list[str] = []

    for source in (model_flags, extra_flags, history_risk_flags(history)):
        if isinstance(source, str):
            flags.extend(parse_semicolon_list(source))
        elif isinstance(source, (list, tuple)):
            flags.extend(str(item) for item in source if str(item).strip())

    if verdict.get("prompt_injection_detected"):
        flags.append("text_instruction_present")

    try:
        if confidence is not None and float(confidence) < CONFIDENCE_REVIEW_THRESHOLD:
            flags.append("manual_review_required")
    except (TypeError, ValueError):
        flags.append("manual_review_required")

    return dedupe_risk_flags(flags)


def history_risk_flags(history: UserHistoryRecord | None) -> list[str]:
    if history is None:
        return []
    return list(parse_semicolon_list(history.history_flags))


def dedupe_risk_flags(flags: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in flags:
        flag = str(raw).strip()
        if not flag or flag not in ALLOWED_RISK_FLAGS or flag in seen:
            continue
        if flag == "none":
            continue
        cleaned.append(flag)
        seen.add(flag)
    return cleaned or ["none"]


def format_risk_flags(flags: list[str] | str) -> str:
    if isinstance(flags, str):
        return flags if flags else "none"
    normalized = dedupe_risk_flags(list(flags))
    return ";".join(normalized)


def format_supporting_ids(image_ids: list[str] | str | None) -> str:
    if isinstance(image_ids, str):
        value = image_ids.strip()
        return value if value else "none"
    if not image_ids:
        return "none"
    cleaned = [str(item).strip() for item in image_ids if str(item).strip()]
    return ";".join(cleaned) if cleaned else "none"


def normalize_id_list(value: Any, valid_ids: tuple[str, ...]) -> list[str]:
    if isinstance(value, str):
        items = parse_semicolon_list(value)
    elif isinstance(value, (list, tuple)):
        items = tuple(str(item).strip() for item in value if str(item).strip())
    else:
        items = ()
    valid = set(valid_ids)
    return [item for item in items if item in valid]


def coerce_enum(value: Any, allowed: set[str], default: str) -> str:
    text = str(value).strip() if value is not None else ""
    return text if text in allowed else default


def to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


def format_bool(value: Any) -> str:
    return "true" if to_bool(value) else "false"


def _short_error_message(exc: Exception) -> str:
    text = str(exc)
    if "429" in text or "quota" in text.lower():
        return "Gemini API quota exceeded; manual review required."
    return text.split("\n", 1)[0][:200]


def fallback_verdict(
    claim: ClaimRecord,
    reason: str,
    history: UserHistoryRecord | None,
) -> dict[str, Any]:
    return {
        "evidence_standard_met": False,
        "evidence_standard_met_reason": reason,
        "risk_flags": collect_risk_flags(["manual_review_required"], {}, history, confidence=0.0),
        "issue_type": "unknown",
        "object_part": "unknown",
        "claim_status": "not_enough_information",
        "claim_status_justification": reason,
        "supporting_image_ids": [],
        "valid_image": any(image.exists for image in claim.images),
        "severity": "unknown",
        "confidence": 0.0,
    }


if __name__ == "__main__":
    root = find_repo_root()
    claim = load_claims(repo_root=root)[0]

    print("=== Offline formatting check ===")
    sample_verdict = {
        "evidence_standard_met": True,
        "evidence_standard_met_reason": "Test reason",
        "risk_flags": ["none"],
        "issue_type": "dent",
        "object_part": "front_bumper",
        "claim_status": "supported",
        "claim_status_justification": "Test justification",
        "supporting_image_ids": ["img_1"],
        "valid_image": True,
        "severity": "medium",
        "confidence": 0.9,
    }
    row = format_output_row(claim, sample_verdict)
    print("columns:", list(row.keys()) == list(OUTPUT_ROW_COLUMNS))
    print("sample row:", {key: row[key] for key in OUTPUT_ROW_COLUMNS[:6]})

    print("\n=== Live single-claim review ===")
    try:
        agent = ClaimReviewAgent.from_env(repo_root=root)
        result = agent.review_claim(claim)
        print("user_id:", result["user_id"])
        print("claim_status:", result["claim_status"])
        print("risk_flags:", result["risk_flags"])
        print(
            f"stats: calls={agent.stats.model_calls} (expect 1), "
            f"images={agent.stats.images_sent}, retries={agent.stats.retries}"
        )
    except (VisionAPIError, ValueError) as exc:
        print(f"Live review skipped/failed: {exc}")
