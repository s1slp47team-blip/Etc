#!/usr/bin/env bash
# 맛집 브리핑 — Supabase 배포
#
#   export SUPABASE_PROJECT_REF=xxxxxxxxxxxx
#   export SUPABASE_SERVICE_ROLE_KEY=eyJ...
#   ./scripts/deploy.sh
#
# 하는 일:
#   1) DB 마이그레이션 적용        (supabase CLI)
#   2) Edge Function 배포          (supabase CLI)
#   3) 정적 프론트를 Storage 에 업로드 (Storage REST API)
#
# 시크릿(KAKAO_REST_API_KEY 등)은 이 스크립트가 건드리지 않는다.
# `supabase secrets set` 으로 따로 등록한다 — docs/SUPABASE.md 참고.

set -euo pipefail
cd "$(dirname "$0")/.."

: "${SUPABASE_PROJECT_REF:?SUPABASE_PROJECT_REF 환경변수가 필요합니다 (프로젝트 설정 > General)}"
: "${SUPABASE_SERVICE_ROLE_KEY:?SUPABASE_SERVICE_ROLE_KEY 환경변수가 필요합니다 (프로젝트 설정 > API)}"

BUCKET="${BUCKET:-app}"
BASE="https://${SUPABASE_PROJECT_REF}.supabase.co"

command -v supabase >/dev/null || {
  echo "supabase CLI 가 필요합니다: https://supabase.com/docs/guides/local-development/cli/getting-started" >&2
  exit 1
}

# link/deploy 는 로그인된 상태여야 한다. 안 되어 있으면 여기서 먼저 알려준다.
supabase projects list >/dev/null 2>&1 || {
  echo "supabase 로그인이 필요합니다. 먼저 실행하세요:" >&2
  echo "  supabase login" >&2
  exit 1
}

echo "▶ 1/3 DB 마이그레이션"
# link 는 데이터베이스 비밀번호를 물어본다 (프로젝트 만들 때 정한 값).
# 잊었다면 대시보드 > Project Settings > Database 에서 재설정할 수 있다.
supabase link --project-ref "$SUPABASE_PROJECT_REF"
supabase db push

echo "▶ 2/3 Edge Function 배포"
# verify_jwt 는 supabase/config.toml 에서 끈다 (프론트가 APP_PASSWORD 로 자체 인증)
supabase functions deploy api --project-ref "$SUPABASE_PROJECT_REF"

echo "▶ 3/3 정적 프론트 업로드 → ${BUCKET}/index.html"
# 버킷이 없으면 만든다 (이미 있으면 409 — 무시)
curl -sS -o /dev/null -w '' -X POST "${BASE}/storage/v1/bucket" \
  -H "Authorization: Bearer ${SUPABASE_SERVICE_ROLE_KEY}" \
  -H "apikey: ${SUPABASE_SERVICE_ROLE_KEY}" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"${BUCKET}\",\"id\":\"${BUCKET}\",\"public\":true}" || true

# 업로드(덮어쓰기). 캐시를 짧게 잡아 다음 배포가 바로 반영되게 한다.
code=$(curl -sS -o /tmp/upload.out -w '%{http_code}' -X PUT \
  "${BASE}/storage/v1/object/${BUCKET}/index.html" \
  -H "Authorization: Bearer ${SUPABASE_SERVICE_ROLE_KEY}" \
  -H "apikey: ${SUPABASE_SERVICE_ROLE_KEY}" \
  -H "Content-Type: text/html; charset=utf-8" \
  -H "Cache-Control: max-age=60" \
  --data-binary @web/index.html)

if [ "$code" != "200" ]; then
  echo "업로드 실패 (HTTP $code):" >&2
  cat /tmp/upload.out >&2
  exit 1
fi

echo
echo "완료. 접속 주소:"
echo "  ${BASE}/storage/v1/object/public/${BUCKET}/index.html"
