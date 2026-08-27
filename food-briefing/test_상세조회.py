# -*- coding: utf-8 -*-
"""카카오맵 상세 조회(사진·별점) 회귀 테스트.

상세는 비공식 API(panel3)라 한꺼번에 몰아 부르면 앞의 몇 건만 받고 나머지를 막는다.
예전에는 재시도가 없어 11번째 가게부터 사진·별점이 통째로 비었다.
호출 제한을 흉내 낸 가짜 응답으로, 제한이 걸려도 결국 전부 받아오는지 확인한다.

실행:
    python test_상세조회.py
"""
import importlib.util
import json
import os
import sys
import threading
import time

os.environ.setdefault("KAKAO_REST_API_KEY", "fake_key_for_test")

_여기 = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("app", os.path.join(_여기, "food_briefing_app.py"))
app = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(app)

사진URL = "https://img.example/a.jpg"
집계 = {"요청": 0, "거부": 0}
_최근: list = []
_잠금 = threading.Lock()
초당허용 = 5


class _응답:
    def __init__(self, 자료, status=200, text=""):
        self._자료, self.status_code, self.text = 자료, status, text or json.dumps(자료)

    def json(self):
        return self._자료


def _제한걸림() -> bool:
    """실제 API처럼 '1초에 N건 초과하면 429'로 막는다."""
    with _잠금:
        지금 = time.time()
        _최근[:] = [t for t in _최근 if 지금 - t < 1.0]
        if len(_최근) >= 초당허용:
            집계["거부"] += 1
            return True
        _최근.append(지금)
        return False


def _가짜(url, **kw):
    if "panel3" in url:
        집계["요청"] += 1
        if _제한걸림():
            return _응답({}, 429)
        return _응답({"photos": {"photos": [{"url": 사진URL}]},
                      "kakaomap_review": {"score_set": {"average_score": 4.2, "review_count": 10}}})
    return _응답({}, 404)


app.requests.get = _가짜
실패 = []


def 확인(설명, 조건, 상세=""):
    print(f"  {'PASS' if 조건 else 'FAIL'}  {설명}" + (f": {상세}" if 상세 else ""))
    if not 조건:
        실패.append(설명)


print("\n[1] 호출 제한이 걸려도 30곳 전부 상세를 받아온다")
app._상세결과캐시.clear()
집계.update({"요청": 0, "거부": 0})
주소들 = [f"http://place.map.kakao.com/{3000 + i}" for i in range(30)]
시작 = time.time()
with app.concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
    결과들 = list(pool.map(app._카카오상세, 주소들))
걸린시간 = time.time() - 시작
사진있음 = [r for r in 결과들 if r.get("photo")]
확인("사진을 받은 가게 수", len(사진있음) == 30, f"{len(사진있음)}/30곳")
확인("별점도 함께 옴", all(r.get("rating") == 4.2 for r in 사진있음), f"{len(사진있음)}곳")
확인("제한에 걸렸는데도 성공", 집계["거부"] > 0,
     f"429 {집계['거부']}회 겪고 요청 {집계['요청']}회로 30곳 완료")
확인("지나치게 오래 걸리지 않음", 걸린시간 < 30, f"{걸린시간:.1f}초")

print("\n[2] 성공한 상세는 캐시에 남아 다시 부르지 않는다")
집계.update({"요청": 0, "거부": 0})
with app.concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
    list(pool.map(app._카카오상세, 주소들))
확인("두 번째 조회 요청 수", 집계["요청"] == 0, f"{집계['요청']}회")

print("\n[3] 진짜 없는 가게(404)는 재시도하지 않고 바로 포기한다")
app._상세결과캐시.clear()
집계.update({"요청": 0, "거부": 0})
_최근.clear()


def _없음(url, **kw):
    집계["요청"] += 1
    return _응답({}, 404)


app.requests.get = _없음
확인("빈 결과", app._카카오상세("http://place.map.kakao.com/9999") == {})
확인("재시도 없음", 집계["요청"] == 1, f"{집계['요청']}회")

print("\n[4] 검색은 상세를 기다리지 않는다 (평점 필터가 꺼져 있을 때)")
# 상세는 비공식 API라 느리다. 카드부터 그리고 /enrich 에서 채워야 첫 화면이 빨리 뜬다.
가게수 = 12


def _장소응답(url, **kw):
    if "v2/local/search/keyword.json" in url:
        질의 = (kw.get("params") or {}).get("query", "")
        if any(t in 질의 for t in ("미쉐린", "미슐랭", "블루리본", "백년가게", "노포", "흑백요리사")):
            return _응답({"documents": [], "meta": {"is_end": True}})
        docs = [{"id": f"{7000 + i}", "place_name": f"가게{i}",
                 "category_name": "음식점 > 한식 > 국수", "category_group_code": "FD6",
                 "address_name": "역삼동", "road_address_name": "테헤란로 1", "phone": "",
                 "place_url": f"http://place.map.kakao.com/{7000 + i}",
                 "x": "127.0365", "y": "37.5007", "distance": "100"} for i in range(가게수)]
        return _응답({"documents": docs, "meta": {"is_end": True}})
    if "panel3" in url:
        집계["요청"] += 1
        return _응답({"kakaomap_review": {"score_set": {"average_score": 4.5, "review_count": 3}},
                      "open_hours": {"headline": {"display_text": "영업중"}}})
    if "maps-bookmark" in url:
        return _응답({"bookmarkList": []})
    return _응답({}, 404)


app.requests.get = _장소응답
app._인증맵캐시.clear()
app._상세결과캐시.clear()
집계["요청"] = 0
목록 = app.맛집검색(127.0364, 37.5006, 1000, "all", 가게수, "none", False, "off", "all")
확인("가게 목록은 나온다", len(목록) == 가게수, f"{len(목록)}곳")
확인("상세를 부르지 않음", 집계["요청"] == 0, f"panel3 {집계['요청']}회")
확인("별점은 비어 있음", all(p["rating"] is None for p in 목록), "/enrich 가 채운다")

print("\n[5] 평점 필터를 켜면 검색 단계에서 상세를 받는다")
app._인증맵캐시.clear()
app._상세결과캐시.clear()
집계["요청"] = 0
걸러진 = app.맛집검색(127.0364, 37.5006, 1000, "all", 가게수, "none", True, "off", "all")
확인("상세를 조회함", 집계["요청"] > 0, f"panel3 {집계['요청']}회")
확인("별점이 채워짐", all(p["rating"] == 4.5 for p in 걸러진), f"{len(걸러진)}곳")

print("\n[6] 동시 호출 수가 묶여 있다")
확인("세마포어 존재", isinstance(app._카카오상세동시, type(threading.Semaphore(1))),
     f"동시 {app._카카오상세동시._value}개")

print("\n" + "=" * 46)
print("결과: " + ("전부 통과" if not 실패 else f"{len(실패)}건 실패 → {실패}"))
sys.exit(1 if 실패 else 0)
