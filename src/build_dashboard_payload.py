from __future__ import annotations

import argparse
from pathlib import Path

from mgimo_ranker.config import load_config
from mgimo_ranker.paths import DEFAULT_CONFIG, DEFAULT_DATA_DIR
from mgimo_ranker.payload import build_dashboard_payload, write_dashboard_payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the public MGIMO dashboard schema v2 payload from model outputs.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Path to YAML config")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR), help="Path to data directory")
    parser.add_argument("--model-output-dir", default="docs/data/model_outputs/current", help="Directory with current model CSV outputs")
    parser.add_argument("--canonical", default="docs/data/mgimo_dashboard_data.json", help="Canonical payload path")
    parser.add_argument("--alias", default="docs/data/dashboard_payload.json", help="Byte-identical alias payload path")
    parser.add_argument("--outputs-copy", default="data/outputs/current/dashboard_data.json", help="Optional byte-identical copy for downstream delivery checks")
    parser.add_argument(
        "--wpp-age-sex-historical",
        default=None,
        help="Official UN WPP 2024 PopulationBySingleAgeSex historical bulk CSV.GZ",
    )
    parser.add_argument(
        "--wpp-age-sex-projection",
        default=None,
        help="Official UN WPP 2024 PopulationBySingleAgeSex medium projection bulk CSV.GZ",
    )
    parser.add_argument(
        "--raw-demography",
        default=None,
        help="Deprecated: disabled. Use --wpp-age-sex-historical and --wpp-age-sex-projection.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = load_config(Path(args.config))
    canonical = Path(args.canonical)
    payload = build_dashboard_payload(
        cfg=cfg,
        data_dir=Path(args.data_dir),
        model_output_dir=Path(args.model_output_dir),
        wpp_age_sex_historical_path=Path(args.wpp_age_sex_historical) if args.wpp_age_sex_historical else None,
        wpp_age_sex_projection_path=Path(args.wpp_age_sex_projection) if args.wpp_age_sex_projection else None,
        raw_demography_path=Path(args.raw_demography) if args.raw_demography else None,
    )
    canonical_path, alias_path = write_dashboard_payload(payload, canonical, Path(args.alias) if args.alias else None)
    print(f"wrote {canonical_path}")
    if alias_path:
        print(f"wrote {alias_path}")
    if args.outputs_copy:
        outputs_copy = Path(args.outputs_copy)
        outputs_copy.parent.mkdir(parents=True, exist_ok=True)
        outputs_copy.write_text(canonical_path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"wrote {outputs_copy}")
    print(f"schema_version={payload['schema_version']} countries={len(payload['countries'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
