#!/usr/bin/env bash
# 원본 파이썬과 Edge Function 이식본의 결과를 대조한다.
# 필요: python3, deno.
set -euo pipefail
cd "$(dirname "$0")/.."

EXPECTED=$(mktemp)
trap 'rm -f "$EXPECTED"' EXIT

python3 scripts/parity_expected.py > "$EXPECTED"
deno run --allow-read --allow-env scripts/parity.ts "$EXPECTED"
