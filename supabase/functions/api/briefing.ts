// 브리핑 생성 — 파이썬판 가게자료수집() / 브리핑생성() 의 이식.
//
// 파이썬판은 30~100곳을 한 요청 안에서 전부 처리했다(1~2분). Edge Function 은
// 요청당 실행시간 제한이 있어 그대로 옮길 수 없으므로, 잡을 만들고 클라이언트가
// STEP_SIZE(10곳) 단위로 나눠 호출하게 한다.
//   start → 잡 생성 (검색 캐시의 places 를 그대로 사용)
//   step  → 구간 하나 처리 후 그 구간의 결과만 반환 (여러 개를 병렬로 불러도 안전)
// 결과가 도착하는 대로 화면에 채워지므로 체감 속도도 파이썬판보다 낫다.

import { STEP_SIZE, TTL } from "./env.ts";
import { db, 캐시쓰기 } from "./db.ts";
import type { Place } from "./places.ts";
import {
  블로그정리,
  카카오블로그,
  카카오사진,
  카카오상세여러개,
  type 상세,
} from "./kakao.ts";
import { GEMINI_사용가능, 청크요약, type 가게자료 } from "./llm.ts";
import { pMap, 천단위 } from "./util.ts";

export interface 브리핑항목 {
  photo: string | null;
  menu: string;
  price: string;
  mood: string;
  reviews: string[];
  rating: number | null;
  rating_count: number | null;
}

/** 가게 1곳의 카카오맵 상세(메뉴판·사진·별점)와 카카오 블로그 후기를 모은다. */
async function 가게자료수집(
  동네: string,
  place: Place,
   상세맵: Map<string, 상세>,
): Promise<가게자료> {
  const 상세 = 상세맵.get(place.url) ?? {};
  const blogs = await 카카오블로그(`${동네} ${place.name}`);
  // 사진 우선순위: 카카오맵 상세 사진 → 상세 페이지 og:image → 없음
  const photo = 상세.photo ?? await 카카오사진(place.url);
  return {
    posts: 블로그정리(blogs),
    photo: photo ?? null,
    menus: 상세.menus ?? [],
    rating: 상세.rating ?? null,
    rating_count: 상세.rating_count ?? null,
  };
}

/** 요약 결과 + 카카오맵 메뉴판으로 카드 한 장을 완성한다. */
function 항목만들기(자료: 가게자료, s: Partial<import("./llm.ts").요약항목>): 브리핑항목 {
  const 메뉴판 = 자료.menus;

  // Gemini 가 못 채우면 카카오맵 메뉴판에서 직접 계산한다
  let menu = s.menu;
  if (!menu || menu === "정보 부족") {
    const 대표 = 메뉴판.filter((m) => m.recommend);
    const 원본 = 대표.length ? 대표 : 메뉴판;
    menu = 원본.slice(0, 3).map((m) => m.name).join(", ") || "정보 부족";
  }

  let price = s.price;
  if ((!price || price === "정보 부족") && 메뉴판.length) {
    const 가격들 = 메뉴판.map((m) => m.price).sort((a, b) => a - b);
    price = 가격들.length > 1
      ? `메뉴 ${천단위(가격들[0])}~${천단위(가격들[가격들.length - 1])}원`
      : `${천단위(가격들[0])}원`;
  }

  return {
    photo: 자료.photo,
    menu,
    price: price || "정보 부족",
    // mood 가 비면 배지를 표시하지 않는다 ("후기 없음" 같은 무의미한 배지 제거)
    mood: s.mood ?? "",
    reviews: (s.reviews ?? []).slice(0, 2),
    rating: 자료.rating,
    rating_count: 자료.rating_count,
  };
}

// ── 잡 관리 ───────────────────────────────────────────────────
export async function 잡생성(
  cacheKey: string,
   동네: string,
  places: readonly Place[],
): Promise<{ job: string; total: number; step: number }> {
  const { data, error } = await db()
    .from("briefing_jobs")
    .insert({
      cache_key: cacheKey,
      neighborhood: 동네,
      places,
      total: places.length,
    })
    .select("id")
    .single();
  if (error) throw new Error(`브리핑 잡 생성 실패: ${error.message}`);
  return { job: data.id, total: places.length, step: STEP_SIZE };
}

export interface 스텝결과 {
  done: boolean;
  start: number;
  end: number;
  items: 브리핑항목[];
  processed: number;
  total: number;
}

