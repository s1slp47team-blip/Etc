// 맛집 브리핑 API (Supabase Edge Function)
//
// 파이썬판 Handler(http.server) 를 대체한다. 라우팅은 /functions/v1/api/<subpath>.
//   POST /login        접속 암호 → 토큰
//   GET  /search       동네 검색 (기존 GET /search)
//   POST /enrich/start 브리핑 잡 생성   ┐ 기존 POST /enrich 를 실행시간 제한에 맞춰
//   POST /enrich/step  구간 하나 처리   ┘ 둘로 나눈 것
//   GET  /enrich/result 잡의 현재 결과 (새로고침 복구용)
//   GET  /diag         진단 (기존 /diag)
//   GET  /sdk          카카오맵 JS SDK 프록시 (기존 SDK_PATH)
//   GET  /config       프론트에 필요한 설정 (암호 필요 여부, JS 키 유무)

import { JS_KEY, KAKAO_KEY, TTL, requireKakaoKey } from "./env.ts";
import { corsHeaders, fetchT, json, 안전하게 } from "./util.ts";
import { 검색키, 캐시쓰기, 캐시읽기 } from "./db.ts";
import { 동네좌표 } from "./kakao.ts";
import { 맛집검색, type Place } from "./places.ts";
import { 잡결과, 잡생성, 잡스텝, type 브리핑항목 } from "./briefing.ts";
import { 공유ID추출, 저장링크들 } from "./naver.ts";
import { 암호필요, 토큰발급, 토큰유효 } from "./auth.ts";

interface 검색조건 {
  q: string;
  radius: number;
  meal: string;
  cnt: number;
  cert: string;
  rate: boolean;
  mine: string;
}

const MEALS = ["all", "lunch", "dinner", "cafe"];
const CERTS = ["none", "any", "michelin", "blueribbon", "century", "bwchef"];
const MINES = ["prefer", "only", "off"];

const 정수 = (v: unknown, 기본: number, 최소: number, 최대: number) => {
  const n = parseInt(String(v ?? ""), 10);
  return Math.min(Math.max(Number.isFinite(n) ? n : 기본, 최소), 최대);
};

/** 파이썬판 do_GET/do_POST 의 파라미터 검증과 동일한 범위·기본값 */
function 조건읽기(get: (k: string) => unknown): 검색조건 {
  const meal = String(get("meal") ?? "all");
  const cert = String(get("cert") ?? "none");
  const mine = String(get("mine") ?? "prefer");
  return {
    q: String(get("q") ?? get("query") ?? "").trim(),
    radius: 정수(get("radius"), 2000, 100, 3000),
    meal: MEALS.includes(meal) ? meal : "all",
    cnt: 정수(get("cnt"), 30, 10, 100),
    cert: CERTS.includes(cert) ? cert : "none",
    rate: String(get("rate") ?? "0") === "4",
    mine: MINES.includes(mine) ? mine : "prefer",
  };
}

async function 검색(조건: 검색조건) {
  if (!조건.q) return { error: "동네 이름을 입력하세요." };
  requireKakaoKey();

  const key = 검색키(조건);
  const cached = await 캐시읽기<{ center: string; places: Place[] }>("search", key);
  const detail = await 캐시읽기<브리핑항목[]>("detail", key);
  if (cached) return { ...cached, key, cached_detail: detail };

  const 좌표 = await 동네좌표(조건.q);
  if (!좌표) {
    return { error: `"${조건.q}" 위치를 찾지 못했습니다. 동네 이름을 다시 확인해 주세요.` };
  }
  const [center, x, y] = 좌표;
  const places = await 맛집검색(
    x, y, 조건.radius, 조건.meal, 조건.cnt, 조건.cert, 조건.rate, 조건.mine,
  );
  const result = { center, places };
  await 캐시쓰기("search", key, result, TTL.search);
  return { ...result, key, cached_detail: null };
}

