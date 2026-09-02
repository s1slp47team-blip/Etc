# -*- coding: utf-8 -*-
r"""
맛집 브리핑 웹앱 (카카오 반경검색·블로그 + Gemini 요약)
======================================================================

동네 이름을 입력하면:
1. 카카오 주소/키워드 검색으로 동네 좌표를 구하고
2. 반경 1km(500m~3km 조절) 이내 음식점을 카카오 키워드 검색으로 10~100곳(선택) 선별
   - 카카오 검색은 질의당 45건 제한 → 복수 검색어 병합으로 최대 100곳 확보
   - 시간대 선택: 점심(식사 위주, 술집·안주 전문 제외) / 저녁(술 동반 가능 업종 + 술집 검색 병합)
3. 가게별 카카오맵 상세(메뉴판·가격, 대표 사진, 별점) + 카카오(다음) 블로그 후기 수집
4. Gemini가 메뉴판·블로그를 근거로 대표 메뉴 / 가격대 / 블로그 반응을 요약
→ 사진·메뉴·가격이 한눈에 보이는 카드형 표로 표시

사전 준비 (환경변수):
- KAKAO_REST_API_KEY   : 카카오 장소·블로그 검색 (필수)
- GEMINI_API_KEY       : 블로그 요약 (없으면 카카오맵 메뉴판 기준으로만 표시)

실행:
   .\python312\python.exe food_briefing_app.py
   또는 "맛집브리핑_시작.bat" 더블클릭
   → 브라우저에서 http://localhost:8767 자동 오픈

※ 별점·메뉴판은 카카오맵 상세 페이지의 내부 API(비공식)에서 가져옵니다.
  막히면 별점·메뉴판 없이 블로그 요약만으로 동작합니다.
※ 검색 결과는 서버 실행 중 메모리에 캐시됩니다 (같은 동네 재검색 시 즉시 표시).
"""

import concurrent.futures
import http.server
import itertools
import json
import os
import random
import re
import socket
import sys
import threading
import time
import urllib.parse
import webbrowser

try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

import requests

# PORT: 외부 클라우드(PaaS)는 포트를 환경변수로 지정한다. 미지정 시 사내 기본 8767
PORT = int(os.environ.get("PORT", "8767"))
# HOST: 클라우드 컨테이너에는 IPv6가 없는 경우가 많아, PaaS(PORT 지정) 환경에서는
# IPv4(0.0.0.0)로 바인딩한다. 사내/로컬은 기존대로 IPv4+IPv6 듀얼스택("::")
HOST = "0.0.0.0" if os.environ.get("PORT") else "::"
맛집수 = 20  # 브리핑할 가게 수 — 가게마다 상세·블로그 조회가 붙어 개수가 곧 대기 시간이다


def _프록시적용():
    """프록시 필수망(백업서버 등)에서도 외부 API에 나갈 수 있도록,
    같은 폴더에 proxy.txt(예: http://프록시주소:포트)가 있으면 적용한다."""
    try:
        경로 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "proxy.txt")
        with open(경로, encoding="utf-8") as f:
            주소 = f.read().strip()
    except OSError:
        return
    if 주소:
        os.environ.setdefault("HTTP_PROXY", 주소)
        os.environ.setdefault("HTTPS_PROXY", 주소)
        os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")


_프록시적용()
# 무료 티어에서 고정 버전 모델(2.5-flash 등)은 일일 한도가 작아 금방 소진됨.
# latest 별칭은 별도 한도 버킷을 쓰므로 이걸 사용 (단순 요약에 충분)
GEMINI_MODEL = "gemini-flash-latest"


def _env(name: str):
    """환경변수를 읽는다. 없으면 사용자 레지스트리(재로그인 전 등록분)에서 찾는다.
    (리눅스 클라우드에는 winreg가 없으므로 ImportError도 무시)"""
    val = os.environ.get(name)
    if val:
        return val
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            return winreg.QueryValueEx(k, name)[0]
    except (OSError, ImportError):
        return None


KAKAO_KEY = _env("KAKAO_REST_API_KEY")
GEMINI_KEY = _env("GEMINI_API_KEY")
GROQ_KEY = _env("GROQ_API_KEY")  # Gemini 무료 한도 소진 시 폴백 (없으면 폴백 생략)
GROQ_MODEL = "llama-3.3-70b-versatile"
JS_KEY = _env("KAKAO_JS_KEY")  # 지도 표시용 (없으면 지도 버튼만 비활성)

# 접속 암호 (외부 공개 인스턴스용): APP_PASSWORD가 설정되어 있으면
# 로그인해야 사용 가능. 공개 URL 유출 시 API 무료 한도 도용을 막는다.
# 사내 서버·로컬(미설정)에서는 기존과 동일하게 암호 없이 동작한다.
APP_PASSWORD = _env("APP_PASSWORD")
_인증쿠키값 = ""
if APP_PASSWORD:
    import hashlib

    _인증쿠키값 = hashlib.sha256(f"cowork-food:{APP_PASSWORD}".encode("utf-8")).hexdigest()[:32]

