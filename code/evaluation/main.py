"""Evaluate the claim-review system on dataset/sample_claims.csv."""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

CODE_DIR = Path(__file__).resolve().parents[1]
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from agent import (  # noqa: E402
    OUTPUT_ROW_COLUMNS,
    ClaimReviewAgent,
    format_bool,
    format_risk_flags,
    format_supporting_ids,
)
from data_loader import (  # noqa: E402
    OUTPUT_COLUMNS,
    SampleClaimRecord,
    find_repo_root,
    load_sample_claims,
    parse_semicolon_list,
)
from vision import UsageStats  # noqa: E402

SCORE_COLUMNS = OUTPUT_COLUMNS
KEY_COLUMNS = (
    "claim_status",
    "issue_type",
    "object_part",
    "severity",
    "evidence_standard_met",
    "valid_image",
    "risk_flags",
    "supporting_image_ids",
)

DEFAULT_STRATEGIES: dict[str, dict[str, Any]] = {
    "primary_temp_0_1": {
        "description": "Three-stage Gemini pipeline at temperature 0.1",
        "temperature": 0.1,
    },
    "comparison_temp_0_5": {
        "description": "Same pipeline at higher temperature 0.5 for comparison",
        "temperature": 0.5,
    },
}


@dataclass
class FieldMetrics:
    field: str
    accuracy: float
    matches: int
    total: int


@dataclass
class EvaluationMetrics:
    strategy: str
    description: str
    total_rows: int
    field_metrics: list[FieldMetrics] = field(default_factory=list)
    claim_status_distribution: dict[str, int] = field(default_factory=dict)
    elapsed_seconds: float = 0.0
    model_calls: int = 0
    images_sent: int = 0
    total_tokens: int = 0
    retries: int = 0

    @property
    def claim_status_accuracy(self) -> float:
        for metric in self.field_metrics:
            if metric.field == "claim_status":
                return metric.accuracy
        return 0.0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["claim_status_accuracy"] = self.claim_status_accuracy
        return payload


@dataclass
class StrategyRun:
    name: str
    description: str
    predictions: pd.DataFrame
    metrics: EvaluationMetrics
    stats: UsageStats
    elapsed_seconds: float


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate claim-review predictions against sample_claims.csv labels.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        help="Repository root containing dataset/ (auto-detected if omitted)",
    )
    parser.add_argument(
        "--sample-path",
        type=Path,
        help="Labeled sample CSV (default: dataset/sample_claims.csv)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory for evaluation artifacts (default: code/evaluation)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Evaluate only the first N labeled sample rows",
    )
    parser.add_argument(
        "--predictions",
        type=Path,
        help="Score an existing predictions CSV instead of running live strategies",
    )
    parser.add_argument(
        "--strategy-name",
        default="provided_predictions",
        help="Label to use when scoring --predictions",
    )
    parser.add_argument(
        "--skip-live",
        action="store_true",
        help="Skip live Gemini runs; only score --predictions if provided",
    )
    return parser.parse_args(argv)


def sample_to_gold_row(sample: SampleClaimRecord) -> dict[str, str]:
    return {
        "user_id": sample.user_id,
        "image_paths": sample.image_paths,
        "user_claim": sample.user_claim,
        "claim_object": sample.claim_object,
        "evidence_standard_met": format_bool(sample.evidence_standard_met),
        "evidence_standard_met_reason": sample.evidence_standard_met_reason,
        "risk_flags": format_risk_flags(sample.risk_flags),
        "issue_type": sample.issue_type,
        "object_part": sample.object_part,
        "claim_status": sample.claim_status,
        "claim_status_justification": sample.claim_status_justification,
        "supporting_image_ids": format_supporting_ids(sample.supporting_image_ids),
        "valid_image": format_bool(sample.valid_image),
        "severity": sample.severity,
    }


def normalize_set_field(value: str) -> frozenset[str]:
    if not value or str(value).strip().lower() == "none":
        return frozenset()
    return frozenset(parse_semicolon_list(str(value)))


def fields_match(field: str, predicted: str, expected: str) -> bool:
    if field in {"risk_flags", "supporting_image_ids"}:
        return normalize_set_field(predicted) == normalize_set_field(expected)
    return str(predicted).strip() == str(expected).strip()


