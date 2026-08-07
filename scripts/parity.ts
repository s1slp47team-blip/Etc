// 이식 정확도 대조 — 원본 food_briefing_app.py 와 Edge Function 이식본이
// 같은 입력에 같은 결과를 내는지 확인한다.
//
//   ./scripts/parity.sh
//
// scripts/parity_expected.py 가 파이썬 원본을 실제로 실행해 expected.json 을 만들고,
// 이 파일이 TypeScript 쪽 결과와 비교한다. 외부 호출이 없는 순수 로직만 대상이다.

import { 시간대적합, type KakaoDoc } from "../supabase/functions/api/kakao.ts";
import { 내저장_매칭, 인증배지찾기 } from "../supabase/functions/api/places.ts";
import { 저장배지, type 저장장소 } from "../supabase/functions/api/naver.ts";
import { 대략거리m, 이름정규화, 태그제거 } from "../supabase/functions/api/util.ts";

const expected = JSON.parse(await Deno.readTextFile(Deno.args[0]));

let 통과 = 0;
const 실패: string[] = [];

function 비교(그룹: string, 입력: unknown, 실제: unknown, 기대: unknown) {
  const a = JSON.stringify(실제);
  const b = JSON.stringify(기대);
  if (a === b) 통과++;
  else 실패.push(`[${그룹}] ${JSON.stringify(입력)}\n    파이썬=${b}\n    TS    =${a}`);
}

for (const [cat, name, 시간대, want] of expected["시간대적합"]) {
  const d = { category_name: cat, place_name: name } as KakaoDoc;
  비교("시간대적합", [cat, name, 시간대], 시간대적합(d, 시간대), want);
}
for (const [s, want] of expected["이름정규화"]) {
  비교("이름정규화", s, 이름정규화(s), want);
}
for (const [a, b, want] of expected["대략거리m"]) {
  // 부동소수 표현 차이를 흡수하기 위해 파이썬과 같은 자리에서 반올림한다
  const got = Math.round(대략거리m(a[0], a[1], b[0], b[1]) * 1e6) / 1e6;
  비교("대략거리m", [a, b], got, want);
}
for (const [s, want] of expected["태그제거"]) {
  비교("태그제거", s, 태그제거(s), want);
}
for (const [f, want] of expected["저장배지"]) {
  비교("저장배지", f, 저장배지(f), want);
}
const 인증정보 = { "미쉐린식당": ["미쉐린"], "블루리본집": ["블루리본"], "가": ["백년가게"] };
for (const [n, want] of expected["인증배지찾기"]) {
  비교("인증배지찾기", n, 인증배지찾기(n, 인증정보), want);
}
const 저장목록: 저장장소[] = [
  { name: "김밥천국", lat: 37.5, lng: 127.0, folder: "가본곳", norm_name: 이름정규화("김밥천국") },
  { name: "김밥천국 역삼점", lat: 37.5, lng: 127.0, folder: "가볼곳", norm_name: 이름정규화("김밥천국 역삼점") },
  { name: "먼가게", lat: 37.6, lng: 127.1, folder: "가본곳", norm_name: 이름정규화("먼가게") },
  { name: "카페온리", lat: 37.5, lng: 127.0, folder: "카페", norm_name: 이름정규화("카페온리") },
];
const 좌표: Record<string, [number, number]> = {
  "김밥천국": [37.5, 127.0],
  "김밥천국 본점": [37.5, 127.0],
  "먼가게": [37.5, 127.0],
  "카페온리": [37.5, 127.0],
  "무관한집": [37.5, 127.0],
};
for (const [name, want] of expected["내저장_매칭"]) {
  const [lat, lng] = 좌표[name];
  비교("내저장_매칭", name, 내저장_매칭({ name, lat, lng }, 저장목록), want);
}

console.log(`대조 케이스 ${통과 + 실패.length}건 · 일치 ${통과} · 불일치 ${실패.length}`);
if (실패.length) {
  console.log("\n불일치 상세:");
  for (const f of 실패) console.log("  " + f);
  Deno.exit(1);
}
console.log("원본 파이썬과 결과가 완전히 일치합니다.");
