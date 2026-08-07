// @ts-nocheck
// 자동 생성 파일 — 직접 고치지 마세요. ./scripts/bundle.sh 로 다시 만듭니다.
// 원본: supabase/functions/api/*.ts (index.ts 가 진입점)
//
// Supabase CLI 없이 대시보드 함수 편집기에 붙여넣어 배포하기 위한 단일 파일입니다.
// 배포 방법은 docs/SUPABASE.md 의 'CLI 없이 배포하기' 절을 보세요.
//
// @ts-nocheck 인 이유: 번들러가 타입 주석을 제거한 JavaScript 를 .ts 파일로
// 내보내므로, 원본에 타입이 다 붙어 있는데도 noImplicitAny 에 걸린다.
// 타입 검증은 원본 9개 파일에 대해 deno check 로 이미 수행된다.

// supabase/functions/api/env.ts
var KAKAO_KEY = Deno.env.get("KAKAO_REST_API_KEY") ?? "";
var GEMINI_KEY = Deno.env.get("GEMINI_API_KEY") ?? "";
var GROQ_KEY = Deno.env.get("GROQ_API_KEY") ?? "";
var JS_KEY = Deno.env.get("KAKAO_JS_KEY") ?? "";
var APP_PASSWORD = Deno.env.get("APP_PASSWORD") ?? "";
var MY_PLACE_LINKS = Deno.env.get("MY_PLACE_LINKS") ?? "";
var SUPABASE_URL = Deno.env.get("SUPABASE_URL") ?? "";
var SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
var GEMINI_MODEL = "gemini-flash-latest";
var GROQ_MODEL = "llama-3.3-70b-versatile";
var \uB9DB\uC9D1\uC218 = 30;
var STEP_SIZE = 10;
var TTL = {
  search: 60 * 60 * 24 * 3,
  detail: 60 * 60 * 24 * 3,
  place: 60 * 60 * 24 * 7,
  photo: 60 * 60 * 24 * 14,
  cert: 60 * 60 * 24 * 14,
  myPlaces: 60 * 60
};
function requireKakaoKey() {
  if (!KAKAO_KEY) {
    throw new Error("KAKAO_REST_API_KEY \uC2DC\uD06C\uB9BF\uC774 \uC5C6\uC2B5\uB2C8\uB2E4. `supabase secrets set KAKAO_REST_API_KEY=...` \uB85C \uB4F1\uB85D\uD558\uC138\uC694.");
  }
}

// supabase/functions/api/util.ts
async function pMap(items, fn, concurrency) {
  const out = new Array(items.length);
  let next = 0;
  const worker = async () => {
    for (; ; ) {
      const i = next++;
      if (i >= items.length) return;
      out[i] = await fn(items[i], i);
    }
  };
  const n = Math.max(1, Math.min(concurrency, items.length));
  await Promise.all(Array.from({
    length: n
  }, worker));
  return out;
}
var sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function \uC774\uB984\uC815\uADDC\uD654(s) {
  return (s ?? "").replace(/[^0-9a-zA-Z가-힣]/g, "").toLowerCase();
}
function \uB300\uB7B5\uAC70\uB9ACm(lat1, lng1, lat2, lng2) {
  const dy = (lat1 - lat2) * 111e3;
  const dx = (lng1 - lng2) * 111e3 * Math.cos((lat1 + lat2) / 2 * Math.PI / 180);
  return Math.hypot(dx, dy);
}
function \uD0DC\uADF8\uC81C\uAC70(s) {
  return (s ?? "").replace(/<[^>]+>/g, "").replace(/&quot;/g, '"').replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">");
}
function \uCC9C\uB2E8\uC704(n) {
  return n.toLocaleString("en-US");
}
async function fetchT(url, init = {}) {
  const { timeoutMs = 1e4, ...rest } = init;
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), timeoutMs);
  try {
    return await fetch(url, {
      ...rest,
      signal: ac.signal
    });
  } finally {
    clearTimeout(timer);
  }
}
async function \uC548\uC804\uD558\uAC8C(fn, \uAE30\uBCF8\uAC12, \uB77C\uBCA8 = "") {
  try {
    return await fn();
  } catch (e) {
    if (\uB77C\uBCA8) console.warn(`${\uB77C\uBCA8} \uC2E4\uD328(\uBB34\uC2DC):`, e.message);
    return \uAE30\uBCF8\uAC12;
  }
}
function json(body, status = 200, extra = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      ...corsHeaders(),
      ...extra
    }
  });
}
function corsHeaders() {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "authorization, content-type, x-app-token",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS"
  };
}

// supabase/functions/api/db.ts
import { createClient } from "npm:@supabase/supabase-js@2";
var _client = null;
function db() {
  if (!_client) {
    if (!SUPABASE_URL || !SERVICE_ROLE_KEY) {
      throw new Error("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY \uAC00 \uC5C6\uC2B5\uB2C8\uB2E4.");
    }
    _client = createClient(SUPABASE_URL, SERVICE_ROLE_KEY, {
      auth: {
        persistSession: false,
        autoRefreshToken: false
      }
    });
  }
  return _client;
}
async function \uCE90\uC2DC\uC77D\uAE30(scope, key) {
  const { data, error } = await db().from("kv_cache").select("value, expires_at").eq("scope", scope).eq("key", key).maybeSingle();
  if (error || !data) return null;
  if (new Date(data.expires_at).getTime() < Date.now()) return null;
  return data.value;
}
async function \uCE90\uC2DC\uC5EC\uB7EC\uAC1C\uC77D\uAE30(scope, keys) {
  const out = /* @__PURE__ */ new Map();
  if (!keys.length) return out;
  const { data, error } = await db().from("kv_cache").select("key, value, expires_at").eq("scope", scope).in("key", [
    ...new Set(keys)
  ]);
  if (error || !data) return out;
  const now = Date.now();
  for (const row of data) {
    if (new Date(row.expires_at).getTime() >= now) out.set(row.key, row.value);
  }
  return out;
}
async function \uCE90\uC2DC\uC4F0\uAE30(scope, key, value, ttlSeconds) {
  const expires_at = new Date(Date.now() + ttlSeconds * 1e3).toISOString();
  const { error } = await db().from("kv_cache").upsert({
    scope,
    key,
    value,
    expires_at
  }, {
    onConflict: "scope,key"
  });
  if (error) console.warn(`\uCE90\uC2DC \uC4F0\uAE30 \uC2E4\uD328(${scope}/${key}):`, error.message);
}
async function \uCE90\uC2DC\uC5EC\uB7EC\uAC1C\uC4F0\uAE30(scope, rows, ttlSeconds) {
  if (!rows.length) return;
  const expires_at = new Date(Date.now() + ttlSeconds * 1e3).toISOString();
  const \uC720\uC77C = new Map(rows.map((r) => [
    r.key,
    r.value
  ]));
  const { error } = await db().from("kv_cache").upsert([
    ...\uC720\uC77C
  ].map(([key, value]) => ({
    scope,
    key,
    value,
    expires_at
  })), {
    onConflict: "scope,key"
  });
  if (error) console.warn(`\uCE90\uC2DC \uC77C\uAD04 \uC4F0\uAE30 \uC2E4\uD328(${scope}):`, error.message);
}
function \uAC80\uC0C9\uD0A4(o) {
  return [
    o.q,
    o.radius,
    o.meal,
    o.cnt,
    o.cert,
    o.rate ? "1" : "0",
    o.mine
  ].join("|");
}

