# 맛집 브리핑 — Render → Supabase 이전 가이드

Render.com 웹서비스로 돌던 파이썬 앱(`food_briefing_app.py`)을 Supabase 위로 옮긴 구성입니다.

## 왜 그냥 옮길 수 없었나

Render는 프로세스를 계속 띄워주는 PaaS이고, Supabase는 Postgres·Auth·Storage·Edge Functions를
제공하는 BaaS입니다. **Supabase에는 파이썬 런타임이 없습니다** — Edge Functions는 Deno/TypeScript
전용입니다. 그래서 "푸시 대상만 바꾸는" 방식이 불가능하고, 아래처럼 재구성했습니다.

| 원본 (Render) | 이전 후 (Supabase) |
|---|---|
| `http.server` + `Handler` | Edge Function `api` (Deno) |
| 파이썬 문자열에 박힌 `PAGE` HTML | Storage 공개 버킷의 정적 `web/index.html` |
| `검색캐시`, `상세캐시` (메모리 dict) | `kv_cache` 테이블 (scope=`search`/`detail`) |
| `_상세결과캐시`, `_인증맵캐시` (메모리) | `kv_cache` (scope=`place`/`cert`/`photo`) |
| `_내맛집캐시` (메모리 1시간) | `my_places` 테이블 + `my_places_sync` |
| `POST /enrich` 한 방에 30~100곳 | `enrich/start` + `enrich/step` 청크 잡 |
| `APP_PASSWORD` + auth 쿠키 | `APP_PASSWORD` + HMAC 서명 토큰 (`X-App-Token`) |
| `google-genai` SDK | Gemini REST 직접 호출 (의존성 없음) |
| Render 환경변수 | `supabase secrets set` |

### 브리핑을 청크로 쪼갠 이유

Edge Function은 요청당 실행시간 제한이 있습니다. 원본은 30~100곳의 카카오맵 상세·블로그·
Gemini 요약을 한 요청에서 1~2분에 걸쳐 처리했는데, 그대로 옮기면 타임아웃에 걸립니다.

그래서 잡을 만들고 10곳씩 나눠 처리합니다. `claim_briefing_chunk()`가 행 잠금으로 구간을
배정하므로 프론트가 워커 2개를 동시에 굴려도 같은 구간이 중복 처리되지 않습니다.
부수 효과로 **결과가 도착하는 대로 화면에 채워져** 체감 속도는 원본보다 낫습니다.

## 배포

### 0. 준비

- Supabase 프로젝트 생성 → 프로젝트 ref(`abcdefghijklmnop`)와 service_role 키를 확보
- [Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started) 설치

### 1. 시크릿 등록

Render 환경변수에 넣어두었던 값들을 그대로 옮깁니다.

```bash
supabase secrets set \
  KAKAO_REST_API_KEY='카카오 REST 키' \
  GEMINI_API_KEY='제미나이 키' \
  --project-ref "$SUPABASE_PROJECT_REF"

# 선택 사항
supabase secrets set \
  GROQ_API_KEY='...' \
  KAKAO_JS_KEY='...' \
  APP_PASSWORD='접속 암호' \
  MY_PLACE_LINKS='https://naver.me/xxxx,https://naver.me/yyyy' \
  --project-ref "$SUPABASE_PROJECT_REF"
```

| 시크릿 | 필수 | 설명 |
|---|---|---|
| `KAKAO_REST_API_KEY` | ✅ | 카카오 장소·블로그 검색 |
| `GEMINI_API_KEY` | | 없으면 카카오맵 메뉴판 기준으로만 표시 |
| `GROQ_API_KEY` | | Gemini 한도 소진 시 폴백 |
| `KAKAO_JS_KEY` | | 지도 보기. 없으면 지도 버튼 비활성 |
| `APP_PASSWORD` | | 설정 시 접속 암호 요구. 미설정이면 누구나 접속 |
| `MY_PLACE_LINKS` | | 네이버지도 공유 링크 (쉼표/공백 구분) |

