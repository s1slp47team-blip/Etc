// 카카오 로컬/블로그 검색 + 카카오맵 내부 API(panel3) — 파이썬판 1~2절의 이식.

import { KAKAO_KEY, TTL } from "./env.ts";
import { 캐시여러개쓰기, 캐시여러개읽기, 캐시쓰기, 캐시읽기 } from "./db.ts";
import { fetchT, pMap, sleep, 태그제거 } from "./util.ts";

export const 브라우저_UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36";

const KAKAO_PANEL_HEADERS = {
  "User-Agent": 브라우저_UA,
  "Accept": "application/json",
  "Origin": "https://place.map.kakao.com",
  "Referer": "https://place.map.kakao.com/",
  "pf": "web",
};

export interface KakaoDoc {
  id: string;
  place_name: string;
  category_name: string;
  road_address_name: string;
  address_name: string;
  phone: string;
  place_url: string;
  x: string;
  y: string;
  distance?: string;
  badges?: string[];
  _저장배지?: string;
  _상세?: 상세;
}

export interface 메뉴 {
  name: string;
  price: number;
  recommend: boolean;
}

export interface 상세 {
  menus?: 메뉴[];
  photo?: string | null;
  rating?: number | null;
  rating_count?: number | null;
  hours?: string;
  open_status?: string;
  booking?: boolean;
}

async function kakaoGet(path: string, params: Record<string, string | number>): Promise<any> {
  const qs = new URLSearchParams(
    Object.entries(params).map(([k, v]) => [k, String(v)]),
  );
  const resp = await fetchT(`https://dapi.kakao.com/v2/local/${path}?${qs}`, {
    headers: { Authorization: `KakaoAK ${KAKAO_KEY}` },
    timeoutMs: 15_000,
  });
  if (!resp.ok) {
    throw new Error(`카카오 API 오류 [${resp.status}] ${(await resp.text()).slice(0, 200)}`);
  }
  return await resp.json();
}

/** 동네 이름 → [중심지명, 경도x, 위도y]. 주소 검색 우선, 없으면 키워드 검색. */
export async function 동네좌표(
  query: string,
): Promise<[string, number, number] | null> {
  const addr = await kakaoGet("search/address.json", { query, size: 1 });
  if (addr.documents?.length) {
    const d = addr.documents[0];
    return [d.address_name, parseFloat(d.x), parseFloat(d.y)];
  }
  const kw = await kakaoGet("search/keyword.json", { query, size: 1 });
  if (kw.documents?.length) {
    const d = kw.documents[0];
    return [d.place_name, parseFloat(d.x), parseFloat(d.y)];
  }
  return null;
}

/** 키워드 검색 결과 수집 (정확도순).
 *  그룹코드: FD6=음식점, CE7=카페 (카카오는 카페를 별도 그룹으로 분류) */
export async function 장소수집(
  query: string,
  x: number,
  y: number,
  radius: number,
   최대 = 45,
  그룹코드 = "FD6",
): Promise<KakaoDoc[]> {
  const docs: KakaoDoc[] = [];
  for (let page = 1; docs.length < 최대 && page <= 3; page++) {
    const data = await kakaoGet("search/keyword.json", {
      query,
      category_group_code: 그룹코드,
      x,
      y,
      radius,
      size: 15,
      page,
    });
    docs.push(...(data.documents ?? []));
    if (data.meta?.is_end) break;
  }
  return docs;
}

