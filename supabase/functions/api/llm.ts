// Gemini 요약 + Groq 폴백 — 파이썬판 3절의 이식.
// google-genai SDK 대신 REST 를 직접 호출한다 (Deno 에서 의존성 없이 동작).

import { GEMINI_KEY, GEMINI_MODEL, GROQ_KEY, GROQ_MODEL } from "./env.ts";
import { fetchT, sleep, 천단위 } from "./util.ts";
import type { 메뉴 } from "./kakao.ts";

export const GEMINI_사용가능 = Boolean(GEMINI_KEY);

export interface 요약항목 {
  index?: number;
  menu?: string;
  price?: string;
  mood?: string;
  reviews?: string[];
}

export interface 가게자료 {
  posts: { title: string; text: string }[];
  photo: string | null;
  menus: 메뉴[];
  rating: number | null;
  rating_count: number | null;
}

const GEMINI_PROMPT = (동네: string, 마지막: number, 가게목록: string) =>
  `다음은 "${동네}" 인근 음식점 목록이다. 가게마다 카카오맵 메뉴판(실제 가격)과
블로그 후기 검색 결과가 붙어 있다.
각 가게에 대해 제공된 자료만을 근거로 아래 형식의 JSON 배열로 답하라. 다른 텍스트는 쓰지 마라.

[{"index": 0,
   "menu": "대표 메뉴 2~3개 (쉼표 구분, 메뉴판·블로그에서 확인된 것만)",
   "price": "1인 기준 가격대 (예: 1인 10,000~15,000원)",
   "mood": "블로그 반응 한 줄 요약 (15자 이내, 예: 긍정적 · 웨이팅 있음)",
   "reviews": ["대표 후기 요약 1~2개, 각 45자 이내 (블로그 문장의 취지를 살린 자연스러운 한국어)"]}, ...]

규칙:
- price는 메뉴판 가격이 있으면 반드시 그것을 근거로 대표 메뉴(단품/1인 기준) 위주로 계산한다.
  대용량·모둠 메뉴(수백 g, 세트)는 1인 기준 환산에 참고만 한다. 메뉴판이 없으면 블로그 근거로,
  그래도 없으면 "정보 부족"으로 표기한다.
- reviews는 광고성 문구를 거르고 실제 경험담 위주로 뽑는다. 블로그 후기가 없는 가게는 빈 배열로 둔다.
- 제공된 자료에 근거가 없는 내용은 지어내지 말고 "정보 부족"으로 표기한다.
- 모든 가게(index 0~${마지막})를 빠짐없이 포함한다.

가게 목록:
${가게목록}
`;

function 프롬프트만들기(
  동네: string,
  places: readonly { name: string; category: string }[],
  자료들: readonly 가게자료[],
): string {
  const 블록 = places.map((p, i) => {
    const 자료 = 자료들[i];
    const 메뉴줄 = 자료.menus.slice(0, 12)
      .map((m) => `${m.name} ${천단위(m.price)}원${m.recommend ? "(추천)" : ""}`)
      .join(", ") || "(메뉴판 정보 없음)";
    const 후기 = 자료.posts.map((b) => `  - ${b.title}: ${b.text}`).join("\n") ||
      "  (블로그 후기 없음)";
    return `[${i}] ${p.name} (${p.category})\n  메뉴판: ${메뉴줄}\n${후기}`;
  });
  return GEMINI_PROMPT(동네, places.length - 1, 블록.join("\n\n"));
}

/** 앞뒤 설명 문장이 붙어도 JSON 배열만 추출한다. */
function JSON배열추출(text: string): 요약항목[] {
  try {
    const v = JSON.parse(text);
    if (Array.isArray(v)) return v;
  } catch { /* 아래 정규식으로 재시도 */ }
  const m = text.match(/\[[\s\S]*\]/);
  if (!m) throw new Error("응답에서 JSON 배열을 찾지 못했습니다");
  return JSON.parse(m[0]);
}