def compute_metrics(
    strategy: str,
    description: str,
    gold_frame: pd.DataFrame,
    pred_frame: pd.DataFrame,
    elapsed_seconds: float = 0.0,
    stats: UsageStats | None = None,
) -> EvaluationMetrics:
    if len(gold_frame) != len(pred_frame):
        raise ValueError(
            f"Row count mismatch: gold={len(gold_frame)} predictions={len(pred_frame)}"
        )

    gold_sorted = gold_frame.sort_values("user_id").reset_index(drop=True)
    pred_sorted = pred_frame.sort_values("user_id").reset_index(drop=True)

    if not gold_sorted["user_id"].equals(pred_sorted["user_id"]):
        raise ValueError("Predictions user_id values do not match labeled sample rows")

    field_metrics: list[FieldMetrics] = []
    total = len(gold_sorted)
    for field in KEY_COLUMNS:
        matches = sum(
            fields_match(field, pred_sorted.at[index, field], gold_sorted.at[index, field])
            for index in range(total)
        )
        field_metrics.append(
            FieldMetrics(
                field=field,
                accuracy=matches / total if total else 0.0,
                matches=matches,
                total=total,
            )
        )

    usage = stats or UsageStats()
    return EvaluationMetrics(
        strategy=strategy,
        description=description,
        total_rows=total,
        field_metrics=field_metrics,
        claim_status_distribution=pred_sorted["claim_status"].value_counts().to_dict(),
        elapsed_seconds=elapsed_seconds,
        model_calls=usage.model_calls,
        images_sent=usage.images_sent,
        total_tokens=usage.total_tokens,
        retries=usage.retries,
    )


def run_strategy(
    name: str,
    description: str,
    samples: list[SampleClaimRecord],
    repo_root: Path,
    client_kwargs: dict[str, Any],
    verbose: bool = True,
) -> StrategyRun:
    started = time.perf_counter()
    agent = ClaimReviewAgent.from_env(repo_root=repo_root, **client_kwargs)
    rows: list[dict[str, str]] = []
    total = len(samples)

    for index, sample in enumerate(samples, start=1):
        if verbose:
            print(
                f"[{name}] [{index}/{total}] {sample.user_id} "
                f"({sample.claim_object}, {len(sample.images)} image(s))"
            )
        rows.append(agent.review_claim(sample))

    pred_frame = pd.DataFrame(rows, columns=list(OUTPUT_ROW_COLUMNS))
    elapsed = time.perf_counter() - started
    gold_rows = [sample_to_gold_row(sample) for sample in samples]
    gold_frame = pd.DataFrame(gold_rows, columns=list(OUTPUT_ROW_COLUMNS))
    metrics = compute_metrics(
        strategy=name,
        description=description,
        gold_frame=gold_frame,
        pred_frame=pred_frame,
        elapsed_seconds=elapsed,
        stats=agent.stats,
    )
    return StrategyRun(
        name=name,
        description=description,
        predictions=pred_frame,
        metrics=metrics,
        stats=agent.stats,
        elapsed_seconds=elapsed,
    )