// ── 카테고리 필터 (파이썬판과 동일한 목록) ────────────────────
// 카카오 카테고리 경로("음식점 > 한식 > 육류,고기 > 삼겹살") 부분일치 기준.
// 저녁: 술을 곁들이기 좋은 업종 / 점심: 술집·안주 전문 업종 제외 → 식사 위주
const 술어울림_카테고리 = [
  "술집", "호프", "요리주점", "포장마차", "민속주점", "와인", "칵테일", "오뎅바",
  "육류,고기", "곱창", "막창", "족발", "보쌈", "회", "참치", "해물", "생선",
  "게,대게", "조개", "치킨", "닭발", "오리",
];
// 저녁 화이트리스트('육류,고기' 등)에 걸리지만 술 동반성이 약한(식사 전문) 세부 업종은 뺀다
const 저녁제외_카테고리 = [
  "삼계탕", "죽", "도시락", "곰탕", "설렁탕", "갈비탕", "국밥", "백반",
  "가정식", "기사식당", "국수", "칼국수", "냉면",
];
// 점심은 '식사'가 목적 — 술집 계열과 술 동반성이 강한 안주·구이·회 전문점을 뺀다.
// (육류,고기 전체를 빼면 갈비탕·불고기 같은 식사류까지 사라져 세부 업종만 제외)
const 점심제외_카테고리 = [
  "술집", "호프", "요리주점", "포장마차", "민속주점", "와인", "칵테일", "오뎅바",
  "곱창", "막창", "닭발", "삼겹살", "회", "참치", "양꼬치", "족발", "보쌈",
];
// 카페·디저트: 카카오 카페 그룹(CE7) + 음식점 그룹의 제과·베이커리·아이스크림까지.
// 단, 술집으로 운영되는 곳과 룸카페·보드게임방 등 비디저트 테마는 제외.
const 카페포함_카테고리 = [
  "카페", "제과", "베이커리", "아이스크림", "빙수", "디저트", "브런치", "도넛", "케이크",
];
const 카페제외_카테고리 = [
  "술집", "호프", "요리주점", "포장마차",
  // 음료·디저트가 목적이 아닌 공간 대여형·체험형 카페
  "룸카페", "만화카페", "보드게임", "PC방", "스터디", "방탈출", "애견", "애완",
  "고양이", "동물", "키즈", "포토", "사진", "공방", "네일", "타로", "마사지",
];
// 카카오가 '테마카페'로만 분류하는 방탈출·체험형 업소는 카테고리로 못 걸러 상호로 판단
const 카페제외_상호 = [
  "방탈출", "이스케이프", "escape", "비트포비아", "룸카페", "만화", "보드게임",
  "애견", "애완", "고양이", "라쿤", "키즈", "스터디", "사주", "타로",
];

function 카테고리매칭(doc: KakaoDoc, 키워드들: readonly string[]): boolean {
  const cat = doc.category_name ?? "";
  return 키워드들.some((k) => cat.includes(k));
}

export function 시간대적합(d: KakaoDoc, 시간대: string): boolean {
  if (시간대 === "lunch") return !카테고리매칭(d, 점심제외_카테고리);
  if (시간대 === "dinner") {
    return 카테고리매칭(d, 술어울림_카테고리) && !카테고리매칭(d, 저녁제외_카테고리);
  }
  if (시간대 === "cafe") {
    if (!카테고리매칭(d, 카페포함_카테고리) || 카테고리매칭(d, 카페제외_카테고리)) {
      return false;
    }
    const 이름 = (d.place_name ?? "").toLowerCase();
    if (카페제외_상호.some((k) => 이름.includes(k))) return false;
    // 세부 분류 없는 순수 '테마카페'는 디저트 목적이 불확실해 제외
    return (d.category_name ?? "").trim() !== "음식점 > 카페 > 테마카페";
  }
  return true;
}

// 카카오 키워드 검색은 질의당 최대 45건만 반환 → 개수가 많으면 복수 검색어를 병합.
// 앞 검색어일수록 정확도(인기) 우선순위가 높다.
export const 검색어풀: Record<string, string[]> = {
  all: ["맛집", "식당", "음식점", "밥집", "한식", "일식", "중식", "양식", "분식", "고기", "국밥", "파스타"],
  lunch: ["맛집", "점심", "식당", "음식점", "밥집", "한식", "일식", "중식", "양식", "분식", "국밥", "돈까스", "국수"],
  dinner: ["맛집", "술집", "고깃집", "이자카야", "호프", "회식", "포차", "와인바", "횟집", "치킨", "곱창", "족발"],
  cafe: ["카페", "디저트", "커피", "베이커리", "빵집", "브런치", "케이크", "빙수", "도넛", "아이스크림"],
};
// 카페 모드는 카카오 카페 그룹(CE7)을 먼저 훑고, 부족하면 음식점 그룹에서 보충
export const 검색그룹코드: Record<string, string[]> = { cafe: ["CE7", "FD6"] };