async function gemini호출(prompt: string): Promise<string> {
  const url =
    `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_MODEL}:generateContent`;
  const resp = await fetchT(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", "x-goog-api-key": GEMINI_KEY },
    body: JSON.stringify({
      contents: [{ role: "user", parts: [{ text: prompt }] }],
      // thinking_config 는 최신 flash 모델이 거부(400)하므로 사용하지 않는다
      generationConfig: { responseMimeType: "application/json", temperature: 0.3 },
    }),
    timeoutMs: 90_000,
  });
  if (!resp.ok) {
    throw new Error(`Gemini ${resp.status}: ${(await resp.text()).slice(0, 200)}`);
  }
  const data = await resp.json();
  const text = data?.candidates?.[0]?.content?.parts?.map((p: any) => p.text ?? "").join("");
  if (!text) throw new Error("Gemini 응답이 비었습니다");
  return text;
}

/** Gemini 한도 소진 시 Groq(무료, llama-3.3-70b)로 같은 요약을 수행한다. */
async function groq호출(prompt: string): Promise<요약항목[]> {
  const resp = await fetchT("https://api.groq.com/openai/v1/chat/completions", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${GROQ_KEY}` },
    body: JSON.stringify({
      model: GROQ_MODEL,
      messages: [{ role: "user", content: prompt }],
      temperature: 0.3,
    }),
    timeoutMs: 60_000,
  });
  if (!resp.ok) {
    throw new Error(`Groq ${resp.status}: ${(await resp.text()).slice(0, 200)}`);
  }
  const data = await resp.json();
  return JSON배열추출(data.choices[0].message.content);
}

/** 가게 한 청크(최대 STEP_SIZE 곳)를 요약한다.
 *  반환 키는 청크 내 상대 index (0부터). 호출부에서 start 를 더해 쓴다. */
export async function 청크요약(
  동네: string,
  places: readonly { name: string; category: string }[],
  자료들: readonly 가게자료[],
): Promise<Map<number, 요약항목>> {
  const 결과 = new Map<number, 요약항목>();
  if (!GEMINI_사용가능 && !GROQ_KEY) return 결과;

  const prompt = 프롬프트만들기(동네, places, 자료들);
  let items: 요약항목[] | null = null;

  if (GEMINI_사용가능) {
    // Groq 폴백이 있으면 Gemini 재시도를 줄여 빨리 넘어간다.
    // 파이썬판은 429 에 25초를 기다렸지만, Edge Function 은 실행시간 제한이 있어
    // 대기를 짧게 잡고 폴백/다음 요청에 맡긴다.
    const 최대시도 = GROQ_KEY ? 2 : 3;
    for (let 시도 = 0; 시도 < 최대시도; 시도++) {
      try {
        items = JSON배열추출(await gemini호출(prompt));
        break;
      } catch (e) {
        const msg = (e as Error).message;
        const 한도 = msg.includes("429") || msg.includes("RESOURCE_EXHAUSTED");
        const 일시 = msg.includes("503") || msg.includes("UNAVAILABLE");
        if ((한도 || 일시) && 시도 < 최대시도 - 1) {
          await sleep(한도 ? 6_000 : 3_000 * (시도 + 1));
          continue;
        }
        // 그 외 오류(모델 정책 변경, 잘못된 인자 등)도 Groq 으로 폴백해 요약이 끊기지 않게 한다
        console.warn(`Gemini 실패: ${msg.slice(0, 150)}`);
        break;
      }
    }
  }

  if (!items && GROQ_KEY) {
    try {
      items = await groq호출(prompt);
    } catch (e) {
      console.warn("Groq 폴백도 실패:", (e as Error).message);
    }
  }
  if (!items) return 결과;

  for (const it of items) {
    if (!it || typeof it !== "object" || it.index == null) continue;
    const i = Number(it.index);
    if (Number.isInteger(i) && i >= 0 && i < places.length) 결과.set(i, it);
  }
  return 결과;
}
