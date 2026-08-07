// 맛집검색 — 파이썬판 맛집검색() / 인증맵() / 내저장_매칭() 의 이식.

import { TTL, 맛집수 } from "./env.ts";
import { 캐시쓰기, 캐시읽기 } from "./db.ts";
import {
  type KakaoDoc,
  검색그룹코드,
  검색어풀,
  인증검색어,
  인증표시명,
  시간대적합,
  장소수집,
  카카오상세여러개,
} from "./kakao.ts";
import { 내맛집목록, 저장배지, type 저장장소 } from "./naver.ts";
import { pMap, 대략거리m, 안전하게, 이름정규화 } from "./util.ts";

export interface Place {
  name: string;
  category: string;
  address: string;
  phone: string;
  url: string;
  distance: number | null;
  lat: number;
  lng: number;
  badges: string[];
  rating: number | null;
  rating_count: number | null;
  hours: string;
  open_status: string;
  booking: boolean;
}

// ── 인증 맛집 목록 ────────────────────────────────────────────
/** 해당 반경의 인증 맛집을 미리 조회해 {정규화 상호: [배지들]} 로 만든다.
 *  인증 필터를 안 걸고 검색해도 인증 배지가 보이도록 하기 위한 것.
 *  카카오 장소 ID는 같은 가게라도 검색 경로에 따라 다를 수 있어 상호로 대조한다. */
export async function 인증맵(
  x: number,
  y: number,
  radius: number,
): Promise<Record<string, string[]>> {
  // 약 100m 격자로 캐시 공유 (파이썬판의 round(x,3) 과 동일)
  const 키 = `${x.toFixed(3)}|${y.toFixed(3)}|${radius}`;
  const 캐시 = await 캐시읽기<Record<string, string[]>>("cert", 키);
  if (캐시) return 캐시;

  const 결과: Record<string, string[]> = {};
  const 항목들 = Object.entries(인증검색어);
  const 묶음 = await pMap(항목들, async ([c, 질의들]) => {
    const 찾음: string[] = [];
    for (const 질의 of 질의들) {
      for (const d of await 장소수집(질의, x, y, radius)) 찾음.push(d.place_name);
    }
    return [인증표시명[c], 찾음] as const;
  }, 4);

  for (const [배지, 이름들] of 묶음) {
    for (const 이름 of 이름들) {
      const 키이름 = 이름정규화(이름);
      if (!키이름) continue;
      (결과[키이름] ??= []);
      if (!결과[키이름].includes(배지)) 결과[키이름].push(배지);
    }
  }
  await 캐시쓰기("cert", 키, 결과, TTL.cert);
  return 결과;
}

/** 상호로 인증 배지를 찾는다. '가게명 지점명' 형태의 표기 차이도 흡수. */
export function 인증배지찾기(place_name: string, 인증정보: Record<string, string[]>): string[] {
  const 이름 = 이름정규화(place_name);
  if (!이름) return [];
  if (인증정보[이름]) return 인증정보[이름];
  for (const [등록명, 배지들] of Object.entries(인증정보)) {
    if (등록명.length >= 3 && (이름.startsWith(등록명) || 등록명.startsWith(이름))) {
      return 배지들;
    }
  }
  return [];
}

/** 검색 결과 1곳이 내 저장 맛집인지 판정 → 배지 문구 (아니면 빈 문자열).
 *  좌표 120m 이내 + 이름 유사(포함 관계)면 같은 가게로 본다.
 *  두 리스트에 모두 있으면 '가본곳'만 표시한다 (이미 가봤으므로). */
