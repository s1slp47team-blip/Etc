// 내 저장 맛집 (네이버지도 공유 리스트) — 파이썬판 1.7절의 이식.
//
// 네이버는 개인 저장 장소 공식 API를 제공하지 않는다. 대신 지도 앱의 '공유' 기능으로
// 만든 공개 리스트를, 공유 페이지가 쓰는 내부 API(v3/shares)에서 읽어온다.
//
// 파이썬판은 1시간 메모리 캐시라 프로세스가 재시작될 때마다 전부 다시 크롤링했다.
// 여기서는 my_places 테이블에 남기므로 갱신 주기 전에는 외부 호출이 없다.

import { MY_PLACE_LINKS, TTL } from "./env.ts";
import { db } from "./db.ts";
import { fetchT, 이름정규화 } from "./util.ts";
import { 브라우저_UA } from "./kakao.ts";

const 저장리스트_API =
  "https://pages.map.naver.com/save-pages/api/maps-bookmark/v3/shares";
const 저장리스트_헤더 = {
  "User-Agent": 브라우저_UA,
  "Accept": "application/json",
  "Referer": "https://pages.map.naver.com/",
};

export interface 저장장소 {
  name: string;
  lat: number;
  lng: number;
  folder: string;
  norm_name: string;
}

/** 공유 링크 출처: MY_PLACE_LINKS 시크릿 (쉼표/공백 구분).
 *  파이썬판의 내맛집링크.txt 는 Edge Function 에 파일 시스템이 없어 지원하지 않는다. */
export function 저장링크들(): string[] {
  if (!MY_PLACE_LINKS) return [];
  return MY_PLACE_LINKS.split(/[,\s]+/).filter((s) => s.trim() && !s.startsWith("#"));
}

/** naver.me 단축링크 또는 map.naver.com 공유 URL에서 32자 공유 ID를 얻는다. */
export async function 공유ID추출(링크: string): Promise<string> {
  const s = 링크.trim();
  if (!s || s.startsWith("#")) return "";
  const m = s.match(/([0-9a-f]{32})/);
  if (m) return m[1];
  try { // 단축링크는 리다이렉트를 따라가 최종 URL에서 뽑는다
    const resp = await fetchT(s, { headers: 저장리스트_헤더, redirect: "follow", timeoutMs: 10_000 });
    const byUrl = resp.url.match(/([0-9a-f]{32})/);
    if (byUrl) return byUrl[1];
    const body = (await resp.text()).slice(0, 4000);
    return body.match(/([0-9a-f]{32})/)?.[1] ?? "";
  } catch {
    return "";
  }
}

async function 링크하나읽기(링크: string): Promise<저장장소[]> {
  const fid = await 공유ID추출(링크);
  if (!fid) return [];
  const 목록: 저장장소[] = [];
  try {
    const 메타resp = await fetchT(`${저장리스트_API}/${fid}`, {
      headers: 저장리스트_헤더,
      timeoutMs: 15_000,
    });
    const 메타 = await 메타resp.json().catch(() => null);
    const 폴더명 = 메타?.folder?.name || "저장";

    for (let 시작 = 0; ; 시작 += 300) { // 공유 API는 한 번에 최대 수백 건 — 넉넉히 페이징
      const qs = new URLSearchParams({ start: String(시작), limit: "300" });
      const resp = await fetchT(`${저장리스트_API}/${fid}/bookmarks?${qs}`, {
        headers: 저장리스트_헤더,
        timeoutMs: 20_000,
      });
      const 항목들 = (await resp.json().catch(() => null))?.bookmarkList ?? [];
      for (const b of 항목들) {
        if (b?.name && b?.px && b?.py) {
          목록.push({
            name: b.name,
            lat: parseFloat(b.py),
            lng: parseFloat(b.px),
            folder: 폴더명,
            norm_name: 이름정규화(b.name),
          });
        }
      }
      if (항목들.length < 300) break;
    }
  } catch (e) {
    console.warn(`내 저장 맛집 로드 실패(${링크.slice(0, 40)}):`, (e as Error).message);
  }
  return 목록;
}

async function 갱신필요한가(): Promise<boolean> {
  const { data } = await db()
    .from("my_places_sync")
    .select("refreshed_at")
    .eq("id", true)
    .maybeSingle();
  if (!data) return true;
  return Date.now() - new Date(data.refreshed_at).getTime() > TTL.myPlaces * 1000;
}

async function 테이블에서읽기(): Promise<저장장소[]> {
  const out: 저장장소[] = [];
  // PostgREST 기본 상한(1000행)을 넘는 저장 리스트도 있을 수 있어 페이징한다.
  for (let from = 0; ; from += 1000) {
    const { data, error } = await db()
      .from("my_places")
      .select("name, lat, lng, folder, norm_name")
      .order("id")
      .range(from, from + 999);
    if (error || !data?.length) break;
    out.push(...(data as 저장장소[]));
    if (data.length < 1000) break;
  }
  return out;
}

/** 저장 리스트 전체를 반환. 갱신 주기(1시간)가 지났을 때만 네이버를 다시 읽는다. */
export async function 내맛집목록(): Promise<저장장소[]> {
  const 링크들 = 저장링크들();
  if (!링크들.length) return []; // 링크가 없으면 기능 자체가 비활성

  if (!(await 갱신필요한가())) {
    const 저장분 = await 테이블에서읽기();
    if (저장분.length) return 저장분;
  }

  const 묶음 = await Promise.all(링크들.map(링크하나읽기));
  const 목록 = 묶음.flat();

  if (목록.length) {
    // 갱신 성공 시에만 교체한다. 네이버가 일시적으로 막혀 빈 결과가 오면
    // 기존 데이터를 지우지 않고 그대로 쓴다 (파이썬판보다 나아진 점).
    await db().from("my_places").delete().neq("id", 0);
    for (let i = 0; i < 목록.length; i += 500) {
      const { error } = await db().from("my_places").insert(목록.slice(i, i + 500));
      if (error) console.warn("내 저장 맛집 저장 실패:", error.message);
    }
    await db().from("my_places_sync").upsert({
      id: true,
      refreshed_at: new Date().toISOString(),
      link_count: 링크들.length,
      place_count: 목록.length,
    });
    console.log(`내 저장 맛집 ${목록.length}곳 로드`);
    return 목록;
  }

  return await 테이블에서읽기();
}

/** 폴더 이름을 읽어 배지 문구를 만든다 (가본곳/가볼곳/카페). */
export function 저장배지(폴더명: string): string {
  if (폴더명.includes("가본")) return "♥ 가본곳";
  if (폴더명.includes("가볼")) return "♡ 가볼곳";
  if (폴더명.includes("카페") || 폴더명.includes("디저트")) return "☕ 내저장";
  return "♥ 내저장";
}
