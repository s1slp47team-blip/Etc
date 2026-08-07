// Postgres 접근 — 기존의 메모리 dict 캐시들을 대체한다.
// service_role 키를 쓰므로 RLS 를 우회한다. 이 키는 Edge Function 안에만 있고
// 프론트로 절대 나가지 않는다.

import { createClient, type SupabaseClient } from "npm:@supabase/supabase-js@2";
import { SERVICE_ROLE_KEY, SUPABASE_URL } from "./env.ts";

let _client: SupabaseClient | null = null;

export function db(): SupabaseClient {
  if (!_client) {
    if (!SUPABASE_URL || !SERVICE_ROLE_KEY) {
      throw new Error("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY 가 없습니다.");
    }
    _client = createClient(SUPABASE_URL, SERVICE_ROLE_KEY, {
      auth: { persistSession: false, autoRefreshToken: false },
    });
  }
  return _client;
}

export type Scope = "search" | "detail" | "place" | "cert" | "photo";

/** kv_cache 읽기 — 만료된 값은 없는 것으로 취급한다. */
export async function 캐시읽기<T>(scope: Scope, key: string): Promise<T | null> {
  const { data, error } = await db()
    .from("kv_cache")
    .select("value, expires_at")
    .eq("scope", scope)
    .eq("key", key)
    .maybeSingle();
  if (error || !data) return null;
  if (new Date(data.expires_at).getTime() < Date.now()) return null;
  return data.value as T;
}

/** 여러 키를 한 번에 — 가게 상세 30~100건을 개별 조회하면 왕복이 너무 많다. */
export async function 캐시여러개읽기<T>(
  scope: Scope,
  keys: readonly string[],
): Promise<Map<string, T>> {
  const out = new Map<string, T>();
  if (!keys.length) return out;
  const { data, error } = await db()
    .from("kv_cache")
    .select("key, value, expires_at")
    .eq("scope", scope)
    .in("key", [...new Set(keys)]);
  if (error || !data) return out;
  const now = Date.now();
  for (const row of data) {
    if (new Date(row.expires_at).getTime() >= now) out.set(row.key, row.value as T);
  }
  return out;
}

export async function 캐시쓰기(
  scope: Scope,
  key: string,
  value: unknown,
  ttlSeconds: number,
): Promise<void> {
  const expires_at = new Date(Date.now() + ttlSeconds * 1000).toISOString();
  const { error } = await db()
    .from("kv_cache")
    .upsert({ scope, key, value, expires_at }, { onConflict: "scope,key" });
  if (error) console.warn(`캐시 쓰기 실패(${scope}/${key}):`, error.message);
}

export async function 캐시여러개쓰기(
  scope: Scope,
  rows: readonly { key: string; value: unknown }[],
  ttlSeconds: number,
): Promise<void> {
  if (!rows.length) return;
  const expires_at = new Date(Date.now() + ttlSeconds * 1000).toISOString();
  // 같은 배치 안에 키가 중복되면 upsert 가 "affect row a second time" 으로 실패한다.
  const 유일 = new Map(rows.map((r) => [r.key, r.value]));
  const { error } = await db()
    .from("kv_cache")
    .upsert(
      [...유일].map(([key, value]) => ({ scope, key, value, expires_at })),
      { onConflict: "scope,key" },
    );
  if (error) console.warn(`캐시 일괄 쓰기 실패(${scope}):`, error.message);
}

/** 검색 조건 → 캐시 키. 기존 튜플 키 (q, radius, meal, cnt, cert, rate, mine) 과 동일. */
export function 검색키(o: {
  q: string;
  radius: number;
  meal: string;
  cnt: number;
  cert: string;
  rate: boolean;
  mine: string;
}): string {
  return [o.q, o.radius, o.meal, o.cnt, o.cert, o.rate ? "1" : "0", o.mine].join("|");
}