// supabase/functions/api/kakao.ts
var \uBE0C\uB77C\uC6B0\uC800_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36";
var KAKAO_PANEL_HEADERS = {
  "User-Agent": \uBE0C\uB77C\uC6B0\uC800_UA,
  "Accept": "application/json",
  "Origin": "https://place.map.kakao.com",
  "Referer": "https://place.map.kakao.com/",
  "pf": "web"
};
async function kakaoGet(path, params) {
  const qs = new URLSearchParams(Object.entries(params).map(([k, v]) => [
    k,
    String(v)
  ]));
  const resp = await fetchT(`https://dapi.kakao.com/v2/local/${path}?${qs}`, {
    headers: {
      Authorization: `KakaoAK ${KAKAO_KEY}`
    },
    timeoutMs: 15e3
  });
  if (!resp.ok) {
    throw new Error(`\uCE74\uCE74\uC624 API \uC624\uB958 [${resp.status}] ${(await resp.text()).slice(0, 200)}`);
  }
  return await resp.json();
}
async function \uB3D9\uB124\uC88C\uD45C(query) {
  const addr = await kakaoGet("search/address.json", {
    query,
    size: 1
  });
  if (addr.documents?.length) {
    const d = addr.documents[0];
    return [
      d.address_name,
      parseFloat(d.x),
      parseFloat(d.y)
    ];
  }
  const kw = await kakaoGet("search/keyword.json", {
    query,
    size: 1
  });
  if (kw.documents?.length) {
    const d = kw.documents[0];
    return [
      d.place_name,
      parseFloat(d.x),
      parseFloat(d.y)
    ];
  }
  return null;
}
async function \uC7A5\uC18C\uC218\uC9D1(query, x, y, radius, \uCD5C\uB300 = 45, \uADF8\uB8F9\uCF54\uB4DC = "FD6") {
  const docs = [];
  for (let page = 1; docs.length < \uCD5C\uB300 && page <= 3; page++) {
    const data = await kakaoGet("search/keyword.json", {
      query,
      category_group_code: \uADF8\uB8F9\uCF54\uB4DC,
      x,
      y,
      radius,
      size: 15,
      page
    });
    docs.push(...data.documents ?? []);
    if (data.meta?.is_end) break;
  }
  return docs;
}
var \uC220\uC5B4\uC6B8\uB9BC_\uCE74\uD14C\uACE0\uB9AC = [
  "\uC220\uC9D1",
  "\uD638\uD504",
  "\uC694\uB9AC\uC8FC\uC810",
  "\uD3EC\uC7A5\uB9C8\uCC28",
  "\uBBFC\uC18D\uC8FC\uC810",
  "\uC640\uC778",
  "\uCE75\uD14C\uC77C",
  "\uC624\uB385\uBC14",
  "\uC721\uB958,\uACE0\uAE30",
  "\uACF1\uCC3D",
  "\uB9C9\uCC3D",
  "\uC871\uBC1C",
  "\uBCF4\uC308",
  "\uD68C",
  "\uCC38\uCE58",
  "\uD574\uBB3C",
  "\uC0DD\uC120",
  "\uAC8C,\uB300\uAC8C",
  "\uC870\uAC1C",
  "\uCE58\uD0A8",
  "\uB2ED\uBC1C",
  "\uC624\uB9AC"
];
var \uC800\uB141\uC81C\uC678_\uCE74\uD14C\uACE0\uB9AC = [
  "\uC0BC\uACC4\uD0D5",
  "\uC8FD",
  "\uB3C4\uC2DC\uB77D",
  "\uACF0\uD0D5",
  "\uC124\uB801\uD0D5",
  "\uAC08\uBE44\uD0D5",
  "\uAD6D\uBC25",
  "\uBC31\uBC18",
  "\uAC00\uC815\uC2DD",
  "\uAE30\uC0AC\uC2DD\uB2F9",
  "\uAD6D\uC218",
  "\uCE7C\uAD6D\uC218",
  "\uB0C9\uBA74"
];
var \uC810\uC2EC\uC81C\uC678_\uCE74\uD14C\uACE0\uB9AC = [
  "\uC220\uC9D1",
  "\uD638\uD504",
  "\uC694\uB9AC\uC8FC\uC810",
  "\uD3EC\uC7A5\uB9C8\uCC28",
  "\uBBFC\uC18D\uC8FC\uC810",
  "\uC640\uC778",
  "\uCE75\uD14C\uC77C",
  "\uC624\uB385\uBC14",
  "\uACF1\uCC3D",
  "\uB9C9\uCC3D",
  "\uB2ED\uBC1C",
  "\uC0BC\uACB9\uC0B4",
  "\uD68C",
  "\uCC38\uCE58",
  "\uC591\uAF2C\uCE58",
  "\uC871\uBC1C",
  "\uBCF4\uC308"
];
var \uCE74\uD398\uD3EC\uD568_\uCE74\uD14C\uACE0\uB9AC = [
  "\uCE74\uD398",
  "\uC81C\uACFC",
  "\uBCA0\uC774\uCEE4\uB9AC",
  "\uC544\uC774\uC2A4\uD06C\uB9BC",
  "\uBE59\uC218",
  "\uB514\uC800\uD2B8",
  "\uBE0C\uB7F0\uCE58",
  "\uB3C4\uB11B",
  "\uCF00\uC774\uD06C"
];
var \uCE74\uD398\uC81C\uC678_\uCE74\uD14C\uACE0\uB9AC = [
  "\uC220\uC9D1",
  "\uD638\uD504",
  "\uC694\uB9AC\uC8FC\uC810",
  "\uD3EC\uC7A5\uB9C8\uCC28",
  // 음료·디저트가 목적이 아닌 공간 대여형·체험형 카페
  "\uB8F8\uCE74\uD398",
  "\uB9CC\uD654\uCE74\uD398",
  "\uBCF4\uB4DC\uAC8C\uC784",
  "PC\uBC29",
  "\uC2A4\uD130\uB514",
  "\uBC29\uD0C8\uCD9C",
  "\uC560\uACAC",
  "\uC560\uC644",
  "\uACE0\uC591\uC774",
  "\uB3D9\uBB3C",
  "\uD0A4\uC988",
  "\uD3EC\uD1A0",
  "\uC0AC\uC9C4",
  "\uACF5\uBC29",
  "\uB124\uC77C",
  "\uD0C0\uB85C",
  "\uB9C8\uC0AC\uC9C0"
];
var \uCE74\uD398\uC81C\uC678_\uC0C1\uD638 = [
  "\uBC29\uD0C8\uCD9C",
  "\uC774\uC2A4\uCF00\uC774\uD504",
  "escape",
  "\uBE44\uD2B8\uD3EC\uBE44\uC544",
  "\uB8F8\uCE74\uD398",
  "\uB9CC\uD654",
  "\uBCF4\uB4DC\uAC8C\uC784",
  "\uC560\uACAC",
  "\uC560\uC644",
  "\uACE0\uC591\uC774",
  "\uB77C\uCFE4",
  "\uD0A4\uC988",
  "\uC2A4\uD130\uB514",
  "\uC0AC\uC8FC",
  "\uD0C0\uB85C"
];
function \uCE74\uD14C\uACE0\uB9AC\uB9E4\uCE6D(doc, \uD0A4\uC6CC\uB4DC\uB4E4) {
  const cat = doc.category_name ?? "";
  return \uD0A4\uC6CC\uB4DC\uB4E4.some((k) => cat.includes(k));
}
function \uC2DC\uAC04\uB300\uC801\uD569(d, \uC2DC\uAC04\uB300) {
  if (\uC2DC\uAC04\uB300 === "lunch") return !\uCE74\uD14C\uACE0\uB9AC\uB9E4\uCE6D(d, \uC810\uC2EC\uC81C\uC678_\uCE74\uD14C\uACE0\uB9AC);
  if (\uC2DC\uAC04\uB300 === "dinner") {
    return \uCE74\uD14C\uACE0\uB9AC\uB9E4\uCE6D(d, \uC220\uC5B4\uC6B8\uB9BC_\uCE74\uD14C\uACE0\uB9AC) && !\uCE74\uD14C\uACE0\uB9AC\uB9E4\uCE6D(d, \uC800\uB141\uC81C\uC678_\uCE74\uD14C\uACE0\uB9AC);
  }
  if (\uC2DC\uAC04\uB300 === "cafe") {
    if (!\uCE74\uD14C\uACE0\uB9AC\uB9E4\uCE6D(d, \uCE74\uD398\uD3EC\uD568_\uCE74\uD14C\uACE0\uB9AC) || \uCE74\uD14C\uACE0\uB9AC\uB9E4\uCE6D(d, \uCE74\uD398\uC81C\uC678_\uCE74\uD14C\uACE0\uB9AC)) {
      return false;
    }
    const \uC774\uB984 = (d.place_name ?? "").toLowerCase();
    if (\uCE74\uD398\uC81C\uC678_\uC0C1\uD638.some((k) => \uC774\uB984.includes(k))) return false;
    return (d.category_name ?? "").trim() !== "\uC74C\uC2DD\uC810 > \uCE74\uD398 > \uD14C\uB9C8\uCE74\uD398";
  }
  return true;
}
var \uAC80\uC0C9\uC5B4\uD480 = {
  all: [
    "\uB9DB\uC9D1",
    "\uC2DD\uB2F9",
    "\uC74C\uC2DD\uC810",
    "\uBC25\uC9D1",
    "\uD55C\uC2DD",
    "\uC77C\uC2DD",
    "\uC911\uC2DD",
    "\uC591\uC2DD",
    "\uBD84\uC2DD",
    "\uACE0\uAE30",
    "\uAD6D\uBC25",
    "\uD30C\uC2A4\uD0C0"
  ],
  lunch: [
    "\uB9DB\uC9D1",
    "\uC810\uC2EC",
    "\uC2DD\uB2F9",
    "\uC74C\uC2DD\uC810",
    "\uBC25\uC9D1",
    "\uD55C\uC2DD",
    "\uC77C\uC2DD",
    "\uC911\uC2DD",
    "\uC591\uC2DD",
    "\uBD84\uC2DD",
    "\uAD6D\uBC25",
    "\uB3C8\uAE4C\uC2A4",
    "\uAD6D\uC218"
  ],
  dinner: [
    "\uB9DB\uC9D1",
    "\uC220\uC9D1",
    "\uACE0\uAE43\uC9D1",
    "\uC774\uC790\uCE74\uC57C",
    "\uD638\uD504",
    "\uD68C\uC2DD",
    "\uD3EC\uCC28",
    "\uC640\uC778\uBC14",
    "\uD69F\uC9D1",
    "\uCE58\uD0A8",
    "\uACF1\uCC3D",
    "\uC871\uBC1C"
  ],
  cafe: [
    "\uCE74\uD398",
    "\uB514\uC800\uD2B8",
    "\uCEE4\uD53C",
    "\uBCA0\uC774\uCEE4\uB9AC",
    "\uBE75\uC9D1",
    "\uBE0C\uB7F0\uCE58",
    "\uCF00\uC774\uD06C",
    "\uBE59\uC218",
    "\uB3C4\uB11B",
    "\uC544\uC774\uC2A4\uD06C\uB9BC"
  ]
};
var \uAC80\uC0C9\uADF8\uB8F9\uCF54\uB4DC = {
  cafe: [
    "CE7",
    "FD6"
  ]
};
var \uC778\uC99D\uAC80\uC0C9\uC5B4 = {
  michelin: [
    "\uBBF8\uC250\uB9B0 \uAC00\uC774\uB4DC",
    "\uBBF8\uC290\uB7AD",
    "\uBBF8\uC250\uB9B0 \uB9DB\uC9D1",
    "\uBBF8\uC250\uB9B0 \uBE55\uAD6C\uB974\uB9DD"
  ],
  blueribbon: [
    "\uBE14\uB8E8\uB9AC\uBCF8",
    "\uBE14\uB8E8\uB9AC\uBCF8 \uB9DB\uC9D1",
    "\uBE14\uB8E8\uB9AC\uBCF8\uC11C\uBCA0\uC774"
  ],
  century: [
    "\uBC31\uB144\uAC00\uAC8C",
    "\uBC31\uB144\uAC00\uAC8C \uB9DB\uC9D1",
    "\uB178\uD3EC"
  ],
  bwchef: [
    "\uD751\uBC31\uC694\uB9AC\uC0AC",
    "\uD751\uBC31\uC694\uB9AC\uC0AC \uB9DB\uC9D1",
    "\uD751\uBC31\uC694\uB9AC\uC0AC \uC170\uD504"
  ]
};
var \uC778\uC99D\uD45C\uC2DC\uBA85 = {
  michelin: "\uBBF8\uC250\uB9B0",
  blueribbon: "\uBE14\uB8E8\uB9AC\uBCF8",
  century: "\uBC31\uB144\uAC00\uAC8C",
  bwchef: "\uD751\uBC31\uC694\uB9AC\uC0AC"
};
async function \uCE74\uCE74\uC624\uBE14\uB85C\uADF8(\uC9C8\uC758, \uAC1C\uC218 = 5) {
  for (let \uC2DC\uB3C4 = 0; \uC2DC\uB3C4 < 4; \uC2DC\uB3C4++) {
    let resp;
    try {
      const qs = new URLSearchParams({
        query: \uC9C8\uC758,
        size: String(\uAC1C\uC218),
        sort: "accuracy"
      });
      resp = await fetchT(`https://dapi.kakao.com/v2/search/blog?${qs}`, {
        headers: {
          Authorization: `KakaoAK ${KAKAO_KEY}`
        },
        timeoutMs: 1e4
      });
    } catch {
      return [];
    }
    if (resp.status === 429) {
      await sleep(500 * (\uC2DC\uB3C4 + 1));
      continue;
    }
    if (!resp.ok) return [];
    const data = await resp.json().catch(() => null);
    return data?.documents ?? [];
  }
  return [];
}
function \uBE14\uB85C\uADF8\uC815\uB9AC(blogs) {
  return blogs.map((b) => ({
    title: \uD0DC\uADF8\uC81C\uAC70(b.title ?? ""),
    text: \uD0DC\uADF8\uC81C\uAC70(b.contents ?? "").slice(0, 200)
  }));
}
function placeId(place_url) {
  const pid = place_url.replace(/\/+$/, "").split("/").pop() ?? "";
  return /^\d+$/.test(pid) ? pid : "";
}
function panel3\uD30C\uC2F1(d) {
  const \uACB0\uACFC = {};
  const \uBA54\uB274\uB4E4 = d?.menu?.menus?.items ?? [];
  \uACB0\uACFC.menus = \uBA54\uB274\uB4E4.filter((m) => m?.name && Number.isInteger(m?.price) && m.price > 0).map((m) => ({
    name: m.name,
    price: m.price,
    recommend: Boolean(m.is_recommend || m.is_ai_mate)
  }));
  const \uC0AC\uC9C4\uB4E4 = d?.photos?.photos ?? [];
  if (\uC0AC\uC9C4\uB4E4.length && \uC0AC\uC9C4\uB4E4[0]?.url) {
    \uACB0\uACFC.photo = String(\uC0AC\uC9C4\uB4E4[0].url).replace(/^http:\/\//, "https://");
  }
  const \uC810\uC218 = d?.kakaomap_review?.score_set ?? {};
  if (\uC810\uC218.average_score) {
    \uACB0\uACFC.rating = Math.round(parseFloat(\uC810\uC218.average_score) * 10) / 10;
    \uACB0\uACFC.rating_count = \uC810\uC218.review_count ?? null;
  }
  const \uD5E4\uB4DC = d?.open_hours?.headline ?? {};
  \uACB0\uACFC.open_status = [
    \uD5E4\uB4DC.display_text,
    \uD5E4\uB4DC.display_text_info
  ].filter(Boolean).join(" ");
  try {
    const days = d.open_hours.week_from_today.week_periods[0].days;
    const \uC624\uB298 = days.find((v) => v?.is_highlight) ?? days[0];
    const on = \uC624\uB298?.on_days ?? {};
    let \uC2DC\uAC04 = on.start_end_time_desc ?? "";
    const \uBE0C\uB808\uC774\uD06C = (on.break_times_desc ?? []).join(", ");
    if (\uBE0C\uB808\uC774\uD06C) \uC2DC\uAC04 += ` (${\uBE0C\uB808\uC774\uD06C})`;
    \uACB0\uACFC.hours = \uC2DC\uAC04;
  } catch {
    \uACB0\uACFC.hours = "";
  }
  const \uC544\uC774\uCF58\uB4E4 = d?.place_add_info?.ai_mate?.store_facility_icons ?? [];
  \uACB0\uACFC.booking = \uC544\uC774\uCF58\uB4E4.some((i) => (i?.text ?? "").includes("\uC608\uC57D\uAC00\uB2A5"));
  return \uACB0\uACFC;
}
async function panel3\uAC00\uC838\uC624\uAE30(pid) {
  try {
    const resp = await fetchT(`https://place-api.map.kakao.com/places/panel3/${pid}`, {
      headers: KAKAO_PANEL_HEADERS,
      timeoutMs: 1e4
    });
    if (!resp.ok) return {};
    return panel3\uD30C\uC2F1(await resp.json());
  } catch {
    return {};
  }
}
async function \uCE74\uCE74\uC624\uC0C1\uC138\uC5EC\uB7EC\uAC1C(place_urls, concurrency = 10) {
  const pids = place_urls.map(placeId).filter(Boolean);
  const \uCE90\uC2DC\uB428 = await \uCE90\uC2DC\uC5EC\uB7EC\uAC1C\uC77D\uAE30("place", pids);
  const \uBBF8\uC870\uD68C = [
    ...new Set(pids.filter((p) => !\uCE90\uC2DC\uB428.has(p)))
  ];
  const \uC2E0\uADDC = await pMap(\uBBF8\uC870\uD68C, (pid) => panel3\uAC00\uC838\uC624\uAE30(pid), concurrency);
  const \uC4F8\uAC83 = [];
  \uBBF8\uC870\uD68C.forEach((pid, i) => {
    \uCE90\uC2DC\uB428.set(pid, \uC2E0\uADDC[i]);
    if (Object.keys(\uC2E0\uADDC[i]).length) \uC4F8\uAC83.push({
      key: pid,
      value: \uC2E0\uADDC[i]
    });
  });
  await \uCE90\uC2DC\uC5EC\uB7EC\uAC1C\uC4F0\uAE30("place", \uC4F8\uAC83, TTL.place);
  const out = /* @__PURE__ */ new Map();
  for (const url of place_urls) {
    const pid = placeId(url);
    out.set(url, pid && \uCE90\uC2DC\uB428.get(pid) || {});
  }
  return out;
}
async function \uCE74\uCE74\uC624\uC0AC\uC9C4(place_url) {
  const pid = placeId(place_url);
  if (!pid) return null;
  const \uCE90\uC2DC = await \uCE90\uC2DC\uC77D\uAE30("photo", pid);
  if (\uCE90\uC2DC) return \uCE90\uC2DC.url;
  let url = null;
  try {
    const resp = await fetchT(`https://place.map.kakao.com/${pid}`, {
      headers: {
        "User-Agent": \uBE0C\uB77C\uC6B0\uC800_UA
      },
      timeoutMs: 1e4
    });
    if (resp.ok) {
      const html = await resp.text();
      const m = html.match(/property="og:image"\s+content="([^"]+)"/);
      if (m && m[1].includes("fname=")) {
        url = m[1].startsWith("//") ? `https:${m[1]}` : m[1];
      }
    }
  } catch {
    return null;
  }
  await \uCE90\uC2DC\uC4F0\uAE30("photo", pid, {
    url
  }, TTL.photo);
  return url;
}

