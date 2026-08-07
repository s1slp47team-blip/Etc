#!/usr/bin/env bash
# Edge Function 9개 파일을 한 파일로 합친다.
#
#   ./scripts/bundle.sh
#   → supabase/functions/api/bundled.ts
#
# CLI 없이 Supabase 대시보드의 함수 편집기에 붙여넣어 배포할 때 쓴다.
# supabase-js 는 --external 로 남겨둔다 (Edge Runtime 이 알아서 받는다).
# 이게 없으면 번들이 800KB 가 넘어 편집기에 붙여넣기 어렵다.
#
# CLI 로 배포한다면 이 파일은 필요 없다 — supabase functions deploy api 가
# index.ts 를 진입점으로 알아서 처리한다.

set -euo pipefail
cd "$(dirname "$0")/.."

command -v deno >/dev/null || {
  echo "deno 가 필요합니다: https://docs.deno.com/runtime/getting_started/installation/" >&2
  exit 1
}

OUT=supabase/functions/api/bundled.ts

{
  echo "// @ts-nocheck"
  echo "// 자동 생성 파일 — 직접 고치지 마세요. ./scripts/bundle.sh 로 다시 만듭니다."
  echo "// 원본: supabase/functions/api/*.ts (index.ts 가 진입점)"
  echo "//"
  echo "// Supabase CLI 없이 대시보드 함수 편집기에 붙여넣어 배포하기 위한 단일 파일입니다."
  echo "// 배포 방법은 docs/SUPABASE.md 의 'CLI 없이 배포하기' 절을 보세요."
  echo "//"
  echo "// @ts-nocheck 인 이유: 번들러가 타입 주석을 제거한 JavaScript 를 .ts 파일로"
  echo "// 내보내므로, 원본에 타입이 다 붙어 있는데도 noImplicitAny 에 걸린다."
  echo "// 타입 검증은 원본 9개 파일에 대해 deno check 로 이미 수행된다."
  echo
  deno bundle --external 'npm:*' --platform deno supabase/functions/api/index.ts
} > "$OUT"

echo "생성됨: $OUT ($(wc -c < "$OUT" | tr -d ' ') bytes, $(wc -l < "$OUT" | tr -d ' ') lines)"