export function 내저장_매칭(
  place: { name: string; lat: number; lng: number },
  저장목록: readonly 저장장소[],
): string {
  const 이름 = 이름정규화(place.name);
  if (!이름) return "";
  const 배지들 = new Set<string>();
  for (const s of 저장목록) {
    if (대략거리m(place.lat, place.lng, s.lat, s.lng) > 120) continue;
    const 저장이름 = s.norm_name || 이름정규화(s.name);
    if (!저장이름) continue;
    if (이름 === 저장이름 || 이름.startsWith(저장이름) || 저장이름.startsWith(이름)) {
      배지들.add(저장배지(s.folder));
    }
  }
  if (!배지들.size) return "";
  return [...배지들].find((b) => b.includes("가본곳")) ?? [...배지들].sort()[0];
}

// ── 본체 ──────────────────────────────────────────────────────
export async function 맛집검색(
  x: number,
  y: number,
  radius: number,
  시간대 = "all",
   개수 = 맛집수,
  cert = "none",
   평점4 = false,
   내저장 = "prefer",
): Promise<Place[]> {
  let 후보: KakaoDoc[] = [];
  const seen = new Map<string, KakaoDoc>();
  const 그룹코드들 = 검색그룹코드[시간대] ?? ["FD6"];

  const 수집 = async (질의: string, 배지 = "") => {
    for (const 코드 of 그룹코드들) {
      for (const d of await 장소수집(질의, x, y, radius, 45, 코드)) {
        if (!시간대적합(d, 시간대)) continue;
        const 기존 = seen.get(d.id);
        if (기존) {
          if (배지 && !기존.badges!.includes(배지)) 기존.badges!.push(배지);
          continue;
        }
        d.badges = 배지 ? [배지] : [];
        seen.set(d.id, d);
        후보.push(d);
      }
    }
  };

  if (cert === "any") {
    // 인증 종류별로 따로 모은 뒤 라운드로빈으로 섞는다 —
    // 한 인증(미쉐린)의 결과가 상위를 독식해 다른 인증이 밀려나지 않게
    const 풀들: KakaoDoc[][] = [];
    for (const [c, 질의들] of Object.entries(인증검색어)) {
      const 시작 = 후보.length;
      for (const 질의 of 질의들) await 수집(질의, 인증표시명[c]);
      풀들.push(후보.slice(시작));
    }
    const 최대길이 = Math.max(0, ...풀들.map((p) => p.length));
    const 섞음: KakaoDoc[] = [];
    for (let i = 0; i < 최대길이; i++) {
      for (const 묶음 of 풀들) if (묶음[i]) 섞음.push(묶음[i]);
    }
    후보 = 섞음;
  } else if (인증검색어[cert]) {
    for (const 질의 of 인증검색어[cert]) await 수집(질의, 인증표시명[cert]);
  } else {
    const 목표 = 평점4 ? 개수 * 2 : 개수; // 평점 필터로 걸러질 몫을 여유 있게 수집
    for (const 검색어 of 검색어풀[시간대] ?? 검색어풀.all) {
      if (후보.length >= 목표) break;
      await 수집(검색어);
    }
  }

  // ── 인증 배지 보강 ──────────────────────────────────────────
  // 인증 필터를 안 걸고 검색해도 인증 맛집이면 배지가 보이도록 한다
  // (카페 모드는 인증 검색어가 음식점 위주라 생략)
  if (시간대 !== "cafe") {
    const 인증정보 = await 안전하게(() => 인증맵(x, y, radius), {}, "인증 배지 조회");
    for (const d of 후보) {
      for (const 배지 of 인증배지찾기(d.place_name, 인증정보)) {
        if (!d.badges!.includes(배지)) d.badges!.push(배지);
      }
    }
  }

  // ── 내 저장 맛집(네이버지도) 반영 ──────────────────────────
  const 저장목록 = (내저장 === "prefer" || 내저장 === "only")
    ? await 안전하게(() => 내맛집목록(), [] as 저장장소[], "내 저장 맛집")
    : [];

  if (저장목록.length) {
    // 반경 안의 저장 맛집이 카카오 검색에 안 잡혔으면 이름으로 직접 찾아 보강한다
    const 검색됨 = new Set(후보.map((d) => 이름정규화(d.place_name)));
    let 누락 = 저장목록.filter((s) => {
      if (대략거리m(y, x, s.lat, s.lng) > radius) return false;
      const sn = s.norm_name || 이름정규화(s.name);
      for (const n of 검색됨) {
        if (!n) continue;
        if (sn === n || sn.startsWith(n) || n.startsWith(sn)) return false;
      }
      return true;
    });

    // 시간대에 맞는 리스트를 앞에 둔다 — 카페 모드에서 맛집 저장분이 앞을
    // 다 차지해 저장한 카페가 상한에 잘려나가지 않도록
    const 카페폴더 = (s: 저장장소) => s.folder.includes("카페") || s.folder.includes("디저트");
    누락 = 시간대 === "cafe"
      ? [...누락.filter(카페폴더), ...누락.filter((s) => !카페폴더(s))]
      : [...누락.filter((s) => !카페폴더(s)), ...누락.filter(카페폴더)];
    누락 = 누락.slice(0, 30); // 과도한 호출 방지

    if (누락.length) {
      const 결과들 = await pMap(누락, async (s) => {
        // 카페 모드는 카페 그룹(CE7)에서도 찾아야 저장한 카페가 잡힌다
        for (const 코드 of 그룹코드들) {
          const docs = await 장소수집(s.name, s.lng, s.lat, 300, 3, 코드);
          if (docs.length) return docs;
        }
        return [] as KakaoDoc[];
      }, 6);

      누락.forEach((s, i) => {
        for (const d of 결과들[i]) {
          if (seen.has(d.id) || !시간대적합(d, 시간대)) continue;
          if (대략거리m(parseFloat(d.y), parseFloat(d.x), s.lat, s.lng) > 150) continue;
          d.badges = [];
          d.distance = String(Math.round(대략거리m(y, x, parseFloat(d.y), parseFloat(d.x))));
          seen.set(d.id, d);
          후보.push(d);
          break;
        }
      });
    }

    for (const d of 후보) {
      const 배지 = 내저장_매칭(
        { name: d.place_name, lat: parseFloat(d.y), lng: parseFloat(d.x) },
        저장목록,
      );
      d._저장배지 = 배지;
      if (배지 && !d.badges!.includes(배지)) d.badges!.unshift(배지);
    }

    후보 = 내저장 === "only"
      ? 후보.filter((d) => d._저장배지)
      // prefer — 저장 맛집을 앞으로 (그 안에서는 기존 정확도순 유지)
      : [...후보.filter((d) => d._저장배지), ...후보.filter((d) => !d._저장배지)];
  }

  // 카카오맵 상세(평점·영업시간·예약)를 붙인다 — 결과 카드와 평점 필터에 사용.
  // 평점 필터가 있으면 후보 전체를, 아니면 상위 개수만 조회 (조회 결과는 캐시됨)
  let 대상 = 평점4 ? 후보 : 후보.slice(0, 개수);
  const 상세맵 = await 카카오상세여러개(대상.map((d) => d.place_url), 10);
  for (const d of 대상) d._상세 = 상세맵.get(d.place_url) ?? {};
  if (평점4) 대상 = 대상.filter((d) => (d._상세?.rating ?? 0) >= 4.0);

  return 대상.slice(0, 개수).map((d) => {
    const 상세 = d._상세 ?? {};
    return {
      name: d.place_name,
      category: d.category_name ? d.category_name.split(" > ").pop()! : "",
      address: d.road_address_name || d.address_name,
      phone: d.phone,
      url: d.place_url,
      distance: d.distance ? parseInt(d.distance, 10) : null,
      lat: parseFloat(d.y),
      lng: parseFloat(d.x),
      badges: d.badges ?? [],
      rating: 상세.rating ?? null,
      rating_count: 상세.rating_count ?? null,
      hours: 상세.hours ?? "",
      open_status: 상세.open_status ?? "",
      booking: Boolean(상세.booking),
    };
  });
}