`SUPABASE_URL`과 `SUPABASE_SERVICE_ROLE_KEY`는 Edge Runtime이 자동 주입하므로 등록하지 않습니다.

### 2. 배포

```bash
export SUPABASE_PROJECT_REF=abcdefghijklmnop
export SUPABASE_SERVICE_ROLE_KEY=eyJ...
./scripts/deploy.sh
```

스크립트가 마이그레이션 적용 → 함수 배포 → `web/index.html` 업로드까지 합니다.

접속 주소:

```
https://<ref>.supabase.co/storage/v1/object/public/app/index.html
```

### 3. 카카오 개발자 콘솔 (지도를 쓸 때만)

카카오 JS SDK는 등록된 도메인에서만 동작합니다. Render 도메인 대신
`https://<ref>.supabase.co`를 **내 애플리케이션 > 플랫폼 > Web 사이트 도메인**에 추가하세요.
이걸 안 하면 카드 목록은 정상인데 "지도로 보기"만 실패합니다.

## 운영

### 캐시 수명

메모리 캐시였을 때는 프로세스 수명이 사실상 TTL이었지만, 이제 영속이라 명시적 수명을 둡니다
(`supabase/functions/api/env.ts`의 `TTL`).

| 항목 | 수명 |
|---|---|
| 검색 결과 | 3일 |
| 브리핑 요약 | 3일 |
| 카카오맵 상세(별점·영업시간) | 7일 |
| 대표 사진 | 14일 |
| 인증 맛집 목록 | 14일 |
| 내 저장 맛집 | 1시간 |

만료분 정리는 `purge_expired_cache()`입니다. 무료 플랜에서도 pg_cron을 쓸 수 있으면
하루 한 번 걸어두면 됩니다 (SQL Editor에서 실행):

```sql
create extension if not exists pg_cron;
select cron.schedule('purge-food-cache', '0 4 * * *', 'select public.purge_expired_cache()');
```

걸지 않아도 동작에는 문제가 없습니다 — 만료된 값은 읽을 때 무시되고, 디스크만 조금 씁니다.

### 진단

```
GET https://<ref>.supabase.co/functions/v1/api/diag
```

내 저장 맛집 링크 인식 여부와 네이버 API 응답 상태를 보여줍니다 (원본 `/diag`와 동일).

### 로그

```bash
supabase functions logs api --project-ref "$SUPABASE_PROJECT_REF"
```

## 보안 메모

- 모든 테이블에 RLS를 켜고 **정책을 하나도 두지 않았습니다.** anon 키로는 아무것도 읽히지
  않고, service_role 키를 가진 Edge Function만 접근합니다. service_role 키는 프론트로
  나가지 않습니다.
- Edge Function은 `verify_jwt = false`입니다. 프론트가 Supabase 인증 대신 `APP_PASSWORD`로
  자체 인증하기 때문입니다. **`APP_PASSWORD`를 설정하지 않으면 함수가 공개 상태**가 되어
  누구나 호출할 수 있고, 카카오·Gemini 무료 한도가 도용될 수 있습니다. 공개 URL로 쓸
  거라면 반드시 설정하세요.
- 토큰은 HMAC-SHA256 서명 + 30일 만료입니다. 암호를 바꾸면 기존 토큰이 전부 무효화됩니다.

## 이식 정확도 확인

원본 파이썬과 이식본이 같은 결과를 내는지 대조하는 하네스가 있습니다
(카테고리 필터·이름 정규화·거리 계산·배지 판정 등 순수 로직 294건).

```bash
./scripts/parity.sh
```

## 원본 파이썬은 어떻게 되나

`food_briefing_app.py`는 그대로 두었습니다. 사내망·로컬에서 `python food_briefing_app.py`로
계속 쓸 수 있고, `내맛집링크.txt`·`proxy.txt` 같은 로컬 전용 기능도 살아 있습니다.
Supabase 배포와는 독립이며, 두 쪽이 같은 로직을 유지하는지는 `scripts/parity.sh`로 확인합니다.