// ── 카카오맵 JS SDK 프록시 ────────────────────────────────────
// 사내망/브라우저 정책이 dapi.kakao.com 을 차단하는 경우가 있어 대신 서빙한다.
let _sdk: ArrayBuffer | null = null;
async function 카카오SDK(): Promise<ArrayBuffer> {
  if (!_sdk) {
    const resp = await fetchT(
      `https://dapi.kakao.com/v2/maps/sdk.js?appkey=${JS_KEY}&autoload=false`,
      { timeoutMs: 10_000 },
    );
    if (!resp.ok) throw new Error(`SDK ${resp.status}`);
    _sdk = await resp.arrayBuffer();
  }
  return _sdk;
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: corsHeaders() });

  // /functions/v1/api/<subpath> → <subpath>
  const url = new URL(req.url);
  const sub = "/" + url.pathname.split("/").slice(4).filter(Boolean).join("/");
  const 토큰 = req.headers.get("x-app-token");

  try {
    // 인증이 필요 없는 경로
    if (sub === "/config") {
      return json({ auth_required: 암호필요(), map: Boolean(JS_KEY), kakao: Boolean(KAKAO_KEY) });
    }
    if (sub === "/login" && req.method === "POST") {
      const { pw } = await req.json().catch(() => ({ pw: "" }));
      const token = await 토큰발급(String(pw ?? ""));
      if (!token) return json({ error: "암호가 올바르지 않습니다." }, 401);
      return json({ token });
    }
    if (sub === "/sdk") {
      if (!JS_KEY) return new Response("// KAKAO_JS_KEY 미설정", { status: 200 });
      return new Response(await 카카오SDK(), {
        headers: {
          "Content-Type": "text/javascript; charset=utf-8",
          "Cache-Control": "public, max-age=3600",
          ...corsHeaders(),
        },
      });
    }

    if (!(await 토큰유효(토큰))) {
      return json({ error: "접속 암호 인증이 필요합니다.", need_login: true }, 401);
    }

    if (sub === "/search") {
      return json(await 검색(조건읽기((k) => url.searchParams.get(k))));
    }

    if (sub === "/enrich/start" && req.method === "POST") {
      const body = await req.json().catch(() => ({}));
      const 조건 = 조건읽기((k) => (body as Record<string, unknown>)[k]);
      const key = 검색키(조건);

      const 완성됨 = await 캐시읽기<브리핑항목[]>("detail", key);
      if (완성됨) return json({ done: true, items: 완성됨 });

      const base = await 캐시읽기<{ places: Place[] }>("search", key);
      if (!base) return json({ error: "먼저 검색을 실행하세요." });
      if (!base.places.length) return json({ done: true, items: [] });

      return json(await 잡생성(key, 조건.q, base.places));
    }

    if (sub === "/enrich/step" && req.method === "POST") {
      const { job } = await req.json().catch(() => ({ job: "" }));
      if (!job) return json({ error: "job 이 필요합니다." }, 400);
      return json(await 잡스텝(String(job)));
    }

    if (sub === "/enrich/result") {
      const job = url.searchParams.get("job");
      if (!job) return json({ error: "job 이 필요합니다." }, 400);
      return json({ items: await 잡결과(job) });
    }

    // 원격 진단 (내 저장 맛집 로드 상태) — 파이썬판 /diag
    if (sub === "/diag") {
      const 링크들 = 저장링크들();
      const 정보: Record<string, unknown> = { links: 링크들.length, kakao: Boolean(KAKAO_KEY) };
      if (링크들.length) {
        const fid = await 안전하게(() => 공유ID추출(링크들[0]), "", "공유ID");
        정보.share_id_ok = Boolean(fid);
        if (fid) {
          await 안전하게(async () => {
            const r = await fetchT(
              `https://pages.map.naver.com/save-pages/api/maps-bookmark/v3/shares/${fid}/bookmarks?start=0&limit=3`,
              { headers: { Accept: "application/json", Referer: "https://pages.map.naver.com/" }, timeoutMs: 15_000 },
            );
            정보.api_status = r.status;
            정보.api_body = (await r.text()).slice(0, 150);
            return null;
          }, null, "진단");
        }
      }
      return json(정보);
    }

    return json({ error: `알 수 없는 경로: ${sub}` }, 404);
  } catch (e) {
    console.error(sub, e);
    return json({ error: (e as Error).message });
  }
});