def compare_strategies(runs: list[StrategyRun]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for run in runs:
        row: dict[str, Any] = {
            "strategy": run.name,
            "description": run.description,
            "claim_status_accuracy": run.metrics.claim_status_accuracy,
            "elapsed_seconds": round(run.elapsed_seconds, 2),
            "model_calls": run.stats.model_calls,
            "images_sent": run.stats.images_sent,
            "total_tokens": run.stats.total_tokens,
            "retries": run.stats.retries,
        }
        for metric in run.metrics.field_metrics:
            row[f"{metric.field}_accuracy"] = round(metric.accuracy, 4)
        rows.append(row)
    return pd.DataFrame(rows)


def print_metrics(metrics: EvaluationMetrics) -> None:
    print(f"\nStrategy: {metrics.strategy}")
    print(f"Description: {metrics.description}")
    print(f"Rows evaluated: {metrics.total_rows}")
    print(f"Elapsed: {metrics.elapsed_seconds:.1f}s")
    print(
        f"Usage: model_calls={metrics.model_calls}, "
        f"images_sent={metrics.images_sent}, "
        f"total_tokens={metrics.total_tokens}, "
        f"retries={metrics.retries}"
    )
    print("Field accuracy:")
    for metric in metrics.field_metrics:
        print(
            f"  - {metric.field}: {metric.matches}/{metric.total} "
            f"({metric.accuracy * 100:.1f}%)"
        )
    print("Predicted claim_status distribution:", metrics.claim_status_distribution)


def write_artifacts(
    output_dir: Path,
    runs: list[StrategyRun],
    comparison: pd.DataFrame,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    comparison.to_csv(output_dir / "strategy_comparison.csv", index=False)

    metrics_payload = [run.metrics.to_dict() for run in runs]
    (output_dir / "evaluation_metrics.json").write_text(
        json.dumps(metrics_payload, indent=2),
        encoding="utf-8",
    )

    for run in runs:
        run.predictions.to_csv(
            output_dir / f"predictions_{run.name}.csv",
            index=False,
        )


def evaluate_samples(
    samples: list[SampleClaimRecord],
    repo_root: Path,
    output_dir: Path,
    strategies: dict[str, dict[str, Any]] | None = None,
    verbose: bool = True,
) -> tuple[list[StrategyRun], pd.DataFrame]:
    strategy_defs = strategies or DEFAULT_STRATEGIES
    runs: list[StrategyRun] = []
    for name, config in strategy_defs.items():
        description = str(config.get("description", name))
        client_kwargs = {
            key: value
            for key, value in config.items()
            if key != "description"
        }
        runs.append(
            run_strategy(
                name=name,
                description=description,
                samples=samples,
                repo_root=repo_root,
                client_kwargs=client_kwargs,
                verbose=verbose,
            )
        )
    comparison = compare_strategies(runs)
    write_artifacts(output_dir, runs, comparison)
    return runs, comparison


def score_predictions_file(
    samples: list[SampleClaimRecord],
    predictions_path: Path,
    strategy_name: str,
    description: str = "Scored from an existing predictions CSV",
) -> StrategyRun:
    gold_rows = [sample_to_gold_row(sample) for sample in samples]
    gold_frame = pd.DataFrame(gold_rows, columns=list(OUTPUT_ROW_COLUMNS))
    pred_frame = pd.read_csv(predictions_path, dtype=str, keep_default_na=False)
    _validate_prediction_columns(pred_frame.columns.tolist())

    sample_ids = {sample.user_id for sample in samples}
    pred_frame = pred_frame[pred_frame["user_id"].isin(sample_ids)].copy()
    pred_frame = pred_frame.sort_values("user_id").reset_index(drop=True)
    gold_frame = gold_frame.sort_values("user_id").reset_index(drop=True)

    metrics = compute_metrics(
        strategy=strategy_name,
        description=description,
        gold_frame=gold_frame,
        pred_frame=pred_frame,
    )
    return StrategyRun(
        name=strategy_name,
        description=description,
        predictions=pred_frame,
        metrics=metrics,
        stats=UsageStats(),
        elapsed_seconds=0.0,
    )


def _validate_prediction_columns(columns: list[str]) -> None:
    expected = list(OUTPUT_ROW_COLUMNS)
    if columns != expected:
        raise ValueError(f"Predictions CSV must have columns {expected}, got {columns}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve() if args.repo_root else find_repo_root()
    sample_path = args.sample_path or (repo_root / "dataset" / "sample_claims.csv")
    output_dir = args.output_dir or (CODE_DIR / "evaluation")

    if not sample_path.is_file():
        print(f"Sample file not found: {sample_path}", file=sys.stderr)
        return 1

    samples = load_sample_claims(csv_path=sample_path, repo_root=repo_root)
    if args.limit is not None:
        samples = samples[: args.limit]

    print(f"Repo root: {repo_root}")
    print(f"Sample:    {sample_path}")
    print(f"Output:    {output_dir}")
    print(f"Rows:      {len(samples)}")

    runs: list[StrategyRun] = []

    if args.predictions:
        print(f"\nScoring predictions file: {args.predictions}")
        runs.append(
            score_predictions_file(
                samples=samples,
                predictions_path=args.predictions,
                strategy_name=args.strategy_name,
            )
        )

    if not args.skip_live and not args.predictions:
        print("\nRunning live strategy comparison...")
        live_runs, comparison = evaluate_samples(
            samples=samples,
            repo_root=repo_root,
            output_dir=output_dir,
        )
        runs.extend(live_runs)
        print("\n=== Strategy Comparison ===")
        print(comparison.to_string(index=False))
        for run in runs:
            print_metrics(run.metrics)
        print(f"\nWrote artifacts to {output_dir}")
        return 0

    if not runs:
        print("No predictions to score. Provide --predictions or remove --skip-live.", file=sys.stderr)
        return 1

    comparison = compare_strategies(runs)
    write_artifacts(output_dir, runs, comparison)
    for run in runs:
        print_metrics(run.metrics)
    print("\n=== Strategy Comparison ===")
    print(comparison.to_string(index=False))
    print(f"\nWrote artifacts to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
