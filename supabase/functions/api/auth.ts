// 접속 암호 — 파이썬판의 APP_PASSWORD + auth 쿠키를 대체한다.
//
// 파이썬판은 sha256(암호) 앞 32자를 쿠키에 심었다. 프론트가 Storage 로 분리되면서
// 쿠키 대신 X-App-Token 헤더를 쓰고, 만료가 있는 HMAC 서명 토큰으로 바꿨다.
// 위조 불가 + 30일 뒤 자동 만료. (공개 URL 유출 시 API 무료 한도 도용 방지)

import { APP_PASSWORD } from "./env.ts";

const 유효기간_초 = 60 * 60 * 24 * 30; // 30일 — 파이썬판 쿠키 Max-Age 와 동일

function b64url(bytes: Uint8Array): string {
  return btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function 서명(payload: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(`cowork-food:${APP_PASSWORD}`),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(payload));
  return b64url(new Uint8Array(sig));
}

/** 타이밍 공격을 피하기 위한 상수 시간 비교 */
function 같은가(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

export const 암호필요 = () => Boolean(APP_PASSWORD);

export async function 토큰발급(pw: string): Promise<string | null> {
  if (!APP_PASSWORD || !같은가(pw, APP_PASSWORD)) return null;
  const exp = String(Math.floor(Date.now() / 1000) + 유효기간_초);
  return `${exp}.${await 서명(exp)}`;
}

export async function 토큰유효(token: string | null): Promise<boolean> {
  if (!APP_PASSWORD) return true; // 암호 미설정 = 누구나 (파이썬판과 동일)
  if (!token) return false;
  const [exp, sig] = token.split(".");
  if (!exp || !sig) return false;
  if (!/^\d+$/.test(exp) || Number(exp) * 1000 < Date.now()) return false;
  return 같은가(sig, await 서명(exp));
}
