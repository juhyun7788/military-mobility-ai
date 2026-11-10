"""명령줄 실행: 위치 주변 CCTV를 찾아 분석 결과를 출력합니다.

예) .venv\\Scripts\\python.exe run_cli.py --lat 37.4842 --lon 127.0347 --radius 2
"""

import argparse
import json
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

from src.analyzer import analyze_video
from src.cctv_source import get_source


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lat", type=float, default=37.4842)
    ap.add_argument("--lon", type=float, default=127.0347)
    ap.add_argument("--radius", type=float, default=2.0, help="검색 반경(km)")
    ap.add_argument("--seconds", type=float, default=15.0, help="CCTV당 분석 시간(초)")
    args = ap.parse_args()

    src = get_source()
    cctvs = src.find_nearby(args.lat, args.lon, args.radius)
    print(f"[{src.name}] 반경 {args.radius}km 안의 CCTV {len(cctvs)}개")
    for c in cctvs:
        t0 = time.time()
        r = analyze_video(c.source, max_seconds=args.seconds, start_seconds=c.start_seconds)
        print(f"\n=== {c.name} ({c.distance_km}km) — {r.frames_analyzed}프레임, {time.time() - t0:.1f}초 소요")
        for k in ("traffic", "incident", "weather", "crowd"):
            print(f"  {k}: {json.dumps(getattr(r, k), ensure_ascii=False)}")


if __name__ == "__main__":
    main()
