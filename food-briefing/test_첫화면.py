# -*- coding: utf-8 -*-
"""첫 화면(검색 전 화면) 회귀 테스트.

가짜 카카오/네이버 응답을 주입하므로 API 키 없이 돌아간다.
- 저장 맛집 카드가 /mine으로 내려오는지
- 카드 조회 결과가 파일 캐시에 남아 재시작 후 API 호출이 0회인지
  (첫 화면 때문에 깨어날 때마다 카카오를 다시 부르면 안 된다)
- 화면 스크립트가 쓰는 요소 id가 템플릿에 다 있는지

실행:
    python test_첫화면.py
"""
import collections
import importlib.util
import json
import os
import sys
import tempfile

os.environ.setdefault("KAKAO_REST_API_KEY", "fake_key_for_test")
# 저장 리스트를 하나로 고정한다 — 실제 내맛집링크.txt(여러 개)를 읽으면 결과 수가 달라진다
os.environ["MY_PLACE_LINKS"] = "https://map.naver.com/p/favorite/sharedPlace/folder/" + "a" * 32

_여기 = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("app", os.path.join(_여기, "food_briefing_app.py"))
app = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(app)

호출수 = collections.Counter()
저장가게 = [("역삼 손칼국수", "가본곳"), ("테헤란 숯불갈비", "가볼곳"), ("선릉 옛날우동", "가본곳")]
_북마크 = [{"name": nm, "px": "127.0365", "py": "37.5007"} for nm, _ in 저장가게]


class _응답:
    def __init__(self, 자료, status=200):
        self._자료, self.status_code = 자료, status
        self.text = json.dumps(자료, ensure_ascii=False)

    def json(self):
        return self._자료


def _가짜검색(url, **kw):
    if "v2/local/search/keyword.json" in url:
        호출수["keyword"] += 1
        질의 = (kw.get("params") or {}).get("query", "")
        return _응답({"documents": [{
            "id": str(abs(hash(질의)) % 10000), "place_name": 질의,
            "category_name": "음식점 > 한식 > 국수", "category_group_code": "FD6",
            "address_name": "서울 강남구 역삼동", "road_address_name": "서울 강남구 테헤란로 1",
            "phone": "", "place_url": "http://place.map.kakao.com/1001",
            "x": "127.0365", "y": "37.5007", "distance": "100",
        }], "meta": {"is_end": True}})
    if "panel3" in url:
        호출수["panel3"] += 1
        return _응답({"photos": {"photos": [{"url": "http://img.example/a.jpg"}]},
                      "kakaomap_review": {"score_set": {"average_score": 4.4, "review_count": 88}}})
    if "maps-bookmark" in url:
        호출수["naver"] += 1
        if url.endswith("/bookmarks") or (kw.get("params") or {}).get("limit"):
            return _응답({"bookmarkList": _북마크})
        return _응답({"folder": {"name": "가본곳"}})
    return _응답({}, 404)


app.requests.get = _가짜검색
app._홈캐시파일 = os.path.join(tempfile.mkdtemp(), "_홈캐시.json")

실패 = []


def 확인(설명, 조건, 상세=""):
    print(f"  {'PASS' if 조건 else 'FAIL'}  {설명}" + (f": {상세}" if 상세 else ""))
    if not 조건:
        실패.append(설명)


def 캐시비우기():
    app._홈캐시.clear()
    app._내맛집캐시["목록"] = []
    app._내맛집캐시["시각"] = 0.0
    app._상세결과캐시.clear()


print("\n[1] 저장 맛집 카드가 내려온다")
캐시비우기()
호출수.clear()
카드들 = app.내맛집홈()
확인("카드 수", len(카드들) == len(저장가게), f"{len(카드들)}장")
if 카드들:
    첫 = 카드들[0]
    확인("이름", 첫["name"] == "역삼 손칼국수", 첫["name"])
    확인("사진 URL", 첫["photo"].startswith("https://"), 첫["photo"])
    확인("업종", 첫["category"] == "국수", 첫["category"])
    확인("별점", 첫["rating"] == 4.4, str(첫["rating"]))
    확인("저장 배지", "가본곳" in 첫["badge"], 첫["badge"])

print("\n[2] 두 번째부터는 카카오를 다시 부르지 않는다")
첫회 = 호출수["keyword"] + 호출수["panel3"]
호출수.clear()
app._내맛집캐시["시각"] = 0.0  # 네이버 목록만 다시 읽게 하고, 가게별 조회는 캐시를 봐야 한다
app.내맛집홈()
확인("가게별 카카오 호출", 호출수["keyword"] + 호출수["panel3"] == 0,
     f"1회차 {첫회}회 → 2회차 {호출수['keyword'] + 호출수['panel3']}회")

print("\n[3] 재시작 후에도 파일 캐시를 쓴다")
app._캐시저장(app._홈캐시파일, app.홈캐시버전, dict(app._홈캐시), app.홈캐시최대)
복원 = app._캐시로드(app._홈캐시파일, app.홈캐시버전, app.홈캐시TTL)
확인("파일에서 복원된 가게 수", len(복원) == len(저장가게), f"{len(복원)}곳")
app._홈캐시.clear()
app._홈캐시.update(복원)
app._내맛집캐시["시각"] = 0.0
호출수.clear()
app.내맛집홈()
확인("복원 후 카카오 호출", 호출수["keyword"] + 호출수["panel3"] == 0,
     f"{호출수['keyword'] + 호출수['panel3']}회")

print("\n[4] 저장 리스트가 없으면 영역을 비운다")
캐시비우기()
_북마크 = []
확인("빈 목록", app.내맛집홈() == [], "카드 없음 → 화면에서 영역이 숨는다")
_북마크 = [{"name": nm, "px": "127.0365", "py": "37.5007"} for nm, _ in 저장가게]

print("\n[5] 화면 스크립트가 쓰는 요소가 템플릿에 다 있다")
필수 = ["id=\"q\"", "id=\"meal\"", "id=\"cuisine\"", "id=\"radius\"", "id=\"cnt\"", "id=\"cert\"",
        "id=\"rate\"", "id=\"mine\"", "id=\"status\"", "id=\"results\"", "id=\"mapbtn\"",
        "id=\"mapwrap\"", "id=\"allmap\"", "id=\"segment\"", "id=\"filters\"", "id=\"sheetdim\"",
        "id=\"minecards\"", "id=\"minewrap\"", "id=\"recent\"", "id=\"filtersum\"", "id=\"helpbox\""]
빠진 = [k for k in 필수 if k not in app.PAGE]
확인("필수 요소", not 빠진, "빠짐: " + ", ".join(빠진) if 빠진 else f"{len(필수)}개 모두 있음")
남은자리 = [t for t in ("__SDKPATH__", "__JSKEY__", "__CUISINEOPTS__") if t in app.PAGE]
확인("치환 안 된 자리표시자 없음", not 남은자리, ", ".join(남은자리) or "없음")

print("\n" + "=" * 46)
print("결과: " + ("전부 통과" if not 실패 else f"{len(실패)}건 실패 → {실패}"))
sys.exit(1 if 실패 else 0)
