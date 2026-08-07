# 원본 파이썬의 순수 로직 결과를 JSON 으로 뽑아 TS 이식본과 대조한다.
import json, os, sys
os.environ["KAKAO_REST_API_KEY"] = "dummy"          # 없으면 import 시 sys.exit
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import food_briefing_app as A

CATS = [
    "음식점 > 한식 > 육류,고기 > 삼겹살",
    "음식점 > 한식 > 국밥",
    "음식점 > 술집 > 요리주점",
    "음식점 > 한식 > 육류,고기 > 갈비탕",
    "음식점 > 카페 > 테마카페",
    "음식점 > 카페 > 커피전문점",
    "음식점 > 간식 > 제과,베이커리",
    "음식점 > 카페 > 테마카페 > 룸카페",
    "음식점 > 일식 > 초밥,롤",
    "음식점 > 한식 > 해물,생선 > 회",
    "음식점 > 치킨",
    "음식점 > 분식",
    "",
]
NAMES = ["김밥천국", "비트포비아 강남", "스터디카페 리더스", "스타벅스 역삼점", "고양이다방"]

out = {"시간대적합": [], "이름정규화": [], "대략거리m": [], "태그제거": [], "저장배지": [],
       "인증배지찾기": [], "내저장_매칭": []}

for cat in CATS:
    for name in NAMES:
        d = {"category_name": cat, "place_name": name}
        for 시간대 in ("all", "lunch", "dinner", "cafe"):
            out["시간대적합"].append([cat, name, 시간대, A._시간대적합(d, 시간대)])

for s in ["스타벅스 역삼점", "Cafe-Onion (성수)", "본가★설렁탕", "  띄어 쓰기  ", "ABC123가나다", ""]:
    out["이름정규화"].append([s, A._이름정규화(s)])

for a in [(37.5, 127.0), (37.4979, 127.0276)]:
    for b in [(37.5, 127.0), (37.5009, 127.0), (37.5, 127.0011), (37.6, 127.1)]:
        out["대략거리m"].append([list(a), list(b), round(A._대략거리m(a[0], a[1], b[0], b[1]), 6)])

for s in ['<b>맛집</b> &quot;최고&quot; &amp; <i>추천</i>', "&lt;태그&gt;", "평범한 텍스트"]:
    out["태그제거"].append([s, A._태그제거(s)])

for f in ["가본곳", "가볼곳", "카페 리스트", "디저트", "내 맛집", "가본 카페"]:
    out["저장배지"].append([f, A._저장배지(f)])

인증정보 = {"미쉐린식당": ["미쉐린"], "블루리본집": ["블루리본"], "가": ["백년가게"]}
for n in ["미쉐린식당", "미쉐린식당 강남점", "미쉐린", "블루리본집", "없는집", "가나"]:
    out["인증배지찾기"].append([n, A._인증배지찾기(n, 인증정보)])

저장목록 = [
    {"name": "김밥천국", "lat": 37.5, "lng": 127.0, "folder": "가본곳"},
    {"name": "김밥천국 역삼점", "lat": 37.5, "lng": 127.0, "folder": "가볼곳"},
    {"name": "먼가게", "lat": 37.6, "lng": 127.1, "folder": "가본곳"},
    {"name": "카페온리", "lat": 37.5, "lng": 127.0, "folder": "카페"},
]
for p in [
    {"name": "김밥천국", "lat": 37.5, "lng": 127.0},
    {"name": "김밥천국 본점", "lat": 37.5, "lng": 127.0},
    {"name": "먼가게", "lat": 37.5, "lng": 127.0},
    {"name": "카페온리", "lat": 37.5, "lng": 127.0},
    {"name": "무관한집", "lat": 37.5, "lng": 127.0},
]:
    out["내저장_매칭"].append([p["name"], A.내저장_매칭(p, 저장목록)])

print(json.dumps(out, ensure_ascii=False, indent=1))
