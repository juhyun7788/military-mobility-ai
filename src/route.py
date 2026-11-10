"""기동로(출발점 → 도착점) 탐색과 경로 위 CCTV 선택.

경로는 공개 OSRM 경로 서비스(OpenStreetMap 도로망)로 구합니다.
연결이 안 되면 출발점과 도착점을 잇는 직선으로 대신합니다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .cctv_source import Cctv

OSRM_URL = "https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}"

# 공개된 도시·지역 중심 좌표 (부대 위치 아님)
PLACES = {
    "서울 (한남대교 남단)": (37.5240, 127.0190),
    "서울 서초": (37.4837, 127.0345),
    "성남 판교": (37.3947, 127.1112),
    "수원": (37.2636, 127.0286),
    "오산": (37.1499, 127.0775),
    "평택": (36.9921, 127.1129),
    "천안": (36.8151, 127.1139),
    "세종": (36.4801, 127.2890),
    "대전": (36.3504, 127.3845),
    "인천": (37.4563, 126.7052),
    "파주": (37.7600, 126.7800),
    "의정부": (37.7381, 127.0337),
    "춘천": (37.8813, 127.7298),
    "원주": (37.3422, 127.9202),
    "강릉": (37.7519, 128.8761),
}


@dataclass
class Route:
    coords: list[tuple[float, float]]  # [(위도, 경도), ...]
    distance_km: float
    duration_min: float | None  # 도로망 기준 예상 시간 (실시간 교통 미반영)
    provider: str
    cum_km: np.ndarray | None = None  # 각 점까지 누적 거리

    def __post_init__(self):
        if self.cum_km is None:
            xy = _to_xy(np.array(self.coords), self.coords[0][0])
            seg = np.hypot(*np.diff(xy, axis=0).T)
            self.cum_km = np.concatenate([[0.0], np.cumsum(seg)])

    def slice(self, from_km: float, to_km: float) -> list[tuple[float, float]]:
        """경로 중 from_km ~ to_km 구간의 좌표."""
        idx = np.where((self.cum_km >= from_km) & (self.cum_km <= to_km))[0]
        pts = [self.point_at(from_km)] + [self.coords[i] for i in idx] + [self.point_at(to_km)]
        return pts

    def point_at(self, km: float) -> tuple[float, float]:
        km = min(max(km, 0.0), float(self.cum_km[-1]))
        i = int(np.searchsorted(self.cum_km, km))
        if i == 0:
            return self.coords[0]
        a, b = self.coords[i - 1], self.coords[i]
        seg = self.cum_km[i] - self.cum_km[i - 1]
        f = (km - self.cum_km[i - 1]) / seg if seg > 0 else 0.0
        return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)


def _to_xy(latlon: np.ndarray, lat0: float) -> np.ndarray:
    """위경도를 km 단위 평면 좌표로 (짧은 거리용 근사)."""
    return np.column_stack([latlon[:, 1] * 111.32 * math.cos(math.radians(lat0)), latlon[:, 0] * 110.57])


def get_route(start: tuple[float, float], end: tuple[float, float]) -> Route:
    import requests

    try:
        url = OSRM_URL.format(lat1=start[0], lon1=start[1], lat2=end[0], lon2=end[1])
        r = requests.get(
            url,
            params={"overview": "full", "geometries": "geojson"},
            timeout=20,
            headers={"User-Agent": "military-mobility-demo/0.1 (hackathon)"},
        )
        r.raise_for_status()
        rt = r.json()["routes"][0]
        coords = [(lat, lon) for lon, lat in rt["geometry"]["coordinates"]]
        return Route(coords, rt["distance"] / 1000, rt["duration"] / 60, "OSRM 도로망 경로")
    except Exception:
        n = 50
        coords = [(start[0] + (end[0] - start[0]) * i / n, start[1] + (end[1] - start[1]) * i / n) for i in range(n + 1)]
        route = Route(coords, 0.0, None, "직선 (경로 서비스 연결 실패)")
        route.distance_km = float(route.cum_km[-1])
        return route


def get_alternatives(start: tuple[float, float], end: tuple[float, float]) -> list[Route]:
    """OSRM이 주는 대체 경로들 (첫 번째는 기본 경로와 같으므로 뺌)."""
    import requests

    try:
        url = OSRM_URL.format(lat1=start[0], lon1=start[1], lat2=end[0], lon2=end[1])
        r = requests.get(
            url,
            params={"overview": "full", "geometries": "geojson", "alternatives": "3"},
            timeout=20,
            headers={"User-Agent": "military-mobility-demo/0.1 (hackathon)"},
        )
        r.raise_for_status()
        routes = r.json()["routes"]
    except Exception:
        return []
    return [
        Route([(lat, lon) for lon, lat in rt["geometry"]["coordinates"]], rt["distance"] / 1000, rt["duration"] / 60, "OSRM 대체 경로")
        for rt in routes[1:]
    ]


def _route_via(points: list[tuple[float, float]]) -> Route | None:
    import requests

    coords = ";".join(f"{lon},{lat}" for lat, lon in points)
    try:
        r = requests.get(
            f"https://router.project-osrm.org/route/v1/driving/{coords}",
            params={"overview": "full", "geometries": "geojson"},
            timeout=20,
            headers={"User-Agent": "military-mobility-demo/0.1 (hackathon)"},
        )
        r.raise_for_status()
        rt = r.json()["routes"][0]
    except Exception:
        return None
    return Route([(lat, lon) for lon, lat in rt["geometry"]["coordinates"]], rt["distance"] / 1000, rt["duration"] / 60, "우회 경로")


def find_detour(
    route: Route, start: tuple[float, float], end: tuple[float, float],
    threat_points: list[tuple[float, float]], keep_km: float = 2.0,
) -> Route | None:
    """위협 지점을 keep_km 이상 피해 가는 우회로.

    1) OSRM 대체 경로 중 위협을 피하는 것
    2) 없으면 위협 지점 옆(경로 진행 방향의 좌우 10·15·20km)을 거쳐 가는 경로를 만들어 가장 짧은 것
    """
    if not threat_points:
        return None
    cands = [a for a in get_alternatives(start, end) if min_distance_km(a, threat_points) >= keep_km]
    if not cands:
        # 위협 지점들의 가운데를 기준으로 경로 진행 방향에 수직으로 비켜 감
        lat0 = sum(p[0] for p in threat_points) / len(threat_points)
        lon0 = sum(p[1] for p in threat_points) / len(threat_points)
        _, along = locate(route, lat0, lon0)
        a, b = route.point_at(max(along - 3, 0)), route.point_at(along + 3)
        kx = 111.32 * math.cos(math.radians(lat0))
        dx, dy = (b[1] - a[1]) * kx, (b[0] - a[0]) * 110.57
        norm = math.hypot(dx, dy) or 1.0
        px, py = -dy / norm, dx / norm  # 진행 방향의 왼쪽 수직 단위벡터 (km 좌표)
        for off in (10, 15, 20):
            for side in (1, -1):
                wp = (lat0 + side * py * off / 110.57, lon0 + side * px * off / kx)
                alt = _route_via([start, wp, end])
                if alt and min_distance_km(alt, threat_points) >= keep_km:
                    cands.append(alt)
            if cands:
                break
    return min(cands, key=lambda r: r.duration_min or r.distance_km) if cands else None


def min_distance_km(route: Route, points: list[tuple[float, float]]) -> float:
    """여러 지점 중 경로에 가장 가까운 지점까지의 거리."""
    return min((locate(route, la, lo)[0] for la, lo in points), default=float("inf"))


def locate(route: Route, lat: float, lon: float) -> tuple[float, float]:
    """(경로에서 벗어난 거리 km, 출발점부터 경로를 따라 잰 거리 km)."""
    lat0 = route.coords[0][0]
    xy = _to_xy(np.array(route.coords), lat0)
    p = _to_xy(np.array([[lat, lon]]), lat0)[0]
    a, b = xy[:-1], xy[1:]
    ab = b - a
    denom = (ab**2).sum(axis=1)
    denom[denom == 0] = 1e-12
    t = np.clip(((p - a) * ab).sum(axis=1) / denom, 0, 1)
    proj = a + ab * t[:, None]
    d = np.hypot(*(proj - p).T)
    i = int(np.argmin(d))
    along = route.cum_km[i] + t[i] * math.sqrt(denom[i])
    return float(d[i]), float(along)


def cctvs_along_route(source, route: Route, buffer_km: float = 0.3, chunk_km: float = 25.0) -> list[Cctv]:
    """경로에서 buffer_km 안에 있는 CCTV를 출발점부터 순서대로 돌려줍니다.

    긴 경로는 chunk_km 단위로 잘라 구간마다 조회합니다 (한 번에 너무 넓은 범위를 묻지 않도록).
    """
    pad_lat = buffer_km / 110.57
    pad_lon = buffer_km / (111.32 * math.cos(math.radians(route.coords[0][0])))
    total = float(route.cum_km[-1])
    found: dict[str, Cctv] = {}
    km = 0.0
    while km < total:
        pts = np.array(route.slice(km, min(km + chunk_km, total)))
        for c in source.find_in_bbox(
            pts[:, 1].min() - pad_lon, pts[:, 1].max() + pad_lon, pts[:, 0].min() - pad_lat, pts[:, 0].max() + pad_lat
        ):
            found.setdefault(c.id, c)
        km += chunk_km

    out = []
    for c in found.values():
        c.offset_km, c.along_km = locate(route, c.lat, c.lon)
        if c.offset_km <= buffer_km:
            out.append(c)
    return sorted(out, key=lambda c: c.along_km)


def offset_point(lat: float, lon: float, bearing_deg: float, dist_km: float) -> tuple[float, float]:
    """기준점에서 방위(북=0°, 시계방향)와 거리만큼 떨어진 지점."""
    b = math.radians(bearing_deg)
    return (lat + dist_km * math.cos(b) / 110.57, lon + dist_km * math.sin(b) / (111.32 * math.cos(math.radians(lat))))


def bearing_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> tuple[float, float]:
    """기준점에서 대상까지 (방위 °, 거리 km)."""
    dx = (lon2 - lon1) * 111.32 * math.cos(math.radians(lat1))
    dy = (lat2 - lat1) * 110.57
    return (math.degrees(math.atan2(dx, dy)) % 360, math.hypot(dx, dy))


_alive_cache: dict[str, tuple[float, bool]] = {}


def _same_place(d: dict) -> tuple:
    return (d["name"], round(float(d["lat"]), 4), round(float(d["lon"]), 4))


def dedupe_real(items: list[dict]) -> list[dict]:
    """같은 CCTV(이름·위치 같음)가 여러 번 저장돼 있으면 가장 최근 저장본만 (영상 주소가 더 새것)."""
    best: dict[tuple, dict] = {}
    for d in items:
        k = _same_place(d)
        if k not in best or str(d.get("saved_at", "")) > str(best[k].get("saved_at", "")):
            best[k] = d
    return list(best.values())


def alive_real(items: list[dict], ttl_s: float = 3600) -> list[dict]:
    """저장된 실제 CCTV 중 아직 재생되는 것만 (결과는 1시간 기억).

    영상 주소는 약 하루 지나면 만료되고, 해외 서버(공개 시연 서버)에서는 열리지 않을 수도 있어
    그런 CCTV는 빼고 공개 샘플 영상으로 대신합니다.
    """
    import time

    import cv2

    out = []
    for d in items:
        hit = _alive_cache.get(d["source"])
        if hit is None or time.time() - hit[0] > ttl_s:
            cap = cv2.VideoCapture(d["source"], cv2.CAP_FFMPEG,
                                   [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 6000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 6000])
            ok = bool(cap.isOpened() and cap.read()[0])
            cap.release()
            hit = (time.time(), ok)
            _alive_cache[d["source"]] = hit
        if hit[1]:
            out.append(d)
    return out


def demo_cctvs_near(lat: float, lon: float, radius_km: float) -> list[Cctv]:
    """시연 모드 지점 주변: 실제 CCTV(반경 안이고 재생될 때) + 공개 샘플 영상(기준점 주변 가상 배치)."""
    import json
    from pathlib import Path

    proj = Path(__file__).resolve().parent.parent
    data = json.loads((proj / "data" / "demo_cctvs.json").read_text(encoding="utf-8"))
    out = []
    near_real = [d for d in dedupe_real(data["real"]) if bearing_distance(lat, lon, d["lat"], d["lon"])[1] <= radius_km]
    for d in alive_real(near_real):
        c = Cctv(id=d["id"], name=d["name"], lat=d["lat"], lon=d["lon"], source=d["source"])
        c.distance_km = round(bearing_distance(lat, lon, c.lat, c.lon)[1], 2)
        out.append(c)
    samples = data.get("near_samples", []) + (data.get("near_samples_fallback", []) if len(out) < 2 else [])
    for d in samples:
        if d["dist_km"] <= radius_km:
            la, lo = offset_point(lat, lon, d["bearing"], d["dist_km"])
            out.append(Cctv(id=d["id"], name=d["name"], lat=la, lon=lo, source=str(proj / d["source"]), distance_km=d["dist_km"]))
    return sorted(out, key=lambda c: c.distance_km)


def save_demo_real(cctvs: list[Cctv]) -> int:
    """실시간 모드에서 받은 실제 CCTV(영상 주소 포함)를 시연 목록에 저장. 영상 주소는 약 하루 재생됩니다."""
    import json
    import time
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "data" / "demo_cctvs.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    by_id = {d["id"]: d for d in data["real"]}
    for c in cctvs:
        if c.source.startswith("http"):
            # 같은 CCTV를 예전 이름(id)으로 저장해 둔 것이 있으면 새 것으로 교체
            key = (c.name, round(c.lat, 4), round(c.lon, 4))
            for oid in [i for i, d in by_id.items() if i != c.id and _same_place(d) == key]:
                by_id.pop(oid)
            old = by_id.get(c.id)
            same = old is not None and old.get("source") == c.source
            by_id[c.id] = {"id": c.id, "name": c.name, "lat": c.lat, "lon": c.lon, "source": c.source,
                           # 영상 주소가 그대로면 처음 받은 시각 유지 (재생 가능 기간을 가늠하기 위함)
                           "saved_at": old.get("saved_at") if same and old.get("saved_at") else time.strftime("%Y-%m-%d %H:%M")}
    data["real"] = list(by_id.values())
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(data["real"])


def demo_cctvs_along_route(route: Route, buffer_km: float = 0.3) -> list[Cctv]:
    """시연 모드: API 없이 실제 CCTV 3개(경로 위에 있을 때) + 공개 샘플 영상(경로 비율 위치에 가상 배치)."""
    import json
    from pathlib import Path

    proj = Path(__file__).resolve().parent.parent
    data = json.loads((proj / "data" / "demo_cctvs.json").read_text(encoding="utf-8"))
    out = []
    on_route = []
    for d in dedupe_real(data["real"]):
        off, along = locate(route, d["lat"], d["lon"])
        if off <= max(buffer_km, 0.3):
            on_route.append((d, off, along))
    alive = {d["source"] for d in alive_real([d for d, _, _ in on_route])}
    for d, off, along in on_route:
        if d["source"] in alive:
            out.append(Cctv(id=d["id"], name=d["name"], lat=d["lat"], lon=d["lon"], source=d["source"],
                            offset_km=off, along_km=along))
    # 실제 CCTV가 없는 구간에만 가상 배치 샘플을 채움 (경로 길이의 15% 안에 실제 CCTV가 있으면 샘플 생략)
    total = float(route.cum_km[-1])
    for d in data["samples"]:
        km = total * d["ratio"]
        if any(abs(c.along_km - km) < total * 0.15 for c in out):
            continue
        lat, lon = route.point_at(km)
        out.append(Cctv(id=d["id"], name=d["name"], lat=lat, lon=lon, source=str(proj / d["source"]), along_km=km))
    return sorted(out, key=lambda c: c.along_km)


def pick_evenly(cctvs: list[Cctv], n: int) -> list[Cctv]:
    """경로 전체에 고르게 퍼지도록 n개를 고릅니다."""
    if len(cctvs) <= n:
        return list(cctvs)
    total = cctvs[-1].along_km
    targets = [total * (i + 0.5) / n for i in range(n)]
    chosen, used = [], set()
    for t in targets:
        best = min((c for c in cctvs if c.id not in used), key=lambda c: abs(c.along_km - t))
        used.add(best.id)
        chosen.append(best)
    return sorted(chosen, key=lambda c: c.along_km)
