// 환경변수 — 기존 _env() 의 역할.
// 파이썬판은 환경변수가 없을 때 윈도우 레지스트리를 뒤졌지만, Edge Function 에는
// `supabase secrets set` 으로 넣은 값만 존재한다.

export const KAKAO_KEY = Deno.env.get("KAKAO_REST_API_KEY") ?? "";
export const GEMINI_KEY = Deno.env.get("GEMINI_API_KEY") ?? "";
export const GROQ_KEY = Deno.env.get("GROQ_API_KEY") ?? "";
export const JS_KEY = Deno.env.get("KAKAO_JS_KEY") ?? "";
export const APP_PASSWORD = Deno.env.get("APP_PASSWORD") ?? "";
export const MY_PLACE_LINKS = Deno.env.get("MY_PLACE_LINKS") ?? "";

// SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY 는 Edge Runtime 이 자동 주입한다.
export const SUPABASE_URL = Deno.env.get("SUPABASE_URL") ?? "";
export const SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";

// 무료 티어에서 고정 버전 모델(2.5-flash 등)은 일일 한도가 작아 금방 소진된다.
// latest 별칭은 별도 한도 버킷을 쓰므로 이걸 사용 (단순 요약에 충분)
export const GEMINI_MODEL = "gemini-flash-latest";
export const GROQ_MODEL = "llama-3.3-70b-versatile";

export const 맛집수 = 30;

// 한 step 에서 처리할 가게 수. Edge Function 실행시간 제한 안에 확실히 끝나도록
// 잡는다 (10곳 = 카카오 호출 ~30건 + Gemini 1회).
export const STEP_SIZE = 10;

// 캐시 유지 기간 — 메모리 캐시였을 때는 프로세스 수명이 사실상 TTL 이었다.
// 이제 영속이므로 항목별로 명시적인 수명을 준다.
export const TTL = {
  search: 60 * 60 * 24 * 3, // 검색 결과 3일 (신규 개업·폐업 반영)
  detail: 60 * 60 * 24 * 3, // 브리핑 요약 3일
  place: 60 * 60 * 24 * 7, // 카카오맵 상세(별점·영업시간) 7일
  photo: 60 * 60 * 24 * 14, // 대표 사진 14일
  cert: 60 * 60 * 24 * 14, // 인증 맛집 목록 14일 (거의 안 바뀜)
  myPlaces: 60 * 60, // 내 저장 맛집 1시간 (기존 내맛집갱신주기와 동일)
};

export function requireKakaoKey(): void {
  if (!KAKAO_KEY) {
    throw new Error(
      "KAKAO_REST_API_KEY 시크릿이 없습니다. " +
        "`supabase secrets set KAKAO_REST_API_KEY=...` 로 등록하세요.",
    );
  }
}
