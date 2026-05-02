#!/usr/bin/env python
"""Plan deterministic public COLA sample days across a date range."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from cola_etl.paths import SAMPLING_DIR, ensure_public_cola_work_dirs
from cola_etl.sampling import choose_sample_days, write_json, write_sample_days_csv


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", default="2025-05-01")
    parser.add_argument("--end-date", default="2026-05-01")
    parser.add_argument("--seed", type=int, default=20260502)
    parser.add_argument("--days-per-month", type=int, default=3)
    parser.add_argument(
        "--selected-days-csv",
        default=str(SAMPLING_DIR / "selected_days.csv"),
    )
    parser.add_argument(
        "--plan-json",
        default=str(SAMPLING_DIR / "plan.json"),
    )
    return parser.parse_args()


def main() -> None:
    """Build and save a deterministic sample-day plan."""

    args = parse_args()
    ensure_public_cola_work_dirs()
    start_date = date.fromisoformat(args.start_date)
    end_date = date.fromisoformat(args.end_date)
    days = choose_sample_days(
        start_date,
        end_date,
        seed=args.seed,
        days_per_month=args.days_per_month,
    )
    selected_days_path = Path(args.selected_days_csv)
    plan_json_path = Path(args.plan_json)
    write_sample_days_csv(selected_days_path, days)
    write_json(
        plan_json_path,
        {
            "start_date": args.start_date,
            "end_date": args.end_date,
            "seed": args.seed,
            "days_per_month": args.days_per_month,
            "selected_day_count": len(days),
            "months": sorted({item.month_key for item in days}),
        },
    )
    print(f"Planned {len(days)} sample day(s) across {len({item.month_key for item in days})} month(s)")
    print(f"selected_days.csv -> {selected_days_path}")
    print(f"plan.json -> {plan_json_path}")


if __name__ == "__main__":
    main()
