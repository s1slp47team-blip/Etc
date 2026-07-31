# -*- coding: utf-8 -*-
r"""
맛집 브리핑 웹앱 (카카오 반경검색·블로그 + Gemini 요약)
======================================================================

동네 이름을 입력하면:
1. 카카오 주소/키워드 검색으로 동네 좌표를 구하고
2. 반경 2km(500m~3km 조절) 이내 음식점을 카카오 키워드 검색으로 10~100곳(선택) 선별
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
import json
import os
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
맛집수 = 30  # 브리핑할 가게 수


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

_인증맵캐시: dict[tuple, dict[str, list[str]]] = {}
_인증맵잠금 = threading.Lock()


def 인증맵(x: float, y: float, radius: int) -> dict[str, list[str]]:
    """해당 반경의 인증 맛집을 미리 조회해 {정규화 상호: [배지들]}로 만든다.
    인증 필터를 안 걸고 검색해도 인증 배지가 보이도록 하기 위한 것.
    카카오 장소 ID는 같은 가게라도 검색 경로에 따라 다를 수 있어 상호로 대조한다.
    좌표·반경 단위로 캐시해 반복 검색 시 추가 호출이 없다."""
    키 = (round(x, 3), round(y, 3), radius)  # 약 100m 격자로 캐시 공유
    with _인증맵잠금:
        if 키 in _인증맵캐시:
            return _인증맵캐시[키]
    결과: dict[str, list[str]] = {}

    def 조사(항목):
        c, 질의들 = 항목
        찾음 = []
        for 질의 in 질의들:
            for d in _장소수집(질의, x, y, radius):
                찾음.append(d["place_name"])
        return 인증표시명[c], 찾음

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for 배지, 이름들 in pool.map(조사, 인증검색어.items()):
            for 이름 in 이름들:
                키이름 = _이름정규화(이름)
                if 키이름 and 배지 not in 결과.setdefault(키이름, []):
                    결과[키이름].append(배지)
    with _인증맵잠금:
        _인증맵캐시[키] = 결과
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
) -> list[dict]:
    """좌표 반경 내 맛집 검색.
    시간대: all/lunch(식사)/dinner(술 동반) · cert: none/any/michelin/blueribbon/century
    평점4: 카카오맵 별점 4.0 이상만."""
    후보, seen = [], {}
    그룹코드들 = 검색그룹코드.get(시간대, ("FD6",))

    def 수집(질의: str, 배지: str = ""):
        for 코드 in 그룹코드들:
            for d in _장소수집(질의, x, y, radius, 그룹코드=코드):
                if not _시간대적합(d, 시간대):
                    continue
                if d["id"] in seen:
                    if 배지 and 배지 not in seen[d["id"]]["badges"]:
                        seen[d["id"]]["badges"].append(배지)
                    continue
                d["badges"] = [배지] if 배지 else []
                seen[d["id"]] = d
                후보.append(d)

    if cert == "any":
        # 인증 종류별로 따로 모은 뒤 라운드로빈으로 섞는다 —
        # 한 인증(미쉐린)의 결과가 상위를 독식해 다른 인증이 밀려나지 않게
        import itertools

        풀들 = []
        for c, 질의들 in 인증검색어.items():
            시작 = len(후보)
            for 질의 in 질의들:
                수집(질의, 인증표시명[c])
            풀들.append(후보[시작:])
        후보 = [d for 묶음 in itertools.zip_longest(*풀들) for d in 묶음 if d is not None]
    elif cert in 인증검색어:
        for 질의 in 인증검색어[cert]:
            수집(질의, 인증표시명[cert])
    else:
        목표 = 개수 * 2 if 평점4 else 개수  # 평점 필터로 걸러질 몫을 여유 있게 수집
        for 검색어 in 검색어풀.get(시간대, 검색어풀["all"]):
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
                    if d["id"] in seen or not _시간대적합(d, 시간대):
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

    # 카카오맵 상세(평점·영업시간·예약)를 붙인다 — 결과 카드와 평점 필터에 사용.
    # 평점 필터가 있으면 후보 전체를, 아니면 상위 개수만 조회 (조회 결과는 캐시됨)
    대상 = 후보 if 평점4 else 후보[:개수]
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        상세들 = list(pool.map(lambda d: _카카오상세(d["place_url"]), 대상))
    for d, 상세 in zip(대상, 상세들):
        d["_상세"] = 상세
    if 평점4:
        대상 = [d for d in 대상 if (d["_상세"].get("rating") or 0) >= 4.0]

    places = []
    for d in 대상[:개수]:
        상세 = d.get("_상세") or {}
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
    try:
        resp = requests.get(
            f"https://place-api.map.kakao.com/places/panel3/{pid}",
            headers=_KAKAO_PANEL_HEADERS,
            timeout=10,
        )
        if resp.status_code != 200:
            return {}
        d = resp.json()
    except (requests.RequestException, ValueError):
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
    try:
        resp = requests.get(
            f"https://place.map.kakao.com/{pid}",
            headers={"User-Agent": _브라우저_UA},
            timeout=10,
        )
        if resp.status_code != 200:
            return None
    except requests.RequestException:
        return None
    m = re.search(r'property="og:image"\s+content="([^"]+)"', resp.text)
    if not m:
        return None
    url = m.group(1)
    if "fname=" not in url:  # 사진 없는 가게의 기본 og 이미지
        return None
    return "https:" + url if url.startswith("//") else url


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


def _groq요약(prompt: str) -> list:
    """Gemini 한도 소진 시 Groq(무료, llama-3.3-70b)로 같은 요약을 수행한다."""
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_KEY}"},
        json={
            "model": GROQ_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
        },
        timeout=60,
    )
    resp.raise_for_status()
    text = resp.json()["choices"][0]["message"]["content"]
    m = re.search(r"\[.*\]", text, re.S)  # 앞뒤 설명 문장이 붙어도 JSON 배열만 추출
    if not m:
        raise ValueError("Groq 응답에서 JSON 배열을 찾지 못했습니다")
    return json.loads(m.group(0))


def _gemini_chunk요약(동네: str, places: list[dict], 자료들: list[dict], start: int) -> dict[int, dict]:
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
    # Groq 폴백이 있으면 Gemini 재시도를 줄여 빨리 넘어간다
    최대시도 = 2 if GROQ_KEY else 4
    for 시도 in range(최대시도):
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
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg:  # 무료 티어 호출 한도
                if 시도 < 최대시도 - 1:
                    time.sleep(25)
                continue
            if "503" in msg or "UNAVAILABLE" in msg:  # 일시적 수요 폭주
                time.sleep(8 * (시도 + 1))
                continue
            # 그 외 오류(모델 정책 변경, 잘못된 인자 등)도 Groq으로 폴백해 요약이 끊기지 않게 한다
            if GROQ_KEY:
                print(f"Gemini 오류 → Groq 폴백: {msg[:100]}")
                break
            raise
    if resp is not None:
        items = json.loads(resp.text)
    elif GROQ_KEY:  # Gemini 실패(한도·오류) → Groq 무료 폴백
        items = _groq요약(prompt)
    else:
        raise RuntimeError("Gemini 요청 한도(429) 재시도 실패")
    return {
        start + int(it["index"]): it
        for it in items
        if isinstance(it, dict) and "index" in it and 0 <= int(it["index"]) < len(places)
    }


def gemini요약(동네: str, places: list[dict], 자료들: list[dict]) -> dict[int, dict]:
    if not gemini_client:
        return {}
    결과: dict[int, dict] = {}
    구간들 = list(range(0, len(places), GEMINI_CHUNK))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(len(구간들), 1)) as pool:
        futures = [
            pool.submit(_gemini_chunk요약, 동네, places[s : s + GEMINI_CHUNK], 자료들[s : s + GEMINI_CHUNK], s)
            for s in 구간들
        ]
        for f in futures:
            try:
                결과.update(f.result())
            except Exception as e:
                print(f"Gemini 요약 실패(일부 구간): {e}")
    return 결과


def 브리핑생성(동네: str, places: list[dict]) -> tuple[list[dict], bool]:
    """가게 목록에 사진·메뉴·가격대·반응을 붙여 완성한다.
    반환: (완성 목록, Gemini 요약 성공 여부 — 실패분은 캐시하지 않도록)"""
    # 카카오 검색 API 초당 제한 대응 — 10개 동시 수집 + 429 재시도(백오프)
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        자료들 = list(pool.map(lambda p: 가게자료수집(동네, p), places))
    요약 = gemini요약(동네, places, 자료들)
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
            }
        )
    return enriched, 요약성공


# ── 4. 페이지 HTML ──────────────────────────────────────────────
PAGE = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta http-equiv="X-UA-Compatible" content="IE=edge">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>맛집 브리핑</title>
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
  .cert.c-my { background: #d63b5b; color: #fff; }   /* 가본곳 */
  .cert.c-my2 { background: #fdeaee; color: #b02a45; border: 1px solid #f3c2ce; }  /* 가볼곳 */
  .cert.c-cf { background: #6b4a2f; color: #fff; }   /* 저장한 카페 */
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
  .reviews p::before { content: '\201C'; color: #b0bdd0; margin-right: 2px; }
  .reviews p::after { content: '\201D'; color: #b0bdd0; margin-left: 2px; }

  /* ── 모바일 레이아웃 (폰에서 자동 적용, PC 화면은 영향 없음) ── */
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
  }
</style>
</head>
<body>
<header>
  <h1>맛집 브리핑</h1>
  <input id="q" placeholder="동네 이름 (예: 역삼동, 서초동, 판교)" onkeydown="if(event.key==='Enter'||event.keyCode===13)doSearch()">
  <select id="meal" title="시간대별 추천 기준">
    <option value="all" selected>전체</option>
    <option value="lunch">점심 (식사 위주)</option>
    <option value="dinner">저녁 (술 한잔)</option>
    <option value="cafe">카페 · 디저트</option>
  </select>
  <select id="radius">
    <option value="500">500m</option>
    <option value="1000">1km</option>
    <option value="1500">1.5km</option>
    <option value="2000" selected>2km</option>
    <option value="3000">3km</option>
  </select>
  <select id="cnt" title="추출 개수">
    <option value="10">10곳</option>
    <option value="20">20곳</option>
    <option value="30" selected>30곳</option>
    <option value="40">40곳</option>
    <option value="50">50곳</option>
    <option value="60">60곳</option>
    <option value="70">70곳</option>
    <option value="80">80곳</option>
    <option value="90">90곳</option>
    <option value="100">100곳</option>
  </select>
  <select id="cert" title="인증 맛집 필터 (카카오맵 검색 연관 기준)">
    <option value="none" selected>인증 무관</option>
    <option value="any">인증맛집만 (통합)</option>
    <option value="michelin">미쉐린 가이드</option>
    <option value="blueribbon">블루리본</option>
    <option value="century">백년가게</option>
    <option value="bwchef">흑백요리사</option>
  </select>
  <select id="rate" title="카카오맵 별점 필터">
    <option value="0" selected>평점 무관</option>
    <option value="4">★4.0 이상</option>
  </select>
  <select id="mine" title="네이버지도에 저장해둔 내 맛집">
    <option value="prefer" selected>내 저장 우선</option>
    <option value="only">내 저장만</option>
    <option value="off">내 저장 무시</option>
  </select>
  <button onclick="doSearch()">검색</button>
  <button id="mapbtn" onclick="toggleMap()" style="display:none">지도로 보기</button>
  <span id="status"></span>
</header>
<div id="mapwrap">
  <div id="allmap"></div>
  <p class="map-hint">번호 핀을 클릭하면 가게 이름이 표시됩니다. 카드 목록의 번호와 동일합니다.</p>
</div>
<div id="results">
  <div class="notice">동네 이름을 입력하면 반경 이내 맛집을 찾아
사진 · 주요 메뉴 · 가격대 · 블로그 반응을 정리해 드립니다.

시간대를 고르면 기준이 달라집니다:
· 점심 — 식사 위주 (술집·안주 전문점 제외)
· 저녁 — 술을 곁들이기 좋은 집 (고기·회·주점 등)
· 카페·디저트 — 카페·베이커리·디저트 전문점 (룸카페 등 제외)

내 저장 맛집(네이버지도에 저장한 리스트)은 기본으로 맨 위에 ♥가본곳·♡가볼곳
배지와 함께 표시됩니다. "내 저장만" 선택 시 저장한 곳만 볼 수 있습니다.

인증 필터(미쉐린 가이드·블루리본·백년가게·흑백요리사)는 카카오맵 검색 연관 기준의
참고용 분류입니다. 공식 명부가 공개되어 있지 않아 누락·오포함이 있을 수
있으며, 블루리본은 데이터가 적어 결과가 없을 수 있습니다.

예) "역삼동" / "서초동" / "판교" / "강남역"</div>
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

function doSearch() {
  if (searching) return;
  var q = document.getElementById('q').value.replace(/^\s+|\s+$/g, '');
  var radius = document.getElementById('radius').value;
  var meal = document.getElementById('meal').value;
  var cnt = document.getElementById('cnt').value;
  var cert = document.getElementById('cert').value;
  var rate = document.getElementById('rate').value;
  var mine = document.getElementById('mine').value;
  if (!q) return;
  searching = true;
  var status = document.getElementById('status');
  var results = document.getElementById('results');
  status.textContent = (cert !== 'none' || rate === '4')
    ? '음식점 검색 + 인증·평점 확인 중... (10~30초)' : '주변 음식점 검색 중...';
  var qs = '/search?q=' + encodeURIComponent(q) + '&radius=' + radius + '&meal=' + meal
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
      fillDetail(data.cached_detail);
      status.textContent = data.center + ' · ' + data.places.length + '곳 (캐시)';
      searching = false;
      return;
    }
    status.textContent = '블로그 후기 분석 중... (' + (data.places.length <= 30 ? '30~40초' : '1~2분') + ')';
    ajax('POST', '/enrich', JSON.stringify({query: q, radius: radius, meal: meal, cnt: cnt, cert: cert, rate: rate, mine: mine}), function (err2, detail) {
      searching = false;
      if (err2) { status.textContent = '오류: ' + err2.message; return; }
      if (detail.error) { status.textContent = detail.error; return; }
      fillDetail(detail.items);
      status.textContent = data.center + ' · ' + data.places.length + '곳 분석 완료';
    });
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
      var cls;
      if (b.indexOf('☕') >= 0) cls = 'c-cf';
      else if (b.indexOf('가본곳') >= 0) cls = 'c-my';
      else if (b.indexOf('가볼곳') >= 0 || b.indexOf('내저장') >= 0) cls = 'c-my2';
      else if (b === '미쉐린') cls = 'c-mi';
      else if (b === '블루리본') cls = 'c-bl';
      else if (b === '흑백요리사') cls = 'c-bw';
      else cls = 'c-hu';
      return '<span class="cert ' + cls + '">' + esc(b) + '</span>';
    }).join('');
    var rating = p.rating ? '★' + p.rating + (p.rating_count ? ' (' + p.rating_count + ')' : '') : '';
    var hours = p.hours ? esc(p.hours) + (p.open_status ? ' · ' + esc(p.open_status) : '') : '정보 없음';
    var reserve = p.booking ? '카카오맵 예약 가능'
                : (p.phone ? '전화 예약 문의 (' + esc(p.phone) + ')' : '매장 문의');
    return '<div class="card" id="card-' + i + '">'
    + '<div class="top">'
    +   '<div class="photo" id="photo-' + i + '">사진 준비 중</div>'
    +   '<div class="info">'
    +     '<a class="name" href="' + esc(p.url) + '" target="_blank" title="카카오맵에서 별점·상세 보기">' + (i + 1) + '. ' + esc(p.name) + '</a>'
    +     certs
    +     '<span class="meta">' + esc(p.category) + (p.distance != null ? ' · ' + fmtDist(p.distance) : '') + '</span>'
    +     '<span class="rate" id="rate-' + i + '">' + rating + '</span>'
    +     '<span class="badge wait" id="mood-' + i + '">분석 중</span>'
    +     '<table class="facts">'
    +       '<tr><td>주요 메뉴</td><td class="skeleton" id="menu-' + i + '">블로그 후기 분석 중...</td></tr>'
    +       '<tr><td>가격대</td><td class="skeleton" id="price-' + i + '">...</td></tr>'
    +       '<tr><td>영업시간</td><td>' + hours + '</td></tr>'
    +       '<tr><td>예약</td><td>' + reserve + '</td></tr>'
    +       '<tr><td>주소</td><td>' + esc(p.address) + (p.phone ? ' · ' + esc(p.phone) : '') + '</td></tr>'
    +     '</table>'
    +   '</div>'
    + '</div>'
    + '<div class="reviews" id="reviews-' + i + '" style="display:none"></div>'
    + '</div>';
  }).join('');
}

function fillDetail(items) {
  items.forEach(function (d, i) {
    var photo = document.getElementById('photo-' + i);
    if (photo) {
      if (d.photo) {
        var img = document.createElement('img');
        img.referrerPolicy = 'no-referrer';
        img.alt = '';
        img.onerror = function () { photo.textContent = '사진 없음'; };
        img.src = d.photo;
        photo.textContent = '';
        photo.appendChild(img);
      } else {
        photo.textContent = '사진 없음';
      }
    }
    setText('menu-' + i, d.menu);
    setText('price-' + i, d.price);
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
  if (el) { el.textContent = text; el.classList.remove('skeleton'); }
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
      '<div style="padding:40px;text-align:center;color:#889">지도를 불러오지 못했습니다.<br>Edge 일반 모드 또는 Chrome으로 열어주세요.</div>';
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
</script>
<script src="__SDKPATH__?appkey=__JSKEY__&autoload=false"></script>
</body>
</html>
"""

