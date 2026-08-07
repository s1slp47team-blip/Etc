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

## 배포 — 처음부터 끝까지

Render는 더 이상 쓰지 않는다는 전제로, Supabase만으로 같은 기능이 나오게 하는 전체 절차입니다.

### 자주 쓰는 링크

`<ref>` 자리에 내 프로젝트 ref를 넣으면 됩니다. `_`를 그대로 두면 Supabase가 프로젝트를
고르라고 물어봅니다.

| 용도 | 링크 |
|---|---|
| 프로젝트 만들기 | https://supabase.com/dashboard/new |
| 프로젝트 목록 · ref 확인 | https://supabase.com/dashboard/projects |
| **시크릿(암호·API 키) 등록** | https://supabase.com/dashboard/project/_/settings/functions |
| service_role 키 확인 | https://supabase.com/dashboard/project/_/settings/api |
| SQL Editor | https://supabase.com/dashboard/project/_/sql |
| Storage 버킷 | https://supabase.com/dashboard/project/_/storage/buckets |
| 함수 로그 | https://supabase.com/dashboard/project/_/functions |
| Supabase CLI 설치 | https://supabase.com/docs/guides/local-development/cli/getting-started |

API 키를 다시 발급받아야 한다면:

| 키 | 발급처 |
|---|---|
| `KAKAO_REST_API_KEY`, `KAKAO_JS_KEY` | https://developers.kakao.com/console/app |
| `GEMINI_API_KEY` | https://aistudio.google.com/apikey |
| `GROQ_API_KEY` | https://console.groq.com/keys |

### 1단계 — 프로젝트 만들고 ref 확인

https://supabase.com/dashboard/new 에서 프로젝트를 만듭니다. 리전은 `Northeast Asia (Seoul)`을
고르는 게 카카오·네이버 API 응답이 가장 빠릅니다.

만들고 나면 주소창이 이렇게 됩니다:

```
https://supabase.com/dashboard/project/abcdefghijklmnop
                                       └──────┬───────┘
                                          이게 ref
```

### 2단계 — 암호와 API 키 등록 (Render의 Environment 탭에 해당)

https://supabase.com/dashboard/project/_/settings/functions 로 갑니다.
(대시보드에서는 **Project Settings → Edge Functions → Secrets**)

`Add new secret`을 눌러 아래를 하나씩 넣습니다. Render의 Environment 탭을 옆에 띄워놓고
이름·값을 그대로 옮겨 적으면 됩니다.

| 시크릿 이름 | 필수 | 설명 |
|---|---|---|
| `KAKAO_REST_API_KEY` | ✅ | 카카오 장소·블로그 검색 |
| `APP_PASSWORD` | ✅ | 접속 암호. **미설정 시 앱이 공개됩니다** (아래 주의) |
| `GEMINI_API_KEY` | | 없으면 카카오맵 메뉴판 기준으로만 표시 |
| `GROQ_API_KEY` | | Gemini 한도 소진 시 폴백 |
| `KAKAO_JS_KEY` | | 지도 보기. 없으면 지도 버튼 비활성 |
| `MY_PLACE_LINKS` | | 네이버지도 공유 링크 (쉼표/공백 구분) |

`APP_PASSWORD`는 Render에서 쓰던 값을 그대로 넣으면 됩니다. Render에서 안 쓰고 있었다면
지금 아무 문자열이나 정해서 넣으세요 — 이 값이 접속 화면에서 물어보는 암호가 됩니다.

`MY_PLACE_LINKS`는 이제 **환경변수만** 동작합니다. 파이썬판처럼 `내맛집링크.txt` 파일을
쓰고 계셨다면, Edge Function에는 파일 시스템이 없으므로 파일 안의 링크들을 쉼표로 이어
붙여 이 시크릿에 넣으세요.

CLI가 편하면 한 줄로도 됩니다. 값은 **반드시 작은따옴표로** 감싸세요 (`$`·`!`·공백이
셸에 먹힙니다):

```bash
export SUPABASE_PROJECT_REF=abcdefghijklmnop

supabase secrets set \
  KAKAO_REST_API_KEY='카카오REST키' \
  APP_PASSWORD='접속암호' \
  GEMINI_API_KEY='제미나이키' \
  GROQ_API_KEY='그록키' \
  KAKAO_JS_KEY='카카오JS키' \
  MY_PLACE_LINKS='https://naver.me/xxxx,https://naver.me/yyyy' \
  --project-ref "$SUPABASE_PROJECT_REF"
```

**등록하면 안 되는 것**

- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` — Edge Runtime이 자동 주입합니다.
  직접 넣으면 거부됩니다.
- `PORT` — Render가 주입하던 값입니다. Supabase에는 포트 개념이 없습니다.
- `PYTHON_VERSION` 등 빌드 변수 — 파이썬 런타임 자체가 없습니다.

### 3단계 — 배포

service_role 키를 https://supabase.com/dashboard/project/_/settings/api 에서 복사한 뒤:

```bash
export SUPABASE_PROJECT_REF=abcdefghijklmnop
export SUPABASE_SERVICE_ROLE_KEY=eyJ...
./scripts/deploy.sh
```

스크립트가 마이그레이션 적용 → 함수 배포 → `web/index.html` 업로드까지 합니다.

### 4단계 — 카카오 개발자 콘솔에 도메인 등록 (지도를 쓸 때만)

https://developers.kakao.com/console/app → 내 애플리케이션 → **플랫폼 → Web → 사이트 도메인**

Render 도메인을 지우고 아래를 추가합니다:

```
https://abcdefghijklmnop.supabase.co
```

이걸 안 하면 카드 목록은 정상인데 "지도로 보기"만 실패합니다.

### 5단계 — 접속

```
https://abcdefghijklmnop.supabase.co/storage/v1/object/public/app/index.html
```

이 주소가 Render URL을 대체합니다. 북마크해 두세요.

### 6단계 — 잘 들어갔는지 확인

```
https://abcdefghijklmnop.supabase.co/functions/v1/api/config
```

```json
{"auth_required":true,"map":true,"kakao":true}
```

- `kakao: false` → `KAKAO_REST_API_KEY` 누락
- `map: false` → `KAKAO_JS_KEY` 누락
- `auth_required: false` → **`APP_PASSWORD` 누락 (앱이 공개 상태)**

내 저장 맛집은 `/functions/v1/api/diag`에서 링크 인식 여부까지 볼 수 있습니다.

### 시크릿을 바꾼 뒤에는

이미 떠 있는 인스턴스가 옛 값을 들고 있을 수 있습니다. 한 번 다시 배포하면 즉시 정리됩니다.

```bash
supabase functions deploy api --project-ref "$SUPABASE_PROJECT_REF"
```

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