// 인증 필터: 카카오 검색의 키워드 연관도를 이용한다. 공식 인증 명부 API가 없어
// (미쉐린·블루리본 모두 비공개) 참고용 분류이며, 블루리본은 결과가 적을 수 있다.
export const 인증검색어: Record<string, string[]> = {
  michelin: ["미쉐린 가이드", "미슐랭", "미쉐린 맛집", "미쉐린 빕구르망"],
  blueribbon: ["블루리본", "블루리본 맛집", "블루리본서베이"],
  century: ["백년가게", "백년가게 맛집", "노포"],
  bwchef: ["흑백요리사", "흑백요리사 맛집", "흑백요리사 셰프"],
};
export const 인증표시명: Record<string, string> = {
  michelin: "미쉐린",
  blueribbon: "블루리본",
  century: "백년가게",
  bwchef: "흑백요리사",
};

// ── 카카오 블로그 검색 ────────────────────────────────────────
/** 무료: 일 3만 건. 장소 검색과 같은 REST 키를 쓴다. */
export async function 카카오블로그(질의: string, 개수 = 5): Promise<any[]> {
  for (let 시도 = 0; 시도 < 4; 시도++) {
    let resp: Response;
    try {
      const qs = new URLSearchParams({ query: 질의, size: String(개수), sort: "accuracy" });
      resp = await fetchT(`https://dapi.kakao.com/v2/search/blog?${qs}`, {
        headers: { Authorization: `KakaoAK ${KAKAO_KEY}` },
        timeoutMs: 10_000,
      });
    } catch {
      return [];
    }
    if (resp.status === 429) { // 초당 호출 제한 초과 → 잠시 대기 후 재시도
      await sleep(500 * (시도 + 1));
      continue;
    }
    if (!resp.ok) return [];
    const data = await resp.json().catch(() => null);
    return data?.documents ?? [];
  }
  return [];
}

export function 블로그정리(blogs: any[]): { title: string; text: string }[] {
  return blogs.map((b) => ({
    title: 태그제거(b.title ?? ""),
    text: 태그제거(b.contents ?? "").slice(0, 200),
  }));
}

// ── 카카오맵 상세 (비공식 panel3 API) ─────────────────────────
export function placeId(place_url: string): string {
  const pid = place_url.replace(/\/+$/, "").split("/").pop() ?? "";
  return /^\d+$/.test(pid) ? pid : "";
}