/** 구간 하나를 처리한다. 남은 구간이 없으면 done=true 로 최종 캐시까지 마무리. */
export async function 잡스텝(jobId: string): Promise<스텝결과> {
  const { data: job, error } = await db()
    .from("briefing_jobs")
    .select("neighborhood, places, total, cache_key, failed")
    .eq("id", jobId)
    .maybeSingle();
  if (error || !job) throw new Error("브리핑 작업을 찾을 수 없습니다. 다시 검색해 주세요.");

  // 구간 원자적 배정 — 클라이언트가 step 을 병렬로 불러도 중복 처리되지 않는다
  const { data: claim, error: cErr } = await db()
    .rpc("claim_briefing_chunk", { p_job: jobId, p_size: STEP_SIZE })
    .maybeSingle<{ start_idx: number; end_idx: number }>();
  if (cErr) throw new Error(`구간 배정 실패: ${cErr.message}`);

  const start = claim?.start_idx ?? job.total;
  const end = claim?.end_idx ?? job.total;

  if (start >= end) {
    // 남은 구간 없음 → 다른 스텝들이 다 끝났는지 확인하고 마무리
    return await 마무리(jobId, job);
  }

  const places = (job.places as Place[]).slice(start, end);
  const 동네 = job.neighborhood as string;

  // 상세는 검색 단계에서 이미 캐시돼 있어 대부분 DB 히트다 (파이썬판의 _상세결과캐시 역할)
  const 상세맵 = await 카카오상세여러개(places.map((p) => p.url), 10);
  // 카카오 검색 API 초당 제한 대응 — 파이썬판과 같은 동시 10개
  const 자료들 = await pMap(places, (p) => 가게자료수집(동네, p, 상세맵), 10);

  const 요약 = await 청크요약(동네, places, 자료들);
  const items = places.map((_, i) => 항목만들기(자료들[i], 요약.get(i) ?? {}));

  const { error: iErr } = await db().from("briefing_items").upsert(
    items.map((item, i) => ({ job_id: jobId, idx: start + i, item })),
    { onConflict: "job_id,idx" },
  );
  if (iErr) console.warn("브리핑 항목 저장 실패:", iErr.message);

  // 요약이 빠진 가게 수를 누적한다 — 최종 캐시 여부 판단에 쓴다.
  // 스텝이 병렬로 돌 수 있으므로 읽고-쓰기 대신 원자적 증가를 쓴다.
  const 미요약 = places.length - 요약.size;
  if (GEMINI_사용가능 && 미요약 > 0) {
    const { error } = await db().rpc("bump_briefing_failed", { p_job: jobId, p_n: 미요약 });
    if (error) console.warn("failed 카운트 갱신 실패:", error.message);
  }

  const { count } = await db()
    .from("briefing_items")
    .select("idx", { count: "exact", head: true })
    .eq("job_id", jobId);

  const processed = count ?? end;
  const done = processed >= job.total;
  // 마지막 구간을 처리한 워커가 그대로 멈추면 최종 캐시가 기록되지 않는다.
  // 여기서 마무리를 직접 부른다 (마무리는 완료 여부를 다시 확인하므로 중복 호출도 안전).
  if (done) await 마무리(jobId, job);

  return { done, start, end, items, processed, total: job.total };
}

async function 마무리(
  jobId: string,
  job: { total: number; cache_key: string },
): Promise<스텝결과> {
  const { data: rows } = await db()
    .from("briefing_items")
    .select("idx, item")
    .eq("job_id", jobId)
    .order("idx");

  const 완료 = rows?.length ?? 0;
  if (완료 >= job.total && job.total > 0) {
    const items = (rows ?? []).map((r) => r.item as 브리핑항목);
    // failed 는 다른 스텝들이 갱신했을 수 있어 지금 다시 읽는다
    const { data: 최신 } = await db()
      .from("briefing_jobs").select("failed").eq("id", jobId).maybeSingle();
    // 대부분(80% 이상) 요약됐을 때만 캐시한다 — 한도 초과로 통째로/절반쯤
    // 빈 결과가 캐시에 박제되는 것을 막는다 (파이썬판 요약성공 판정과 동일 취지)
    const 요약성공 = !GEMINI_사용가능 || (최신?.failed ?? 0) <= job.total * 0.2;
    if (요약성공) await 캐시쓰기("detail", job.cache_key, items, TTL.detail);
    await db().from("briefing_jobs").update({ status: "done" }).eq("id", jobId);
  }

  return {
    done: 완료 >= job.total,
    start: job.total,
    end: job.total,
    items: [],
    processed: 완료,
    total: job.total,
  };
}

/** 잡의 현재까지 결과 전체 (새로고침·재접속 시 사용) */
export async function 잡결과(jobId: string): Promise<(브리핑항목 | null)[]> {
  const { data: job } = await db()
    .from("briefing_jobs").select("total").eq("id", jobId).maybeSingle();
  if (!job) return [];
  const { data: rows } = await db()
    .from("briefing_items").select("idx, item").eq("job_id", jobId).order("idx");
  const out = new Array<브리핑항목 | null>(job.total).fill(null);
  for (const r of rows ?? []) out[r.idx] = r.item as 브리핑항목;
  return out;
}
