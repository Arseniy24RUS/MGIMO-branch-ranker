#!/usr/bin/env python3
"""Deprecated guard for the old payload-level demography normalizer.

Production demography must be rebuilt from official UN WPP 2024
PopulationBySingleAgeSex bulk files. This script intentionally refuses to edit
the public payload because rescaling age-sex matrices after the fact would
destroy source-level traceability.
"""
from __future__ import annotations


def main() -> int:
    raise SystemExit(
        "Deprecated: rebuild with src/build_dashboard_payload.py using "
        "--wpp-age-sex-historical and --wpp-age-sex-projection."
    )


if __name__ == "__main__":
    main()
