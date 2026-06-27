"""Load and normalize dataset CSV files for the damage-claim verification system."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pandas as pd

ClaimObject = Literal["car", "laptop", "package"]
ClaimStatus = Literal["supported", "contradicted", "not_enough_information"]

INPUT_COLUMNS = ("user_id", "image_paths", "user_claim", "claim_object")

OUTPUT_COLUMNS = (
    "evidence_standard_met",
    "evidence_standard_met_reason",
    "risk_flags",
    "issue_type",
    "object_part",
    "claim_status",
    "claim_status_justification",
    "supporting_image_ids",
    "valid_image",
    "severity",
)

SAMPLE_CLAIM_COLUMNS = INPUT_COLUMNS + OUTPUT_COLUMNS

RISK_FLAGS = (
    "none",
    "blurry_image",
    "cropped_or_obstructed",
    "low_light_or_glare",
    "wrong_angle",
    "wrong_object",
    "wrong_object_part",
    "damage_not_visible",
    "claim_mismatch",
    "possible_manipulation",
    "non_original_image",
    "text_instruction_present",
    "user_history_risk",
    "manual_review_required",
)

ISSUE_TYPES = (
    "dent",
    "scratch",
    "crack",
    "glass_shatter",
    "broken_part",
    "missing_part",
    "torn_packaging",
    "crushed_packaging",
    "water_damage",
    "stain",
    "none",
    "unknown",
)

CAR_OBJECT_PARTS = (
    "front_bumper",
    "rear_bumper",
    "door",
    "hood",
    "windshield",
    "side_mirror",
    "headlight",
    "taillight",
    "fender",
    "quarter_panel",
    "body",
    "unknown",
)

LAPTOP_OBJECT_PARTS = (
    "screen",
    "keyboard",
    "trackpad",
    "hinge",
    "lid",
    "corner",
    "port",
    "base",
    "body",
    "unknown",
)

PACKAGE_OBJECT_PARTS = (
    "box",
    "package_corner",
    "package_side",
    "seal",
    "label",
    "contents",
    "item",
    "unknown",
)

SEVERITY_LEVELS = ("none", "low", "medium", "high", "unknown")


@dataclass(frozen=True)
class ImageRef:
    """One submitted image referenced by a claim row."""

    image_id: str
    relative_path: str
    absolute_path: Path

    @property
    def exists(self) -> bool:
        return self.absolute_path.is_file()


@dataclass(frozen=True)
class ClaimRecord:
    user_id: str
    user_claim: str
    claim_object: str
    images: tuple[ImageRef, ...]

    @property
    def image_paths(self) -> str:
        return ";".join(image.relative_path for image in self.images)

    @property
    def image_ids(self) -> tuple[str, ...]:
        return tuple(image.image_id for image in self.images)


@dataclass(frozen=True)
class SampleClaimRecord(ClaimRecord):
    evidence_standard_met: bool
    evidence_standard_met_reason: str
    risk_flags: tuple[str, ...]
    issue_type: str
    object_part: str
    claim_status: str
    claim_status_justification: str
    supporting_image_ids: tuple[str, ...]
    valid_image: bool
    severity: str


@dataclass(frozen=True)
class UserHistoryRecord:
    user_id: str
    past_claim_count: int
    accept_claim: int
    manual_review_claim: int
    rejected_claim: int
    last_90_days_claim_count: int
    history_flags: str
    history_summary: str


@dataclass(frozen=True)
class EvidenceRequirement:
    requirement_id: str
    claim_object: str
    applies_to: str
    minimum_image_evidence: str


def find_repo_root(start: Path | None = None) -> Path:
    """Walk upward from *start* until a directory containing ``dataset/`` is found."""
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "dataset").is_dir():
            return candidate
    raise FileNotFoundError(
        "Could not locate repo root (expected a parent directory containing dataset/)"
    )


def image_id_from_path(path: str | Path) -> str:
    return Path(path).stem


def resolve_image_absolute_path(relative: str, repo_root: Path) -> Path:
    """Resolve a CSV image path against repo layout variants."""
    normalized = relative.strip().replace("\\", "/")
    candidates = (
        repo_root / normalized,
        repo_root / "dataset" / normalized,
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return candidates[0].resolve()


def parse_image_paths(image_paths: str, repo_root: Path) -> tuple[ImageRef, ...]:
    """Parse semicolon-separated relative image paths into resolved ``ImageRef`` rows."""
    if not image_paths or not str(image_paths).strip():
        return ()

    refs: list[ImageRef] = []
    for raw in str(image_paths).split(";"):
        relative = raw.strip().replace("\\", "/")
        if not relative:
            continue
        image_id = image_id_from_path(relative)
        absolute = resolve_image_absolute_path(relative, repo_root)
        refs.append(
            ImageRef(
                image_id=image_id,
                relative_path=relative,
                absolute_path=absolute,
            )
        )
    return tuple(refs)


def parse_semicolon_list(value: str) -> tuple[str, ...]:
    if not value or str(value).strip().lower() == "none":
        return ()
    return tuple(part.strip() for part in str(value).split(";") if part.strip())


def _parse_bool(value: object) -> bool:
    return str(value).strip().lower() == "true"


def _row_to_claim(row: pd.Series, repo_root: Path) -> ClaimRecord:
    return ClaimRecord(
        user_id=str(row["user_id"]),
        user_claim=str(row["user_claim"]),
        claim_object=str(row["claim_object"]),
        images=parse_image_paths(str(row["image_paths"]), repo_root),
    )


def _row_to_sample_claim(row: pd.Series, repo_root: Path) -> SampleClaimRecord:
    base = _row_to_claim(row, repo_root)
    return SampleClaimRecord(
        user_id=base.user_id,
        user_claim=base.user_claim,
        claim_object=base.claim_object,
        images=base.images,
        evidence_standard_met=_parse_bool(row["evidence_standard_met"]),
        evidence_standard_met_reason=str(row["evidence_standard_met_reason"]),
        risk_flags=parse_semicolon_list(str(row["risk_flags"])),
        issue_type=str(row["issue_type"]),
        object_part=str(row["object_part"]),
        claim_status=str(row["claim_status"]),
        claim_status_justification=str(row["claim_status_justification"]),
        supporting_image_ids=parse_semicolon_list(str(row["supporting_image_ids"])),
        valid_image=_parse_bool(row["valid_image"]),
        severity=str(row["severity"]),
    )


def load_claims(
    csv_path: Path | str | None = None,
    repo_root: Path | str | None = None,
) -> list[ClaimRecord]:
    root = Path(repo_root).resolve() if repo_root else find_repo_root()
    path = Path(csv_path) if csv_path else root / "dataset" / "claims.csv"
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    _validate_columns(df.columns.tolist(), INPUT_COLUMNS, path)
    return [_row_to_claim(row, root) for _, row in df.iterrows()]


def load_sample_claims(
    csv_path: Path | str | None = None,
    repo_root: Path | str | None = None,
) -> list[SampleClaimRecord]:
    root = Path(repo_root).resolve() if repo_root else find_repo_root()
    path = Path(csv_path) if csv_path else root / "dataset" / "sample_claims.csv"
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    _validate_columns(df.columns.tolist(), SAMPLE_CLAIM_COLUMNS, path)
    return [_row_to_sample_claim(row, root) for _, row in df.iterrows()]


def load_user_history(
    csv_path: Path | str | None = None,
    repo_root: Path | str | None = None,
) -> dict[str, UserHistoryRecord]:
    root = Path(repo_root).resolve() if repo_root else find_repo_root()
    path = Path(csv_path) if csv_path else root / "dataset" / "user_history.csv"
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    expected = (
        "user_id",
        "past_claim_count",
        "accept_claim",
        "manual_review_claim",
        "rejected_claim",
        "last_90_days_claim_count",
        "history_flags",
        "history_summary",
    )
    _validate_columns(df.columns.tolist(), expected, path)

    history: dict[str, UserHistoryRecord] = {}
    for _, row in df.iterrows():
        record = UserHistoryRecord(
            user_id=str(row["user_id"]),
            past_claim_count=int(row["past_claim_count"]),
            accept_claim=int(row["accept_claim"]),
            manual_review_claim=int(row["manual_review_claim"]),
            rejected_claim=int(row["rejected_claim"]),
            last_90_days_claim_count=int(row["last_90_days_claim_count"]),
            history_flags=str(row["history_flags"]),
            history_summary=str(row["history_summary"]),
        )
        history[record.user_id] = record
    return history


def load_evidence_requirements(
    csv_path: Path | str | None = None,
    repo_root: Path | str | None = None,
) -> list[EvidenceRequirement]:
    root = Path(repo_root).resolve() if repo_root else find_repo_root()
    path = (
        Path(csv_path)
        if csv_path
        else root / "dataset" / "evidence_requirements.csv"
    )
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    expected = ("requirement_id", "claim_object", "applies_to", "minimum_image_evidence")
    _validate_columns(df.columns.tolist(), expected, path)

    requirements: list[EvidenceRequirement] = []
    for _, row in df.iterrows():
        requirements.append(
            EvidenceRequirement(
                requirement_id=str(row["requirement_id"]),
                claim_object=str(row["claim_object"]),
                applies_to=str(row["applies_to"]),
                minimum_image_evidence=str(row["minimum_image_evidence"]),
            )
        )
    return requirements


def requirements_for_claim(
    claim_object: str,
    requirements: list[EvidenceRequirement] | None = None,
    repo_root: Path | str | None = None,
) -> list[EvidenceRequirement]:
    """Return evidence rules that apply to *claim_object* plus global ``all`` rules."""
    rules = requirements or load_evidence_requirements(repo_root=repo_root)
    return [
        rule
        for rule in rules
        if rule.claim_object in ("all", claim_object)
    ]


def _validate_columns(actual: list[str], expected: tuple[str, ...], path: Path) -> None:
    if actual != list(expected):
        raise ValueError(
            f"Unexpected columns in {path}. Expected {list(expected)}, got {actual}"
        )


if __name__ == "__main__":
    root = find_repo_root()
    claims = load_claims(repo_root=root)
    samples = load_sample_claims(repo_root=root)
    history = load_user_history(repo_root=root)
    requirements = load_evidence_requirements(repo_root=root)

    print(f"repo_root: {root}")
    print(f"claims: {len(claims)} rows")
    print(f"sample_claims: {len(samples)} rows")
    print(f"user_history: {len(history)} users")
    print(f"evidence_requirements: {len(requirements)} rules")
    if claims:
        first = claims[0]
        print(f"first claim images: {[img.image_id for img in first.images]}")
        print(f"first claim paths exist: {[img.exists for img in first.images]}")