// supabase/functions/api/naver.ts
var \uC800\uC7A5\uB9AC\uC2A4\uD2B8_API = "https://pages.map.naver.com/save-pages/api/maps-bookmark/v3/shares";
var \uC800\uC7A5\uB9AC\uC2A4\uD2B8_\uD5E4\uB354 = {
  "User-Agent": \uBE0C\uB77C\uC6B0\uC800_UA,
  "Accept": "application/json",
  "Referer": "https://pages.map.naver.com/"
};
function \uC800\uC7A5\uB9C1\uD06C\uB4E4() {
  if (!MY_PLACE_LINKS) return [];
  return MY_PLACE_LINKS.split(/[,\s]+/).filter((s) => s.trim() && !s.startsWith("#"));
}
async function \uACF5\uC720ID\uCD94\uCD9C(\uB9C1\uD06C) {
  const s = \uB9C1\uD06C.trim();
  if (!s || s.startsWith("#")) return "";
  const m = s.match(/([0-9a-f]{32})/);
  if (m) return m[1];
  try {
    const resp = await fetchT(s, {
      headers: \uC800\uC7A5\uB9AC\uC2A4\uD2B8_\uD5E4\uB354,
      redirect: "follow",
      timeoutMs: 1e4
    });
    const byUrl = resp.url.match(/([0-9a-f]{32})/);
    if (byUrl) return byUrl[1];
    const body = (await resp.text()).slice(0, 4e3);
    return body.match(/([0-9a-f]{32})/)?.[1] ?? "";
  } catch {
    return "";
  }
}
async function \uB9C1\uD06C\uD558\uB098\uC77D\uAE30(\uB9C1\uD06C) {
  const fid = await \uACF5\uC720ID\uCD94\uCD9C(\uB9C1\uD06C);
  if (!fid) return [];
  const \uBAA9\uB85D = [];
  try {
    const \uBA54\uD0C0resp = await fetchT(`${\uC800\uC7A5\uB9AC\uC2A4\uD2B8_API}/${fid}`, {
      headers: \uC800\uC7A5\uB9AC\uC2A4\uD2B8_\uD5E4\uB354,
      timeoutMs: 15e3
    });
    const \uBA54\uD0C0 = await \uBA54\uD0C0resp.json().catch(() => null);
    const \uD3F4\uB354\uBA85 = \uBA54\uD0C0?.folder?.name || "\uC800\uC7A5";
    for (let \uC2DC\uC791 = 0; ; \uC2DC\uC791 += 300) {
      const qs = new URLSearchParams({
        start: String(\uC2DC\uC791),
        limit: "300"
      });
      const resp = await fetchT(`${\uC800\uC7A5\uB9AC\uC2A4\uD2B8_API}/${fid}/bookmarks?${qs}`, {
        headers: \uC800\uC7A5\uB9AC\uC2A4\uD2B8_\uD5E4\uB354,
        timeoutMs: 2e4
      });
      const \uD56D\uBAA9\uB4E4 = (await resp.json().catch(() => null))?.bookmarkList ?? [];
      for (const b of \uD56D\uBAA9\uB4E4) {
        if (b?.name && b?.px && b?.py) {
          \uBAA9\uB85D.push({
            name: b.name,
            lat: parseFloat(b.py),
            lng: parseFloat(b.px),
            folder: \uD3F4\uB354\uBA85,
            norm_name: \uC774\uB984\uC815\uADDC\uD654(b.name)
          });
        }
      }
      if (\uD56D\uBAA9\uB4E4.length < 300) break;
    }
  } catch (e) {
    console.warn(`\uB0B4 \uC800\uC7A5 \uB9DB\uC9D1 \uB85C\uB4DC \uC2E4\uD328(${\uB9C1\uD06C.slice(0, 40)}):`, e.message);
  }
  return \uBAA9\uB85D;
}
async function \uAC31\uC2E0\uD544\uC694\uD55C\uAC00() {
  const { data } = await db().from("my_places_sync").select("refreshed_at").eq("id", true).maybeSingle();
  if (!data) return true;
  return Date.now() - new Date(data.refreshed_at).getTime() > TTL.myPlaces * 1e3;
}
async function \uD14C\uC774\uBE14\uC5D0\uC11C\uC77D\uAE30() {
  const out = [];
  for (let from = 0; ; from += 1e3) {
    const { data, error } = await db().from("my_places").select("name, lat, lng, folder, norm_name").order("id").range(from, from + 999);
    if (error || !data?.length) break;
    out.push(...data);
    if (data.length < 1e3) break;
  }
  return out;
}
async function \uB0B4\uB9DB\uC9D1\uBAA9\uB85D() {
  const \uB9C1\uD06C\uB4E4 = \uC800\uC7A5\uB9C1\uD06C\uB4E4();
  if (!\uB9C1\uD06C\uB4E4.length) return [];
  if (!await \uAC31\uC2E0\uD544\uC694\uD55C\uAC00()) {
    const \uC800\uC7A5\uBD84 = await \uD14C\uC774\uBE14\uC5D0\uC11C\uC77D\uAE30();
    if (\uC800\uC7A5\uBD84.length) return \uC800\uC7A5\uBD84;
  }
  const \uBB36\uC74C = await Promise.all(\uB9C1\uD06C\uB4E4.map(\uB9C1\uD06C\uD558\uB098\uC77D\uAE30));
  const \uBAA9\uB85D = \uBB36\uC74C.flat();
  if (\uBAA9\uB85D.length) {
    await db().from("my_places").delete().neq("id", 0);
    for (let i = 0; i < \uBAA9\uB85D.length; i += 500) {
      const { error } = await db().from("my_places").insert(\uBAA9\uB85D.slice(i, i + 500));
      if (error) console.warn("\uB0B4 \uC800\uC7A5 \uB9DB\uC9D1 \uC800\uC7A5 \uC2E4\uD328:", error.message);
    }
    await db().from("my_places_sync").upsert({
      id: true,
      refreshed_at: (/* @__PURE__ */ new Date()).toISOString(),
      link_count: \uB9C1\uD06C\uB4E4.length,
      place_count: \uBAA9\uB85D.length
    });
    console.log(`\uB0B4 \uC800\uC7A5 \uB9DB\uC9D1 ${\uBAA9\uB85D.length}\uACF3 \uB85C\uB4DC`);
    return \uBAA9\uB85D;
  }
  return await \uD14C\uC774\uBE14\uC5D0\uC11C\uC77D\uAE30();
}
function \uC800\uC7A5\uBC30\uC9C0(\uD3F4\uB354\uBA85) {
  if (\uD3F4\uB354\uBA85.includes("\uAC00\uBCF8")) return "\u2665 \uAC00\uBCF8\uACF3";
  if (\uD3F4\uB354\uBA85.includes("\uAC00\uBCFC")) return "\u2661 \uAC00\uBCFC\uACF3";
  if (\uD3F4\uB354\uBA85.includes("\uCE74\uD398") || \uD3F4\uB354\uBA85.includes("\uB514\uC800\uD2B8")) return "\u2615 \uB0B4\uC800\uC7A5";
  return "\u2665 \uB0B4\uC800\uC7A5";
}

// supabase/functions/api/places.ts
async function \uC778\uC99D\uB9F5(x, y, radius) {
  const \uD0A4 = `${x.toFixed(3)}|${y.toFixed(3)}|${radius}`;
  const \uCE90\uC2DC = await \uCE90\uC2DC\uC77D\uAE30("cert", \uD0A4);
  if (\uCE90\uC2DC) return \uCE90\uC2DC;
  const \uACB0\uACFC = {};
  const \uD56D\uBAA9\uB4E4 = Object.entries(\uC778\uC99D\uAC80\uC0C9\uC5B4);
  const \uBB36\uC74C = await pMap(\uD56D\uBAA9\uB4E4, async ([c, \uC9C8\uC758\uB4E4]) => {
    const \uCC3E\uC74C = [];
    for (const \uC9C8\uC758 of \uC9C8\uC758\uB4E4) {
      for (const d of await \uC7A5\uC18C\uC218\uC9D1(\uC9C8\uC758, x, y, radius)) \uCC3E\uC74C.push(d.place_name);
    }
    return [
      \uC778\uC99D\uD45C\uC2DC\uBA85[c],
      \uCC3E\uC74C
    ];
  }, 4);
  for (const [\uBC30\uC9C0, \uC774\uB984\uB4E4] of \uBB36\uC74C) {
    for (const \uC774\uB984 of \uC774\uB984\uB4E4) {
      const \uD0A4\uC774\uB984 = \uC774\uB984\uC815\uADDC\uD654(\uC774\uB984);
      if (!\uD0A4\uC774\uB984) continue;
      \uACB0\uACFC[\uD0A4\uC774\uB984] ??= [];
      if (!\uACB0\uACFC[\uD0A4\uC774\uB984].includes(\uBC30\uC9C0)) \uACB0\uACFC[\uD0A4\uC774\uB984].push(\uBC30\uC9C0);
    }
  }
  await \uCE90\uC2DC\uC4F0\uAE30("cert", \uD0A4, \uACB0\uACFC, TTL.cert);
  return \uACB0\uACFC;
}
function \uC778\uC99D\uBC30\uC9C0\uCC3E\uAE30(place_name, \uC778\uC99D\uC815\uBCF4) {
  const \uC774\uB984 = \uC774\uB984\uC815\uADDC\uD654(place_name);
  if (!\uC774\uB984) return [];
  if (\uC778\uC99D\uC815\uBCF4[\uC774\uB984]) return \uC778\uC99D\uC815\uBCF4[\uC774\uB984];
  for (const [\uB4F1\uB85D\uBA85, \uBC30\uC9C0\uB4E4] of Object.entries(\uC778\uC99D\uC815\uBCF4)) {
    if (\uB4F1\uB85D\uBA85.length >= 3 && (\uC774\uB984.startsWith(\uB4F1\uB85D\uBA85) || \uB4F1\uB85D\uBA85.startsWith(\uC774\uB984))) {
      return \uBC30\uC9C0\uB4E4;
    }
  }
  return [];
}
function \uB0B4\uC800\uC7A5_\uB9E4\uCE6D(place, \uC800\uC7A5\uBAA9\uB85D) {
  const \uC774\uB984 = \uC774\uB984\uC815\uADDC\uD654(place.name);
  if (!\uC774\uB984) return "";
  const \uBC30\uC9C0\uB4E4 = /* @__PURE__ */ new Set();
  for (const s of \uC800\uC7A5\uBAA9\uB85D) {
    if (\uB300\uB7B5\uAC70\uB9ACm(place.lat, place.lng, s.lat, s.lng) > 120) continue;
    const \uC800\uC7A5\uC774\uB984 = s.norm_name || \uC774\uB984\uC815\uADDC\uD654(s.name);
    if (!\uC800\uC7A5\uC774\uB984) continue;
    if (\uC774\uB984 === \uC800\uC7A5\uC774\uB984 || \uC774\uB984.startsWith(\uC800\uC7A5\uC774\uB984) || \uC800\uC7A5\uC774\uB984.startsWith(\uC774\uB984)) {
      \uBC30\uC9C0\uB4E4.add(\uC800\uC7A5\uBC30\uC9C0(s.folder));
    }
  }
  if (!\uBC30\uC9C0\uB4E4.size) return "";
  return [
    ...\uBC30\uC9C0\uB4E4
  ].find((b) => b.includes("\uAC00\uBCF8\uACF3")) ?? [
    ...\uBC30\uC9C0\uB4E4
  ].sort()[0];
}
async function \uB9DB\uC9D1\uAC80\uC0C9(x, y, radius, \uC2DC\uAC04\uB300 = "all", \uAC1C\uC218 = \uB9DB\uC9D1\uC218, cert = "none", \uD3C9\uC8104 = false, \uB0B4\uC800\uC7A5 = "prefer") {
  let \uD6C4\uBCF4 = [];
  const seen = /* @__PURE__ */ new Map();
  const \uADF8\uB8F9\uCF54\uB4DC\uB4E4 = \uAC80\uC0C9\uADF8\uB8F9\uCF54\uB4DC[\uC2DC\uAC04\uB300] ?? [
    "FD6"
  ];
  const \uC218\uC9D1 = async (\uC9C8\uC758, \uBC30\uC9C0 = "") => {
    for (const \uCF54\uB4DC of \uADF8\uB8F9\uCF54\uB4DC\uB4E4) {
      for (const d of await \uC7A5\uC18C\uC218\uC9D1(\uC9C8\uC758, x, y, radius, 45, \uCF54\uB4DC)) {
        if (!\uC2DC\uAC04\uB300\uC801\uD569(d, \uC2DC\uAC04\uB300)) continue;
        const \uAE30\uC874 = seen.get(d.id);
        if (\uAE30\uC874) {
          if (\uBC30\uC9C0 && !\uAE30\uC874.badges.includes(\uBC30\uC9C0)) \uAE30\uC874.badges.push(\uBC30\uC9C0);
          continue;
        }
        d.badges = \uBC30\uC9C0 ? [
          \uBC30\uC9C0
        ] : [];
        seen.set(d.id, d);
        \uD6C4\uBCF4.push(d);
      }
    }
  };
  if (cert === "any") {
    const \uD480\uB4E4 = [];
    for (const [c, \uC9C8\uC758\uB4E4] of Object.entries(\uC778\uC99D\uAC80\uC0C9\uC5B4)) {
      const \uC2DC\uC791 = \uD6C4\uBCF4.length;
      for (const \uC9C8\uC758 of \uC9C8\uC758\uB4E4) await \uC218\uC9D1(\uC9C8\uC758, \uC778\uC99D\uD45C\uC2DC\uBA85[c]);
      \uD480\uB4E4.push(\uD6C4\uBCF4.slice(\uC2DC\uC791));
    }
    const \uCD5C\uB300\uAE38\uC774 = Math.max(0, ...\uD480\uB4E4.map((p) => p.length));
    const \uC11E\uC74C = [];
    for (let i = 0; i < \uCD5C\uB300\uAE38\uC774; i++) {
      for (const \uBB36\uC74C of \uD480\uB4E4) if (\uBB36\uC74C[i]) \uC11E\uC74C.push(\uBB36\uC74C[i]);
    }
    \uD6C4\uBCF4 = \uC11E\uC74C;
  } else if (\uC778\uC99D\uAC80\uC0C9\uC5B4[cert]) {
    for (const \uC9C8\uC758 of \uC778\uC99D\uAC80\uC0C9\uC5B4[cert]) await \uC218\uC9D1(\uC9C8\uC758, \uC778\uC99D\uD45C\uC2DC\uBA85[cert]);
  } else {
    const \uBAA9\uD45C = \uD3C9\uC8104 ? \uAC1C\uC218 * 2 : \uAC1C\uC218;
    for (const \uAC80\uC0C9\uC5B4 of \uAC80\uC0C9\uC5B4\uD480[\uC2DC\uAC04\uB300] ?? \uAC80\uC0C9\uC5B4\uD480.all) {
      if (\uD6C4\uBCF4.length >= \uBAA9\uD45C) break;
      await \uC218\uC9D1(\uAC80\uC0C9\uC5B4);
    }
  }
  if (\uC2DC\uAC04\uB300 !== "cafe") {
    const \uC778\uC99D\uC815\uBCF4 = await \uC548\uC804\uD558\uAC8C(() => \uC778\uC99D\uB9F5(x, y, radius), {}, "\uC778\uC99D \uBC30\uC9C0 \uC870\uD68C");
    for (const d of \uD6C4\uBCF4) {
      for (const \uBC30\uC9C0 of \uC778\uC99D\uBC30\uC9C0\uCC3E\uAE30(d.place_name, \uC778\uC99D\uC815\uBCF4)) {
        if (!d.badges.includes(\uBC30\uC9C0)) d.badges.push(\uBC30\uC9C0);
      }
    }
  }
  const \uC800\uC7A5\uBAA9\uB85D = \uB0B4\uC800\uC7A5 === "prefer" || \uB0B4\uC800\uC7A5 === "only" ? await \uC548\uC804\uD558\uAC8C(() => \uB0B4\uB9DB\uC9D1\uBAA9\uB85D(), [], "\uB0B4 \uC800\uC7A5 \uB9DB\uC9D1") : [];
  if (\uC800\uC7A5\uBAA9\uB85D.length) {
    const \uAC80\uC0C9\uB428 = new Set(\uD6C4\uBCF4.map((d) => \uC774\uB984\uC815\uADDC\uD654(d.place_name)));
    let \uB204\uB77D = \uC800\uC7A5\uBAA9\uB85D.filter((s) => {
      if (\uB300\uB7B5\uAC70\uB9ACm(y, x, s.lat, s.lng) > radius) return false;
      const sn = s.norm_name || \uC774\uB984\uC815\uADDC\uD654(s.name);
      for (const n of \uAC80\uC0C9\uB428) {
        if (!n) continue;
        if (sn === n || sn.startsWith(n) || n.startsWith(sn)) return false;
      }
      return true;
    });
    const \uCE74\uD398\uD3F4\uB354 = (s) => s.folder.includes("\uCE74\uD398") || s.folder.includes("\uB514\uC800\uD2B8");
    \uB204\uB77D = \uC2DC\uAC04\uB300 === "cafe" ? [
      ...\uB204\uB77D.filter(\uCE74\uD398\uD3F4\uB354),
      ...\uB204\uB77D.filter((s) => !\uCE74\uD398\uD3F4\uB354(s))
    ] : [
      ...\uB204\uB77D.filter((s) => !\uCE74\uD398\uD3F4\uB354(s)),
      ...\uB204\uB77D.filter(\uCE74\uD398\uD3F4\uB354)
    ];
    \uB204\uB77D = \uB204\uB77D.slice(0, 30);
    if (\uB204\uB77D.length) {
      const \uACB0\uACFC\uB4E4 = await pMap(\uB204\uB77D, async (s) => {
        for (const \uCF54\uB4DC of \uADF8\uB8F9\uCF54\uB4DC\uB4E4) {
          const docs = await \uC7A5\uC18C\uC218\uC9D1(s.name, s.lng, s.lat, 300, 3, \uCF54\uB4DC);
          if (docs.length) return docs;
        }
        return [];
      }, 6);
      \uB204\uB77D.forEach((s, i) => {
        for (const d of \uACB0\uACFC\uB4E4[i]) {
          if (seen.has(d.id) || !\uC2DC\uAC04\uB300\uC801\uD569(d, \uC2DC\uAC04\uB300)) continue;
          if (\uB300\uB7B5\uAC70\uB9ACm(parseFloat(d.y), parseFloat(d.x), s.lat, s.lng) > 150) continue;
          d.badges = [];
          d.distance = String(Math.round(\uB300\uB7B5\uAC70\uB9ACm(y, x, parseFloat(d.y), parseFloat(d.x))));
          seen.set(d.id, d);
          \uD6C4\uBCF4.push(d);
          break;
        }
      });
    }
    for (const d of \uD6C4\uBCF4) {
      const \uBC30\uC9C0 = \uB0B4\uC800\uC7A5_\uB9E4\uCE6D({
        name: d.place_name,
        lat: parseFloat(d.y),
        lng: parseFloat(d.x)
      }, \uC800\uC7A5\uBAA9\uB85D);
      d._\uC800\uC7A5\uBC30\uC9C0 = \uBC30\uC9C0;
      if (\uBC30\uC9C0 && !d.badges.includes(\uBC30\uC9C0)) d.badges.unshift(\uBC30\uC9C0);
    }
    \uD6C4\uBCF4 = \uB0B4\uC800\uC7A5 === "only" ? \uD6C4\uBCF4.filter((d) => d._\uC800\uC7A5\uBC30\uC9C0) : [
      ...\uD6C4\uBCF4.filter((d) => d._\uC800\uC7A5\uBC30\uC9C0),
      ...\uD6C4\uBCF4.filter((d) => !d._\uC800\uC7A5\uBC30\uC9C0)
    ];
  }
  let \uB300\uC0C1 = \uD3C9\uC8104 ? \uD6C4\uBCF4 : \uD6C4\uBCF4.slice(0, \uAC1C\uC218);
  const \uC0C1\uC138\uB9F5 = await \uCE74\uCE74\uC624\uC0C1\uC138\uC5EC\uB7EC\uAC1C(\uB300\uC0C1.map((d) => d.place_url), 10);
  for (const d of \uB300\uC0C1) d._\uC0C1\uC138 = \uC0C1\uC138\uB9F5.get(d.place_url) ?? {};
  if (\uD3C9\uC8104) \uB300\uC0C1 = \uB300\uC0C1.filter((d) => (d._\uC0C1\uC138?.rating ?? 0) >= 4);
  return \uB300\uC0C1.slice(0, \uAC1C\uC218).map((d) => {
    const \uC0C1\uC138 = d._\uC0C1\uC138 ?? {};
    return {
      name: d.place_name,
      category: d.category_name ? d.category_name.split(" > ").pop() : "",
      address: d.road_address_name || d.address_name,
      phone: d.phone,
      url: d.place_url,
      distance: d.distance ? parseInt(d.distance, 10) : null,
      lat: parseFloat(d.y),
      lng: parseFloat(d.x),
      badges: d.badges ?? [],
      rating: \uC0C1\uC138.rating ?? null,
      rating_count: \uC0C1\uC138.rating_count ?? null,
      hours: \uC0C1\uC138.hours ?? "",
      open_status: \uC0C1\uC138.open_status ?? "",
      booking: Boolean(\uC0C1\uC138.booking)
    };
  });
}

