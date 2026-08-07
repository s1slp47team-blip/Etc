# 맛집 브리핑 — Supabase 배포 (Windows PowerShell)
#
#   $env:SUPABASE_PROJECT_REF      = "xxxxxxxxxxxx"
#   $env:SUPABASE_SERVICE_ROLE_KEY = "eyJ..."
#   .\scripts\deploy.ps1
#
# scripts/deploy.sh 와 하는 일이 같다:
#   1) DB 마이그레이션 적용            (supabase CLI)
#   2) Edge Function 배포              (supabase CLI)
#   3) 정적 프론트를 Storage 에 업로드 (Storage REST API)
#
# 시크릿(KAKAO_REST_API_KEY 등)은 이 스크립트가 건드리지 않는다.
# 대시보드나 `supabase secrets set` 으로 따로 등록한다 — docs/SUPABASE.md 참고.
#
# 이 파일은 UTF-8 BOM 으로 저장되어야 한다. Windows PowerShell 5.1 은 BOM 이 없으면
# 스크립트를 ANSI 로 읽어 아래 한글 메시지가 깨진다.

[CmdletBinding()]
param(
  [string]$ProjectRef     = $env:SUPABASE_PROJECT_REF,
  [string]$ServiceRoleKey = $env:SUPABASE_SERVICE_ROLE_KEY,
  [string]$Bucket         = 'app'
)

$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not $ProjectRef) {
  throw 'SUPABASE_PROJECT_REF 가 필요합니다. 대시보드 > Project Settings > General 의 Reference ID.'
}
if (-not $ServiceRoleKey) {
  throw 'SUPABASE_SERVICE_ROLE_KEY 가 필요합니다. 대시보드 > Project Settings > API 의 service_role 키.'
}

# supabase CLI 가 PATH 에 있으면 그걸 쓰고, 없으면 npx 로 대신 실행한다.
# (Windows 는 npm 전역 설치가 막혀 있어 npx 경로가 더 흔하다)
if (Get-Command supabase -ErrorAction SilentlyContinue) {
  $script:SupabasePrefix = @('supabase')
} elseif (Get-Command npx -ErrorAction SilentlyContinue) {
  Write-Host 'supabase CLI 가 없어 npx 로 실행합니다 (처음 한 번은 내려받느라 느립니다).'
  $script:SupabasePrefix = @('npx', '--yes', 'supabase@latest')
} else {
  throw @'
supabase CLI 도 npx 도 없습니다. 둘 중 하나를 설치하세요.
  - Scoop:        scoop install supabase
  - Node.js 설치 후 npx 사용: https://nodejs.org
  - 직접 내려받기: https://github.com/supabase/cli/releases
'@
}

# 인자를 배열 하나로 받는다. PowerShell 이 --project-ref 같은 토큰을 자기 파라미터로
# 해석하려 드는 것을 피하기 위해서다 (ValueFromRemainingArguments 는 이 경우 불안정).
function Invoke-Supabase {
  param([Parameter(Mandatory)][string[]]$SupaArgs)

  $exe  = $script:SupabasePrefix[0]
  # Select-Object -Skip 1 을 쓴다. $arr[1..($arr.Count-1)] 은 원소가 하나일 때
  # 1..0 이 내림차순 범위(1,0)로 해석돼 엉뚱한 인자가 붙는다.
  $rest = @($script:SupabasePrefix | Select-Object -Skip 1) + $SupaArgs

  & $exe @rest
  if ($LASTEXITCODE -ne 0) {
    throw "supabase $($SupaArgs -join ' ') 실패 (종료코드 $LASTEXITCODE)"
  }
}

$base = "https://$ProjectRef.supabase.co"

Write-Host ''
Write-Host '▶ 1/3 DB 마이그레이션' -ForegroundColor Cyan
# link 는 데이터베이스 비밀번호를 물어본다 (프로젝트 만들 때 정한 값).
# 잊었다면 대시보드 > Project Settings > Database 에서 재설정할 수 있다.
Invoke-Supabase @('link', '--project-ref', $ProjectRef)
Invoke-Supabase @('db', 'push')

Write-Host ''
Write-Host '▶ 2/3 Edge Function 배포' -ForegroundColor Cyan
Invoke-Supabase @('functions', 'deploy', 'api', '--project-ref', $ProjectRef)

Write-Host ''
Write-Host "▶ 3/3 정적 프론트 업로드 → $Bucket/index.html" -ForegroundColor Cyan

$authHeaders = @{
  Authorization = "Bearer $ServiceRoleKey"
  apikey        = $ServiceRoleKey
}

# 버킷이 없으면 만든다 (이미 있으면 400/409 — 무시)
try {
  $body = @{ name = $Bucket; id = $Bucket; public = $true } | ConvertTo-Json
  Invoke-RestMethod -Method Post -Uri "$base/storage/v1/bucket" `
    -Headers $authHeaders -ContentType 'application/json' -Body $body | Out-Null
  Write-Host "  버킷 '$Bucket' 생성됨"
} catch {
  # 연결 자체가 실패하면 Response 가 없으므로 방어적으로 읽는다
  $resp = $_.Exception.Response
  $code = if ($resp) { [int]$resp.StatusCode } else { 0 }
  if ($code -eq 409 -or $code -eq 400) {
    Write-Host "  버킷 '$Bucket' 이미 있음"
  } else {
    throw "버킷 생성 실패 (HTTP $code): $($_.Exception.Message)"
  }
}

# 업로드(덮어쓰기). 캐시를 짧게 잡아 다음 배포가 바로 반영되게 한다.
$uploadHeaders = @{
  Authorization   = "Bearer $ServiceRoleKey"
  apikey          = $ServiceRoleKey
  'Cache-Control' = 'max-age=60'
}
Invoke-WebRequest -Method Put -Uri "$base/storage/v1/object/$Bucket/index.html" `
  -Headers $uploadHeaders -ContentType 'text/html; charset=utf-8' `
  -InFile 'web/index.html' -UseBasicParsing | Out-Null

Write-Host ''
Write-Host '완료. 접속 주소:' -ForegroundColor Green
Write-Host "  $base/storage/v1/object/public/$Bucket/index.html"
Write-Host ''
Write-Host '확인:' -ForegroundColor Green
Write-Host "  $base/functions/v1/api/config"
