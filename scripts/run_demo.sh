#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python -m mgimo_ranker.cli --mode demo --output-dir outputs/demo --mc-iterations 500 --usd-rub 73.3436
