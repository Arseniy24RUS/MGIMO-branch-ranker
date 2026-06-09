from __future__ import annotations

import argparse
from pathlib import Path

from rich.console import Console
from rich.table import Table

from mgimo_ranker.config import load_config
from mgimo_ranker.paths import DEFAULT_CONFIG, DEFAULT_DATA_DIR, DEFAULT_OUTPUT_DIR
from mgimo_ranker.pipeline import run_pipeline

console = Console()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mgimo-ranker",
        description="Country ranking platform for prospective MGIMO foreign branches",
    )
    parser.add_argument("--mode", choices=["snapshot", "demo", "live"], default="snapshot", help="snapshot uses the bundled global panel; demo uses fixtures; live downloads APIs")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Path to YAML config")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR), help="Path to data directory")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR / "run"), help="Output directory")
    parser.add_argument("--mc-iterations", type=int, default=1000, help="Monte Carlo iterations for rank robustness")
    parser.add_argument("--finance-mc-iterations", type=int, default=None, help="Optional override for NPV Monte Carlo iterations in the financial module")
    parser.add_argument("--usd-rub", type=float, default=None, help="Optional explicit USD/RUB rate; otherwise CBR XML is required")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    cfg = load_config(Path(args.config))
    if args.finance_mc_iterations is not None:
        cfg.raw.setdefault("financial", {})["finance_mc_iterations"] = int(args.finance_mc_iterations)
    files = run_pipeline(
        cfg=cfg,
        data_dir=Path(args.data_dir),
        output_dir=Path(args.output_dir),
        mode=args.mode,
        mc_iterations=args.mc_iterations,
        usd_rub=args.usd_rub,
    )
    table = Table(title="MGIMO branch ranker default-priority outputs")
    table.add_column("Artifact")
    table.add_column("Path")
    for key, path in files.items():
        table.add_row(key, str(path))
    console.print(table)


if __name__ == "__main__":  # pragma: no cover
    main()