// supabase/functions/api/llm.ts
var GEMINI_\uC0AC\uC6A9\uAC00\uB2A5 = Boolean(GEMINI_KEY);
var GEMINI_PROMPT = (\uB3D9\uB124, \uB9C8\uC9C0\uB9C9, \uAC00\uAC8C\uBAA9\uB85D) => `\uB2E4\uC74C\uC740 "${\uB3D9\uB124}" \uC778\uADFC \uC74C\uC2DD\uC810 \uBAA9\uB85D\uC774\uB2E4. \uAC00\uAC8C\uB9C8\uB2E4 \uCE74\uCE74\uC624\uB9F5 \uBA54\uB274\uD310(\uC2E4\uC81C \uAC00\uACA9)\uACFC
\uBE14\uB85C\uADF8 \uD6C4\uAE30 \uAC80\uC0C9 \uACB0\uACFC\uAC00 \uBD99\uC5B4 \uC788\uB2E4.
\uAC01 \uAC00\uAC8C\uC5D0 \uB300\uD574 \uC81C\uACF5\uB41C \uC790\uB8CC\uB9CC\uC744 \uADFC\uAC70\uB85C \uC544\uB798 \uD615\uC2DD\uC758 JSON \uBC30\uC5F4\uB85C \uB2F5\uD558\uB77C. \uB2E4\uB978 \uD14D\uC2A4\uD2B8\uB294 \uC4F0\uC9C0 \uB9C8\uB77C.

[{"index": 0,
   "menu": "\uB300\uD45C \uBA54\uB274 2~3\uAC1C (\uC27C\uD45C \uAD6C\uBD84, \uBA54\uB274\uD310\xB7\uBE14\uB85C\uADF8\uC5D0\uC11C \uD655\uC778\uB41C \uAC83\uB9CC)",
   "price": "1\uC778 \uAE30\uC900 \uAC00\uACA9\uB300 (\uC608: 1\uC778 10,000~15,000\uC6D0)",
   "mood": "\uBE14\uB85C\uADF8 \uBC18\uC751 \uD55C \uC904 \uC694\uC57D (15\uC790 \uC774\uB0B4, \uC608: \uAE0D\uC815\uC801 \xB7 \uC6E8\uC774\uD305 \uC788\uC74C)",
   "reviews": ["\uB300\uD45C \uD6C4\uAE30 \uC694\uC57D 1~2\uAC1C, \uAC01 45\uC790 \uC774\uB0B4 (\uBE14\uB85C\uADF8 \uBB38\uC7A5\uC758 \uCDE8\uC9C0\uB97C \uC0B4\uB9B0 \uC790\uC5F0\uC2A4\uB7EC\uC6B4 \uD55C\uAD6D\uC5B4)"]}, ...]

\uADDC\uCE59:
- price\uB294 \uBA54\uB274\uD310 \uAC00\uACA9\uC774 \uC788\uC73C\uBA74 \uBC18\uB4DC\uC2DC \uADF8\uAC83\uC744 \uADFC\uAC70\uB85C \uB300\uD45C \uBA54\uB274(\uB2E8\uD488/1\uC778 \uAE30\uC900) \uC704\uC8FC\uB85C \uACC4\uC0B0\uD55C\uB2E4.
  \uB300\uC6A9\uB7C9\xB7\uBAA8\uB460 \uBA54\uB274(\uC218\uBC31 g, \uC138\uD2B8)\uB294 1\uC778 \uAE30\uC900 \uD658\uC0B0\uC5D0 \uCC38\uACE0\uB9CC \uD55C\uB2E4. \uBA54\uB274\uD310\uC774 \uC5C6\uC73C\uBA74 \uBE14\uB85C\uADF8 \uADFC\uAC70\uB85C,
  \uADF8\uB798\uB3C4 \uC5C6\uC73C\uBA74 "\uC815\uBCF4 \uBD80\uC871"\uC73C\uB85C \uD45C\uAE30\uD55C\uB2E4.
- reviews\uB294 \uAD11\uACE0\uC131 \uBB38\uAD6C\uB97C \uAC70\uB974\uACE0 \uC2E4\uC81C \uACBD\uD5D8\uB2F4 \uC704\uC8FC\uB85C \uBF51\uB294\uB2E4. \uBE14\uB85C\uADF8 \uD6C4\uAE30\uAC00 \uC5C6\uB294 \uAC00\uAC8C\uB294 \uBE48 \uBC30\uC5F4\uB85C \uB454\uB2E4.
- \uC81C\uACF5\uB41C \uC790\uB8CC\uC5D0 \uADFC\uAC70\uAC00 \uC5C6\uB294 \uB0B4\uC6A9\uC740 \uC9C0\uC5B4\uB0B4\uC9C0 \uB9D0\uACE0 "\uC815\uBCF4 \uBD80\uC871"\uC73C\uB85C \uD45C\uAE30\uD55C\uB2E4.
- \uBAA8\uB4E0 \uAC00\uAC8C(index 0~${\uB9C8\uC9C0\uB9C9})\uB97C \uBE60\uC9D0\uC5C6\uC774 \uD3EC\uD568\uD55C\uB2E4.

\uAC00\uAC8C \uBAA9\uB85D:
${\uAC00\uAC8C\uBAA9\uB85D}
`;
function \uD504\uB86C\uD504\uD2B8\uB9CC\uB4E4\uAE30(\uB3D9\uB124, places, \uC790\uB8CC\uB4E4) {
  const \uBE14\uB85D = places.map((p, i) => {
    const \uC790\uB8CC = \uC790\uB8CC\uB4E4[i];
    const \uBA54\uB274\uC904 = \uC790\uB8CC.menus.slice(0, 12).map((m) => `${m.name} ${\uCC9C\uB2E8\uC704(m.price)}\uC6D0${m.recommend ? "(\uCD94\uCC9C)" : ""}`).join(", ") || "(\uBA54\uB274\uD310 \uC815\uBCF4 \uC5C6\uC74C)";
    const \uD6C4\uAE30 = \uC790\uB8CC.posts.map((b) => `  - ${b.title}: ${b.text}`).join("\n") || "  (\uBE14\uB85C\uADF8 \uD6C4\uAE30 \uC5C6\uC74C)";
    return `[${i}] ${p.name} (${p.category})
  \uBA54\uB274\uD310: ${\uBA54\uB274\uC904}
${\uD6C4\uAE30}`;
  });
  return GEMINI_PROMPT(\uB3D9\uB124, places.length - 1, \uBE14\uB85D.join("\n\n"));
}
function JSON\uBC30\uC5F4\uCD94\uCD9C(text) {
  try {
    const v = JSON.parse(text);
    if (Array.isArray(v)) return v;
  } catch {
  }
  const m = text.match(/\[[\s\S]*\]/);
  if (!m) throw new Error("\uC751\uB2F5\uC5D0\uC11C JSON \uBC30\uC5F4\uC744 \uCC3E\uC9C0 \uBABB\uD588\uC2B5\uB2C8\uB2E4");
  return JSON.parse(m[0]);
}
async function gemini\uD638\uCD9C(prompt) {
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_MODEL}:generateContent`;
  const resp = await fetchT(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-goog-api-key": GEMINI_KEY
    },
    body: JSON.stringify({
      contents: [
        {
          role: "user",
          parts: [
            {
              text: prompt
            }
          ]
        }
      ],
      // thinking_config 는 최신 flash 모델이 거부(400)하므로 사용하지 않는다
      generationConfig: {
        responseMimeType: "application/json",
        temperature: 0.3
      }
    }),
    timeoutMs: 9e4
  });
  if (!resp.ok) {
    throw new Error(`Gemini ${resp.status}: ${(await resp.text()).slice(0, 200)}`);
  }
  const data = await resp.json();
  const text = data?.candidates?.[0]?.content?.parts?.map((p) => p.text ?? "").join("");
  if (!text) throw new Error("Gemini \uC751\uB2F5\uC774 \uBE44\uC5C8\uC2B5\uB2C8\uB2E4");
  return text;
}
async function groq\uD638\uCD9C(prompt) {
  const resp = await fetchT("https://api.groq.com/openai/v1/chat/completions", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${GROQ_KEY}`
    },
    body: JSON.stringify({
      model: GROQ_MODEL,
      messages: [
        {
          role: "user",
          content: prompt
        }
      ],
      temperature: 0.3
    }),
    timeoutMs: 6e4
  });
  if (!resp.ok) {
    throw new Error(`Groq ${resp.status}: ${(await resp.text()).slice(0, 200)}`);
  }
  const data = await resp.json();
  return JSON\uBC30\uC5F4\uCD94\uCD9C(data.choices[0].message.content);
}
async function \uCCAD\uD06C\uC694\uC57D(\uB3D9\uB124, places, \uC790\uB8CC\uB4E4) {
  const \uACB0\uACFC = /* @__PURE__ */ new Map();
  if (!GEMINI_\uC0AC\uC6A9\uAC00\uB2A5 && !GROQ_KEY) return \uACB0\uACFC;
  const prompt = \uD504\uB86C\uD504\uD2B8\uB9CC\uB4E4\uAE30(\uB3D9\uB124, places, \uC790\uB8CC\uB4E4);
  let items = null;
  if (GEMINI_\uC0AC\uC6A9\uAC00\uB2A5) {
    const \uCD5C\uB300\uC2DC\uB3C4 = GROQ_KEY ? 2 : 3;
    for (let \uC2DC\uB3C4 = 0; \uC2DC\uB3C4 < \uCD5C\uB300\uC2DC\uB3C4; \uC2DC\uB3C4++) {
      try {
        items = JSON\uBC30\uC5F4\uCD94\uCD9C(await gemini\uD638\uCD9C(prompt));
        break;
      } catch (e) {
        const msg = e.message;
        const \uD55C\uB3C4 = msg.includes("429") || msg.includes("RESOURCE_EXHAUSTED");
        const \uC77C\uC2DC = msg.includes("503") || msg.includes("UNAVAILABLE");
        if ((\uD55C\uB3C4 || \uC77C\uC2DC) && \uC2DC\uB3C4 < \uCD5C\uB300\uC2DC\uB3C4 - 1) {
          await sleep(\uD55C\uB3C4 ? 6e3 : 3e3 * (\uC2DC\uB3C4 + 1));
          continue;
        }
        console.warn(`Gemini \uC2E4\uD328: ${msg.slice(0, 150)}`);
        break;
      }
    }
  }
  if (!items && GROQ_KEY) {
    try {
      items = await groq\uD638\uCD9C(prompt);
    } catch (e) {
      console.warn("Groq \uD3F4\uBC31\uB3C4 \uC2E4\uD328:", e.message);
    }
  }
  if (!items) return \uACB0\uACFC;
  for (const it of items) {
    if (!it || typeof it !== "object" || it.index == null) continue;
    const i = Number(it.index);
    if (Number.isInteger(i) && i >= 0 && i < places.length) \uACB0\uACFC.set(i, it);
  }
  return \uACB0\uACFC;
}