PAGE = PAGE.replace("__SDKPATH__", SDK_PATH).replace("__JSKEY__", JS_KEY or "")


# ── 5. HTTP 서버 ────────────────────────────────────────────────
검색캐시: dict[tuple, dict] = {}  # (q, radius) → {"center","places"}
상세캐시: dict[tuple, list] = {}  # (q, radius) → enriched items
캐시잠금 = threading.Lock()


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, data: bytes, ctype: str, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

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
        elif parsed.path == SDK_PATH:  # 카카오맵 JS SDK 프록시 (사내망 차단 우회)
            try:
                self._send(카카오SDK(), "text/javascript; charset=utf-8")
            except Exception:
                self.send_error(502)
        elif parsed.path == "/search":
            qs = urllib.parse.parse_qs(parsed.query)
            q = qs.get("q", [""])[0].strip()
            radius = min(max(int(qs.get("radius", ["2000"])[0]), 100), 3000)
            meal = qs.get("meal", ["all"])[0]
            if meal not in ("all", "lunch", "dinner", "cafe"):
                meal = "all"
            cnt = min(max(int(qs.get("cnt", ["30"])[0]), 10), 100)
            cert = qs.get("cert", ["none"])[0]
            if cert not in ("none", "any", "michelin", "blueribbon", "century", "bwchef"):
                cert = "none"
            rate = qs.get("rate", ["0"])[0] == "4"
            mine = qs.get("mine", ["prefer"])[0]
            if mine not in ("prefer", "only", "off"):
                mine = "prefer"
            try:
                self._send_json(self._search(q, radius, meal, cnt, cert, rate, mine))
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
            radius = min(max(int(req.get("radius", 2000)), 100), 3000)
            meal = req.get("meal", "all")
            if meal not in ("all", "lunch", "dinner", "cafe"):
                meal = "all"
            cnt = min(max(int(req.get("cnt", 30)), 10), 100)
            cert = req.get("cert", "none")
            if cert not in ("none", "any", "michelin", "blueribbon", "century", "bwchef"):
                cert = "none"
            rate = str(req.get("rate", "0")) == "4"
            mine = req.get("mine", "prefer")
            if mine not in ("prefer", "only", "off"):
                mine = "prefer"
            key = (q, radius, meal, cnt, cert, rate, mine)
            with 캐시잠금:
                cached = 상세캐시.get(key)
                base = 검색캐시.get(key)
            if cached:
                self._send_json({"items": cached})
                return
            if not base:
                self._send_json({"error": "먼저 검색을 실행하세요."})
                return
            items, 요약성공 = 브리핑생성(q, base["places"])
            if 요약성공:  # Gemini가 통째로 실패한 결과는 캐시하지 않는다 (재검색 시 재시도)
                with 캐시잠금:
                    상세캐시[key] = items
            self._send_json({"items": items})
        except Exception as e:
            self._send_json({"error": str(e)})

    def _search(
        self, q: str, radius: int, meal: str = "all", cnt: int = 30,
        cert: str = "none", rate: bool = False, mine: str = "prefer",
    ) -> dict:
        if not q:
            return {"error": "동네 이름을 입력하세요."}
        key = (q, radius, meal, cnt, cert, rate, mine)
        with 캐시잠금:
            cached = 검색캐시.get(key)
            detail = 상세캐시.get(key)
        if cached:
            return {**cached, "cached_detail": detail}
        좌표 = 동네좌표(q)
        if not 좌표:
            return {"error": f'"{q}" 위치를 찾지 못했습니다. 동네 이름을 다시 확인해 주세요.'}
        center, x, y = 좌표
        places = 맛집검색(x, y, radius, meal, cnt, cert, rate, mine)
        result = {"center": center, "places": places}
        with 캐시잠금:
            검색캐시[key] = result
        return {**result, "cached_detail": None}

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {fmt % args}")


def main():
    url = f"http://localhost:{PORT}"
    no_browser = os.environ.get("NO_BROWSER") == "1" or "--no-browser" in sys.argv

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
