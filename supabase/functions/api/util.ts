// 파이썬판이 ThreadPoolExecutor·re·math 로 하던 잡일들의 Deno 대응물.

/** ThreadPoolExecutor(max_workers=N) + pool.map 과 같은 역할.
 *  입력 순서를 유지한 결과 배열을 돌려준다. */
export async function pMap<T, R>(
  items: readonly T[],
  fn: (item: T, index: number) => Promise<R>,
  concurrency: number,
): Promise<R[]> {
  const out = new Array<R>(items.length);
  let next = 0;
  const worker = async () => {
    for (;;) {
      const i = next++;
      if (i >= items.length) return;
      out[i] = await fn(items[i], i);
    }
  };
  const n = Math.max(1, Math.min(concurrency, items.length));
  await Promise.all(Array.from({ length: n }, worker));
  return out;
}

export const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** _이름정규화 — 한글·영숫자만 남기고 소문자화 */
export function 이름정규화(s: string): string {
  return (s ?? "").replace(/[^0-9a-zA-Z가-힣]/g, "").toLowerCase();
}

/** _대략거리m — 짧은 거리용 근사 (위도 1도≈111km, 경도는 cos 보정) */
export function 대략거리m(
  lat1: number,
  lng1: number,
  lat2: number,
  lng2: number,
): number {
  const dy = (lat1 - lat2) * 111_000;
  const dx = (lng1 - lng2) * 111_000 *
    Math.cos(((lat1 + lat2) / 2) * Math.PI / 180);
  return Math.hypot(dx, dy);
}

/** _태그제거 */
export function 태그제거(s: string): string {
  return (s ?? "")
    .replace(/<[^>]+>/g, "")
    .replace(/&quot;/g, '"')
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">");
}

/** 천 단위 쉼표 — 파이썬 f"{n:,}" */
export function 천단위(n: number): string {
  return n.toLocaleString("en-US");
}

/** fetch + 타임아웃. Edge Function 은 응답이 안 오는 외부 API 때문에
 *  실행시간 제한에 걸리는 게 가장 흔한 실패라 모든 외부 호출에 건다. */
export async function fetchT(
  url: string,
  init: RequestInit & { timeoutMs?: number } = {},
): Promise<Response> {
  const { timeoutMs = 10_000, ...rest } = init;
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), timeoutMs);
  try {
    return await fetch(url, { ...rest, signal: ac.signal });
  } finally {
    clearTimeout(timer);
  }
}

/** 실패해도 전체를 멈추면 안 되는 외부 호출용 — 실패 시 기본값 */
export async function 안전하게<T>(
  fn: () => Promise<T>,
   기본값: T,
  라벨 = "",
): Promise<T> {
  try {
    return await fn();
  } catch (e) {
    if (라벨) console.warn(`${라벨} 실패(무시):`, (e as Error).message);
    return 기본값;
  }
}

export function json(body: unknown, status = 200, extra: HeadersInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...corsHeaders(), ...extra },
  });
}

export function corsHeaders(): Record<string, string> {
  // 프론트(Storage)와 함수는 같은 오리진(<ref>.supabase.co)이라 CORS 가 필수는
  // 아니지만, 로컬 개발이나 별도 도메인에 프론트를 올릴 때를 위해 열어둔다.
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "authorization, content-type, x-app-token",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  };
}