// supabase/functions/api/briefing.ts
async function \uAC00\uAC8C\uC790\uB8CC\uC218\uC9D1(\uB3D9\uB124, place, \uC0C1\uC138\uB9F5) {
  const \uC0C1\uC138 = \uC0C1\uC138\uB9F5.get(place.url) ?? {};
  const blogs = await \uCE74\uCE74\uC624\uBE14\uB85C\uADF8(`${\uB3D9\uB124} ${place.name}`);
  const photo = \uC0C1\uC138.photo ?? await \uCE74\uCE74\uC624\uC0AC\uC9C4(place.url);
  return {
    posts: \uBE14\uB85C\uADF8\uC815\uB9AC(blogs),
    photo: photo ?? null,
    menus: \uC0C1\uC138.menus ?? [],
    rating: \uC0C1\uC138.rating ?? null,
    rating_count: \uC0C1\uC138.rating_count ?? null
  };
}
function \uD56D\uBAA9\uB9CC\uB4E4\uAE30(\uC790\uB8CC, s) {
  const \uBA54\uB274\uD310 = \uC790\uB8CC.menus;
  let menu = s.menu;
  if (!menu || menu === "\uC815\uBCF4 \uBD80\uC871") {
    const \uB300\uD45C = \uBA54\uB274\uD310.filter((m) => m.recommend);
    const \uC6D0\uBCF8 = \uB300\uD45C.length ? \uB300\uD45C : \uBA54\uB274\uD310;
    menu = \uC6D0\uBCF8.slice(0, 3).map((m) => m.name).join(", ") || "\uC815\uBCF4 \uBD80\uC871";
  }
  let price = s.price;
  if ((!price || price === "\uC815\uBCF4 \uBD80\uC871") && \uBA54\uB274\uD310.length) {
    const \uAC00\uACA9\uB4E4 = \uBA54\uB274\uD310.map((m) => m.price).sort((a, b) => a - b);
    price = \uAC00\uACA9\uB4E4.length > 1 ? `\uBA54\uB274 ${\uCC9C\uB2E8\uC704(\uAC00\uACA9\uB4E4[0])}~${\uCC9C\uB2E8\uC704(\uAC00\uACA9\uB4E4[\uAC00\uACA9\uB4E4.length - 1])}\uC6D0` : `${\uCC9C\uB2E8\uC704(\uAC00\uACA9\uB4E4[0])}\uC6D0`;
  }
  return {
    photo: \uC790\uB8CC.photo,
    menu,
    price: price || "\uC815\uBCF4 \uBD80\uC871",
    // mood 가 비면 배지를 표시하지 않는다 ("후기 없음" 같은 무의미한 배지 제거)
    mood: s.mood ?? "",
    reviews: (s.reviews ?? []).slice(0, 2),
    rating: \uC790\uB8CC.rating,
    rating_count: \uC790\uB8CC.rating_count
  };
}
async function \uC7A1\uC0DD\uC131(cacheKey, \uB3D9\uB124, places) {
  const { data, error } = await db().from("briefing_jobs").insert({
    cache_key: cacheKey,
    neighborhood: \uB3D9\uB124,
    places,
    total: places.length
  }).select("id").single();
  if (error) throw new Error(`\uBE0C\uB9AC\uD551 \uC7A1 \uC0DD\uC131 \uC2E4\uD328: ${error.message}`);
  return {
    job: data.id,
    total: places.length,
    step: STEP_SIZE
  };
}
async function \uC7A1\uC2A4\uD15D(jobId) {
  const { data: job, error } = await db().from("briefing_jobs").select("neighborhood, places, total, cache_key, failed").eq("id", jobId).maybeSingle();
  if (error || !job) throw new Error("\uBE0C\uB9AC\uD551 \uC791\uC5C5\uC744 \uCC3E\uC744 \uC218 \uC5C6\uC2B5\uB2C8\uB2E4. \uB2E4\uC2DC \uAC80\uC0C9\uD574 \uC8FC\uC138\uC694.");
  const { data: claim, error: cErr } = await db().rpc("claim_briefing_chunk", {
    p_job: jobId,
    p_size: STEP_SIZE
  }).maybeSingle();
  if (cErr) throw new Error(`\uAD6C\uAC04 \uBC30\uC815 \uC2E4\uD328: ${cErr.message}`);
  const start = claim?.start_idx ?? job.total;
  const end = claim?.end_idx ?? job.total;
  if (start >= end) {
    return await \uB9C8\uBB34\uB9AC(jobId, job);
  }
  const places = job.places.slice(start, end);
  const \uB3D9\uB124 = job.neighborhood;
  const \uC0C1\uC138\uB9F5 = await \uCE74\uCE74\uC624\uC0C1\uC138\uC5EC\uB7EC\uAC1C(places.map((p) => p.url), 10);
  const \uC790\uB8CC\uB4E4 = await pMap(places, (p) => \uAC00\uAC8C\uC790\uB8CC\uC218\uC9D1(\uB3D9\uB124, p, \uC0C1\uC138\uB9F5), 10);
  const \uC694\uC57D = await \uCCAD\uD06C\uC694\uC57D(\uB3D9\uB124, places, \uC790\uB8CC\uB4E4);
  const items = places.map((_, i) => \uD56D\uBAA9\uB9CC\uB4E4\uAE30(\uC790\uB8CC\uB4E4[i], \uC694\uC57D.get(i) ?? {}));
  const { error: iErr } = await db().from("briefing_items").upsert(items.map((item, i) => ({
    job_id: jobId,
    idx: start + i,
    item
  })), {
    onConflict: "job_id,idx"
  });
  if (iErr) console.warn("\uBE0C\uB9AC\uD551 \uD56D\uBAA9 \uC800\uC7A5 \uC2E4\uD328:", iErr.message);
  const \uBBF8\uC694\uC57D = places.length - \uC694\uC57D.size;
  if (GEMINI_\uC0AC\uC6A9\uAC00\uB2A5 && \uBBF8\uC694\uC57D > 0) {
    const { error: error2 } = await db().rpc("bump_briefing_failed", {
      p_job: jobId,
      p_n: \uBBF8\uC694\uC57D
    });
    if (error2) console.warn("failed \uCE74\uC6B4\uD2B8 \uAC31\uC2E0 \uC2E4\uD328:", error2.message);
  }
  const { count } = await db().from("briefing_items").select("idx", {
    count: "exact",
    head: true
  }).eq("job_id", jobId);
  const processed = count ?? end;
  const done = processed >= job.total;
  if (done) await \uB9C8\uBB34\uB9AC(jobId, job);
  return {
    done,
    start,
    end,
    items,
    processed,
    total: job.total
  };
}
async function \uB9C8\uBB34\uB9AC(jobId, job) {
  const { data: rows } = await db().from("briefing_items").select("idx, item").eq("job_id", jobId).order("idx");
  const \uC644\uB8CC = rows?.length ?? 0;
  if (\uC644\uB8CC >= job.total && job.total > 0) {
    const items = (rows ?? []).map((r) => r.item);
    const { data: \uCD5C\uC2E0 } = await db().from("briefing_jobs").select("failed").eq("id", jobId).maybeSingle();
    const \uC694\uC57D\uC131\uACF5 = !GEMINI_\uC0AC\uC6A9\uAC00\uB2A5 || (\uCD5C\uC2E0?.failed ?? 0) <= job.total * 0.2;
    if (\uC694\uC57D\uC131\uACF5) await \uCE90\uC2DC\uC4F0\uAE30("detail", job.cache_key, items, TTL.detail);
    await db().from("briefing_jobs").update({
      status: "done"
    }).eq("id", jobId);
  }
  return {
    done: \uC644\uB8CC >= job.total,
    start: job.total,
    end: job.total,
    items: [],
    processed: \uC644\uB8CC,
    total: job.total
  };
}
async function \uC7A1\uACB0\uACFC(jobId) {
  const { data: job } = await db().from("briefing_jobs").select("total").eq("id", jobId).maybeSingle();
  if (!job) return [];
  const { data: rows } = await db().from("briefing_items").select("idx, item").eq("job_id", jobId).order("idx");
  const out = new Array(job.total).fill(null);
  for (const r of rows ?? []) out[r.idx] = r.item;
  return out;
}

// supabase/functions/api/auth.ts
var \uC720\uD6A8\uAE30\uAC04_\uCD08 = 60 * 60 * 24 * 30;
function b64url(bytes) {
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
async function \uC11C\uBA85(payload) {
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(`cowork-food:${APP_PASSWORD}`), {
    name: "HMAC",
    hash: "SHA-256"
  }, false, [
    "sign"
  ]);
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(payload));
  return b64url(new Uint8Array(sig));
}
function \uAC19\uC740\uAC00(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}
var \uC554\uD638\uD544\uC694 = () => Boolean(APP_PASSWORD);
async function \uD1A0\uD070\uBC1C\uAE09(pw) {
  if (!APP_PASSWORD || !\uAC19\uC740\uAC00(pw, APP_PASSWORD)) return null;
  const exp = String(Math.floor(Date.now() / 1e3) + \uC720\uD6A8\uAE30\uAC04_\uCD08);
  return `${exp}.${await \uC11C\uBA85(exp)}`;
}
async function \uD1A0\uD070\uC720\uD6A8(token) {
  if (!APP_PASSWORD) return true;
  if (!token) return false;
  const [exp, sig] = token.split(".");
  if (!exp || !sig) return false;
  if (!/^\d+$/.test(exp) || Number(exp) * 1e3 < Date.now()) return false;
  return \uAC19\uC740\uAC00(sig, await \uC11C\uBA85(exp));
}

