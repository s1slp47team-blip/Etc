# -*- coding: utf-8 -*-
"""인증 배지 조회의 카카오 API 호출 수를 재는 회귀 테스트.

실제 카카오 API 대신 가짜 응답을 주입하므로 API 키 없이 돌아간다.
인증 조회는 검색 1회당 호출의 대부분을 차지하던 부분이라,
리팩터링으로 호출이 다시 늘어나지 않는지 수치로 지킨다.

실행:
    python test_인증호출수.py
"""
import collections
import importlib.util
import json
import os
import sys
import tempfile

os.environ.setdefault("KAKAO_REST_API_KEY", "fake_key_for_test")

_여기 = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("app", os.path.join(_여기, "food_briefing_app.py"))
app = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(app)

호출수 = collections.Counter()


class _응답:
    def __init__(self, 자료, status=200):
        self._자료, self.status_code = 자료, status
        self.text = json.dumps(자료, ensure_ascii=False)

    def json(self):
        return self._자료


def _가짜검색(url, **kw):
    """카카오처럼 45건을 3페이지에 나눠 준다 (is_end는 마지막 페이지에만 True)."""
    params = kw.get("params") or {}
    if "search/address.json" in url:
        return _응답({"documents": [{"address_name": "서울 강남구 역삼동",
                                     "x": "127.0364", "y": "37.5006"}]})
    if "v2/local/search/keyword.json" in url:
        호출수["keyword"] += 1
        page = params.get("page", 1)
        docs = [{
            "id": f"{i:04d}", "place_name": f"가게{i}", "category_name": "음식점 > 한식 > 국수",
            "category_group_code": "FD6", "address_name": "서울 강남구 역삼동",
            "road_address_name": "서울 강남구 테헤란로 1", "phone": "",
            "place_url": f"http://place.map.kakao.com/{i:04d}",
            "x": "127.0365", "y": "37.5007", "distance": "100",
        } for i in range((page - 1) * 15, page * 15)]
        return _응답({"documents": docs, "meta": {"is_end": page >= 3}})
    if "panel3" in url:
        return _응답({"kakaomap_review": {"score_set": {"average_score": 4.5, "review_count": 1}}})
    if "maps-bookmark" in url:
        return _응답({"bookmarkList": []} if url.endswith("bookmarks") else {"folder": {"name": "f"}})
    return _응답({}, 404)


app.requests.get = _가짜검색

# 인증 질의는 4종 × 3~4개 = 13개. 각 질의가 1페이지만 부르는 것이 기준선이다.
질의수 = sum(len(v) for v in app.인증검색어.values())
실패 = []


def 확인(설명, 실제, 기대):
    ok = 실제 == 기대
    print(f"  {'PASS' if ok else 'FAIL'}  {설명}: {실제}회 (기대 {기대}회)")
    if not ok:
        실패.append(설명)


def 캐시비우기():
    app._인증맵캐시.clear()
    app._상세결과캐시.clear()
    app.검색캐시.clear()


def 검색(cert):
    캐시비우기()
    호출수.clear()
    app.맛집검색(127.0364, 37.5006, 1000, "all", 30, cert, False, "off", "all")
    return 호출수["keyword"]


# 캐시 파일이 테스트에 섞이지 않도록 임시 경로로 돌린다
app._인증캐시파일 = os.path.join(tempfile.mkdtemp(), "_인증캐시.json")

print("\n[1] 인증 조회는 질의당 1페이지만 부른다")
캐시비우기()          # 지난 실행이 남긴 캐시 파일이 로드돼 있을 수 있다
호출수.clear()
자료 = app.인증자료(127.0364, 37.5006, 1000)
확인("인증 조회 호출", 호출수["keyword"], 질의수)
확인("인증 종류 수", len(자료), len(app.인증검색어))

print("\n[2] 인증 필터를 켜도 같은 질의를 두 번 돌지 않는다")
확인("cert=any", 검색("any"), 질의수)
확인("cert=michelin", 검색("michelin"), 질의수)

print("\n[3] 기본 검색(cert=none)의 인증 조회 몫")
기본 = 검색("none")
확인("cert=none 총 호출", 기본, 질의수 + 3)  # 인증 13 + 일반 검색어 3

print("\n[4] 같은 격자·반경 재검색은 인증 조회를 다시 하지 않는다")
호출수.clear()
app.검색캐시.clear()
app.맛집검색(127.0364, 37.5006, 1000, "all", 30, "none", False, "off", "all")
확인("2회차 총 호출", 호출수["keyword"], 3)  # 일반 검색어만

print("\n[5] 캐시가 파일로 남아 프로세스 재시작 후에도 쓰인다")
app._인증캐시저장()
저장본 = dict(app._인증맵캐시)
app._인증맵캐시.clear()
app._인증캐시로드()
확인("파일에서 복원된 격자 수", len(app._인증맵캐시), len(저장본))
호출수.clear()
app.인증자료(127.0364, 37.5006, 1000)
확인("복원 후 인증 조회", 호출수["keyword"], 0)

print("\n" + "=" * 46)
print("결과: " + ("전부 통과" if not 실패 else f"{len(실패)}건 실패 → {실패}"))
sys.exit(1 if 실패 else 0)