LOGIN_PAGE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta http-equiv="X-UA-Compatible" content="IE=edge">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>맛집 브리핑 - 접속 암호</title>
<style>
  body { font-family: 'Malgun Gothic', sans-serif; background: #1d2a3a;
         background-image: linear-gradient(120deg, #141e30, #2c3e50);
         display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
  .box { background: #fff; border-radius: 14px; padding: 34px 38px; width: 320px; text-align: center; }
  h1 { font-size: 1.15em; color: #1d2a3a; margin: 0 0 18px; }
  input { width: 100%; padding: 11px 12px; font-size: 1em; border: 1px solid #ccd3dc;
          border-radius: 8px; margin-bottom: 12px; }
  button { width: 100%; padding: 11px; font-size: 1em; background: #c9a227; color: #16222e;
           border: 0; border-radius: 8px; font-weight: bold; cursor: pointer; }
  .err { color: #c0392b; font-size: .85em; margin-top: 10px; }
</style></head>
<body><div class="box">
  <h1>맛집 브리핑</h1>
  <form method="post" action="/login">
    <input type="password" name="pw" placeholder="접속 암호" autofocus>
    <button type="submit">입장</button>
  </form>
  __ERR__
</div></body></html>"""

# 카카오맵 JS SDK 프록시 — 사내망/브라우저 정책이 dapi.kakao.com을 차단하는 경우가 있어
# 우리 서버가 같은 경로로 대신 서빙한다 (건물 브리핑과 동일 방식)
SDK_PATH = "/dapi.kakao.com/v2/maps/sdk.js"
_sdk_cache: dict[str, bytes] = {}


def 카카오SDK() -> bytes:
    if "js" not in _sdk_cache:
        resp = requests.get(
            f"https://dapi.kakao.com/v2/maps/sdk.js?appkey={JS_KEY}&autoload=false",
            timeout=10,
        )
        resp.raise_for_status()
        _sdk_cache["js"] = resp.content
    return _sdk_cache["js"]

if not KAKAO_KEY:
    sys.exit(
        "오류: KAKAO_REST_API_KEY 환경변수가 없습니다.\n"
        "PowerShell에서 아래 실행 후 새 창에서 다시 시도하세요:\n"
        '[Environment]::SetEnvironmentVariable("KAKAO_REST_API_KEY", "REST키", "User")'
    )

gemini_client = None
if GEMINI_KEY:
    try:
        from google import genai
        from google.genai import types as genai_types

        gemini_client = genai.Client(api_key=GEMINI_KEY)
    except ImportError:
        pass


# ── 1. 카카오: 동네 좌표 + 반경 내 맛집 검색 ────────────────────
def _kakao_get(path: str, params: dict) -> dict:
    resp = requests.get(
        f"https://dapi.kakao.com/v2/local/{path}",
        headers={"Authorization": f"KakaoAK {KAKAO_KEY}"},
        params=params,
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"카카오 API 오류 [{resp.status_code}] {resp.text[:200]}")
    return resp.json()


def 동네좌표(query: str):
    """동네 이름 → (중심지명, 경도x, 위도y). 주소 검색 우선, 없으면 키워드 검색."""
    docs = _kakao_get("search/address.json", {"query": query, "size": 1})["documents"]
    if docs:
        d = docs[0]
        return d["address_name"], float(d["x"]), float(d["y"])
    docs = _kakao_get("search/keyword.json", {"query": query, "size": 1})["documents"]
    if docs:
        d = docs[0]
        return d["place_name"], float(d["x"]), float(d["y"])
    return None


def _장소수집(query: str, x: float, y: float, radius: int, 최대: int = 45,
              그룹코드: str = "FD6") -> list[dict]:
    """키워드 검색 결과를 카테고리 전체 경로와 함께 모은다 (정확도순).
    그룹코드: FD6=음식점, CE7=카페 (카카오는 카페를 별도 그룹으로 분류)."""
    docs, page = [], 1
    while len(docs) < 최대 and page <= 3:
        data = _kakao_get(
            "search/keyword.json",
            {
                "query": query,
                "category_group_code": 그룹코드,
                "x": x,
                "y": y,
                "radius": radius,
                "size": 15,
                "page": page,
            },
        )
        docs.extend(data["documents"])
        if data["meta"]["is_end"]:
            break
        page += 1
    return docs


# 카카오 카테고리 경로("음식점 > 한식 > 육류,고기 > 삼겹살") 부분일치 기준.
# 저녁: 술을 곁들이기 좋은 업종 / 점심: 술집·안주 전문 업종 제외 → 식사 위주
술어울림_카테고리 = (
    "술집", "호프", "요리주점", "포장마차", "민속주점", "와인", "칵테일", "오뎅바",
    "육류,고기", "곱창", "막창", "족발", "보쌈", "회", "참치", "해물", "생선",
    "게,대게", "조개", "치킨", "닭발", "오리",
)
# 저녁 화이트리스트('육류,고기' 등)에 걸리지만 술 동반성이 약한(식사 전문) 세부 업종은 뺀다
저녁제외_카테고리 = (
    "삼계탕", "죽", "도시락", "곰탕", "설렁탕", "갈비탕", "국밥", "백반",
    "가정식", "기사식당", "국수", "칼국수", "냉면",
)

# 점심은 '식사'가 목적 — 술집 계열과 술 동반성이 강한 안주·구이·회 전문점을 뺀다.
# (육류,고기 전체를 빼면 갈비탕·불고기 같은 식사류까지 사라져 세부 업종만 제외)
점심제외_카테고리 = (
    "술집", "호프", "요리주점", "포장마차", "민속주점", "와인", "칵테일", "오뎅바",
    "곱창", "막창", "닭발", "삼겹살", "회", "참치", "양꼬치", "족발", "보쌈",
)

# 업종을 직접 고른 경우에도 점심 검색에서는 빼야 할 '술집 계열'.
# (업종 우선 규칙이 시간대 필터를 건너뛰더라도, 점심의 '식사 목적'만은 지킨다)
술집계열_카테고리 = ("술집", "호프", "요리주점", "포장마차", "민속주점", "와인", "칵테일", "오뎅바")


def _카테고리매칭(doc: dict, 키워드들: tuple) -> bool:
    cat = doc.get("category_name") or ""
    return any(k in cat for k in 키워드들)


# 카페·디저트: 카카오 카페 그룹(CE7) + 음식점 그룹의 제과·베이커리·아이스크림까지 포함.
# 단, 술집으로 운영되는 곳(카페 이름의 포차 등)과 룸카페·보드게임방 등 비디저트 테마는 제외.
카페포함_카테고리 = ("카페", "제과", "베이커리", "아이스크림", "빙수", "디저트", "브런치", "도넛", "케이크")
카페제외_카테고리 = (
    "술집", "호프", "요리주점", "포장마차",
    # 음료·디저트가 목적이 아닌 공간 대여형·체험형 카페
    "룸카페", "만화카페", "보드게임", "PC방", "스터디", "방탈출", "애견", "애완",
    "고양이", "동물", "키즈", "포토", "사진", "공방", "네일", "타로", "마사지",
)


# 카카오가 '테마카페'로만 분류하는 방탈출·체험형 업소는 카테고리로 못 걸러 상호로 판단한다
카페제외_상호 = ("방탈출", "이스케이프", "escape", "비트포비아", "룸카페", "만화", "보드게임",
              "애견", "애완", "고양이", "라쿤", "키즈", "스터디", "사주", "타로")


def _시간대적합(d: dict, 시간대: str) -> bool:
    if 시간대 == "lunch":
        return not _카테고리매칭(d, 점심제외_카테고리)
    if 시간대 == "dinner":
        return _카테고리매칭(d, 술어울림_카테고리) and not _카테고리매칭(d, 저녁제외_카테고리)
    if 시간대 == "cafe":
        if not _카테고리매칭(d, 카페포함_카테고리) or _카테고리매칭(d, 카페제외_카테고리):
            return False
        이름 = (d.get("place_name") or "").lower()
        if any(k in 이름 for k in 카페제외_상호):
            return False
        # 세부 분류 없는 순수 '테마카페'는 디저트 목적이 불확실해 제외
        return (d.get("category_name") or "").strip() != "음식점 > 카페 > 테마카페"
    return True


# 카카오 키워드 검색은 질의당 최대 45건만 반환 → 개수가 많으면 복수 검색어를 병합한다.
# 앞 검색어일수록 정확도(인기) 우선순위가 높다.
검색어풀 = {
    "all": ("맛집", "식당", "음식점", "밥집", "한식", "일식", "중식", "양식", "분식", "고기", "국밥", "파스타"),
    "lunch": ("맛집", "점심", "식당", "음식점", "밥집", "한식", "일식", "중식", "양식", "분식", "국밥", "돈까스", "국수"),
    "dinner": ("맛집", "술집", "고깃집", "이자카야", "호프", "회식", "포차", "와인바", "횟집", "치킨", "곱창", "족발"),
    "cafe": ("카페", "디저트", "커피", "베이커리", "빵집", "브런치", "케이크", "빙수", "도넛", "아이스크림"),
}
# 카페 모드는 카카오 카페 그룹(CE7)을 먼저 훑고, 부족하면 음식점 그룹(제과·베이커리)에서 보충
검색그룹코드 = {"cafe": ("CE7", "FD6")}


# ── 1.5 업종(요리 종류) 필터 ────────────────────────────────────
# 시간대(점심/저녁/카페)와는 별개의 축이다. 검색어로 넓게 건지고 카테고리로 걸러낸다 —
# 검색어만 쓰면 무관한 업종이 섞이고, 카테고리만 쓰면 카카오가 세부 분류를 비워 둔
# 가게를 놓치기 때문에 둘을 겹쳐 쓴다.
# '고기'·'해산물,회'는 한식·일식에 걸쳐 있어("일식 > 회", "한식 > 해물,생선") 국가별
# 분류와 겹친다. 겹침은 그대로 둔다 — 한식을 고르면 고깃집도 나오는 게 자연스럽다.
업종정의 = {
    "korean":   {"이름": "한식",
                 "검색어": ("한식", "백반", "국밥", "찌개", "한정식", "가정식"),
                 "포함": ("한식",)},
    "chinese":  {"이름": "중식",
                 "검색어": ("중식", "중국집", "짜장면", "짬뽕", "탕수육", "마라탕"),
                 "포함": ("중식",)},
    "japanese": {"이름": "일식",
                 "검색어": ("일식", "초밥", "돈까스", "라멘", "우동", "이자카야"),
                 "포함": ("일식",)},
    "western":  {"이름": "양식",
                 "검색어": ("양식", "파스타", "스테이크", "피자", "이탈리안", "브런치"),
                 "포함": ("양식",)},
    "meat":     {"이름": "고기",
                 "검색어": ("고깃집", "삼겹살", "소고기", "갈비", "곱창", "족발"),
                 "포함": ("육류,고기", "정육", "곱창", "막창", "족발", "보쌈", "양꼬치")},
    "seafood":  {"이름": "해산물·회",
                 "검색어": ("횟집", "해산물", "조개구이", "대게", "물회", "생선구이"),
                 "포함": ("회", "해물", "생선", "조개", "게,대게", "참치", "장어",
                        "아구", "복어", "매운탕")},
    "chicken":  {"이름": "치킨",
                 "검색어": ("치킨", "닭갈비", "찜닭", "닭한마리", "닭발"),
                 "포함": ("치킨", "닭")},
    "asian":    {"이름": "아시안",
                 "검색어": ("쌀국수", "베트남", "태국", "인도", "아시안", "마라"),
                 "포함": ("아시아", "베트남", "태국", "인도", "중동")},
    "snack":    {"이름": "분식",
                 "검색어": ("분식", "떡볶이", "김밥", "순대", "튀김", "라면"),
                 "포함": ("분식",)},
}
업종키 = ("all",) + tuple(업종정의)


def _업종적합(d: dict, 업종: str) -> bool:
    정의 = 업종정의.get(업종)
    return True if not 정의 else _카테고리매칭(d, 정의["포함"])


def _적합(d: dict, 시간대: str, 업종: str = "all") -> bool:
    """시간대 · 업종을 함께 본 최종 판정.

    업종 우선 — 업종을 직접 고르면 시간대의 업종 화이트/블랙리스트는 건너뛴다.
    저녁의 '술 어울림' 목록에는 중식·양식이 없고 점심 제외 목록에는 삼겹살·회가
    있어, 그대로 AND로 걸면 '저녁 × 중식'·'점심 × 고기'가 0건이 되기 때문이다.
    다만 점심의 '식사 목적'은 지켜야 하므로 술집 계열만은 계속 제외한다."""
    if 업종 not in 업종정의:
        return _시간대적합(d, 시간대)
    if not _업종적합(d, 업종):
        return False
    if 시간대 == "cafe":
        return _시간대적합(d, 시간대)
    if 시간대 == "lunch":
        return not _카테고리매칭(d, 술집계열_카테고리)
    return True  # all · dinner — 업종 필터만으로 충분


def _검색어목록(시간대: str, 업종: str) -> tuple:
    """업종을 고르면 업종 검색어를 쓰고, 마지막에 '맛집'으로 한 번 더 훑는다.
    ('맛집'은 인기 상위를 끌어오는 역할이고, 섞여 들어온 타 업종은 카테고리가 거른다)"""
    if 업종 in 업종정의:
        return 업종정의[업종]["검색어"] + ("맛집",)
    return 검색어풀.get(시간대, 검색어풀["all"])


# ── 1.7 내 저장 맛집 (네이버지도 공유 리스트) ───────────────────
# 네이버는 개인 저장 장소 공식 API를 제공하지 않는다. 대신 지도 앱의 '공유' 기능으로
# 만든 공개 리스트를, 공유 페이지가 쓰는 내부 API(v3/shares)에서 읽어온다.
# 링크는 내맛집링크.txt에 한 줄씩 넣는다 (없으면 기능 자체가 비활성).
_저장리스트_API = "https://pages.map.naver.com/save-pages/api/maps-bookmark/v3/shares"
_저장리스트_헤더 = {
    "User-Agent": _브라우저_UA if "_브라우저_UA" in dir() else "Mozilla/5.0",
    "Accept": "application/json",
    "Referer": "https://pages.map.naver.com/",
}
_내맛집캐시: dict = {"목록": [], "시각": 0.0}
_내맛집잠금 = threading.Lock()
내맛집갱신주기 = 3600  # 1초 단위 — 네이버지도에서 새로 저장한 가게가 1시간 내 반영됨


def _공유ID추출(링크: str) -> str:
    """naver.me 단축링크 또는 map.naver.com 공유 URL에서 32자 공유 ID를 얻는다."""
    링크 = 링크.strip()
    if not 링크 or 링크.startswith("#"):
        return ""
    m = re.search(r"([0-9a-f]{32})", 링크)
    if m:
        return m.group(1)
    try:  # naver.me 단축링크는 리다이렉트를 따라가 최종 URL에서 뽑는다
        resp = requests.get(링크, headers=_저장리스트_헤더, timeout=10, allow_redirects=True)
        m = re.search(r"([0-9a-f]{32})", resp.url) or re.search(r"([0-9a-f]{32})", resp.text[:4000])
        return m.group(1) if m else ""
    except requests.RequestException:
        return ""


def _저장링크들() -> list[str]:
    """공유 링크 출처: ① 환경변수 MY_PLACE_LINKS(쉼표/공백 구분 — 외부 클라우드용)
    ② 같은 폴더의 내맛집링크.txt (사내·로컬용). 둘 다 없으면 기능 비활성."""
    링크들 = []
    환경값 = _env("MY_PLACE_LINKS")
    if 환경값:
        링크들 = [s for s in re.split(r"[,\s]+", 환경값) if s.strip()]
    if not 링크들:
        경로 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "내맛집링크.txt")
        try:
            with open(경로, encoding="utf-8") as f:
                링크들 = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
        except OSError:
            return []
    return 링크들


def 내맛집목록() -> list[dict]:
    """저장 리스트 전체를 [{name, lat, lng, folder}] 로 반환 (1시간 캐시)."""
    with _내맛집잠금:
        if _내맛집캐시["목록"] and time.time() - _내맛집캐시["시각"] < 내맛집갱신주기:
            return _내맛집캐시["목록"]
    목록 = []
    for 링크 in _저장링크들():
        fid = _공유ID추출(링크)
        if not fid:
            continue
        try:
            메타 = requests.get(f"{_저장리스트_API}/{fid}", headers=_저장리스트_헤더, timeout=15)
            폴더명 = ((메타.json() or {}).get("folder") or {}).get("name") or "저장"
            시작 = 0
            while True:  # 공유 API는 한 번에 최대 수백 건 — 넉넉히 페이징
                resp = requests.get(
                    f"{_저장리스트_API}/{fid}/bookmarks",
                    params={"start": 시작, "limit": 300},
                    headers=_저장리스트_헤더,
                    timeout=20,
                )
                항목들 = (resp.json() or {}).get("bookmarkList") or []
                for b in 항목들:
                    if b.get("name") and b.get("px") and b.get("py"):
                        목록.append(
                            {
                                "name": b["name"],
                                "lat": float(b["py"]),
                                "lng": float(b["px"]),
                                "folder": 폴더명,
                            }
                        )
                if len(항목들) < 300:
                    break
                시작 += 300
        except (requests.RequestException, ValueError) as e:
            print(f"내 저장 맛집 로드 실패({링크[:40]}): {e}")
    with _내맛집잠금:
        _내맛집캐시["목록"], _내맛집캐시["시각"] = 목록, time.time()
    if 목록:
        print(f"내 저장 맛집 {len(목록)}곳 로드")
    return 목록


def _저장배지(폴더명: str) -> str:
    """폴더 이름을 읽어 배지 문구를 만든다 (가본곳/가볼곳/카페)."""
    if "가본" in 폴더명:
        return "♥ 가본곳"
    if "가볼" in 폴더명:
        return "♡ 가볼곳"
    if "카페" in 폴더명 or "디저트" in 폴더명:
        return "☕ 내저장"
    return "♥ 내저장"


def _대략거리m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """짧은 거리용 근사 계산 (위도 1도≈111km, 경도는 cos 보정)."""
    import math

    dy = (lat1 - lat2) * 111_000
    dx = (lng1 - lng2) * 111_000 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dx, dy)


def _이름정규화(s: str) -> str:
    return re.sub(r"[^0-9a-zA-Z가-힣]", "", s or "").lower()


def 내저장_매칭(place: dict, 저장목록: list[dict]) -> str:
    """검색 결과 1곳이 내 저장 맛집인지 판정 → 배지 문구 (아니면 빈 문자열).
    좌표 120m 이내 + 이름 유사(포함 관계)면 같은 가게로 본다.
    두 리스트에 모두 있으면 '가본곳'만 표시한다 (이미 가봤으므로)."""
    이름 = _이름정규화(place["name"])
    배지들 = set()
    for s in 저장목록:
        if _대략거리m(place["lat"], place["lng"], s["lat"], s["lng"]) > 120:
            continue
        저장이름 = _이름정규화(s["name"])
        if not 저장이름 or not 이름:
            continue
        if 이름 == 저장이름 or 이름.startswith(저장이름) or 저장이름.startswith(이름):
            배지들.add(_저장배지(s["folder"]))
    if not 배지들:
        return ""
    가본 = next((b for b in 배지들 if "가본곳" in b), "")
    return 가본 or sorted(배지들)[0]


# 인증 필터: 카카오 검색의 키워드 연관도(리뷰·블로그에 해당 인증으로 언급되는 정도)를
# 이용한다. 공식 인증 명부 API가 없어(미쉐린·블루리본 모두 비공개) 참고용 분류이며,
# 블루리본은 카카오 데이터가 빈약해 결과가 적을 수 있다.
인증검색어 = {
    "michelin": ("미쉐린 가이드", "미슐랭", "미쉐린 맛집", "미쉐린 빕구르망"),
    "blueribbon": ("블루리본", "블루리본 맛집", "블루리본서베이"),
    "century": ("백년가게", "백년가게 맛집", "노포"),
    "bwchef": ("흑백요리사", "흑백요리사 맛집", "흑백요리사 셰프"),
}
인증표시명 = {"michelin": "미쉐린", "blueribbon": "블루리본", "century": "백년가게", "bwchef": "흑백요리사"}

# 인증 맛집은 반경 안에 많아야 십수 곳이라 1페이지(15건)면 충분하다.
# 기본값(45건)으로 두면 질의마다 3페이지를 넘겨 호출이 3배로 늘어난다.
인증조회건수 = 15
인증캐시TTL = 7 * 24 * 3600  # 인증 명부는 몇 달에 한 번 바뀌므로 1주일이면 넉넉하다
인증캐시버전 = 1
인증캐시최대 = 100  # 격자 항목 수 상한 — 항목당 약 15KB이므로 파일은 1.5MB 안쪽
_인증캐시파일 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_인증캐시.json")
# 캐시에 남길 필드만 추린다 — 카카오 응답 전체를 저장하면 파일이 불필요하게 커진다
_인증보관필드 = (
    "id", "place_name", "category_name", "category_group_code",
    "address_name", "road_address_name", "phone", "place_url", "x", "y",
)

_인증맵캐시: dict[str, dict] = {}  # 격자키 → {"시각": epoch, "docs": {인증키: [장소,...]}}
_인증맵잠금 = threading.Lock()


def _인증키(x: float, y: float, radius: int, 그룹코드들: tuple) -> str:
    """약 100m 격자로 묶어 캐시를 공유한다 (JSON 키로 쓰려고 문자열)."""
    return f"{round(x, 3)}:{round(y, 3)}:{radius}:{'+'.join(그룹코드들)}"


def _캐시로드(경로: str, 버전: int, 유효초: float) -> dict:
    """지난 실행이 남긴 JSON 캐시를 읽는다. 클라우드는 유휴 시 프로세스가 죽으므로,
    파일로 남겨두지 않으면 깨어날 때마다 외부 조회를 처음부터 다시 한다.
    항목마다 "시각"(epoch)이 있어야 하며, 만료된 것은 버리고 돌려준다."""
    try:
        with open(경로, encoding="utf-8") as f:
            데이터 = json.load(f)
    except (OSError, ValueError):
        return {}
    if 데이터.get("버전") != 버전:
        return {}  # 형식이 바뀌었으면 통째로 버린다
    지금, 살아있는 = time.time(), {}
    for 키, 값 in (데이터.get("항목") or {}).items():
        try:
            if 지금 - float(값["시각"]) < 유효초:
                살아있는[키] = 값
        except (KeyError, TypeError, ValueError):
            continue
    return 살아있는


def _캐시저장(경로: str, 버전: int, 항목: dict, 최대: int):
    """읽기 전용 파일시스템 등 쓰기 실패는 무시한다 — 캐시는 없어도 동작한다."""
    try:
        최신 = sorted(항목.items(), key=lambda kv: kv[1]["시각"], reverse=True)
        임시 = 경로 + ".tmp"
        with open(임시, "w", encoding="utf-8") as f:
            json.dump({"버전": 버전, "항목": dict(최신[:최대])}, f, ensure_ascii=False)
        os.replace(임시, 경로)  # 쓰다 만 파일이 남지 않도록 원자적 교체
    except (OSError, TypeError, ValueError):
        pass


def _인증캐시로드():
    _인증맵캐시.update(_캐시로드(_인증캐시파일, 인증캐시버전, 인증캐시TTL))


def _인증캐시저장():
    with _인증맵잠금:
        스냅 = dict(_인증맵캐시)
    _캐시저장(_인증캐시파일, 인증캐시버전, 스냅, 인증캐시최대)


_인증캐시로드()


def 인증자료(x: float, y: float, radius: int,
             그룹코드들: tuple = ("FD6",)) -> dict[str, list[dict]]:
    """반경 내 인증 맛집을 인증 종류별 장소 목록으로 조회한다.

    인증 배지 표시와 인증 필터가 함께 쓰는 단일 창구다. 예전에는 두 기능이
    각자 같은 질의를 돌려 인증 필터를 켜면 호출이 정확히 2배가 됐다.
    거리는 격자 중심이 아니라 실제 검색 좌표 기준으로 다시 계산해 돌려준다."""
    키 = _인증키(x, y, radius, 그룹코드들)
    지금 = time.time()

    def 내보내기(docs: dict[str, list[dict]]) -> dict[str, list[dict]]:
        결과 = {}
        for c, 목록 in docs.items():
            나온 = []
            for d in 목록:
                복사 = dict(d)  # 캐시 원본이 호출부에서 변형되지 않도록
                복사["distance"] = str(int(_대략거리m(y, x, float(d["y"]), float(d["x"]))))
                나온.append(복사)
            결과[c] = 나온
        return 결과

    with _인증맵잠금:
        항목 = _인증맵캐시.get(키)
        if 항목 and 지금 - 항목["시각"] < 인증캐시TTL:
            return 내보내기(항목["docs"])

    def 조사(항목쌍):
        c, 질의들 = 항목쌍
        모음, 본id = [], set()
        for 질의 in 질의들:
            for 코드 in 그룹코드들:
                for d in _장소수집(질의, x, y, radius, 최대=인증조회건수, 그룹코드=코드):
                    if d["id"] in 본id:
                        continue
                    본id.add(d["id"])
                    모음.append({k: d.get(k) for k in _인증보관필드})
        return c, 모음

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        docs = dict(pool.map(조사, 인증검색어.items()))
    with _인증맵잠금:
        _인증맵캐시[키] = {"시각": 지금, "docs": docs}
    _인증캐시저장()
    return 내보내기(docs)


def 인증맵(x: float, y: float, radius: int) -> dict[str, list[str]]:
    """인증 맛집을 {정규화 상호: [배지들]}로 만든다.
    인증 필터를 안 걸고 검색해도 인증 배지가 보이도록 하기 위한 것.
    카카오 장소 ID는 같은 가게라도 검색 경로에 따라 다를 수 있어 상호로 대조한다."""
    결과: dict[str, list[str]] = {}
    for c, 목록 in 인증자료(x, y, radius).items():
        배지 = 인증표시명[c]
        for d in 목록:
            키이름 = _이름정규화(d["place_name"])
            if 키이름 and 배지 not in 결과.setdefault(키이름, []):
                결과[키이름].append(배지)
    return 결과


def _인증배지찾기(place_name: str, 인증정보: dict[str, list[str]]) -> list[str]:
    """상호로 인증 배지를 찾는다. '가게명 지점명' 형태의 표기 차이도 흡수."""
    이름 = _이름정규화(place_name)
    if not 이름:
        return []
    if 이름 in 인증정보:
        return 인증정보[이름]
    for 등록명, 배지들 in 인증정보.items():
        if len(등록명) >= 3 and (이름.startswith(등록명) or 등록명.startswith(이름)):
            return 배지들
    return []


def 맛집검색(
    x: float, y: float, radius: int, 시간대: str = "all", 개수: int = 맛집수,
    cert: str = "none", 평점4: bool = False, 내저장: str = "prefer",
    업종: str = "all",
) -> list[dict]:
    """좌표 반경 내 맛집 검색.
    시간대: all/lunch(식사)/dinner(술 동반) · cert: none/any/michelin/blueribbon/century
    업종: all + 업종정의 키(korean/chinese/…) · 평점4: 카카오맵 별점 4.0 이상만."""
    후보, seen = [], {}
    그룹코드들 = 검색그룹코드.get(시간대, ("FD6",))
    if 시간대 == "cafe":
        업종 = "all"  # 카페·디저트는 업종 축과 배타 — 카페 판정만 적용한다

    def 담기(d: dict, 배지: str = ""):
        if not _적합(d, 시간대, 업종):
            return
        if d["id"] in seen:
            if 배지 and 배지 not in seen[d["id"]]["badges"]:
                seen[d["id"]]["badges"].append(배지)
            return
        d["badges"] = [배지] if 배지 else []
        seen[d["id"]] = d
        후보.append(d)

    def 수집(질의: str, 배지: str = ""):
        for 코드 in 그룹코드들:
            for d in _장소수집(질의, x, y, radius, 그룹코드=코드):
                담기(d, 배지)

    if cert == "any":
        # 인증 종류별로 따로 모은 뒤 라운드로빈으로 섞는다 —
        # 한 인증(미쉐린)의 결과가 상위를 독식해 다른 인증이 밀려나지 않게
        자료 = 인증자료(x, y, radius, 그룹코드들)
        풀들 = []
        for c in 인증검색어:
            시작 = len(후보)
            for d in 자료.get(c) or []:
                담기(d, 인증표시명[c])
            풀들.append(후보[시작:])
        후보 = [d for 묶음 in itertools.zip_longest(*풀들) for d in 묶음 if d is not None]
    elif cert in 인증검색어:
        for d in 인증자료(x, y, radius, 그룹코드들).get(cert) or []:
            담기(d, 인증표시명[cert])
    else:
        목표 = 개수 * 2 if 평점4 else 개수  # 평점 필터로 걸러질 몫을 여유 있게 수집
        for 검색어 in _검색어목록(시간대, 업종):
            if len(후보) >= 목표:
                break
            수집(검색어)

    # ── 인증 배지 보강 ────────────────────────────────────────
    # 인증 필터를 안 걸고 검색해도 인증 맛집이면 배지가 보이도록 한다
    # (카페 모드는 인증 검색어가 음식점 위주라 생략)
    if 시간대 != "cafe":
        try:
            인증정보 = 인증맵(x, y, radius)
            for d in 후보:
                for 배지 in _인증배지찾기(d["place_name"], 인증정보):
                    if 배지 not in d["badges"]:
                        d["badges"].append(배지)
        except Exception as e:
            print(f"인증 배지 조회 실패(무시): {e}")

    # ── 내 저장 맛집(네이버지도) 반영 ─────────────────────────
    저장목록 = 내맛집목록() if 내저장 in ("prefer", "only") else []
    if 저장목록:
        # 반경 안의 저장 맛집이 카카오 검색에 안 잡혔으면 이름으로 직접 찾아 보강한다
        검색됨 = {
            _이름정규화(d["place_name"])
            for d in 후보
        }
        누락 = [
            s for s in 저장목록
            if _대략거리m(y, x, s["lat"], s["lng"]) <= radius
            and not any(
                _이름정규화(s["name"]) == n
                or (n and _이름정규화(s["name"]).startswith(n))
                or (n and n.startswith(_이름정규화(s["name"])))
                for n in 검색됨
            )
        ]
        # 시간대에 맞는 리스트를 앞에 둔다 — 카페 모드에서 맛집 저장분이 앞을
        # 다 차지해 저장한 카페가 상한에 잘려나가지 않도록
        카페폴더 = lambda s: ("카페" in s["folder"] or "디저트" in s["folder"])
        if 시간대 == "cafe":
            누락 = [s for s in 누락 if 카페폴더(s)] + [s for s in 누락 if not 카페폴더(s)]
        else:
            누락 = [s for s in 누락 if not 카페폴더(s)] + [s for s in 누락 if 카페폴더(s)]
        누락 = 누락[:30]  # 과도한 호출 방지
        if 누락:
            def 개별검색(s):
                # 카페 모드는 카페 그룹(CE7)에서도 찾아야 저장한 카페가 잡힌다
                for 코드 in 그룹코드들:
                    docs = _장소수집(s["name"], s["lng"], s["lat"], 300, 최대=3, 그룹코드=코드)
                    if docs:
                        return docs
                return []

            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
                결과들 = list(pool.map(개별검색, 누락))
            for s, docs in zip(누락, 결과들):
                for d in docs:
                    if d["id"] in seen or not _적합(d, 시간대, 업종):
                        continue
                    if _대략거리m(float(d["y"]), float(d["x"]), s["lat"], s["lng"]) > 150:
                        continue
                    if cert not in ("none",) and not d.get("badges"):
                        pass  # 인증 필터 중이면 배지 없이 들어오되 저장 배지로 표시됨
                    d["badges"] = []
                    d["distance"] = str(int(_대략거리m(y, x, float(d["y"]), float(d["x"]))))
                    seen[d["id"]] = d
                    후보.append(d)
                    break
        for d in 후보:
            배지 = 내저장_매칭(
                {"name": d["place_name"], "lat": float(d["y"]), "lng": float(d["x"])}, 저장목록
            )
            d["_저장배지"] = 배지
            if 배지 and 배지 not in d["badges"]:
                d["badges"].insert(0, 배지)
        if 내저장 == "only":
            후보 = [d for d in 후보 if d.get("_저장배지")]
        else:  # prefer — 저장 맛집을 앞으로 (그 안에서는 기존 정확도순 유지)
            후보 = [d for d in 후보 if d.get("_저장배지")] + [d for d in 후보 if not d.get("_저장배지")]

    # 카카오맵 상세(평점·영업시간·예약)는 비공식 API라 느리다. 평점으로 걸러야 할
    # 때만 여기서 받고, 아니면 카드부터 먼저 그리고 /enrich 구간에서 채운다 —
    # 예전에는 30곳 상세를 다 받은 뒤에야 카드가 떠서 그동안 빈 화면이었다.
    대상 = 후보 if 평점4 else 후보[:개수]
    if 평점4:
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            상세들 = list(pool.map(lambda d: _카카오상세(d["place_url"]), 대상))
        for d, 상세 in zip(대상, 상세들):
            d["_상세"] = 상세
        대상 = [d for d in 대상 if (d["_상세"].get("rating") or 0) >= 4.0]

    places = []
    for d in 대상[:개수]:
        상세 = d.get("_상세") or {}  # 평점 필터를 안 걸었으면 비어 있다
        places.append(
            {
                "name": d["place_name"],
                "category": d["category_name"].split(" > ")[-1] if d["category_name"] else "",
                "address": d["road_address_name"] or d["address_name"],
                "phone": d["phone"],
                "url": d["place_url"],
                "distance": int(d["distance"]) if d.get("distance") else None,
                "lat": float(d["y"]),
                "lng": float(d["x"]),
                "badges": d.get("badges") or [],
                "rating": 상세.get("rating"),
                "rating_count": 상세.get("rating_count"),
                "hours": 상세.get("hours") or "",
                "open_status": 상세.get("open_status") or "",
                "booking": bool(상세.get("booking")),
            }
        )
    return places


# ── 2. 카카오(다음) 검색: 블로그 후기 ───────────────────────────
def _카카오블로그(질의: str, 개수: int = 5) -> list[dict]:
    """카카오 블로그 검색 (무료: 일 3만 건). 장소 검색과 같은 REST 키를 쓴다."""
    for 시도 in range(4):
        try:
            resp = requests.get(
                "https://dapi.kakao.com/v2/search/blog",
                headers={"Authorization": f"KakaoAK {KAKAO_KEY}"},
                params={"query": 질의, "size": 개수, "sort": "accuracy"},
                timeout=10,
            )
        except requests.RequestException:
            return []
        if resp.status_code == 429:  # 초당 호출 제한 초과 → 잠시 대기 후 재시도
            time.sleep(0.5 * (시도 + 1))
            continue
        if resp.status_code != 200:
            return []
        return resp.json().get("documents", [])
    return []


def _태그제거(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s)
    return s.replace("&quot;", '"').replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")


_브라우저_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

_KAKAO_PANEL_HEADERS = {
    "User-Agent": _브라우저_UA,
    "Accept": "application/json",
    "Origin": "https://place.map.kakao.com",
    "Referer": "https://place.map.kakao.com/",
    "pf": "web",
}


_상세결과캐시: dict[str, dict] = {}  # place id → panel3 요약 (검색·분석 단계 간 재사용)
_상세캐시잠금 = threading.Lock()


# 카카오맵 상세(panel3)와 상세 페이지는 비공식 경로라, 한꺼번에 몰아 부르면
# 앞의 몇 건만 받고 나머지를 막는다. 예전에는 검색이 동시 10개로 두드리고
# 막히면 즉시 포기해, 11번째 가게부터 사진·별점이 통째로 비었다.
#
# 실제 제한값이 공개돼 있지 않으므로 고정 간격을 박지 않는다. 막히면 간격을
# 늘리고 잘 통과하면 도로 줄이는 방식으로, 그때그때 통하는 속도를 찾아간다.
# 여유 있는 시간대에는 간격이 0으로 수렴해 예전만큼 빠르다.
_카카오상세동시 = threading.Semaphore(4)  # 순간 폭주를 막는 상한
_상세재시도 = 6
_상세간격상한 = 0.6
_상세페이스잠금 = threading.Lock()
_상세다음시각 = [0.0]
_상세간격 = [0.0]


def _상세페이스():
    """다음 호출까지 순서를 잡아 간격을 벌린다 (간격이 0이면 그대로 통과)."""
    with _상세페이스잠금:
        지금 = time.monotonic()
        예정 = max(지금, _상세다음시각[0])
        _상세다음시각[0] = 예정 + _상세간격[0]
    남음 = 예정 - time.monotonic()
    if 남음 > 0:
        time.sleep(남음)


def _상세제한겪음():
    with _상세페이스잠금:
        _상세간격[0] = min(_상세간격상한, max(0.1, _상세간격[0] * 2))


def _상세통과():
    with _상세페이스잠금:
        if _상세간격[0]:
            _상세간격[0] = max(0.0, _상세간격[0] * 0.9)


def _카카오상세(place_url: str) -> dict:
    """카카오맵 상세 페이지가 쓰는 내부 API(panel3)에서
    메뉴판(이름·가격)·대표 사진·별점·영업시간·예약 여부를 가져온다.
    비공식 API라 언제든 막힐 수 있으므로 실패 시 빈 dict를 돌려준다."""
    pid = place_url.rstrip("/").split("/")[-1]
    if not pid.isdigit():
        return {}
    with _상세캐시잠금:
        if pid in _상세결과캐시:
            return _상세결과캐시[pid]
    d = None
    for 시도 in range(_상세재시도):
        _상세페이스()
        try:
            with _카카오상세동시:
                resp = requests.get(
                    f"https://place-api.map.kakao.com/places/panel3/{pid}",
                    headers=_KAKAO_PANEL_HEADERS,
                    timeout=10,
                )
        except requests.RequestException:
            return {}
        if resp.status_code in (429, 403, 500, 502, 503):  # 호출 제한 → 간격을 늘리고 다시
            _상세제한겪음()
            time.sleep(0.4 * (시도 + 1))
            continue
        _상세통과()
        if resp.status_code != 200:
            return {}
        try:
            d = resp.json()
        except ValueError:
            return {}
        break
    if d is None:  # 재시도해도 계속 막히면 사진·별점 없이 나머지 정보로 표시한다
        print(f"카카오맵 상세 조회 실패({pid}) — 마지막 응답 {resp.status_code}")
        return {}
    결과 = {}
    메뉴들 = ((d.get("menu") or {}).get("menus") or {}).get("items") or []
    결과["menus"] = [
        {"name": m["name"], "price": m["price"], "recommend": bool(m.get("is_recommend") or m.get("is_ai_mate"))}
        for m in 메뉴들
        if m.get("name") and isinstance(m.get("price"), int) and m["price"] > 0
    ]
    사진들 = (d.get("photos") or {}).get("photos") or []
    if 사진들 and 사진들[0].get("url"):
        결과["photo"] = 사진들[0]["url"].replace("http://", "https://", 1)
    점수 = (d.get("kakaomap_review") or {}).get("score_set") or {}
    if 점수.get("average_score"):
        결과["rating"] = round(float(점수["average_score"]), 1)
        결과["rating_count"] = 점수.get("review_count")
    # 영업시간: 오늘 영업시간 + 현재 상태(영업중/브레이크타임 등)
    영업 = d.get("open_hours") or {}
    헤드 = 영업.get("headline") or {}
    결과["open_status"] = " ".join(
        s for s in (헤드.get("display_text"), 헤드.get("display_text_info")) if s
    )
    try:
        days = 영업["week_from_today"]["week_periods"][0]["days"]
        오늘 = next((v for v in days if v.get("is_highlight")), days[0])
        on = 오늘.get("on_days") or {}
        시간 = on.get("start_end_time_desc") or ""
        브레이크 = ", ".join(on.get("break_times_desc") or [])
        if 브레이크:
            시간 += f" ({브레이크})"
        결과["hours"] = 시간
    except (KeyError, IndexError, TypeError):
        결과["hours"] = ""
    # 예약: 매장 편의정보 아이콘에 '예약가능'이 있을 때만 (BOOKING 탭은 모든 가게에 떠서 부정확)
    아이콘들 = (((d.get("place_add_info") or {}).get("ai_mate") or {}).get("store_facility_icons")) or []
    결과["booking"] = any("예약가능" in (i.get("text") or "") for i in 아이콘들)
    with _상세캐시잠금:
        _상세결과캐시[pid] = 결과
    return 결과


def _카카오사진(place_url: str):
    """카카오맵 상세 페이지의 og:image = 그 가게의 실제 대표 사진.
    공식 REST API가 장소 사진을 제공하지 않아 페이지 메타 태그에서 가져온다."""
    pid = place_url.rstrip("/").split("/")[-1]
    if not pid.isdigit():
        return None
    resp = None
    for 시도 in range(_상세재시도):
        _상세페이스()
        try:
            with _카카오상세동시:
                resp = requests.get(
                    f"https://place.map.kakao.com/{pid}",
                    headers={"User-Agent": _브라우저_UA},
                    timeout=10,
                )
        except requests.RequestException:
            return None
        if resp.status_code in (429, 403, 500, 502, 503):
            _상세제한겪음()
            time.sleep(0.4 * (시도 + 1))
            resp = None
            continue
        _상세통과()
        if resp.status_code != 200:
            return None
        break
    if resp is None:
        return None
    m = re.search(r'property="og:image"\s+content="([^"]+)"', resp.text)
    if not m:
        return None
    url = m.group(1)
    if "fname=" not in url:  # 사진 없는 가게의 기본 og 이미지
        return None
    return "https:" + url if url.startswith("//") else url


# ── 2.5 첫 화면용 내 저장 맛집 카드 ─────────────────────────────
# 검색 전 화면이 비어 있지 않도록, 네이버지도에 저장해 둔 맛집을 사진과 함께 보여준다.
# 가게별 사진·업종은 잘 바뀌지 않으므로 파일 캐시에 남겨, 프로세스가 재시작돼도
# 첫 화면이 카카오 API 호출 없이 뜨게 한다.
홈캐시TTL = 7 * 24 * 3600
홈캐시버전 = 1
홈캐시최대 = 300
홈표시수 = 8  # 첫 화면에 띄울 카드 수
_홈캐시파일 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_홈캐시.json")
_홈캐시: dict[str, dict] = _캐시로드(_홈캐시파일, 홈캐시버전, 홈캐시TTL)
_홈캐시잠금 = threading.Lock()


def _홈뽑기(전체: list[dict], 개수: int) -> list[dict]:
    """첫 화면에 띄울 가게를 고른다.

    폴더별로 묶어 번갈아 뽑는다 — 목록 앞에서 그냥 자르면 첫 폴더가 화면을
    독식해 나머지 폴더는 영영 뜨지 않는다. 폴더 안에서는 매번 다시 섞어,
    묻혀 있던 저장 맛집도 돌아가며 보이게 한다.

    단, 이미 사진을 받아둔 가게를 앞세운다. 매번 처음 보는 가게만 뽑으면
    화면을 열 때마다 카카오 조회가 붙어 첫 화면이 느려지기 때문이다.
    (캐시가 차면 이 조건이 무의미해져 결국 전체에서 고르게 섞인다)"""
    폴더별: dict[str, list] = {}
    for s in 전체:
        폴더별.setdefault(s["folder"], []).append(s)
    with _홈캐시잠금:
        받아둔 = set(_홈캐시)
    for 목록 in 폴더별.values():
        random.shuffle(목록)
        목록.sort(key=lambda s: _이름정규화(s["name"]) not in 받아둔)  # 안정 정렬 → 섞인 순서 유지
    순서 = []
    for 묶음 in itertools.zip_longest(*폴더별.values()):
        순서.extend(s for s in 묶음 if s is not None)
    return 순서[:개수]


def 내맛집홈() -> list[dict]:
    """첫 화면 카드 목록. 저장 리스트가 없으면 빈 목록을 돌려주고, 화면에서도 영역이 숨는다."""
    저장 = _홈뽑기(내맛집목록(), 홈표시수)
    if not 저장:
        return []

    def 채우기(s: dict) -> dict:
        키 = _이름정규화(s["name"])
        with _홈캐시잠금:
            정보 = _홈캐시.get(키)
        if not 정보:
            정보 = {"시각": time.time(), "photo": "", "category": "", "url": "", "rating": None}
            try:
                for d in _장소수집(s["name"], s["lng"], s["lat"], 300, 최대=3):
                    # 같은 이름의 다른 지점을 잡지 않도록 저장 좌표에서 200m 이내만
                    if _대략거리m(float(d["y"]), float(d["x"]), s["lat"], s["lng"]) > 200:
                        continue
                    상세 = _카카오상세(d["place_url"])
                    정보["url"] = d["place_url"]
                    정보["category"] = (d["category_name"] or "").split(" > ")[-1]
                    정보["photo"] = 상세.get("photo") or ""
                    정보["rating"] = 상세.get("rating")
                    break
            except Exception as e:  # 첫 화면은 실패해도 검색을 막지 않는다
                print(f"첫 화면 저장 맛집 조회 실패(무시): {e}")
            with _홈캐시잠금:
                _홈캐시[키] = 정보
        return {
            "name": s["name"],
            "badge": _저장배지(s["folder"]),
            "category": 정보.get("category") or "",
            "photo": 정보.get("photo") or "",
            "url": 정보.get("url") or "",
            "rating": 정보.get("rating"),
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        카드들 = list(pool.map(채우기, 저장))
    with _홈캐시잠금:
        스냅 = dict(_홈캐시)
    _캐시저장(_홈캐시파일, 홈캐시버전, 스냅, 홈캐시최대)
    return 카드들


def 가게자료수집(동네: str, place: dict) -> dict:
    """가게 1곳의 카카오맵 상세(메뉴판·사진·별점)와 카카오 블로그 후기를 모은다."""
    상호 = place["name"]
    상세 = _카카오상세(place["url"])
    blogs = _카카오블로그(f"{동네} {상호}")
    posts = [
        {"title": _태그제거(b.get("title", "")), "text": _태그제거(b.get("contents", ""))[:200]}
        for b in blogs
    ]
    # 사진 우선순위: 카카오맵 상세 사진 → 상세 페이지 og:image → 없음
    photo = 상세.get("photo") or _카카오사진(place["url"])
    return {
        "posts": posts,
        "photo": photo,
        "menus": 상세.get("menus") or [],
        "rating": 상세.get("rating"),
        "rating_count": 상세.get("rating_count"),
        "hours": 상세.get("hours") or "",
        "open_status": 상세.get("open_status") or "",
        "booking": bool(상세.get("booking")),
    }


# ── 3. Gemini: 블로그 내용 → 메뉴/가격대/반응/후기 요약 ─────────
GEMINI_PROMPT = """다음은 "{동네}" 인근 음식점 목록이다. 가게마다 카카오맵 메뉴판(실제 가격)과
블로그 후기 검색 결과가 붙어 있다.
각 가게에 대해 제공된 자료만을 근거로 아래 형식의 JSON 배열로 답하라. 다른 텍스트는 쓰지 마라.

[{{"index": 0,
   "menu": "대표 메뉴 2~3개 (쉼표 구분, 메뉴판·블로그에서 확인된 것만)",
   "price": "1인 기준 가격대 (예: 1인 10,000~15,000원)",
   "mood": "블로그 반응 한 줄 요약 (15자 이내, 예: 긍정적 · 웨이팅 있음)",
   "reviews": ["대표 후기 요약 1~2개, 각 45자 이내 (블로그 문장의 취지를 살린 자연스러운 한국어)"]}}, ...]

규칙:
- price는 메뉴판 가격이 있으면 반드시 그것을 근거로 대표 메뉴(단품/1인 기준) 위주로 계산한다.
  대용량·모둠 메뉴(수백 g, 세트)는 1인 기준 환산에 참고만 한다. 메뉴판이 없으면 블로그 근거로,
  그래도 없으면 "정보 부족"으로 표기한다.
- reviews는 광고성 문구를 거르고 실제 경험담 위주로 뽑는다. 블로그 후기가 없는 가게는 빈 배열로 둔다.
- 제공된 자료에 근거가 없는 내용은 지어내지 말고 "정보 부족"으로 표기한다.
- 모든 가게(index 0~{마지막})를 빠짐없이 포함한다.

가게 목록:
{가게목록}
"""


GEMINI_CHUNK = 10  # 가게 10곳씩 나눠 병렬 요약 — 호출 횟수(무료 한도 소모)와 응답 속도의 절충

# 요약 단계의 총 시간 예산(초). 429(무료 한도) 재시도 대기가 쌓이면 /enrich 응답이
# 몇 분씩 지연되고, 그 사이 호스팅 프록시가 연결을 끊어 클라이언트는 502를,
# 서버는 BrokenPipeError를 본다. 예산을 넘기면 요약을 포기하고 카카오맵 메뉴판
# 기준 결과라도 돌려준다 — 사진·메뉴·가격은 Gemini 없이도 채워지기 때문이다.
요약예산초 = 70


def _groq요약(prompt: str, 제한초: float = 60) -> list:
    """Gemini 한도 소진 시 Groq(무료, llama-3.3-70b)로 같은 요약을 수행한다.
    제한초: 남은 시간 예산. 고정 타임아웃을 쓰면 폴백 한 번이 예산을 넘길 수 있다."""
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_KEY}"},
        json={
            "model": GROQ_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
        },
        timeout=min(60.0, 제한초),
    )
    resp.raise_for_status()
    text = resp.json()["choices"][0]["message"]["content"]
    m = re.search(r"\[.*\]", text, re.S)  # 앞뒤 설명 문장이 붙어도 JSON 배열만 추출
    if not m:
        raise ValueError("Groq 응답에서 JSON 배열을 찾지 못했습니다")
    return json.loads(m.group(0))


def _gemini_chunk요약(동네: str, places: list[dict], 자료들: list[dict], start: int,
                      마감: float | None = None) -> dict[int, dict]:
    블록 = []
    for i, (p, 자료) in enumerate(zip(places, 자료들)):
        메뉴줄 = ", ".join(
            f"{m['name']} {m['price']:,}원" + ("(추천)" if m["recommend"] else "")
            for m in 자료.get("menus", [])[:12]
        ) or "(메뉴판 정보 없음)"
        후기 = "\n".join(f"  - {b['title']}: {b['text']}" for b in 자료["posts"]) or "  (블로그 후기 없음)"
        블록.append(f"[{i}] {p['name']} ({p['category']})\n  메뉴판: {메뉴줄}\n{후기}")
    prompt = GEMINI_PROMPT.format(동네=동네, 마지막=len(places) - 1, 가게목록="\n\n".join(블록))
    resp = None
    남은시간 = (lambda: float("inf") if 마감 is None else 마감 - time.monotonic())
    # Groq 폴백이 있으면 Gemini 재시도를 줄여 빨리 넘어간다
    최대시도 = 2 if GROQ_KEY else 4
    for 시도 in range(최대시도):
        if 남은시간() <= 0:  # 예산 소진 — 남은 재시도를 포기하고 폴백/생략으로 넘어간다
            print(f"Gemini 요약 시간 예산 초과 — 구간 {start} 생략")
            break
        try:
            resp = gemini_client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                # thinking_config는 최신 flash 모델이 거부(400)하므로 사용하지 않는다
                config=genai_types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.3,
                ),
            )
            break
        except Exception as e:
            # 일시 오류는 재시도. 대기가 총 2분을 넘으면 유휴 연결이 끊기므로 짧게 유지한다.
            msg = str(e)
            # 대기는 남은 예산을 넘지 않는다 — 예산이 없으면 즉시 다음 판단으로 넘어간다
            def 대기(초: float):
                time.sleep(max(0.0, min(초, 남은시간())))

            if "429" in msg or "RESOURCE_EXHAUSTED" in msg:  # 무료 티어 호출 한도
                if 시도 < 최대시도 - 1:
                    대기(25)
                continue
            if "503" in msg or "UNAVAILABLE" in msg:  # 일시적 수요 폭주
                대기(8 * (시도 + 1))
                continue
            # 그 외 오류(모델 정책 변경, 잘못된 인자 등)도 Groq으로 폴백해 요약이 끊기지 않게 한다
            if GROQ_KEY:
                print(f"Gemini 오류 → Groq 폴백: {msg[:100]}")
                break
            raise
    if resp is not None:
        items = json.loads(resp.text)
    # 남은 예산이 너무 적으면 폴백을 시작하지 않는다 — 어차피 중간에 잘린다
    elif GROQ_KEY and 남은시간() > 10:  # Gemini 실패(한도·오류) → Groq 무료 폴백
        items = _groq요약(prompt, 남은시간())
    else:
        raise RuntimeError("Gemini 요약 실패 — 요청 한도 또는 시간 예산 초과")
    return {
        start + int(it["index"]): it
        for it in items
        if isinstance(it, dict) and "index" in it and 0 <= int(it["index"]) < len(places)
    }


# 요약 결과는 '가게' 단위로 캐시한다. 검색 조건(동네·반경·시간대·업종…) 단위로
# 캐시하면 조건을 하나만 바꿔도 겹치는 가게까지 전부 다시 요약해 무료 한도를
# 빠르게 태운다. 가게 단위로 두면 조건을 바꿔가며 검색해도 새 가게만 호출한다.
# 요약 내용은 가게에 대한 것이라 다른 동네 검색에서 나와도 그대로 쓸 수 있다.
# (프로세스 메모리라 재배포·재시작 시 비워진다 — 영구 보관은 별도 저장소가 필요)
요약캐시: dict[str, dict] = {}
요약캐시잠금 = threading.Lock()
요약캐시상한 = 3000


def _가게키(p: dict) -> str:
    """카카오 place_url은 가게마다 고유하다. 없으면 상호+주소로 대신한다."""
    return p.get("url") or f'{p.get("name", "")}|{p.get("address", "")}'


def _구간요약(동네: str, places: list[dict], 자료들: list[dict],
            인덱스들: list[int], 마감: float | None) -> dict[int, dict]:
    """캐시에 없는 가게만 골라 한 구간으로 요약하고, 원래 인덱스로 되돌린다."""
    부분 = _gemini_chunk요약(
        동네, [places[i] for i in 인덱스들], [자료들[i] for i in 인덱스들], 0, 마감
    )
    return {인덱스들[j]: v for j, v in 부분.items() if 0 <= j < len(인덱스들)}


def gemini요약(동네: str, places: list[dict], 자료들: list[dict],
              마감: float | None = None) -> dict[int, dict]:
    if not gemini_client:
        return {}
    결과: dict[int, dict] = {}
    미요약: list[int] = []
    with 요약캐시잠금:
        for i, p in enumerate(places):
            캐시된 = 요약캐시.get(_가게키(p))
            if 캐시된 is None:
                미요약.append(i)
            else:
                결과[i] = 캐시된
    print(f"요약 캐시 적중 {len(결과)}/{len(places)}곳 — {len(미요약)}곳만 새로 호출")
    if not 미요약:
        return 결과

    구간들 = [미요약[s : s + GEMINI_CHUNK] for s in range(0, len(미요약), GEMINI_CHUNK)]
    신규: dict[int, dict] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(len(구간들), 1)) as pool:
        futures = [pool.submit(_구간요약, 동네, places, 자료들, 묶음, 마감) for 묶음 in 구간들]
        for f in futures:
            try:
                신규.update(f.result())
            except Exception as e:
                print(f"Gemini 요약 실패(일부 구간): {e}")
    결과.update(신규)

    with 요약캐시잠금:
        for i, 항목 in 신규.items():
            항목.pop("index", None)  # 구간 내 위치라 재사용 시 의미가 없다
            요약캐시[_가게키(places[i])] = 항목
        # 상한을 넘으면 오래 들어온 것부터 버린다 (dict은 삽입 순서를 유지)
        for 키 in list(요약캐시)[: max(0, len(요약캐시) - 요약캐시상한)]:
            del 요약캐시[키]
    return 결과


def 브리핑생성(동네: str, places: list[dict]) -> tuple[list[dict], bool]:
    """가게 목록에 사진·메뉴·가격대·반응을 붙여 완성한다.
    반환: (완성 목록, Gemini 요약 성공 여부 — 실패분은 캐시하지 않도록)

    자료 수집이 늦어진 만큼 요약에 쓸 시간이 줄도록, 예산은 호출 시점부터 잰다."""
    마감 = time.monotonic() + 요약예산초
    # 카카오 검색 API 초당 제한 대응 — 10개 동시 수집 + 429 재시도(백오프)
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        자료들 = list(pool.map(lambda p: 가게자료수집(동네, p), places))
    요약 = gemini요약(동네, places, 자료들, 마감)
    # 대부분(80% 이상) 요약됐을 때만 성공으로 보고 캐시한다 — 한도 초과로
    # 통째로/절반쯤 빈 결과가 캐시에 박제되는 것을 막는다
    요약성공 = (not gemini_client) or len(요약) >= len(places) * 0.8
    enriched = []
    for i, (p, 자료) in enumerate(zip(places, 자료들)):
        s = 요약.get(i, {})
        메뉴판 = 자료.get("menus") or []
        # Gemini가 못 채우면 카카오맵 메뉴판에서 직접 계산한다
        menu = s.get("menu")
        if not menu or menu == "정보 부족":
            대표 = [m for m in 메뉴판 if m["recommend"]] or 메뉴판
            menu = ", ".join(m["name"] for m in 대표[:3]) or "정보 부족"
        price = s.get("price")
        if (not price or price == "정보 부족") and 메뉴판:
            가격들 = sorted(m["price"] for m in 메뉴판)
            price = f"메뉴 {가격들[0]:,}~{가격들[-1]:,}원" if len(가격들) > 1 else f"{가격들[0]:,}원"
        enriched.append(
            {
                "photo": 자료["photo"],
                "menu": menu,
                "price": price or "정보 부족",
                # mood가 비면 배지를 표시하지 않는다 ("후기 없음" 같은 무의미한 배지 제거)
                "mood": s.get("mood") or "",
                "reviews": (s.get("reviews") or [])[:2],
                "rating": 자료.get("rating"),
                "rating_count": 자료.get("rating_count"),
                # 검색 단계에서 상세를 건너뛰었으므로 영업시간·예약도 여기서 채운다
                "hours": 자료.get("hours") or "",
                "open_status": 자료.get("open_status") or "",
                "booking": bool(자료.get("booking")),
                "phone": p.get("phone") or "",
            }
        )
    return enriched, 요약성공


# 한 요청에 몇 곳까지 처리할지. 30~100곳을 한 번에 처리하면 응답이 수십 초~몇 분
# 걸리고, 그 사이 호스팅 프록시가 유휴 연결을 끊어 502(BrokenPipeError)가 난다.
# 구간을 나눠 요청 하나를 짧게 유지하면 이 문제가 구조적으로 사라지고,
# 진행률 표시와 부분 실패 격리도 함께 얻는다.
브리핑배치 = 10


# ── 4. 페이지 HTML ──────────────────────────────────────────────
PAGE = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta http-equiv="X-UA-Compatible" content="IE=edge">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>맛집 브리핑</title>
<!-- 제목용 둥근 글꼴. 사내망 등에서 차단되면 CSS의 대체 글꼴로 조용히 내려간다. -->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Jua&display=swap" rel="stylesheet">
<style>
  /* 색: 따뜻한 종이색 바탕 + 고추장 계열 강조색.
     구형 브라우저(IE 모드)에서도 동작해야 하므로 CSS 변수와 position:sticky는 쓰지 않는다.
       종이 #f7f4ef · 카드 #ffffff · 연한면 #f1ece4 · 글자 #191411 · 보조글자 #4a423c
       흐린글자 #8b8078 · 선 #e4ded5 · 진한선 #d3cabe · 강조 #d2371a · 강조연함 #fbeae4 */
  * { box-sizing: border-box; }
  body { font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif; margin: 0;
         background: #f7f4ef; color: #191411; }
  button { font-family: inherit; }

  /* ── 브랜드 바 ─────────────────────────────────────────── */
  .brandbar { display: flex; align-items: center; justify-content: space-between;
              padding: 13px 26px; background: #fff; border-bottom: 1px solid #e4ded5; }
  .logo { display: flex; align-items: center; gap: 9px; }
  .logo svg { width: 22px; height: 22px; flex-shrink: 0; }
  .logo b { font-size: 1.02em; letter-spacing: -.01em; white-space: nowrap; }
  .brandnav { display: flex; gap: 8px; }
  .linkbtn { background: none; border: 1px solid #e4ded5; border-radius: 8px; padding: 7px 13px;
             font-size: .82em; color: #4a423c; cursor: pointer; }
  .linkbtn:hover { border-color: #d3cabe; background: #f7f4ef; }

  /* ── 히어로 검색 ───────────────────────────────────────── */
  .hero { position: relative; overflow: hidden; padding: 46px 26px 32px; text-align: center;
          background: #fff; border-bottom: 1px solid #e4ded5; }
  /* 음식 사진의 색감만 옮겨온 배경. 흐리게 번지게 해 각진 색블록으로 보이지 않게 한다.
     filter를 모르는 구형 브라우저에서는 옅은 색 띠로 남는다 — 읽는 데 지장 없음. */
  .hero-strip { position: absolute; top: -30px; left: -30px; right: -30px; bottom: -30px;
                display: flex; opacity: .16; pointer-events: none;
                filter: blur(38px); -webkit-filter: blur(38px); }
  .hero-strip div { flex: 1; }
  .hero-inner { position: relative; }
  /* 제목은 둥근 글꼴로. Jua는 굵기가 하나뿐이라 bold를 주면 브라우저가 억지로
     굵게 그려 뭉개진다 → normal로 두고 크기를 조금 키워 무게를 맞춘다. */
  .hero h2 { font-family: 'Jua', 'Apple SD Gothic Neo', 'Malgun Gothic', Gulim, 굴림, sans-serif;
             font-size: 1.92em; margin: 0 0 6px; letter-spacing: -.01em; font-weight: normal; }
  .hero .sub { font-size: .86em; color: #8b8078; margin: 0 0 24px; }

  .searchbar { display: flex; gap: 8px; max-width: 560px; margin: 0 auto; }
  .searchfield { flex: 1; display: flex; align-items: center; gap: 10px; background: #fff;
                 border: 1.5px solid #191411; border-radius: 10px; padding: 0 14px;
                 box-shadow: 0 1px 2px rgba(25,20,17,.05), 0 8px 24px rgba(25,20,17,.06); }
  .searchfield svg { flex-shrink: 0; opacity: .5; }
  .searchfield input { flex: 1; border: 0; outline: none; padding: 13px 0; font-size: 1em;
                       background: none; color: #191411; min-width: 0; }
  .btn-go { background: #d2371a; color: #fff; border: 0; border-radius: 10px; padding: 13px 26px;
            font-size: 1em; font-weight: bold; cursor: pointer; white-space: nowrap; }
  .btn-go:hover { background: #b82f14; }

  .segment { display: inline-flex; gap: 4px; margin: 20px auto 0; padding: 4px;
             background: #f1ece4; border-radius: 10px; max-width: 100%; }
  .seg { padding: 8px 16px; border: 0; background: none; border-radius: 7px; font-size: .88em;
         color: #4a423c; cursor: pointer; white-space: nowrap; }
  .seg.on { background: #fff; color: #191411; font-weight: bold;
            box-shadow: 0 1px 2px rgba(25,20,17,.08); }

  .chiprow { display: flex; gap: 8px; justify-content: center; align-items: center;
             margin-top: 18px; flex-wrap: wrap; }
  .chip { border: 1px solid #d3cabe; border-radius: 99px; padding: 6px 14px; font-size: .84em;
          color: #4a423c; background: #fff; cursor: pointer; }
  .chip:hover { border-color: #191411; }
  /* 이전엔 점선·흐린 글자라 비활성처럼 보였다. 지금 걸린 조건을 그대로 띄우고
     화살표로 펼침을 알려, 눌러서 바꿀 수 있는 자리임이 드러나게 한다. */
  .chip.more { border-color: #191411; color: #191411; font-weight: bold; font-size: .88em;
               padding: 9px 18px; box-shadow: 0 1px 2px rgba(25,20,17,.08); }
  .chip.more:hover { background: #f1ece4; }
  .chip.more .sum { font-weight: normal; color: #6b6259; margin-left: 2px; }
  .chip.more .arw { color: #8b8078; margin-left: 7px; font-size: .9em; }
  .chip.more.on { border-color: #d2371a; color: #d2371a; background: #fbeae4; }
  .chip.more.on .sum, .chip.more.on .arw { color: #d2371a; }

  #status { color: #8b8078; font-size: .84em; margin-top: 14px; min-height: 1.2em; }

  /* ── 상세 필터 (PC: 펼침 패널 / 모바일: 바텀시트) ───────── */
  #sheetdim { display: none; }
  #filters { display: none; max-width: 640px; margin: 16px auto 0; background: #fff;
             border: 1px solid #e4ded5; border-radius: 12px; padding: 18px 20px; text-align: left;
             box-shadow: 0 2px 6px rgba(25,20,17,.08), 0 24px 60px rgba(25,20,17,.10); }
  #filters.open { display: block; }
  .fgrid { display: flex; flex-wrap: wrap; gap: 12px; }
  .fld { flex: 1 1 30%; min-width: 150px; }
  .fld .k { display: block; font-size: .76em; color: #8b8078; margin-bottom: 5px; }
  .fld select { width: 100%; padding: 9px 8px; border: 1px solid #d3cabe; border-radius: 8px;
                background: #fff; font-size: .9em; color: #191411; }
  .fld select:disabled { background: #f1ece4; color: #8b8078; }
  .grab, .sheet-title, .sheet-done { display: none; }

  /* ── 첫 화면: 내 저장 맛집 + 안내 ──────────────────────── */
  #home { max-width: 1200px; margin: 0 auto; padding: 30px 20px 40px; }
  .strip-head { display: flex; align-items: baseline; justify-content: space-between;
                margin-bottom: 14px; }
  .strip-head h3 { margin: 0; font-size: 1.04em; }
  .strip-head h3 span { color: #8b8078; font-weight: normal; font-size: .84em; margin-left: 6px; }
  .strip-head h3 .rand { color: #d2371a; }
  .mine-cards { display: flex; flex-wrap: wrap; gap: 14px; }
  .fcard { width: calc(25% - 11px); background: #fff; border: 1px solid #e4ded5;
           border-radius: 12px; overflow: hidden; text-decoration: none; color: inherit;
           box-shadow: 0 1px 2px rgba(25,20,17,.05); display: block; }
  .fcard:hover { border-color: #d3cabe; }
  /* 배경색을 두지 않는다 — 아래 .ph0~.ph5 색 타일이 덮이지 않도록 (선택자 우선순위) */
  .fcard .fph { height: 104px; position: relative; overflow: hidden; }
  .fcard .fph img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .fcard .fbody { padding: 10px 12px 12px; }
  .fcard .fnm { font-size: .9em; font-weight: bold; line-height: 1.35; }
  .fcard .fdt { font-size: .78em; color: #8b8078; margin-top: 3px; }
  .mine-skel { color: #b5aca3; font-size: .88em; padding: 8px 2px; }

  .how { display: flex; flex-wrap: wrap; gap: 16px; margin-top: 34px; }
  .how-item { flex: 1 1 240px; border-left: 2px solid #d2371a; padding-left: 14px; }
  .how-item b { display: block; font-size: .92em; }
  .how-item span { display: block; font-size: .84em; color: #8b8078; margin-top: 3px;
                   line-height: 1.6; }
  /* 우상단 토글을 없앤 대신, 첫 화면 맨 아래 잔글씨로 상시 노출한다.
     인증 필터의 누락·오포함 같은 주의사항은 어딘가에 남아 있어야 한다. */
  #helpbox { margin-top: 26px; border-top: 1px solid #e4ded5; padding: 18px 2px 0;
             color: #8b8078; font-size: .8em; line-height: 1.8; white-space: pre-line; }

  /* ── 결과 카드 (구조는 기존 그대로) ─────────────────────── */
  #results { max-width: 1200px; margin: 0 auto; padding: 16px 20px 40px;
             display: flex; flex-wrap: wrap; justify-content: space-between;
             align-items: flex-start; }
  .notice { color: #8b8078; font-size: .9em; padding: 24px 4px; white-space: pre-wrap; width: 100%; }
  .card { background: #fff; border: 1px solid #e4ded5; border-radius: 12px; padding: 16px 20px;
          margin-bottom: 12px; width: calc(50% - 6px); }
  @media (max-width: 920px) { .card { width: 100%; } }
  .top { display: flex; gap: 16px; }
  .photo { width: 104px; height: 104px; border-radius: 8px; background: #f1ece4; flex-shrink: 0;
           display: flex; align-items: center; justify-content: center; color: #a8998a;
           font-size: .78em; overflow: hidden; }
  .photo img { width: 100%; height: 100%; object-fit: cover; }
  .info { flex: 1; min-width: 0; }
  .name { font-size: 1.05em; font-weight: bold; color: #191411; text-decoration: none; }
  .name:hover { color: #d2371a; text-decoration: underline; }
  .meta { color: #8b8078; font-size: .84em; margin-left: 8px; }
  .rate { color: #b8791a; font-size: .88em; font-weight: bold; margin-left: 8px; white-space: nowrap; }
  .badge { display: inline-block; font-size: .8em; padding: 2px 10px; border-radius: 10px;
           background: #fbeae4; color: #a02c11; margin-left: 8px; vertical-align: 1px; }
  .badge.wait { background: #f1ece4; color: #8b8078; }
  .cert { display: inline-block; font-size: .76em; font-weight: bold; padding: 2px 9px;
          border-radius: 9px; margin-left: 6px; vertical-align: 1px; }
  /* 인증 배지 색은 이미 의미가 붙어 있어 그대로 둔다 */
  .cert.c-mi { background: #7d0f0f; color: #fff; }
  .cert.c-bl { background: #123c8a; color: #fff; }
  .cert.c-hu { background: #6a4b16; color: #fff; }
  .cert.c-bw { background: #111; color: #fff; border: 1px solid #555; }
  .cert.c-my { background: #d63b5b; color: #fff; }   /* 가본곳 */
  .cert.c-my2 { background: #fdeaee; color: #b02a45; border: 1px solid #f3c2ce; }  /* 가볼곳 */
  .cert.c-cf { background: #6b4a2f; color: #fff; }   /* 저장한 카페 */

  #mapwrap { max-width: 1200px; margin: 14px auto 0; padding: 0 20px; display: none; }
  #allmap { width: 100%; height: 460px; border: 1px solid #e4ded5; border-radius: 12px;
            background: #f1ece4; }
  .map-hint { color: #8b8078; font-size: .82em; margin: 6px 2px 0; }
  table.facts { width: 100%; font-size: .9em; margin-top: 8px; border-collapse: collapse; }
  table.facts td { padding: 3px 0; vertical-align: top; }
  table.facts td:first-child { color: #8b8078; width: 76px; }
  .skeleton { color: #b5aca3; }
  .reviews { border-top: 1px solid #f1ece4; margin-top: 12px; padding-top: 10px;
             font-size: .9em; color: #4a423c; line-height: 1.6; }
  .reviews p { margin: 0 0 4px; }
  .reviews p::before { content: '\201C'; color: #c3b6a6; margin-right: 2px; }
  .reviews p::after { content: '\201D'; color: #c3b6a6; margin-left: 2px; }

  /* 사진이 없는 가게의 자리 — 음식 색에서 가져온 여섯 가지 타일.
     초록·분홍 같은 찬 색을 섞으면 음식 목록에서 튀어 보여, 전부 따뜻한 색으로 둔다. */
  .ph0 { background: linear-gradient(150deg, #e8b04b, #c4622a); }  /* 구운 색 */
  .ph1 { background: linear-gradient(150deg, #d9502f, #a32418); }  /* 고추장 */
  .ph2 { background: linear-gradient(150deg, #f0dca8, #c9a15c); }  /* 누룽지 */
  .ph3 { background: linear-gradient(150deg, #b09a55, #6f5c22); }  /* 된장 */
  .ph4 { background: linear-gradient(150deg, #e5d2bc, #b08962); }  /* 라떼 */
  .ph5 { background: linear-gradient(150deg, #b5462f, #6e1f13); }  /* 진한 양념 */

  /* 모바일 하단 고정 버튼 — PC에서는 감춘다 */
  #mobilecta { display: none; }

  /* ── 모바일 ────────────────────────────────────────────── */
  @media (max-width: 640px) {
    body { font-size: 17px; padding-bottom: 78px; }
    .brandbar { padding: 10px 12px; }
    .logo b { font-size: .96em; }
    .linkbtn { padding: 6px 10px; font-size: .76em; white-space: nowrap; }
    .hero { padding: 24px 16px 20px; }
    .hero h2 { font-size: 1.46em; }
    .hero .sub { font-size: .8em; margin-bottom: 18px; }
    .sub-long { display: none; }
    .searchfield { padding: 0 13px; }
    .searchfield input { font-size: 16px; padding: 12px 0; }  /* 16px 미만이면 iOS가 확대한다 */
    .searchbar .btn-go { display: none; }                     /* 검색은 하단 고정 버튼으로 */
    .segment { display: flex; gap: 6px; margin-top: 16px; padding: 0; background: none;
               overflow-x: auto; -webkit-overflow-scrolling: touch; justify-content: flex-start; }
    .seg { border: 1px solid #d3cabe; border-radius: 99px; background: #fff; padding: 7px 14px;
           font-size: .82em; flex-shrink: 0; }
    .seg.on { background: #191411; color: #fff; border-color: #191411; box-shadow: none; }
    .chiprow { justify-content: flex-start; margin-top: 14px; }
    .chip.more { display: none; }              /* 필터는 하단 버튼으로 연다 */
    #status { text-align: left; }

    #sheetdim.open { display: block; position: fixed; top: 0; left: 0; right: 0; bottom: 0;
                     background: rgba(20,15,12,.45); z-index: 55; }
    #filters { margin: 0; max-width: none; border-radius: 16px 16px 0 0; border: 0;
               padding: 10px 16px 20px; max-height: 82%; overflow-y: auto; }
    #filters.open { position: fixed; left: 0; right: 0; bottom: 0; z-index: 60; }
    .grab { display: block; width: 34px; height: 4px; border-radius: 99px; background: #d3cabe;
            margin: 0 auto 14px; }
    .sheet-title { display: block; margin: 0 0 14px; font-size: 1em; font-weight: bold; }
    .fld { flex: 1 1 100%; }
    .sheet-done { display: block; width: 100%; margin-top: 16px; padding: 13px; border: 0;
                  border-radius: 10px; background: #191411; color: #fff; font-size: 1em;
                  font-weight: bold; cursor: pointer; }

    #mobilecta { display: flex; position: fixed; left: 0; right: 0; bottom: 0; z-index: 50;
                 gap: 9px; padding: 11px 16px 14px; background: #fff;
                 border-top: 1px solid #e4ded5; }
    #mobilecta .filter { border: 1px solid #d3cabe; border-radius: 10px; padding: 12px 15px;
                         font-size: .88em; color: #4a423c; background: #fff; cursor: pointer;
                         white-space: nowrap; }
    #mobilecta .go { flex: 1; border: 0; border-radius: 10px; padding: 12px; background: #d2371a;
                     color: #fff; font-size: 1em; font-weight: bold; cursor: pointer; }

    #home { padding: 22px 0 30px; }
    .strip-head { padding: 0 16px; }
    /* 저장 맛집은 가로 캐러셀 — 두 장 반쯤 보여 옆에 더 있다는 것을 알린다 */
    .mine-cards { flex-wrap: nowrap; overflow-x: auto; -webkit-overflow-scrolling: touch;
                  padding: 0 16px 4px; gap: 10px; }
    .fcard { width: 142px; flex-shrink: 0; }
    .fcard .fph { height: 88px; }
    .mine-skel { padding: 8px 16px; }
    .how { padding: 0 16px; margin-top: 26px; gap: 12px; }
    .how-item { flex: 1 1 100%; }
    #helpbox { margin: 22px 16px 0; }

    #results { padding: 10px 10px 30px; }
    .card { width: 100%; padding: 14px; margin-bottom: 10px; border-radius: 14px; }
    /* 폰에서는 사진을 카드 위로 크게 올린다 */
    .top { display: block; }
    .photo { width: 100%; height: 190px; border-radius: 10px; margin-bottom: 12px; }
    .name { font-size: 1.15em; display: inline-block; margin-bottom: 2px; }
    .meta { display: block; margin-left: 0; margin-top: 2px; font-size: .86em; }
    .rate { font-size: .95em; }
    table.facts { font-size: .95em; margin-top: 10px; }
    table.facts td { padding: 4px 0; }
    table.facts td:first-child { width: 72px; white-space: nowrap; }
    .reviews { font-size: .95em; }
    #mapwrap { padding: 0 8px; }
    #allmap { height: 340px; }
    .notice { font-size: .95em; padding: 16px 6px; }
  }
</style>
</head>
<body>

<div class="brandbar">
  <span class="logo">
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M3 10.5h18c0 5-4 8.5-9 8.5s-9-3.5-9-8.5z" fill="#d2371a"></path>
      <path d="M2 10.5h20" stroke="#191411" stroke-width="1.6" stroke-linecap="round"></path>
      <path d="M9 7.2c0-1.4 1.2-1.6 1.2-3M13 6.6c0-1.2 1-1.4 1-2.6" stroke="#a87b22"
            stroke-width="1.5" stroke-linecap="round"></path>
    </svg>
    <b>맛집 브리핑</b>
  </span>
  <span class="brandnav">
    <button type="button" class="linkbtn" id="mapbtn" onclick="toggleMap()" style="display:none">지도로 보기</button>
  </span>
</div>

<div class="hero">
  <div class="hero-strip" aria-hidden="true">
    <div class="ph0"></div><div class="ph2"></div><div class="ph1"></div>
    <div class="ph4"></div><div class="ph3"></div><div class="ph5"></div>
  </div>
  <div class="hero-inner">
    <h2>오늘 어디서 먹을까요?</h2>
    <p class="sub">동네 이름만 넣으면 <span class="sub-long">반경 안의 맛집을 </span>사진 · 대표 메뉴 · 가격대 · 블로그 반응으로 정리해 드립니다</p>

    <div class="searchbar">
      <span class="searchfield">
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#191411"
             stroke-width="2.2" stroke-linecap="round" aria-hidden="true">
          <circle cx="11" cy="11" r="7"></circle><path d="M20 20l-3.6-3.6"></path>
        </svg>
        <input id="q" placeholder="역삼동, 서초동, 판교…" aria-label="동네 이름"
               onkeydown="if(event.key==='Enter'||event.keyCode===13)doSearch()">
      </span>
      <button type="button" class="btn-go" onclick="doSearch()">검색</button>
    </div>

    <div class="segment" id="segment">
      <button type="button" class="seg on" data-meal="all" onclick="pickMeal(this)">전체</button>
      <button type="button" class="seg" data-meal="lunch" onclick="pickMeal(this)">점심</button>
      <button type="button" class="seg" data-meal="dinner" onclick="pickMeal(this)">저녁</button>
      <button type="button" class="seg" data-meal="cafe" onclick="pickMeal(this)">카페 · 디저트</button>
    </div>

    <div class="chiprow">
      <button type="button" class="chip more" id="filterchip" onclick="toggleFilters()"
              aria-expanded="false">상세 필터 <span class="sum" id="filtersum"></span><span class="arw" id="filterarw">▾</span></button>
    </div>

    <div id="status"></div>

    <div id="filters">
      <div class="grab"></div>
      <h3 class="sheet-title">상세 필터</h3>
      <div class="fgrid">
        <label class="fld"><span class="k">반경</span>
          <select id="radius" onchange="updateFilterSummary()">
            <option value="500">500m</option>
            <option value="1000" selected>1km</option>
            <option value="1500">1.5km</option>
            <option value="2000">2km</option>
            <option value="3000">3km</option>
          </select>
        </label>
        <label class="fld"><span class="k">업종</span>
          <select id="cuisine" onchange="updateFilterSummary()">
            <option value="all" selected>업종 전체</option>__CUISINEOPTS__
          </select>
        </label>
        <label class="fld"><span class="k">추출 개수</span>
          <select id="cnt" onchange="updateFilterSummary()">
            <option value="10">10곳</option>
            <option value="20" selected>20곳</option>
            <option value="30">30곳</option>
            <option value="40">40곳</option>
            <option value="50">50곳</option>
            <option value="60">60곳</option>
            <option value="70">70곳</option>
            <option value="80">80곳</option>
            <option value="90">90곳</option>
            <option value="100">100곳</option>
          </select>
        </label>
        <label class="fld"><span class="k">인증 맛집</span>
          <select id="cert" onchange="updateFilterSummary()">
            <option value="none" selected>인증 무관</option>
            <option value="any">인증맛집만 (통합)</option>
            <option value="michelin">미쉐린 가이드</option>
            <option value="blueribbon">블루리본</option>
            <option value="century">백년가게</option>
            <option value="bwchef">흑백요리사</option>
          </select>
        </label>
        <label class="fld"><span class="k">평점</span>
          <select id="rate" onchange="updateFilterSummary()">
            <option value="0" selected>평점 무관</option>
            <option value="4">★4.0 이상</option>
          </select>
        </label>
        <label class="fld"><span class="k">내 저장 맛집</span>
          <select id="mine" onchange="updateFilterSummary()">
            <option value="prefer" selected>내 저장 우선</option>
            <option value="only">내 저장만</option>
            <option value="off">내 저장 무시</option>
          </select>
        </label>
      </div>
      <button type="button" class="sheet-done" onclick="toggleFilters()">적용</button>
    </div>
  </div>
</div>

<div id="sheetdim" onclick="toggleFilters()"></div>

<!-- 시간대는 위 세그먼트 버튼으로 고른다. 값은 여기에 담아 검색에 그대로 실린다. -->
<select id="meal" style="display:none" onchange="syncCuisine()">
  <option value="all" selected>전체</option>
  <option value="lunch">점심 (식사 위주)</option>
  <option value="dinner">저녁 (술 한잔)</option>
  <option value="cafe">카페 · 디저트</option>
</select>

<div id="mapwrap">
  <div id="allmap"></div>
  <p class="map-hint">번호 핀을 클릭하면 가게 이름이 표시됩니다. 카드 목록의 번호와 동일합니다.</p>
</div>

<div id="home">
  <div id="minewrap" style="display:none">
    <div class="strip-head">
      <h3>내 저장 맛집 <span class="rand">(랜덤 추천)</span> <span id="minecount"></span></h3>
    </div>
    <div class="mine-cards" id="minecards"><div class="mine-skel">불러오는 중…</div></div>
  </div>

  <div class="how">
    <div class="how-item"><b>점심</b><span>식사 위주로 봅니다. 술집·안주 전문점은 뺍니다.</span></div>
    <div class="how-item"><b>저녁</b><span>술 곁들이기 좋은 집을 봅니다. 고기·회·주점을 넣습니다.</span></div>
    <div class="how-item"><b>카페 · 디저트</b><span>카페·베이커리·디저트 전문점만 봅니다.</span></div>
  </div>

  <div id="helpbox">업종(한식·중식·일식·양식·고기·해산물·회·치킨·아시안·분식)은 시간대와 함께 걸 수 있습니다. 업종을 고르면 그 업종이 우선이라, "저녁 × 중식"처럼 시간대 기준에 없는 조합도 결과가 나옵니다. (카페·디저트에서는 업종 선택이 꺼집니다)

내 저장 맛집(네이버지도에 저장한 리스트)은 기본으로 맨 위에 ♥가본곳·♡가볼곳 배지와 함께 표시됩니다. "내 저장만"을 고르면 저장한 곳만 볼 수 있습니다.

인증 필터(미쉐린 가이드·블루리본·백년가게·흑백요리사)는 카카오맵 검색 연관 기준의 참고용 분류입니다. 공식 명부가 공개되어 있지 않아 누락·오포함이 있을 수 있으며, 블루리본은 데이터가 적어 결과가 없을 수 있습니다.

별점·메뉴판은 카카오맵 상세 페이지에서 가져옵니다. 막히면 별점·메뉴판 없이 블로그 요약만으로 동작합니다.</div>
</div>

<div id="results"></div>

<div id="mobilecta">
  <button type="button" class="filter" onclick="toggleFilters()">상세 필터</button>
  <button type="button" class="go" onclick="doSearch()">검색</button>
</div>

<script>
// IE 모드/구형 브라우저에서도 동작하도록 ES5 문법(var, function, XHR)만 사용한다.
var searching = false;

function ajax(method, url, body, cb) {
  var xhr = new XMLHttpRequest();
  xhr.open(method, url, true);
  if (body) xhr.setRequestHeader('Content-Type', 'application/json');
  xhr.onreadystatechange = function () {
    if (xhr.readyState !== 4) return;
    if (xhr.status !== 200) { cb(new Error('HTTP ' + xhr.status), null); return; }
    try { cb(null, JSON.parse(xhr.responseText)); }
    catch (e) { cb(e, null); }
  };
  xhr.onerror = function () { cb(new Error('네트워크 오류'), null); };
  xhr.send(body || null);
}

var lastPlaces = [];  // 지도 표시용 — 마지막 검색 결과

// ── 시간대 세그먼트 ────────────────────────────────────────
function pickMeal(btn) {
  var segs = document.getElementById('segment').getElementsByTagName('button');
  for (var i = 0; i < segs.length; i++) segs[i].className = 'seg';
  btn.className = 'seg on';
  document.getElementById('meal').value = btn.getAttribute('data-meal');
  syncCuisine();
  updateFilterSummary();
}

function syncCuisine() {
  // 카페·디저트는 업종 축과 배타 — 선택을 초기화하고 잠근다
  var sel = document.getElementById('cuisine');
  sel.disabled = (document.getElementById('meal').value === 'cafe');
  if (sel.disabled) sel.value = 'all';
}

// ── 상세 필터 (PC 펼침 / 모바일 바텀시트) ──────────────────
function toggleFilters() {
  var box = document.getElementById('filters');
  var dim = document.getElementById('sheetdim');
  var chip = document.getElementById('filterchip');
  var open = box.className.indexOf('open') < 0;
  box.className = open ? 'open' : '';
  dim.className = open ? 'open' : '';
  chip.className = open ? 'chip more on' : 'chip more';
  chip.setAttribute('aria-expanded', open ? 'true' : 'false');
  document.getElementById('filterarw').innerHTML = open ? '&#9652;' : '&#9662;';
}

function updateFilterSummary() {
  var 반경 = document.getElementById('radius');
  var 개수 = document.getElementById('cnt');
  var 인증 = document.getElementById('cert');
  var 평점 = document.getElementById('rate');
  var 업종 = document.getElementById('cuisine');
  var 부분 = [반경.options[반경.selectedIndex].text, 개수.options[개수.selectedIndex].text];
  if (!업종.disabled && 업종.value !== 'all') 부분.push(업종.options[업종.selectedIndex].text);
  if (인증.value !== 'none') 부분.push(인증.options[인증.selectedIndex].text);
  if (평점.value === '4') 부분.push('★4.0 이상');
  document.getElementById('filtersum').textContent = 부분.join(' · ');
}

// ── 첫 화면: 내 저장 맛집 카드 ─────────────────────────────
// 페이지를 먼저 그린 뒤 따로 불러온다 — 첫 화면이 사진 조회를 기다리지 않도록.
function loadMine() {
  ajax('GET', '/mine', null, function (err, data) {
    var wrap = document.getElementById('minewrap');
    if (err || !data || !data.items || !data.items.length) { wrap.style.display = 'none'; return; }
    wrap.style.display = '';
    document.getElementById('minecount').textContent = '네이버지도에서 불러온 ' + data.items.length + '곳';
    document.getElementById('minecards').innerHTML = data.items.map(function (m) {
      var 사진 = m.photo
        ? '<img src="' + esc(m.photo) + '" alt="" referrerpolicy="no-referrer">'
        : '';
      var 배지 = m.badge ? '<span class="cert ' + certClass(m.badge) + '">' + esc(m.badge) + '</span>' : '';
      var 별점 = m.rating ? ' · ★' + m.rating : '';
      var 열기 = m.url ? ' href="' + esc(m.url) + '" target="_blank"' : '';
      return '<a class="fcard"' + 열기 + '>'
        + '<div class="fph ' + phClass(m.name) + '">' + 사진 + '</div>'
        + '<div class="fbody"><div class="fnm">' + esc(m.name) + '</div>'
        + '<div class="fdt">' + esc(m.category || '저장한 곳') + 별점 + '</div>'
        + 배지 + '</div></a>';
    }).join('');
  });
}

// 사진이 없을 때 쓰는 색 타일 — 상호에서 정해 같은 가게는 늘 같은 색이 되게 한다
function phClass(name) {
  var h = 0, i;
  for (i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) % 6;
  return 'ph' + h;
}

function certClass(b) {
  if (b.indexOf('☕') >= 0) return 'c-cf';
  if (b.indexOf('가본곳') >= 0) return 'c-my';
  if (b.indexOf('가볼곳') >= 0 || b.indexOf('내저장') >= 0) return 'c-my2';
  if (b === '미쉐린') return 'c-mi';
  if (b === '블루리본') return 'c-bl';
  if (b === '흑백요리사') return 'c-bw';
  return 'c-hu';
}

// ── 검색 ───────────────────────────────────────────────────
function doSearch() {
  if (searching) return;
  var q = document.getElementById('q').value.replace(/^\s+|\s+$/g, '');
  var radius = document.getElementById('radius').value;
  var meal = document.getElementById('meal').value;
  var cuisine = document.getElementById('cuisine').value;
  var cnt = document.getElementById('cnt').value;
  var cert = document.getElementById('cert').value;
  var rate = document.getElementById('rate').value;
  var mine = document.getElementById('mine').value;
  if (!q) { document.getElementById('q').focus(); return; }
  if (document.getElementById('filters').className.indexOf('open') >= 0) toggleFilters();
  searching = true;
  document.getElementById('home').style.display = 'none';
  var status = document.getElementById('status');
  var results = document.getElementById('results');
  status.textContent = (cert !== 'none' || rate === '4')
    ? '음식점 검색 + 인증·평점 확인 중... (10~30초)' : '주변 음식점 검색 중...';
  var qs = '/search?q=' + encodeURIComponent(q) + '&radius=' + radius + '&meal=' + meal
         + '&cuisine=' + cuisine
         + '&cnt=' + cnt + '&cert=' + cert + '&rate=' + rate + '&mine=' + mine;
  ajax('GET', qs, null, function (err, data) {
    if (err) { status.textContent = '오류: ' + err.message; searching = false; return; }
    if (data.error) {
      results.innerHTML = '<div class="notice">' + esc(data.error) + '</div>';
      status.textContent = '';
      searching = false;
      return;
    }
    lastPlaces = data.places;
    document.getElementById('mapbtn').style.display = data.places.length ? '' : 'none';
    renderMap();  // 지도가 열려 있으면 새 결과로 갱신
    renderBase(data);
    if (data.cached_detail) {
      fillDetail(data.cached_detail, 0);
      status.textContent = data.center + ' · ' + data.places.length + '곳 (캐시)';
      searching = false;
      return;
    }
    // 전부를 한 요청에 처리하면 응답이 길어져 호스팅 프록시가 연결을 끊는다(502).
    // 서버가 알려주는 next 위치를 따라 구간을 이어서 요청해 요청 하나를 짧게 유지한다.
    var total = data.places.length;
    var body = {query: q, radius: radius, meal: meal, cuisine: cuisine,
                cnt: cnt, cert: cert, rate: rate, mine: mine};
    // 구간을 두 개씩 겹쳐 보낸다. 카카오 상세는 서버에서 호출 간격이 조절되므로
    // 한 구간이 기다리는 동안 다른 구간의 블로그·요약 작업이 진행돼 전체가 빨라진다.
    var anyPartial = false, 채운수 = 0, 다음구간 = 0, 진행중 = 0, 끝남 = false;
    var 배치크기 = __BATCH__, 동시구간 = 2;
    status.textContent = '블로그 후기 분석 중... (0/' + total + ')';

    function 구간보내기(offset) {
      진행중++;
      var 몸통 = {}, k;
      for (k in body) if (body.hasOwnProperty(k)) 몸통[k] = body[k];
      몸통.offset = offset;
      ajax('POST', '/enrich', JSON.stringify(몸통), function (err2, detail) {
        진행중--;
        if (끝남) return;
        if (err2) { 끝남 = true; searching = false; status.textContent = '오류: ' + err2.message; return; }
        if (detail.error) { 끝남 = true; searching = false; status.textContent = detail.error; return; }
        fillDetail(detail.items, detail.offset);
        if (detail.partial) anyPartial = true;
        채운수 += detail.items.length;
        if (채운수 >= total) {
          끝남 = true;
          searching = false;
          status.textContent = data.center + ' · ' + total + '곳 '
            + (anyPartial ? '표시 (일부 블로그 요약 생략 — 메뉴판 기준)' : '분석 완료');
          return;
        }
        status.textContent = '블로그 후기 분석 중... (' + 채운수 + '/' + total + ')';
        구간채우기();
      });
    }

    function 구간채우기() {
      while (!끝남 && 진행중 < 동시구간 && 다음구간 < total) {
        구간보내기(다음구간);
        다음구간 += 배치크기;
      }
    }
    구간채우기();
  });
}

function renderBase(data) {
  var results = document.getElementById('results');
  if (!data.places.length) {
    results.innerHTML = '<div class="notice">반경 내 음식점을 찾지 못했습니다.</div>';
    return;
  }
  results.innerHTML = data.places.map(function (p, i) {
    var certs = (p.badges || []).map(function (b) {
      return '<span class="cert ' + certClass(b) + '">' + esc(b) + '</span>';
    }).join('');
    var rating = p.rating ? '★' + p.rating + (p.rating_count ? ' (' + p.rating_count + ')' : '') : '';
    return '<div class="card" id="card-' + i + '">'
    + '<div class="top">'
    +   '<div class="photo ' + phClass(p.name) + '" id="photo-' + i + '"></div>'
    +   '<div class="info">'
    +     '<a class="name" href="' + esc(p.url) + '" target="_blank" title="카카오맵에서 별점·상세 보기">' + (i + 1) + '. ' + esc(p.name) + '</a>'
    +     certs
    +     '<span class="meta">' + esc(p.category) + (p.distance != null ? ' · ' + fmtDist(p.distance) : '') + '</span>'
    +     '<span class="rate" id="rate-' + i + '">' + rating + '</span>'
    +     '<span class="badge wait" id="mood-' + i + '">분석 중</span>'
    +     '<table class="facts">'
    +       '<tr><td>주요 메뉴</td><td class="skeleton" id="menu-' + i + '">블로그 후기 분석 중...</td></tr>'
    +       '<tr><td>가격대</td><td class="skeleton" id="price-' + i + '">...</td></tr>'
    +       '<tr><td>영업시간</td><td class="skeleton" id="hours-' + i + '">확인 중...</td></tr>'
    +       '<tr><td>예약</td><td class="skeleton" id="book-' + i + '">확인 중...</td></tr>'
    +       '<tr><td>주소</td><td>' + esc(p.address) + (p.phone ? ' · ' + esc(p.phone) : '') + '</td></tr>'
    +     '</table>'
    +   '</div>'
    + '</div>'
    + '<div class="reviews" id="reviews-' + i + '" style="display:none"></div>'
    + '</div>';
  }).join('');
}

function fillDetail(items, offset) {
  items.forEach(function (d, n) {
    var i = (offset || 0) + n;  // 구간 단위로 오므로 카드 번호는 전체 목록 기준으로 환산
    var photo = document.getElementById('photo-' + i);
    if (photo && d.photo) {
      var img = document.createElement('img');
      img.referrerPolicy = 'no-referrer';
      img.alt = '';
      img.onerror = function () { photo.innerHTML = ''; };  // 실패하면 색 타일만 남긴다
      img.src = d.photo;
      photo.innerHTML = '';
      photo.appendChild(img);
    }
    setText('menu-' + i, d.menu);
    setText('price-' + i, d.price);
    setText('hours-' + i, d.hours ? d.hours + (d.open_status ? ' · ' + d.open_status : '') : '정보 없음');
    setText('book-' + i, d.booking ? '카카오맵 예약 가능'
            : (d.phone ? '전화 예약 문의 (' + d.phone + ')' : '매장 문의'));
    var rt = document.getElementById('rate-' + i);
    if (rt && d.rating) {
      rt.textContent = '★' + d.rating + (d.rating_count ? ' (' + d.rating_count + ')' : '');
    }
    var mood = document.getElementById('mood-' + i);
    if (mood) {
      if (d.mood) { mood.textContent = d.mood; mood.className = 'badge'; }
      else { mood.style.display = 'none'; }  // 후기 없음 등 무의미한 배지는 표시하지 않음
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
  if (el) { el.textContent = text; el.className = el.className.replace(/\s*skeleton/, ''); }
}

function fmtDist(m) { return m >= 1000 ? (m / 1000).toFixed(1) + 'km' : m + 'm'; }

function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ── 지도 보기 ──────────────────────────────────────────────
var mapOpen = false, theMap = null, mapMarkers = [], theInfo = null;

function toggleMap() {
  mapOpen = !mapOpen;
  document.getElementById('mapwrap').style.display = mapOpen ? 'block' : 'none';
  document.getElementById('mapbtn').textContent = mapOpen ? '지도 닫기' : '지도로 보기';
  if (mapOpen) renderMap();
}

function renderMap() {
  if (!mapOpen || !lastPlaces.length) return;
  if (typeof kakao === 'undefined' || !kakao.maps || !kakao.maps.load) {
    document.getElementById('allmap').innerHTML =
      '<div style="padding:40px;text-align:center;color:#8b8078">지도를 불러오지 못했습니다.<br>Edge 일반 모드 또는 Chrome으로 열어주세요.</div>';
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
            + (p.rating ? ' · ★' + p.rating : '')
            + '<br><a href="' + esc(p.url) + '" target="_blank">카카오맵 상세</a></div>');
          theInfo.open(theMap, marker);
        });
        mapMarkers.push(marker);
      })(lastPlaces[i], i);
    }
    theMap.setBounds(bounds);
    setTimeout(function () { theMap.relayout(); theMap.setBounds(bounds); }, 100);
  });
}

// ── 시작 ───────────────────────────────────────────────────
syncCuisine();
updateFilterSummary();
loadMine();
document.getElementById('q').focus();
</script>
<script src="__SDKPATH__?appkey=__JSKEY__&autoload=false"></script>
</body>
</html>
"""

업종옵션HTML = "".join(
    f'\n    <option value="{키}">{정의["이름"]}</option>' for 키, 정의 in 업종정의.items()
)
PAGE = (PAGE.replace("__SDKPATH__", SDK_PATH).replace("__JSKEY__", JS_KEY or "")
        .replace("__CUISINEOPTS__", 업종옵션HTML).replace("__BATCH__", str(브리핑배치)))


# ── 5. HTTP 서버 ────────────────────────────────────────────────
# 캐시 키는 결과를 바꾸는 모든 조건을 담는다 — 하나라도 빠지면 조건을 바꿔도
# 이전 결과가 그대로 돌아온다. (q, radius, meal, cnt, cert, rate, mine, cuisine)
검색캐시: dict[tuple, dict] = {}  # 조건 → {"center","places"}
상세캐시: dict[tuple, list] = {}  # (조건, offset) → 그 구간의 enriched items
캐시잠금 = threading.Lock()

def _캐시된상세(key: tuple, 총개수: int) -> list | None:
    """모든 구간이 캐시에 있을 때만 이어 붙여 돌려준다 (일부만 있으면 None).
    호출자가 캐시잠금을 쥔 상태여야 한다."""
    모음: list = []
    for off in range(0, 총개수, 브리핑배치):
        구간 = 상세캐시.get(key + (off,))
        if 구간 is None:
            return None
        모음.extend(구간)
    return 모음 or None


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, data: bytes, ctype: str, status: int = 200):
        # 브라우저가 먼저 떠났거나 프록시가 대기를 포기하면 쓰기가 실패한다.
        # 이미 끊긴 연결이라 복구할 것이 없으므로 로그만 한 줄 남기고 넘어간다.
        try:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            print(f"응답 전송 중 연결 끊김(무시): {self.path}")

    def _send_json(self, obj):
        self._send(json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _인증됨(self) -> bool:
        if not APP_PASSWORD:
            return True
        return f"auth={_인증쿠키값}" in (self.headers.get("Cookie") or "")

    def _로그인페이지(self, 오류: str = ""):
        html_page = LOGIN_PAGE.replace("__ERR__", f"<p class='err'>{오류}</p>" if 오류 else "")
        self._send(html_page.encode("utf-8"), "text/html; charset=utf-8")

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if not self._인증됨():
            if parsed.path == "/":
                self._로그인페이지()
            else:
                self._send_json({"error": "접속 암호 인증이 필요합니다. 첫 화면에서 로그인하세요."})
            return
        if parsed.path == "/":
            self._send(PAGE.encode("utf-8"), "text/html; charset=utf-8")
        elif parsed.path == "/diag":  # 원격 진단 (내 저장 맛집 로드 상태)
            정보 = {"links": len(_저장링크들()), "cached": len(_내맛집캐시["목록"])}
            try:
                fid = _공유ID추출(_저장링크들()[0]) if _저장링크들() else ""
                정보["share_id_ok"] = bool(fid)
                if fid:
                    r = requests.get(
                        f"{_저장리스트_API}/{fid}/bookmarks",
                        params={"start": 0, "limit": 3},
                        headers=_저장리스트_헤더,
                        timeout=15,
                    )
                    정보["api_status"] = r.status_code
                    정보["api_body"] = r.text[:150]
            except Exception as e:
                정보["error"] = f"{type(e).__name__}: {str(e)[:150]}"
            self._send_json(정보)
        elif parsed.path == "/mine":  # 첫 화면 저장 맛집 카드 (페이지를 먼저 그린 뒤 채운다)
            try:
                self._send_json({"items": 내맛집홈()})
            except Exception as e:
                self._send_json({"items": [], "error": f"{type(e).__name__}: {e}"})
        elif parsed.path == SDK_PATH:  # 카카오맵 JS SDK 프록시 (사내망 차단 우회)
            try:
                self._send(카카오SDK(), "text/javascript; charset=utf-8")
            except Exception:
                self.send_error(502)
        elif parsed.path == "/search":
            qs = urllib.parse.parse_qs(parsed.query)
            q = qs.get("q", [""])[0].strip()
            radius = min(max(int(qs.get("radius", ["1000"])[0]), 100), 3000)
            meal = qs.get("meal", ["all"])[0]
            if meal not in ("all", "lunch", "dinner", "cafe"):
                meal = "all"
            cuisine = qs.get("cuisine", ["all"])[0]
            if cuisine not in 업종키 or meal == "cafe":
                cuisine = "all"
            cnt = min(max(int(qs.get("cnt", ["20"])[0]), 10), 100)
            cert = qs.get("cert", ["none"])[0]
            if cert not in ("none", "any", "michelin", "blueribbon", "century", "bwchef"):
                cert = "none"
            rate = qs.get("rate", ["0"])[0] == "4"
            mine = qs.get("mine", ["prefer"])[0]
            if mine not in ("prefer", "only", "off"):
                mine = "prefer"
            try:
                self._send_json(self._search(q, radius, meal, cnt, cert, rate, mine, cuisine))
            except Exception as e:
                self._send_json({"error": str(e)})
        else:
            self.send_error(404)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/login":
            length = int(self.headers.get("Content-Length", 0))
            form = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8"))
            pw = form.get("pw", [""])[0]
            if APP_PASSWORD and pw == APP_PASSWORD:
                self.send_response(303)
                self.send_header("Location", "/")
                self.send_header(
                    "Set-Cookie",
                    f"auth={_인증쿠키값}; Path=/; Max-Age=2592000; HttpOnly",
                )
                self.send_header("Content-Length", "0")
                self.end_headers()
            else:
                self._로그인페이지("암호가 올바르지 않습니다.")
            return
        if not self._인증됨():
            self._send_json({"error": "접속 암호 인증이 필요합니다. 첫 화면에서 로그인하세요."})
            return
        if path != "/enrich":
            self.send_error(404)
            return
        try:
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            req = json.loads(body)
            q = req["query"].strip()
            radius = min(max(int(req.get("radius", 1000)), 100), 3000)
            meal = req.get("meal", "all")
            if meal not in ("all", "lunch", "dinner", "cafe"):
                meal = "all"
            cuisine = req.get("cuisine", "all")
            if cuisine not in 업종키 or meal == "cafe":
                cuisine = "all"
            cnt = min(max(int(req.get("cnt", 20)), 10), 100)
            cert = req.get("cert", "none")
            if cert not in ("none", "any", "michelin", "blueribbon", "century", "bwchef"):
                cert = "none"
            rate = str(req.get("rate", "0")) == "4"
            mine = req.get("mine", "prefer")
            if mine not in ("prefer", "only", "off"):
                mine = "prefer"
            offset = max(0, int(req.get("offset", 0)))
            key = (q, radius, meal, cnt, cert, rate, mine, cuisine)
            with 캐시잠금:
                base = 검색캐시.get(key)
                cached = 상세캐시.get(key + (offset,))
            if not base:
                self._send_json({"error": "먼저 검색을 실행하세요."})
                return
            총개수 = len(base["places"])
            끝 = offset + 브리핑배치
            # next는 다음 구간의 시작 위치. 마지막 구간이면 None을 보내 클라이언트가 멈춘다
            응답 = {"offset": offset, "total": 총개수, "next": 끝 if 끝 < 총개수 else None}
            if cached is not None:
                self._send_json({**응답, "items": cached, "partial": False})
                return
            items, 요약성공 = 브리핑생성(q, base["places"][offset:끝])
            if 요약성공:  # Gemini가 통째로 실패한 구간은 캐시하지 않는다 (재검색 시 재시도)
                with 캐시잠금:
                    상세캐시[key + (offset,)] = items
            self._send_json({**응답, "items": items, "partial": not 요약성공})
        except Exception as e:
            self._send_json({"error": str(e)})

    def _search(
        self, q: str, radius: int, meal: str = "all", cnt: int = 30,
        cert: str = "none", rate: bool = False, mine: str = "prefer",
        cuisine: str = "all",
    ) -> dict:
        if not q:
            return {"error": "동네 이름을 입력하세요."}
        key = (q, radius, meal, cnt, cert, rate, mine, cuisine)
        with 캐시잠금:
            cached = 검색캐시.get(key)
            detail = _캐시된상세(key, len(cached["places"])) if cached else None
        if cached:
            return {**cached, "cached_detail": detail}
        좌표 = 동네좌표(q)
        if not 좌표:
            return {"error": f'"{q}" 위치를 찾지 못했습니다. 동네 이름을 다시 확인해 주세요.'}
        center, x, y = 좌표
        places = 맛집검색(x, y, radius, meal, cnt, cert, rate, mine, 업종=cuisine)
        result = {"center": center, "places": places}
        with 캐시잠금:
            검색캐시[key] = result
        return {**result, "cached_detail": None}

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {fmt % args}")


def main():
    url = f"http://localhost:{PORT}"
    # 클라우드(PORT 지정)에는 열 브라우저가 없다 — 굳이 시도하지 않는다
    no_browser = (os.environ.get("NO_BROWSER") == "1" or "--no-browser" in sys.argv
                  or bool(os.environ.get("PORT")))

    if not gemini_client:
        print("경고: GEMINI_API_KEY가 없어 블로그 요약 없이 카카오맵 메뉴판 기준으로만 표시됩니다.")

    class DualStackServer(http.server.ThreadingHTTPServer):
        # Windows에서는 SO_REUSEADDR이 켜져 있으면 같은 포트에 중복 바인딩이
        # 허용되어 구버전 프로세스가 계속 응답할 수 있으므로 끈다.
        allow_reuse_address = False
        address_family = socket.AF_INET6 if HOST == "::" else socket.AF_INET

        def server_bind(self):
            if self.address_family == socket.AF_INET6:
                try:
                    self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
                except OSError:
                    pass
            super().server_bind()

    try:
        server = DualStackServer((HOST, PORT), Handler)
    except OSError:
        print(f"이미 실행 중입니다: {url}")
        if not no_browser:
            webbrowser.open(url)
        return

    print(f"맛집 브리핑 실행 중: {url}")
    print(f"사내망 공유 주소: http://{socket.gethostname()}:{PORT}")
    print("종료하려면 이 창에서 Ctrl+C 또는 창을 닫으세요.")
    if not no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
