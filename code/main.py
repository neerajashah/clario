"""CLI entry point: process claims.csv and write output.csv."""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from agent import OUTPUT_ROW_COLUMNS, ClaimReviewAgent
from data_loader import ClaimRecord, find_repo_root, load_claims
from vision import UsageStats


@dataclass
class RunResult:
    frame: pd.DataFrame
    stats: UsageStats
    elapsed_seconds: float


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify damage claims with Gemini and write structured predictions.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="Input claims CSV (default: dataset/claims.csv under repo root)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output CSV path (default: output.csv under repo root)",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        help="Repository root containing dataset/ (auto-detected if omitted)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Process only the first N claims (useful for smoke tests)",
    )
    parser.add_argument(
        "--start-from",
        type=int,
        default=0,
        help="Skip first N claims (resume after crash)",
    )
    return parser.parse_args(argv)


def process_claims(
    claims: list[ClaimRecord],
    agent: ClaimReviewAgent,
    output_path: Path | str,
    verbose: bool = True,
) -> RunResult:
    """Review claims with *agent* and write predictions to *output_path*."""
    started = time.perf_counter()
    rows: list[dict[str, str]] = []
    total = len(claims)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    for index, claim in enumerate(claims, start=1):
        if verbose:
            print(
                f"[{index}/{total}] Reviewing {claim.user_id} "
                f"({claim.claim_object}, {len(claim.images)} image(s))..."
            )
        row = agent.review_claim(claim)
        rows.append(row)

        # Save immediately after each claim
        write_header = not output.exists() or output.stat().st_size == 0
        pd.DataFrame([row], columns=list(OUTPUT_ROW_COLUMNS)).to_csv(
            output, index=False, mode='a', header=write_header
        )

        if verbose:
            print(
                f"    -> {row['claim_status']} | "
                f"evidence_met={row['evidence_standard_met']} | "
                f"risk_flags={row['risk_flags']}"
            )

    frame = pd.DataFrame(rows, columns=list(OUTPUT_ROW_COLUMNS))
    return RunResult(
        frame=frame,
        stats=agent.stats,
        elapsed_seconds=time.perf_counter() - started,
    )

def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve() if args.repo_root else find_repo_root()
    input_path = args.input or (repo_root / "dataset" / "claims.csv")
    output_path = args.output or (repo_root / "output.csv")

    if not input_path.is_file():
        print(f"Input file not found: {input_path}", file=sys.stderr)
        return 1

    load_dotenv(repo_root / ".env")
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    print(f"Repo root: {repo_root}")
    print(f"Input:     {input_path}")
    print(f"Output:    {output_path}")
    print(f"Model:     {model_name}")

    claims = load_claims(csv_path=input_path, repo_root=repo_root)
    if args.start_from:
        claims = claims[args.start_from:]
        print(f"Resuming from claim {args.start_from + 1}")
    if args.limit is not None:
        claims = claims[: args.limit]
        print(f"Limit:     {args.limit} claim(s)")

    agent = ClaimReviewAgent.from_env(repo_root=repo_root, model_name=model_name)
    result = process_claims(claims, agent, output_path)

    stats = result.stats
    print("\nDone.")
    print(f"Wrote {len(result.frame)} row(s) to {output_path}")
    print(
        "Usage: "
        f"model_calls={stats.model_calls}, "
        f"images_sent={stats.images_sent}, "
        f"prompt_tokens={stats.prompt_tokens}, "
        f"output_tokens={stats.output_tokens}, "
        f"total_tokens={stats.total_tokens}, "
        f"retries={stats.retries}"
    )
    print(f"Elapsed: {result.elapsed_seconds:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