function panel3파싱(d: any): 상세 {
  const 결과: 상세 = {};
  const 메뉴들 = d?.menu?.menus?.items ?? [];
  결과.menus = 메뉴들
    .filter((m: any) => m?.name && Number.isInteger(m?.price) && m.price > 0)
    .map((m: any) => ({
      name: m.name,
      price: m.price,
      recommend: Boolean(m.is_recommend || m.is_ai_mate),
    }));

  const 사진들 = d?.photos?.photos ?? [];
  if (사진들.length && 사진들[0]?.url) {
    결과.photo = String(사진들[0].url).replace(/^http:\/\//, "https://");
  }

  const 점수 = d?.kakaomap_review?.score_set ?? {};
  if (점수.average_score) {
    결과.rating = Math.round(parseFloat(점수.average_score) * 10) / 10;
    결과.rating_count = 점수.review_count ?? null;
  }

  // 영업시간: 오늘 영업시간 + 현재 상태(영업중/브레이크타임 등)
  const 헤드 = d?.open_hours?.headline ?? {};
  결과.open_status = [헤드.display_text, 헤드.display_text_info].filter(Boolean).join(" ");
  try {
    const days = d.open_hours.week_from_today.week_periods[0].days;
    const 오늘 = days.find((v: any) => v?.is_highlight) ?? days[0];
    const on = 오늘?.on_days ?? {};
    let 시간 = on.start_end_time_desc ?? "";
    const 브레이크 = (on.break_times_desc ?? []).join(", ");
    if (브레이크) 시간 += ` (${브레이크})`;
    결과.hours = 시간;
  } catch {
    결과.hours = "";
  }

  // 예약: 매장 편의정보 아이콘에 '예약가능'이 있을 때만
  // (BOOKING 탭은 모든 가게에 떠서 부정확)
  const 아이콘들 = d?.place_add_info?.ai_mate?.store_facility_icons ?? [];
  결과.booking = 아이콘들.some((i: any) => (i?.text ?? "").includes("예약가능"));
  return 결과;
}

async function panel3가져오기(pid: string): Promise<상세> {
  try {
    const resp = await fetchT(`https://place-api.map.kakao.com/places/panel3/${pid}`, {
      headers: KAKAO_PANEL_HEADERS,
      timeoutMs: 10_000,
    });
    if (!resp.ok) return {};
    return panel3파싱(await resp.json());
  } catch {
    // 비공식 API라 언제든 막힐 수 있다 — 실패 시 빈 값으로 계속 진행
    return {};
  }
}

/** 여러 가게의 상세를 캐시와 함께 조회한다.
 *  파이썬판은 _상세결과캐시(프로세스 메모리)를 썼지만 여기서는 kv_cache 를 쓴다. */
export async function 카카오상세여러개(
  place_urls: readonly string[],
  concurrency = 10,
): Promise<Map<string, 상세>> {
  const pids = place_urls.map(placeId).filter(Boolean);
  const 캐시됨 = await 캐시여러개읽기<상세>("place", pids);

  const 미조회 = [...new Set(pids.filter((p) => !캐시됨.has(p)))];
  const 신규 = await pMap(미조회, (pid) => panel3가져오기(pid), concurrency);

  const 쓸것: { key: string; value: unknown }[] = [];
  미조회.forEach((pid, i) => {
    캐시됨.set(pid, 신규[i]);
    // 빈 결과(차단·비공개)는 캐시하지 않는다 — 다음 검색에서 다시 시도되도록
    if (Object.keys(신규[i]).length) 쓸것.push({ key: pid, value: 신규[i] });
  });
  await 캐시여러개쓰기("place", 쓸것, TTL.place);

  // place_url 기준으로 되돌려준다
  const out = new Map<string, 상세>();
  for (const url of place_urls) {
    const pid = placeId(url);
    out.set(url, (pid && 캐시됨.get(pid)) || {});
  }
  return out;
}

export async function 카카오상세(place_url: string): Promise<상세> {
  return (await 카카오상세여러개([place_url], 1)).get(place_url) ?? {};
}

/** 카카오맵 상세 페이지의 og:image = 그 가게의 실제 대표 사진.
 *  공식 REST API가 장소 사진을 제공하지 않아 페이지 메타 태그에서 가져온다. */
export async function 카카오사진(place_url: string): Promise<string | null> {
  const pid = placeId(place_url);
  if (!pid) return null;

  const 캐시 = await 캐시읽기<{ url: string | null }>("photo", pid);
  if (캐시) return 캐시.url;

  let url: string | null = null;
  try {
    const resp = await fetchT(`https://place.map.kakao.com/${pid}`, {
      headers: { "User-Agent": 브라우저_UA },
      timeoutMs: 10_000,
    });
    if (resp.ok) {
      const html = await resp.text();
      const m = html.match(/property="og:image"\s+content="([^"]+)"/);
      // fname= 이 없으면 사진 없는 가게의 기본 og 이미지
      if (m && m[1].includes("fname=")) {
        url = m[1].startsWith("//") ? `https:${m[1]}` : m[1];
      }
    }
  } catch {
    return null; // 실패는 캐시하지 않는다
  }
  await 캐시쓰기("photo", pid, { url }, TTL.photo);
  return url;
}
