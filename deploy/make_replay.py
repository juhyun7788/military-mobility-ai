"""녹화 시연 데이터 만들기: 지금 시연 모드로 실제 분석을 1번씩 돌려 결과와 사진을 web/replay/에 저장합니다.

웹페이지는 분석 서버(노트북)가 꺼져 있을 때 "▶ 녹화된 시연 보기"로 이 결과를 그대로 재생합니다.
(서버·API 호출 없이 Vercel만으로 동작)

실행 (cctv_demo 폴더에서):  .venv\\Scripts\\python.exe deploy\\make_replay.py
- 시연 모드라 ITS API 호출 없음, Supabase 분석 기록에도 남기지 않음
- 다시 실행하면 최신 분석으로 교체됩니다
"""

import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
PROJ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJ))

import server.api as A  # noqa: E402
from server import history  # noqa: E402

history.save = lambda row: None  # 녹화용 분석은 Supabase 기록에 남기지 않음

OUT = PROJ / "web" / "replay"


class _Req:  # 공개 방문자처럼 보이는 가짜 요청 (실시간 잠금 상태의 설정을 얻기 위함)
    headers = {"host": "replay"}
    client = None


def copy_images(obj, jid: str, prefix: str):
    """결과 안의 /media/<jid>/파일 경로를 replay/<prefix>_파일로 바꾸고 사진을 복사."""
    if isinstance(obj, dict):
        return {k: copy_images(v, jid, prefix) for k, v in obj.items()}
    if isinstance(obj, list):
        return [copy_images(v, jid, prefix) for v in obj]
    if isinstance(obj, str) and obj.startswith(f"/media/{jid}/"):
        name = f"{prefix}_{obj.rsplit('/', 1)[1]}"
        shutil.copy2(A.RESULTS / jid / obj.rsplit("/", 1)[1], OUT / name)
        return f"replay/{name}"
    return obj


def run(fn, req, prefix: str):
    jid = f"replay_{prefix}_{int(time.time())}"
    t = time.time()
    res = A.clean(fn(jid, req, lambda p, m: print(f"  {p * 100:5.1f}% {m}")))
    print(f"  완료 {time.time() - t:.0f}초")
    return copy_images(res, jid, prefix)


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    cfg = A.clean(A.config(_Req()))
    cfg.update(has_key=False, live_locked=True, admin_available=False, admin=False, api_usage=0, api_today=0)

    # 1) 기동로: 서울 → 천안, 시연용 ISR 2건
    start_name, end_name = "서울 (한남대교 남단)", "천안"
    isr = cfg["demo_isr"]["items"]
    rreq = A.RouteReq(start=list(A.PLACES[start_name]), end=list(A.PLACES[end_name]), start_name=start_name,
                      end_name=end_name, buffer_km=0.3, max_cctvs=6, seconds=10, demo=True, isr=isr)
    print("기동로 분석:", start_name, "→", end_name)
    route_info = A.clean(A.route_info(rreq, _Req()))
    route_result = run(A.run_route_job, rreq, "route")

    # 2) 지점 주변: 서울 서초 반경 3km, 시연용 ISR 2건
    place = "서울 서초"
    lat, lon = A.PLACES[place]
    near_isr = cfg["demo_isr"]["near"]
    areq = A.AreaReq(lat=lat, lon=lon, radius=3.0, place=place, seconds=10, demo=True, isr=near_isr)
    print("지점 주변 분석:", place)
    nearby = A.clean(A.nearby(areq, _Req()))
    area_result = run(A.run_area_job, areq, "area")

    bundle = {
        "recorded_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "config": cfg,
        "route": {"start": start_name, "end": end_name, "buffer_km": 0.3, "max_cctvs": 6,
                  "isr": isr, "info": route_info, "result": route_result},
        "area": {"place": place, "lat": lat, "lon": lon, "radius": 3.0,
                 "isr": near_isr, "cctvs": nearby["cctvs"], "result": area_result},
    }
    (OUT / "replay.json").write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")
    size = sum(p.stat().st_size for p in OUT.iterdir()) / 1024 / 1024
    print(f"저장: web/replay/ ({len(list(OUT.iterdir()))}개 파일, {size:.1f}MB)")
    print("기동로 판단:", route_result["verdict"]["text"])
    print("지점 판단:", area_result["assessment"]["text"])


if __name__ == "__main__":
    main()