// supabase/functions/api/page.ts
var PAGE = `<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta http-equiv="X-UA-Compatible" content="IE=edge">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>\uB9DB\uC9D1 \uBE0C\uB9AC\uD551</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: 'Malgun Gothic', sans-serif; margin: 0; background: #f4f6f9; }
  header { padding: 12px 20px; background: #1d2a3a;
           background-image: linear-gradient(120deg, #141e30, #2c3e50);
           border-bottom: 2px solid #c9a227;
           display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
           position: sticky; top: 0; z-index: 10; }
  header h1 { color: #fff; font-size: 1.05em; margin: 0 12px 0 0; white-space: nowrap; }
  header input { flex: 1; max-width: 380px; padding: 9px 12px; font-size: 1em; border: 0; border-radius: 6px; }
  header select { padding: 9px 8px; font-size: .95em; border: 0; border-radius: 6px; }
  header button { padding: 9px 18px; font-size: 1em; border: 0; border-radius: 6px;
                  background: #c9a227; color: #16222e; font-weight: bold; cursor: pointer; }
  header button:hover { background: #dbb948; }
  #status { color: #b9c6d8; font-size: .85em; margin-left: 8px; }
  #results { max-width: 1200px; margin: 0 auto; padding: 16px 20px 40px;
             display: flex; flex-wrap: wrap; justify-content: space-between;
             align-items: flex-start; }
  .notice { color: #777; font-size: .9em; padding: 24px 4px; white-space: pre-wrap; width: 100%; }
  .card { background: #fff; border: 1px solid #e3e6ea; border-radius: 12px; padding: 16px 20px;
          margin-bottom: 12px; width: calc(50% - 6px); }
  @media (max-width: 920px) { .card { width: 100%; } }
  .top { display: flex; gap: 16px; }
  .photo { width: 104px; height: 104px; border-radius: 8px; background: #e8eef7; flex-shrink: 0;
           display: flex; align-items: center; justify-content: center; color: #8aa4c8;
           font-size: .78em; overflow: hidden; }
  .photo img { width: 100%; height: 100%; object-fit: cover; }
  .info { flex: 1; min-width: 0; }
  .name { font-size: 1.05em; font-weight: bold; color: #0a4da3; text-decoration: none; }
  .name:hover { text-decoration: underline; }
  .meta { color: #888; font-size: .84em; margin-left: 8px; }
  .rate { color: #e59a13; font-size: .88em; font-weight: bold; margin-left: 8px; white-space: nowrap; }
  .badge { display: inline-block; font-size: .8em; padding: 2px 10px; border-radius: 10px;
           background: #e1f5ee; color: #085041; margin-left: 8px; vertical-align: 1px; }
  .badge.wait { background: #f0f2f5; color: #666; }
  .cert { display: inline-block; font-size: .76em; font-weight: bold; padding: 2px 9px;
          border-radius: 9px; margin-left: 6px; vertical-align: 1px; }
  .cert.c-mi { background: #7d0f0f; color: #fff; }
  .cert.c-bl { background: #123c8a; color: #fff; }
  .cert.c-hu { background: #6a4b16; color: #fff; }
  .cert.c-bw { background: #111; color: #fff; border: 1px solid #555; }
  .cert.c-my { background: #d63b5b; color: #fff; }   /* \uAC00\uBCF8\uACF3 */
  .cert.c-my2 { background: #fdeaee; color: #b02a45; border: 1px solid #f3c2ce; }  /* \uAC00\uBCFC\uACF3 */
  .cert.c-cf { background: #6b4a2f; color: #fff; }   /* \uC800\uC7A5\uD55C \uCE74\uD398 */
  #mapbtn { background: #2c3e50; color: #fff; }
  #mapbtn:hover { background: #3d5368; }
  #mapwrap { max-width: 1200px; margin: 14px auto 0; padding: 0 20px; display: none; }
  #allmap { width: 100%; height: 460px; border: 1px solid #d8dee6; border-radius: 12px;
            background: #eef1f5; }
  .map-hint { color: #778; font-size: .82em; margin: 6px 2px 0; }
  table.facts { width: 100%; font-size: .9em; margin-top: 8px; border-collapse: collapse; }
  table.facts td { padding: 3px 0; vertical-align: top; }
  table.facts td:first-child { color: #888; width: 76px; }
  .skeleton { color: #b5bcc7; }
  .reviews { border-top: 1px solid #eee; margin-top: 12px; padding-top: 10px;
             font-size: .9em; color: #555; line-height: 1.6; }
  .reviews p { margin: 0 0 4px; }
  .reviews p::before { content: '\\201C'; color: #b0bdd0; margin-right: 2px; }
  .reviews p::after { content: '\\201D'; color: #b0bdd0; margin-left: 2px; }

  /* \uC9C4\uD589 \uB9C9\uB300 \u2014 \uBE0C\uB9AC\uD551\uC774 \uCCAD\uD06C \uB2E8\uC704\uB85C \uCC44\uC6CC\uC9C0\uBBC0\uB85C \uC9C4\uD589\uB960\uC744 \uBCF4\uC5EC\uC900\uB2E4 */
  #progress { width: 100%; max-width: 1200px; margin: 0 auto; padding: 0 20px; display: none; }
  #progress .bar { height: 4px; background: #dfe4ea; border-radius: 2px; overflow: hidden; }
  #progress .fill { height: 100%; width: 0; background: #c9a227; transition: width .3s; }

  /* \uC811\uC18D \uC554\uD638 */
  #login { position: fixed; inset: 0; z-index: 100;
           background-image: linear-gradient(120deg, #141e30, #2c3e50);
           display: none; align-items: center; justify-content: center; }
  #login .box { background: #fff; border-radius: 14px; padding: 34px 38px; width: 320px; text-align: center; }
  #login h1 { font-size: 1.15em; color: #1d2a3a; margin: 0 0 18px; }
  #login input { width: 100%; padding: 11px 12px; font-size: 1em; border: 1px solid #ccd3dc;
                 border-radius: 8px; margin-bottom: 12px; }
  #login button { width: 100%; padding: 11px; font-size: 1em; background: #c9a227; color: #16222e;
                  border: 0; border-radius: 8px; font-weight: bold; cursor: pointer; }
  #login .err { color: #c0392b; font-size: .85em; margin-top: 10px; min-height: 1em; }

  /* \u2500\u2500 \uBAA8\uBC14\uC77C \uB808\uC774\uC544\uC6C3 (\uD3F0\uC5D0\uC11C \uC790\uB3D9 \uC801\uC6A9, PC \uD654\uBA74\uC740 \uC601\uD5A5 \uC5C6\uC74C) \u2500\u2500 */
  @media (max-width: 640px) {
    body { font-size: 17px; }
    header { padding: 10px 12px; gap: 6px; position: static; }
    header h1 { font-size: 1.15em; margin-right: 4px; }
    header input { flex: 1 1 100%; max-width: none; font-size: 16px; padding: 12px; }
    header select { flex: 1 1 30%; font-size: 15px; padding: 11px 6px; }
    header button { flex: 1 1 45%; font-size: 16px; padding: 12px; }
    #status { flex: 1 1 100%; margin-left: 0; font-size: .9em; }
    #results { padding: 10px 10px 40px; }
    .card { width: 100%; padding: 14px; margin-bottom: 10px; border-radius: 14px; }
    .top { gap: 12px; }
    .photo { width: 92px; height: 92px; }
    .name { font-size: 1.15em; display: inline-block; margin-bottom: 2px; }
    .meta { display: block; margin-left: 0; margin-top: 2px; font-size: .86em; }
    .rate { font-size: .95em; }
    table.facts { font-size: .95em; margin-top: 10px; }
    table.facts td { padding: 4px 0; }
    table.facts td:first-child { width: 64px; }
    .reviews { font-size: .95em; }
    #mapwrap { padding: 0 8px; }
    #allmap { height: 340px; }
    .notice { font-size: .95em; padding: 16px 6px; }
    #progress { padding: 0 10px; }
  }
</style>
</head>
<body>
<div id="login">
  <div class="box">
    <h1>\uB9DB\uC9D1 \uBE0C\uB9AC\uD551</h1>
    <input id="pw" type="password" placeholder="\uC811\uC18D \uC554\uD638" autofocus
           onkeydown="if(event.key==='Enter'||event.keyCode===13)doLogin()">
    <button onclick="doLogin()">\uC785\uC7A5</button>
    <p class="err" id="loginerr"></p>
  </div>
</div>

<header>
  <h1>\uB9DB\uC9D1 \uBE0C\uB9AC\uD551</h1>
  <input id="q" placeholder="\uB3D9\uB124 \uC774\uB984 (\uC608: \uC5ED\uC0BC\uB3D9, \uC11C\uCD08\uB3D9, \uD310\uAD50)" onkeydown="if(event.key==='Enter'||event.keyCode===13)doSearch()">
  <select id="meal" title="\uC2DC\uAC04\uB300\uBCC4 \uCD94\uCC9C \uAE30\uC900">
    <option value="all" selected>\uC804\uCCB4</option>
    <option value="lunch">\uC810\uC2EC (\uC2DD\uC0AC \uC704\uC8FC)</option>
    <option value="dinner">\uC800\uB141 (\uC220 \uD55C\uC794)</option>
    <option value="cafe">\uCE74\uD398 \xB7 \uB514\uC800\uD2B8</option>
  </select>
  <select id="radius">
    <option value="500">500m</option>
    <option value="1000">1km</option>
    <option value="1500">1.5km</option>
    <option value="2000" selected>2km</option>
    <option value="3000">3km</option>
  </select>
  <select id="cnt" title="\uCD94\uCD9C \uAC1C\uC218">
    <option value="10">10\uACF3</option>
    <option value="20">20\uACF3</option>
    <option value="30" selected>30\uACF3</option>
    <option value="40">40\uACF3</option>
    <option value="50">50\uACF3</option>
    <option value="60">60\uACF3</option>
    <option value="70">70\uACF3</option>
    <option value="80">80\uACF3</option>
    <option value="90">90\uACF3</option>
    <option value="100">100\uACF3</option>
  </select>
  <select id="cert" title="\uC778\uC99D \uB9DB\uC9D1 \uD544\uD130 (\uCE74\uCE74\uC624\uB9F5 \uAC80\uC0C9 \uC5F0\uAD00 \uAE30\uC900)">
    <option value="none" selected>\uC778\uC99D \uBB34\uAD00</option>
    <option value="any">\uC778\uC99D\uB9DB\uC9D1\uB9CC (\uD1B5\uD569)</option>
    <option value="michelin">\uBBF8\uC250\uB9B0 \uAC00\uC774\uB4DC</option>
    <option value="blueribbon">\uBE14\uB8E8\uB9AC\uBCF8</option>
    <option value="century">\uBC31\uB144\uAC00\uAC8C</option>
    <option value="bwchef">\uD751\uBC31\uC694\uB9AC\uC0AC</option>
  </select>
  <select id="rate" title="\uCE74\uCE74\uC624\uB9F5 \uBCC4\uC810 \uD544\uD130">
    <option value="0" selected>\uD3C9\uC810 \uBB34\uAD00</option>
    <option value="4">\u26054.0 \uC774\uC0C1</option>
  </select>
  <select id="mine" title="\uB124\uC774\uBC84\uC9C0\uB3C4\uC5D0 \uC800\uC7A5\uD574\uB454 \uB0B4 \uB9DB\uC9D1">
    <option value="prefer" selected>\uB0B4 \uC800\uC7A5 \uC6B0\uC120</option>
    <option value="only">\uB0B4 \uC800\uC7A5\uB9CC</option>
    <option value="off">\uB0B4 \uC800\uC7A5 \uBB34\uC2DC</option>
  </select>
  <button onclick="doSearch()">\uAC80\uC0C9</button>
  <button id="mapbtn" onclick="toggleMap()" style="display:none">\uC9C0\uB3C4\uB85C \uBCF4\uAE30</button>
  <span id="status"></span>
</header>
<div id="progress"><div class="bar"><div class="fill" id="pfill"></div></div></div>
<div id="mapwrap">
  <div id="allmap"></div>
  <p class="map-hint">\uBC88\uD638 \uD540\uC744 \uD074\uB9AD\uD558\uBA74 \uAC00\uAC8C \uC774\uB984\uC774 \uD45C\uC2DC\uB429\uB2C8\uB2E4. \uCE74\uB4DC \uBAA9\uB85D\uC758 \uBC88\uD638\uC640 \uB3D9\uC77C\uD569\uB2C8\uB2E4.</p>
</div>
<div id="results">
  <div class="notice">\uB3D9\uB124 \uC774\uB984\uC744 \uC785\uB825\uD558\uBA74 \uBC18\uACBD \uC774\uB0B4 \uB9DB\uC9D1\uC744 \uCC3E\uC544
\uC0AC\uC9C4 \xB7 \uC8FC\uC694 \uBA54\uB274 \xB7 \uAC00\uACA9\uB300 \xB7 \uBE14\uB85C\uADF8 \uBC18\uC751\uC744 \uC815\uB9AC\uD574 \uB4DC\uB9BD\uB2C8\uB2E4.

\uC2DC\uAC04\uB300\uB97C \uACE0\uB974\uBA74 \uAE30\uC900\uC774 \uB2EC\uB77C\uC9D1\uB2C8\uB2E4:
\xB7 \uC810\uC2EC \u2014 \uC2DD\uC0AC \uC704\uC8FC (\uC220\uC9D1\xB7\uC548\uC8FC \uC804\uBB38\uC810 \uC81C\uC678)
\xB7 \uC800\uB141 \u2014 \uC220\uC744 \uACC1\uB4E4\uC774\uAE30 \uC88B\uC740 \uC9D1 (\uACE0\uAE30\xB7\uD68C\xB7\uC8FC\uC810 \uB4F1)
\xB7 \uCE74\uD398\xB7\uB514\uC800\uD2B8 \u2014 \uCE74\uD398\xB7\uBCA0\uC774\uCEE4\uB9AC\xB7\uB514\uC800\uD2B8 \uC804\uBB38\uC810 (\uB8F8\uCE74\uD398 \uB4F1 \uC81C\uC678)

\uB0B4 \uC800\uC7A5 \uB9DB\uC9D1(\uB124\uC774\uBC84\uC9C0\uB3C4\uC5D0 \uC800\uC7A5\uD55C \uB9AC\uC2A4\uD2B8)\uC740 \uAE30\uBCF8\uC73C\uB85C \uB9E8 \uC704\uC5D0 \u2665\uAC00\uBCF8\uACF3\xB7\u2661\uAC00\uBCFC\uACF3
\uBC30\uC9C0\uC640 \uD568\uAED8 \uD45C\uC2DC\uB429\uB2C8\uB2E4. "\uB0B4 \uC800\uC7A5\uB9CC" \uC120\uD0DD \uC2DC \uC800\uC7A5\uD55C \uACF3\uB9CC \uBCFC \uC218 \uC788\uC2B5\uB2C8\uB2E4.

\uC778\uC99D \uD544\uD130(\uBBF8\uC250\uB9B0 \uAC00\uC774\uB4DC\xB7\uBE14\uB8E8\uB9AC\uBCF8\xB7\uBC31\uB144\uAC00\uAC8C\xB7\uD751\uBC31\uC694\uB9AC\uC0AC)\uB294 \uCE74\uCE74\uC624\uB9F5 \uAC80\uC0C9 \uC5F0\uAD00 \uAE30\uC900\uC758
\uCC38\uACE0\uC6A9 \uBD84\uB958\uC785\uB2C8\uB2E4. \uACF5\uC2DD \uBA85\uBD80\uAC00 \uACF5\uAC1C\uB418\uC5B4 \uC788\uC9C0 \uC54A\uC544 \uB204\uB77D\xB7\uC624\uD3EC\uD568\uC774 \uC788\uC744 \uC218
\uC788\uC73C\uBA70, \uBE14\uB8E8\uB9AC\uBCF8\uC740 \uB370\uC774\uD130\uAC00 \uC801\uC5B4 \uACB0\uACFC\uAC00 \uC5C6\uC744 \uC218 \uC788\uC2B5\uB2C8\uB2E4.

\uC608) "\uC5ED\uC0BC\uB3D9" / "\uC11C\uCD08\uB3D9" / "\uD310\uAD50" / "\uAC15\uB0A8\uC5ED"</div>
</div>

<script>
// IE \uBAA8\uB4DC/\uAD6C\uD615 \uBE0C\uB77C\uC6B0\uC800\uC5D0\uC11C\uB3C4 \uB3D9\uC791\uD558\uB3C4\uB85D ES5 \uBB38\uBC95(var, function, XHR)\uB9CC \uC0AC\uC6A9\uD55C\uB2E4.

// \u2500\u2500 API \uC8FC\uC18C \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
// \uC774 \uD398\uC774\uC9C0\uB294 Supabase Storage \uACF5\uAC1C \uBC84\uD0B7\uC5D0\uC11C \uC11C\uBE59\uB418\uACE0, Edge Function \uC740 \uAC19\uC740
// \uD638\uC2A4\uD2B8\uC758 /functions/v1/api \uC5D0 \uC788\uB2E4 \u2192 \uAE30\uBCF8\uAC12\uC740 \uD604\uC7AC \uC624\uB9AC\uC9C4.
// \uB2E4\uB978 \uACF3(\uB85C\uCEEC \uD30C\uC77C\xB7\uBCC4\uB3C4 \uB3C4\uBA54\uC778)\uC5D0 \uC62C\uB9B4 \uB54C\uB294 ?api=... \uB85C \uB36E\uC5B4\uC4F8 \uC218 \uC788\uB2E4.
var API = (function () {
  var m = location.search.match(/[?&]api=([^&]+)/);
  if (m) return decodeURIComponent(m[1]).replace(/\\/+$/, '');
  if (window.API_BASE) return String(window.API_BASE).replace(/\\/+$/, '');
  return location.origin + '/functions/v1/api';
})();

var TOKEN = '';
try { TOKEN = localStorage.getItem('food_token') || ''; } catch (e) { TOKEN = ''; }

function ajax(method, path, body, cb) {
  var xhr = new XMLHttpRequest();
  xhr.open(method, API + path, true);
  if (body) xhr.setRequestHeader('Content-Type', 'application/json');
  if (TOKEN) xhr.setRequestHeader('X-App-Token', TOKEN);
  xhr.onreadystatechange = function () {
    if (xhr.readyState !== 4) return;
    var data = null;
    try { data = JSON.parse(xhr.responseText); } catch (e) { data = null; }
    if (xhr.status === 401 && data && data.need_login) { showLogin(); cb(new Error('\uC778\uC99D \uD544\uC694'), null); return; }
    if (xhr.status !== 200) { cb(new Error((data && data.error) || ('HTTP ' + xhr.status)), null); return; }
    if (!data) { cb(new Error('\uC751\uB2F5\uC744 \uD574\uC11D\uD558\uC9C0 \uBABB\uD588\uC2B5\uB2C8\uB2E4'), null); return; }
    cb(null, data);
  };
  xhr.onerror = function () { cb(new Error('\uB124\uD2B8\uC6CC\uD06C \uC624\uB958'), null); };
  xhr.send(body || null);
}

// \u2500\u2500 \uC811\uC18D \uC554\uD638 \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
function showLogin() { document.getElementById('login').style.display = 'flex'; }
function hideLogin() { document.getElementById('login').style.display = 'none'; }

function doLogin() {
  var pw = document.getElementById('pw').value;
  var err = document.getElementById('loginerr');
  err.textContent = '';
  ajax('POST', '/login', JSON.stringify({ pw: pw }), function (e, data) {
    if (e || !data || !data.token) { err.textContent = '\uC554\uD638\uAC00 \uC62C\uBC14\uB974\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4.'; return; }
    TOKEN = data.token;
    try { localStorage.setItem('food_token', TOKEN); } catch (e2) {}
    hideLogin();
    loadSdk();
  });
}

function boot() {
  ajax('GET', '/config', null, function (err, cfg) {
    if (err) { document.getElementById('status').textContent = '\uC11C\uBC84\uC5D0 \uC5F0\uACB0\uD558\uC9C0 \uBABB\uD588\uC2B5\uB2C8\uB2E4: ' + err.message; return; }
    if (cfg.auth_required && !TOKEN) { showLogin(); return; }
    if (cfg.map) loadSdk();
  });
}

// \uCE74\uCE74\uC624\uB9F5 JS SDK \uB294 Edge Function \uC774 \uD504\uB85D\uC2DC\uD55C\uB2E4 (\uC571\uD0A4\uB294 \uC11C\uBC84\uC5D0\uB9CC \uC874\uC7AC).
var sdkLoaded = false;
function loadSdk() {
  if (sdkLoaded) return;
  sdkLoaded = true;
  var s = document.createElement('script');
  s.src = API + '/sdk';
  s.onerror = function () { sdkLoaded = false; };
  document.body.appendChild(s);
}

// \u2500\u2500 \uAC80\uC0C9 \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
var searching = false;
var lastPlaces = [];  // \uC9C0\uB3C4 \uD45C\uC2DC\uC6A9 \u2014 \uB9C8\uC9C0\uB9C9 \uAC80\uC0C9 \uACB0\uACFC

function \uC870\uAC74() {
  return {
    q: document.getElementById('q').value.replace(/^\\s+|\\s+$/g, ''),
    radius: document.getElementById('radius').value,
    meal: document.getElementById('meal').value,
    cnt: document.getElementById('cnt').value,
    cert: document.getElementById('cert').value,
    rate: document.getElementById('rate').value,
    mine: document.getElementById('mine').value
  };
}

function doSearch() {
  if (searching) return;
  var c = \uC870\uAC74();
  if (!c.q) return;
  searching = true;
  setProgress(0, 0);

  var status = document.getElementById('status');
  var results = document.getElementById('results');
  status.textContent = (c.cert !== 'none' || c.rate === '4')
    ? '\uC74C\uC2DD\uC810 \uAC80\uC0C9 + \uC778\uC99D\xB7\uD3C9\uC810 \uD655\uC778 \uC911... (10~30\uCD08)' : '\uC8FC\uBCC0 \uC74C\uC2DD\uC810 \uAC80\uC0C9 \uC911...';

  var qs = '/search?q=' + encodeURIComponent(c.q) + '&radius=' + c.radius + '&meal=' + c.meal
         + '&cnt=' + c.cnt + '&cert=' + c.cert + '&rate=' + c.rate + '&mine=' + c.mine;

  ajax('GET', qs, null, function (err, data) {
    if (err) { status.textContent = '\uC624\uB958: ' + err.message; searching = false; return; }
    if (data.error) {
      results.innerHTML = '<div class="notice">' + esc(data.error) + '</div>';
      status.textContent = '';
      searching = false;
      return;
    }
    lastPlaces = data.places;
    document.getElementById('mapbtn').style.display = data.places.length ? '' : 'none';
    renderMap();  // \uC9C0\uB3C4\uAC00 \uC5F4\uB824 \uC788\uC73C\uBA74 \uC0C8 \uACB0\uACFC\uB85C \uAC31\uC2E0
    renderBase(data);

    if (data.cached_detail) {
      fillDetail(data.cached_detail, 0);
      status.textContent = data.center + ' \xB7 ' + data.places.length + '\uACF3 (\uCE90\uC2DC)';
      searching = false;
      return;
    }
    runBriefing(c, data);
  });
}

// \u2500\u2500 \uBE0C\uB9AC\uD551 (\uCCAD\uD06C \uBC29\uC2DD) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
// Edge Function \uC740 \uC694\uCCAD\uB2F9 \uC2E4\uD589\uC2DC\uAC04 \uC81C\uD55C\uC774 \uC788\uC5B4 30~100\uACF3\uC744 \uD55C \uBC88\uC5D0 \uBABB \uB3CC\uB9B0\uB2E4.
// start \uB85C \uC7A1\uC744 \uB9CC\uB4E4\uACE0 step \uC744 \uBC18\uBCF5 \uD638\uCD9C\uD55C\uB2E4. \uB450 \uAC1C\uB97C \uB3D9\uC2DC\uC5D0 \uAD74\uB824 \uC2DC\uAC04\uC744 \uC904\uC778\uB2E4.
function runBriefing(c, data) {
  var status = document.getElementById('status');
  status.textContent = '\uBE14\uB85C\uADF8 \uD6C4\uAE30 \uBD84\uC11D \uC911... (' + (data.places.length <= 30 ? '30~40\uCD08' : '1~2\uBD84') + ')';

  ajax('POST', '/enrich/start', JSON.stringify(c), function (err, job) {
    if (err) { status.textContent = '\uC624\uB958: ' + err.message; searching = false; return; }
    if (job.error) { status.textContent = job.error; searching = false; return; }
    if (job.done) {  // \uC774\uBBF8 \uC644\uC131\uB41C \uBE0C\uB9AC\uD551\uC774 \uCE90\uC2DC\uC5D0 \uC788\uC5C8\uB2E4
      fillDetail(job.items, 0);
      status.textContent = data.center + ' \xB7 ' + data.places.length + '\uACF3 (\uCE90\uC2DC)';
      searching = false;
      return;
    }

    var total = job.total;
    var workers = total > job.step ? 2 : 1;  // \uAD6C\uAC04\uC774 \uD558\uB098\uBA74 \uC6CC\uCEE4\uB3C4 \uD558\uB098\uBA74 \uCDA9\uBD84
    var remaining = workers, stalled = 0, finished = false;
    setProgress(0, total);

    function \uB05D (msg) {
      if (finished) return;
      finished = true;
      searching = false;
      setProgress(total, total);
      setTimeout(function () { document.getElementById('progress').style.display = 'none'; }, 600);
      status.textContent = msg;
    }

    function step() {
      ajax('POST', '/enrich/step', JSON.stringify({ job: job.job }), function (e2, res) {
        if (finished) return;
        if (e2) { remaining--; if (!remaining) \uB05D('\uC624\uB958: ' + e2.message); return; }
        if (res.error) { remaining--; if (!remaining) \uB05D(res.error); return; }

        if (res.items && res.items.length) fillDetail(res.items, res.start);
        setProgress(res.processed, res.total);

        if (res.done) { \uB05D(data.center + ' \xB7 ' + total + '\uACF3 \uBD84\uC11D \uC644\uB8CC'); return; }

        if (res.start >= res.end) {
          // \uBC30\uC815\uD560 \uAD6C\uAC04\uC774 \uC5C6\uB2E4 = \uB2E4\uB978 \uC6CC\uCEE4\uAC00 \uC544\uC9C1 \uCC98\uB9AC \uC911. \uC7A0\uC2DC \uB4A4 \uB2E4\uC2DC \uD655\uC778\uD55C\uB2E4.
          if (++stalled > 40) { \uB05D('\uC77C\uBD80 \uAD6C\uAC04\uC774 \uC9C0\uC5F0\uB418\uACE0 \uC788\uC2B5\uB2C8\uB2E4. \uB2E4\uC2DC \uAC80\uC0C9\uD574 \uC8FC\uC138\uC694.'); return; }
          setTimeout(step, 2000);
          return;
        }
        stalled = 0;
        step();
      });
    }

    step();
    // \uB450 \uBC88\uC9F8 \uC6CC\uCEE4\uB294 \uC0B4\uC9DD \uB2A6\uAC8C \uC2DC\uC791\uD574 \uAC19\uC740 \uC21C\uAC04\uC5D0 \uAD6C\uAC04\uC744 \uB2E4\uD22C\uC9C0 \uC54A\uAC8C \uD55C\uB2E4
    if (workers > 1) setTimeout(function () { if (!finished) step(); }, 400);
  });
}

function setProgress(done, total) {
  var wrap = document.getElementById('progress');
  if (!total) { wrap.style.display = 'none'; return; }
  wrap.style.display = 'block';
  document.getElementById('pfill').style.width = Math.round(done / total * 100) + '%';
}

// \u2500\u2500 \uB80C\uB354\uB9C1 \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
function renderBase(data) {
  var results = document.getElementById('results');
  if (!data.places.length) {
    results.innerHTML = '<div class="notice">\uBC18\uACBD \uB0B4 \uC74C\uC2DD\uC810\uC744 \uCC3E\uC9C0 \uBABB\uD588\uC2B5\uB2C8\uB2E4.</div>';
    return;
  }
  results.innerHTML = data.places.map(function (p, i) {
    var certs = (p.badges || []).map(function (b) {
      var cls;
      if (b.indexOf('\u2615') >= 0) cls = 'c-cf';
      else if (b.indexOf('\uAC00\uBCF8\uACF3') >= 0) cls = 'c-my';
      else if (b.indexOf('\uAC00\uBCFC\uACF3') >= 0 || b.indexOf('\uB0B4\uC800\uC7A5') >= 0) cls = 'c-my2';
      else if (b === '\uBBF8\uC250\uB9B0') cls = 'c-mi';
      else if (b === '\uBE14\uB8E8\uB9AC\uBCF8') cls = 'c-bl';
      else if (b === '\uD751\uBC31\uC694\uB9AC\uC0AC') cls = 'c-bw';
      else cls = 'c-hu';
      return '<span class="cert ' + cls + '">' + esc(b) + '</span>';
    }).join('');
    var rating = p.rating ? '\u2605' + p.rating + (p.rating_count ? ' (' + p.rating_count + ')' : '') : '';
    var hours = p.hours ? esc(p.hours) + (p.open_status ? ' \xB7 ' + esc(p.open_status) : '') : '\uC815\uBCF4 \uC5C6\uC74C';
    var reserve = p.booking ? '\uCE74\uCE74\uC624\uB9F5 \uC608\uC57D \uAC00\uB2A5'
                : (p.phone ? '\uC804\uD654 \uC608\uC57D \uBB38\uC758 (' + esc(p.phone) + ')' : '\uB9E4\uC7A5 \uBB38\uC758');
    return '<div class="card" id="card-' + i + '">'
    + '<div class="top">'
    +   '<div class="photo" id="photo-' + i + '">\uC0AC\uC9C4 \uC900\uBE44 \uC911</div>'
    +   '<div class="info">'
    +     '<a class="name" href="' + esc(p.url) + '" target="_blank" title="\uCE74\uCE74\uC624\uB9F5\uC5D0\uC11C \uBCC4\uC810\xB7\uC0C1\uC138 \uBCF4\uAE30">' + (i + 1) + '. ' + esc(p.name) + '</a>'
    +     certs
    +     '<span class="meta">' + esc(p.category) + (p.distance != null ? ' \xB7 ' + fmtDist(p.distance) : '') + '</span>'
    +     '<span class="rate" id="rate-' + i + '">' + rating + '</span>'
    +     '<span class="badge wait" id="mood-' + i + '">\uBD84\uC11D \uC911</span>'
    +     '<table class="facts">'
    +       '<tr><td>\uC8FC\uC694 \uBA54\uB274</td><td class="skeleton" id="menu-' + i + '">\uBE14\uB85C\uADF8 \uD6C4\uAE30 \uBD84\uC11D \uC911...</td></tr>'
    +       '<tr><td>\uAC00\uACA9\uB300</td><td class="skeleton" id="price-' + i + '">...</td></tr>'
    +       '<tr><td>\uC601\uC5C5\uC2DC\uAC04</td><td>' + hours + '</td></tr>'
    +       '<tr><td>\uC608\uC57D</td><td>' + reserve + '</td></tr>'
    +       '<tr><td>\uC8FC\uC18C</td><td>' + esc(p.address) + (p.phone ? ' \xB7 ' + esc(p.phone) : '') + '</td></tr>'
    +     '</table>'
    +   '</div>'
    + '</div>'
    + '<div class="reviews" id="reviews-' + i + '" style="display:none"></div>'
    + '</div>';
  }).join('');
}

// offset: \uC774 \uCCAD\uD06C\uAC00 \uC804\uCCB4 \uBAA9\uB85D\uC5D0\uC11C \uC2DC\uC791\uD558\uB294 \uC704\uCE58 (\uCCAD\uD06C \uBC29\uC2DD\uC774\uB77C \uD544\uC694)
function fillDetail(items, offset) {
  offset = offset || 0;
  items.forEach(function (d, k) {
    if (!d) return;
    var i = offset + k;
    var photo = document.getElementById('photo-' + i);
    if (photo) {
      if (d.photo) {
        var img = document.createElement('img');
        img.referrerPolicy = 'no-referrer';
        img.alt = '';
        img.onerror = function () { photo.textContent = '\uC0AC\uC9C4 \uC5C6\uC74C'; };
        img.src = d.photo;
        photo.textContent = '';
        photo.appendChild(img);
      } else {
        photo.textContent = '\uC0AC\uC9C4 \uC5C6\uC74C';
      }
    }
    setText('menu-' + i, d.menu);
    setText('price-' + i, d.price);
    var rt = document.getElementById('rate-' + i);
    if (rt && d.rating) {
      rt.textContent = '\u2605' + d.rating + (d.rating_count ? ' (' + d.rating_count + ')' : '');
    }
    var mood = document.getElementById('mood-' + i);
    if (mood) {
      if (d.mood) { mood.textContent = d.mood; mood.className = 'badge'; }
      else { mood.style.display = 'none'; }  // \uD6C4\uAE30 \uC5C6\uC74C \uB4F1 \uBB34\uC758\uBBF8\uD55C \uBC30\uC9C0\uB294 \uD45C\uC2DC\uD558\uC9C0 \uC54A\uC74C
    }
    var rv = document.getElementById('reviews-' + i);
    if (rv && d.reviews && d.reviews.length) {
      rv.innerHTML = d.reviews.map(function (r) { return '<p>' + esc(r) + '</p>'; }).join('');
      rv.style.display = '';
    }
  });
}

function setText(id, text) {
  var el = document.getElementById(id);
  if (el) { el.textContent = text; el.classList.remove('skeleton'); }
}

function fmtDist(m) { return m >= 1000 ? (m / 1000).toFixed(1) + 'km' : m + 'm'; }

function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// \u2500\u2500 \uC9C0\uB3C4 \uBCF4\uAE30 \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
var mapOpen = false, theMap = null, mapMarkers = [], theInfo = null;

function toggleMap() {
  mapOpen = !mapOpen;
  document.getElementById('mapwrap').style.display = mapOpen ? 'block' : 'none';
  document.getElementById('mapbtn').textContent = mapOpen ? '\uC9C0\uB3C4 \uB2EB\uAE30' : '\uC9C0\uB3C4\uB85C \uBCF4\uAE30';
  if (mapOpen) renderMap();
}

function renderMap() {
  if (!mapOpen || !lastPlaces.length) return;
  if (typeof kakao === 'undefined' || !kakao.maps || !kakao.maps.load) {
    document.getElementById('allmap').innerHTML =
      '<div style="padding:40px;text-align:center;color:#889">\uC9C0\uB3C4\uB97C \uBD88\uB7EC\uC624\uC9C0 \uBABB\uD588\uC2B5\uB2C8\uB2E4.<br>KAKAO_JS_KEY \uC2DC\uD06C\uB9BF\uACFC \uCE74\uCE74\uC624 \uAC1C\uBC1C\uC790 \uCF58\uC194\uC758 \uC0AC\uC774\uD2B8 \uB3C4\uBA54\uC778 \uB4F1\uB85D\uC744 \uD655\uC778\uD574 \uC8FC\uC138\uC694.</div>';
    return;
  }
  kakao.maps.load(function () {
    var i;
    if (!theMap) {
      theMap = new kakao.maps.Map(document.getElementById('allmap'), {
        center: new kakao.maps.LatLng(lastPlaces[0].lat, lastPlaces[0].lng), level: 5
      });
      theMap.addControl(new kakao.maps.ZoomControl(), kakao.maps.ControlPosition.RIGHT);
      theInfo = new kakao.maps.InfoWindow({ removable: true });
    }
    for (i = 0; i < mapMarkers.length; i++) mapMarkers[i].setMap(null);
    mapMarkers = [];
    theInfo.close();
    var bounds = new kakao.maps.LatLngBounds();
    for (i = 0; i < lastPlaces.length; i++) {
      (function (p, idx) {
        var pos = new kakao.maps.LatLng(p.lat, p.lng);
        bounds.extend(pos);
        var marker = new kakao.maps.Marker({ map: theMap, position: pos, title: (idx + 1) + '. ' + p.name });
        kakao.maps.event.addListener(marker, 'click', function () {
          theInfo.setContent('<div style="padding:6px 10px;font-size:.85em;max-width:220px"><b>'
            + (idx + 1) + '. ' + esc(p.name) + '</b><br>' + esc(p.category)
            + (p.rating ? ' \xB7 \u2605' + p.rating : '')
            + '<br><a href="' + esc(p.url) + '" target="_blank">\uCE74\uCE74\uC624\uB9F5 \uC0C1\uC138</a></div>');
          theInfo.open(theMap, marker);
        });
        mapMarkers.push(marker);
      })(lastPlaces[i], i);
    }
    theMap.setBounds(bounds);
    setTimeout(function () { theMap.relayout(); theMap.setBounds(bounds); }, 100);
  });
}

boot();
<\/script>
</body>
</html>
`;

