"""위치 기반 CCTV 조회.

- LocalCatalogSource: 인증키 없이 쓰는 데모용 가상 CCTV 목록 (data/cctv_catalog.json)
- ItsApiSource: 국가교통정보센터 CCTV 화상자료 Open API (인증키 발급 후 사용)

get_source()는 .env에 ITS_API_KEY가 있으면 ITS API를, 없으면 데모 목록을 씁니다.
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = PROJECT_DIR / "data" / "cache"  # ITS API 응답 저장 (호출 한도 절약)
# ITS 영상 주소는 받은 뒤 약 하루 재생됨 (2026-11-09 13시 수신 → 11-10 09:32에도 재생 확인)
# → 같은 범위 조회는 하루 동안 저장본을 쓰고 API를 다시 부르지 않음
CACHE_MINUTES = 24 * 60
USAGE_FILE = CACHE_DIR / "api_usage.json"


def api_usage(month: str | None = None) -> int:
    """이번 달 ITS API 실제 호출 수 (이 프로그램에서 부른 것만)."""
    month = month or time.strftime("%Y-%m")
    try:
        return int(json.loads(USAGE_FILE.read_text(encoding="utf-8")).get(month, 0))
    except Exception:
        return 0


def _count_api_call() -> None:
    month = time.strftime("%Y-%m")
    try:
        data = json.loads(USAGE_FILE.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    data[month] = int(data.get(month, 0)) + 1
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    USAGE_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


@dataclass
class Cctv:
    id: str
    name: str
    lat: float
    lon: float
    source: str  # 로컬 영상 경로 또는 스트림 URL
    start_seconds: float = 0.0  # 분석 시작 지점 (녹화 영상용)
    distance_km: float = 0.0  # 검색 위치에서의 거리
    along_km: float = 0.0  # 기동로 출발점부터 경로를 따라 잰 거리
    offset_km: float = 0.0  # 기동로에서 벗어난 거리


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """두 좌표 사이의 거리(km)."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def bounding_box(lat: float, lon: float, radius_km: float) -> tuple[float, float, float, float]:
    """중심 좌표와 반경으로 (minX, maxX, minY, maxY) = (경도, 경도, 위도, 위도) 범위를 만듭니다."""
    dlat = radius_km / 111.0
    dlon = radius_km / (111.0 * math.cos(math.radians(lat)))
    return lon - dlon, lon + dlon, lat - dlat, lat + dlat


def _within_radius(items: list[Cctv], lat: float, lon: float, radius_km: float) -> list[Cctv]:
    out = []
    for c in items:
        c.distance_km = round(haversine_km(lat, lon, c.lat, c.lon), 2)
        if c.distance_km <= radius_km:
            out.append(c)
    return sorted(out, key=lambda c: c.distance_km)


class LocalCatalogSource:
    name = "데모용 가상 CCTV 목록 (공개 샘플 영상)"

    def __init__(self, catalog_path: Path = PROJECT_DIR / "data" / "cctv_catalog.json"):
        data = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
        self.items = [
            Cctv(
                id=d["id"],
                name=d["name"],
                lat=d["lat"],
                lon=d["lon"],
                source=str(PROJECT_DIR / d["source"]),
                start_seconds=float(d.get("start_seconds", 0)),
            )
            for d in data["cctvs"]
        ]

    def find_nearby(self, lat: float, lon: float, radius_km: float) -> list[Cctv]:
        return _within_radius([replace(c) for c in self.items], lat, lon, radius_km)

    def find_in_bbox(self, min_x: float, max_x: float, min_y: float, max_y: float) -> list[Cctv]:
        return [replace(c) for c in self.items if min_x <= c.lon <= max_x and min_y <= c.lat <= max_y]


