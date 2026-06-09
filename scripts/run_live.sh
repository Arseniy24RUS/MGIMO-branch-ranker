#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python -m mgimo_ranker.cli --mode live --output-dir outputs/live --mc-iterations 2000