// supabase/functions/api/index.ts
var MEALS = [
  "all",
  "lunch",
  "dinner",
  "cafe"
];
var CERTS = [
  "none",
  "any",
  "michelin",
  "blueribbon",
  "century",
  "bwchef"
];
var MINES = [
  "prefer",
  "only",
  "off"
];
var \uC815\uC218 = (v, \uAE30\uBCF8, \uCD5C\uC18C, \uCD5C\uB300) => {
  const n = parseInt(String(v ?? ""), 10);
  return Math.min(Math.max(Number.isFinite(n) ? n : \uAE30\uBCF8, \uCD5C\uC18C), \uCD5C\uB300);
};
function \uC870\uAC74\uC77D\uAE30(get) {
  const meal = String(get("meal") ?? "all");
  const cert = String(get("cert") ?? "none");
  const mine = String(get("mine") ?? "prefer");
  return {
    q: String(get("q") ?? get("query") ?? "").trim(),
    radius: \uC815\uC218(get("radius"), 2e3, 100, 3e3),
    meal: MEALS.includes(meal) ? meal : "all",
    cnt: \uC815\uC218(get("cnt"), 30, 10, 100),
    cert: CERTS.includes(cert) ? cert : "none",
    rate: String(get("rate") ?? "0") === "4",
    mine: MINES.includes(mine) ? mine : "prefer"
  };
}
async function \uAC80\uC0C9(\uC870\uAC74) {
  if (!\uC870\uAC74.q) return {
    error: "\uB3D9\uB124 \uC774\uB984\uC744 \uC785\uB825\uD558\uC138\uC694."
  };
  requireKakaoKey();
  const key = \uAC80\uC0C9\uD0A4(\uC870\uAC74);
  const cached = await \uCE90\uC2DC\uC77D\uAE30("search", key);
  const detail = await \uCE90\uC2DC\uC77D\uAE30("detail", key);
  if (cached) return {
    ...cached,
    key,
    cached_detail: detail
  };
  const \uC88C\uD45C = await \uB3D9\uB124\uC88C\uD45C(\uC870\uAC74.q);
  if (!\uC88C\uD45C) {
    return {
      error: `"${\uC870\uAC74.q}" \uC704\uCE58\uB97C \uCC3E\uC9C0 \uBABB\uD588\uC2B5\uB2C8\uB2E4. \uB3D9\uB124 \uC774\uB984\uC744 \uB2E4\uC2DC \uD655\uC778\uD574 \uC8FC\uC138\uC694.`
    };
  }
  const [center, x, y] = \uC88C\uD45C;
  const places = await \uB9DB\uC9D1\uAC80\uC0C9(x, y, \uC870\uAC74.radius, \uC870\uAC74.meal, \uC870\uAC74.cnt, \uC870\uAC74.cert, \uC870\uAC74.rate, \uC870\uAC74.mine);
  const result = {
    center,
    places
  };
  await \uCE90\uC2DC\uC4F0\uAE30("search", key, result, TTL.search);
  return {
    ...result,
    key,
    cached_detail: null
  };
}
var _sdk = null;
async function \uCE74\uCE74\uC624SDK() {
  if (!_sdk) {
    const resp = await fetchT(`https://dapi.kakao.com/v2/maps/sdk.js?appkey=${JS_KEY}&autoload=false`, {
      timeoutMs: 1e4
    });
    if (!resp.ok) throw new Error(`SDK ${resp.status}`);
    _sdk = await resp.arrayBuffer();
  }
  return _sdk;
}
Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, {
    headers: corsHeaders()
  });
  const url = new URL(req.url);
  const sub = "/" + url.pathname.split("/").slice(4).filter(Boolean).join("/");
  const \uD1A0\uD070 = req.headers.get("x-app-token");
  try {
    if (sub === "/" || sub === "/index.html") {
      return new Response(PAGE, {
        headers: {
          "Content-Type": "text/html; charset=utf-8",
          "Cache-Control": "public, max-age=60",
          ...corsHeaders()
        }
      });
    }
    if (sub === "/config") {
      return json({
        auth_required: \uC554\uD638\uD544\uC694(),
        map: Boolean(JS_KEY),
        kakao: Boolean(KAKAO_KEY)
      });
    }
    if (sub === "/login" && req.method === "POST") {
      const { pw } = await req.json().catch(() => ({
        pw: ""
      }));
      const token = await \uD1A0\uD070\uBC1C\uAE09(String(pw ?? ""));
      if (!token) return json({
        error: "\uC554\uD638\uAC00 \uC62C\uBC14\uB974\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4."
      }, 401);
      return json({
        token
      });
    }
    if (sub === "/sdk") {
      if (!JS_KEY) return new Response("// KAKAO_JS_KEY \uBBF8\uC124\uC815", {
        status: 200
      });
      return new Response(await \uCE74\uCE74\uC624SDK(), {
        headers: {
          "Content-Type": "text/javascript; charset=utf-8",
          "Cache-Control": "public, max-age=3600",
          ...corsHeaders()
        }
      });
    }
    if (!await \uD1A0\uD070\uC720\uD6A8(\uD1A0\uD070)) {
      return json({
        error: "\uC811\uC18D \uC554\uD638 \uC778\uC99D\uC774 \uD544\uC694\uD569\uB2C8\uB2E4.",
        need_login: true
      }, 401);
    }
    if (sub === "/search") {
      return json(await \uAC80\uC0C9(\uC870\uAC74\uC77D\uAE30((k) => url.searchParams.get(k))));
    }
    if (sub === "/enrich/start" && req.method === "POST") {
      const body = await req.json().catch(() => ({}));
      const \uC870\uAC74 = \uC870\uAC74\uC77D\uAE30((k) => body[k]);
      const key = \uAC80\uC0C9\uD0A4(\uC870\uAC74);
      const \uC644\uC131\uB428 = await \uCE90\uC2DC\uC77D\uAE30("detail", key);
      if (\uC644\uC131\uB428) return json({
        done: true,
        items: \uC644\uC131\uB428
      });
      const base = await \uCE90\uC2DC\uC77D\uAE30("search", key);
      if (!base) return json({
        error: "\uBA3C\uC800 \uAC80\uC0C9\uC744 \uC2E4\uD589\uD558\uC138\uC694."
      });
      if (!base.places.length) return json({
        done: true,
        items: []
      });
      return json(await \uC7A1\uC0DD\uC131(key, \uC870\uAC74.q, base.places));
    }
    if (sub === "/enrich/step" && req.method === "POST") {
      const { job } = await req.json().catch(() => ({
        job: ""
      }));
      if (!job) return json({
        error: "job \uC774 \uD544\uC694\uD569\uB2C8\uB2E4."
      }, 400);
      return json(await \uC7A1\uC2A4\uD15D(String(job)));
    }
    if (sub === "/enrich/result") {
      const job = url.searchParams.get("job");
      if (!job) return json({
        error: "job \uC774 \uD544\uC694\uD569\uB2C8\uB2E4."
      }, 400);
      return json({
        items: await \uC7A1\uACB0\uACFC(job)
      });
    }
    if (sub === "/diag") {
      const \uB9C1\uD06C\uB4E4 = \uC800\uC7A5\uB9C1\uD06C\uB4E4();
      const \uC815\uBCF4 = {
        links: \uB9C1\uD06C\uB4E4.length,
        kakao: Boolean(KAKAO_KEY)
      };
      if (\uB9C1\uD06C\uB4E4.length) {
        const fid = await \uC548\uC804\uD558\uAC8C(() => \uACF5\uC720ID\uCD94\uCD9C(\uB9C1\uD06C\uB4E4[0]), "", "\uACF5\uC720ID");
        \uC815\uBCF4.share_id_ok = Boolean(fid);
        if (fid) {
          await \uC548\uC804\uD558\uAC8C(async () => {
            const r = await fetchT(`https://pages.map.naver.com/save-pages/api/maps-bookmark/v3/shares/${fid}/bookmarks?start=0&limit=3`, {
              headers: {
                Accept: "application/json",
                Referer: "https://pages.map.naver.com/"
              },
              timeoutMs: 15e3
            });
            \uC815\uBCF4.api_status = r.status;
            \uC815\uBCF4.api_body = (await r.text()).slice(0, 150);
            return null;
          }, null, "\uC9C4\uB2E8");
        }
      }
      return json(\uC815\uBCF4);
    }
    return json({
      error: `\uC54C \uC218 \uC5C6\uB294 \uACBD\uB85C: ${sub}`
    }, 404);
  } catch (e) {
    console.error(sub, e);
    return json({
      error: e.message
    });
  }
});