class ItsApiSource:
    """국가교통정보센터 CCTV 화상자료 API.

    요청 변수는 its.go.kr 'CCTV 화상자료' 페이지 안내를 따릅니다 (2026-11-09 실제 키로 확인).
    """

    name = "국가교통정보센터 CCTV API"
    url = "https://openapi.its.go.kr:9443/cctvInfo"

    def __init__(self, api_key: str, road_types: tuple[str, ...] = ("ex",), cctv_type: int = 4):
        self.stale = False  # API 실패로 오래된 저장본을 쓴 적이 있으면 True
        self.api_key = api_key
        self.road_types = road_types  # ex: 고속도로, its: 국도
        self.cctv_type = cctv_type  # 4: 실시간 스트리밍(HLS, HTTPS)

    def _query(self, road_type: str, min_x: float, max_x: float, min_y: float, max_y: float) -> list[Cctv]:
        """API 결과를 파일에 저장해 두고 재사용합니다 (월간 호출 한도 절약).

        - 저장한 지 CACHE_MINUTES 안이면 API를 부르지 않고 저장본을 씀
        - API가 실패하면(한도 초과 등) 오래된 저장본이라도 씀 (영상 주소가 만료됐을 수 있음)
        """
        bbox = tuple(round(v, 3) for v in (min_x, max_x, min_y, max_y))
        cache_file = CACHE_DIR / f"{road_type}_{'_'.join(f'{v:.3f}' for v in bbox)}.json"
        cached = None
        if cache_file.exists():
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            if time.time() - cached["saved_at"] < CACHE_MINUTES * 60:
                return [Cctv(**c) for c in cached["items"]]
        try:
            items = self._fetch(road_type, *bbox)
        except RuntimeError:
            if cached is not None:
                self.stale = True
                return [Cctv(**c) for c in cached["items"]]
            raise
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(
            json.dumps({"saved_at": time.time(), "items": [asdict(c) for c in items]}, ensure_ascii=False),
            encoding="utf-8",
        )
        return items

    def _fetch(self, road_type: str, min_x: float, max_x: float, min_y: float, max_y: float) -> list[Cctv]:
        import requests

        params = {
            "apiKey": self.api_key,
            "type": road_type,
            "cctvType": self.cctv_type,
            "minX": min_x,
            "maxX": max_x,
            "minY": min_y,
            "maxY": max_y,
            "getType": "json",
        }
        _count_api_call()
        try:
            resp = requests.get(self.url, params=params, timeout=30)
        except Exception as e:
            # 오류 메시지에 인증키가 든 URL이 섞이지 않도록 종류만 알림
            raise RuntimeError(f"ITS CCTV API 연결 실패 ({type(e).__name__})") from None
        try:
            body = resp.json()
        except ValueError:
            raise RuntimeError(f"ITS CCTV API 응답 오류 (HTTP {resp.status_code})") from None
        header = body.get("header") or {}
        code = str(header.get("resultCode", ""))
        if code == "4001":
            raise RuntimeError(
                "ITS CCTV API 월간 호출 한도 초과. its.go.kr 로그인 → 인증키 상세정보에서 월 호출 한도를 늘려주세요."
            )
        if resp.status_code != 200 or (code and code not in ("0", "00", "200", "SUCCESS")):
            msg = str(header.get("resultMsg", "")).replace(self.api_key, "***")[:100]
            raise RuntimeError(f"ITS CCTV API 오류 (HTTP {resp.status_code}, 코드 {code or '-'}) {msg}")
        rows = body.get("response", body).get("data", [])
        if isinstance(rows, dict):
            rows = [rows]
        return [
            Cctv(
                id=f"{r.get('cctvname', '')}@{r['coordy']},{r['coordx']}",
                name=r.get("cctvname", "이름 없음"),
                lat=float(r["coordy"]),
                lon=float(r["coordx"]),
                source=r["cctvurl"],
            )
            for r in rows
        ]

    def find_in_bbox(self, min_x: float, max_x: float, min_y: float, max_y: float) -> list[Cctv]:
        seen, out = set(), []
        for road_type in self.road_types:
            for c in self._query(road_type, min_x, max_x, min_y, max_y):
                if c.id not in seen:
                    seen.add(c.id)
                    out.append(c)
        return out

    def find_nearby(self, lat: float, lon: float, radius_km: float) -> list[Cctv]:
        # 위치가 조금씩 바뀔 때마다 API를 부르지 않도록, 0.05도 격자 칸 단위로 넉넉히 조회해 저장본을 재사용
        cell_lat, cell_lon = round(lat / 0.05) * 0.05, round(lon / 0.05) * 0.05
        pad = 0.05 / 2 + radius_km / 85.0
        items = self.find_in_bbox(cell_lon - pad, cell_lon + pad, cell_lat - pad, cell_lat + pad)
        return _within_radius(items, lat, lon, radius_km)


def get_source():
    try:
        from dotenv import load_dotenv

        load_dotenv(PROJECT_DIR / ".env")
    except ImportError:
        pass
    key = os.getenv("ITS_API_KEY", "").strip()
    if key:
        types = tuple(t.strip() for t in os.getenv("ITS_ROAD_TYPE", "ex,its").split(",") if t.strip())
        return ItsApiSource(key, road_types=types or ("ex",))
    return LocalCatalogSource()
