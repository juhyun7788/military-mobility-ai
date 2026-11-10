"""지능형 기동지원 군사상황 정보판단 프로그램 — 웹 API 서버 (FastAPI).

웹페이지(web/)를 함께 제공하므로, 이 서버 하나만 켜면 브라우저에서 바로 씁니다.
실행 (cctv_demo 폴더에서):  .venv\\Scripts\\python.exe -m uvicorn server.api:app --port 8000
접속: http://localhost:8000

배포 구조 (나중에):
- web/      → Vercel (정적 웹페이지). web/config.js의 API_BASE를 분석 서버 주소로 바꿈
- server/   → AI 분석 서버 (YOLO·영상 처리라 Vercel 서버리스에는 맞지 않음, PC·클라우드 서버에서 실행)
- 결과·보고서 저장 → Supabase (아직 연동 안 함)
"""

from __future__ import annotations

import json
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

PROJ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJ))

from server import history  # noqa: E402
from src.analyzer import analyze_video  # noqa: E402
from src.cctv_source import LocalCatalogSource, api_usage, get_source  # noqa: E402
from src.report import (  # noqa: E402
    LEVELS, MOBILITY, IsrInput, area_assessment, build_segments, make_area_report, make_report, overall, traffic_level,
)
from src.route import (  # noqa: E402
    PLACES, bearing_distance, cctvs_along_route, demo_cctvs_along_route, demo_cctvs_near, find_detour, get_route,
    offset_point, pick_evenly, save_demo_real,
)

DATA = PROJ / "data"
WEB = PROJ / "web"
RESULTS = DATA / "results"
UPLOADS = DATA / "uploads"
RESULTS.mkdir(parents=True, exist_ok=True)
UPLOADS.mkdir(parents=True, exist_ok=True)
API_LIMIT = 5000
ISR_EXT = {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".webm", ".avi", ".mov", ".ogv"}

# 공개 시연 서버(예: Hugging Face Spaces)에서는 PUBLIC_DEMO=1로 실행
# - 실시간 모드(ITS API 호출) 잠금: 방문자가 월 5,000건 한도를 쓰지 못하게. ALLOW_LIVE=1이면 허용
# - 업로드 크기 제한, 하루 지난 결과·업로드 파일 자동 삭제
import os  # noqa: E402

PUBLIC_DEMO = os.getenv("PUBLIC_DEMO", "0") == "1"
LIVE_LOCKED = PUBLIC_DEMO and os.getenv("ALLOW_LIVE", "0") != "1"
MAX_UPLOAD_MB = 30 if PUBLIC_DEMO else 200
KEEP_HOURS = 24

app = FastAPI(title="지능형 기동지원 군사상황 정보판단 API")
# 나중에 Vercel 웹페이지(다른 주소)에서 부를 수 있도록 허용
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

SOURCE = get_source()
HAS_KEY = not isinstance(SOURCE, LocalCatalogSource)
ANALYSIS_LOCK = threading.Lock()  # AI 모델은 한 번에 하나의 분석만
JOBS: dict[str, dict] = {}
_route_cache: dict[tuple, object] = {}
_cctv_cache: dict[tuple, tuple[float, list]] = {}


# ------------------------------------------------------------------ 공통 도구
def clean(o):
    """numpy 값 등을 JSON으로 보낼 수 있게 바꿈."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items() if not str(k).startswith("_")}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    return o


def resolve_source(key: str) -> str:
    """웹에서 받은 ISR 파일 이름을 실제 경로로 (data/isr, data/uploads 안만 허용)."""
    p = (DATA / key).resolve()
    if not any(p.is_relative_to((DATA / d).resolve()) for d in ("isr", "uploads")) or not p.exists():
        raise HTTPException(400, f"ISR 파일을 찾을 수 없습니다: {key}")
    return str(p)


def route_for(start, end):
    key = (tuple(start), tuple(end))
    if key not in _route_cache:
        _route_cache[key] = get_route(tuple(start), tuple(end))
    return _route_cache[key]


def route_cctvs(start, end, buffer_km: float, demo: bool) -> list:
    route = route_for(start, end)
    if demo:
        return demo_cctvs_along_route(route, buffer_km)
    key = (tuple(start), tuple(end), buffer_km)
    hit = _cctv_cache.get(key)
    if hit and time.time() - hit[0] < 86400:
        return hit[1]
    items = cctvs_along_route(SOURCE, route, buffer_km)  # ITS API 호출 (파일 저장본이 있으면 재사용)
    _cctv_cache[key] = (time.time(), items)
    return items


def near_cctvs(lat: float, lon: float, radius: float, demo: bool) -> list:
    items = demo_cctvs_near(lat, lon, radius) if demo else SOURCE.find_nearby(lat, lon, radius)
    for c in items:
        c.distance_km = round(bearing_distance(lat, lon, c.lat, c.lon)[1], 2)
    return items


def save_img(rgb: np.ndarray | None, job: str, name: str) -> str | None:
    if rgb is None:
        return None
    d = RESULTS / job
    d.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(d / name), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 85])
    return f"/media/{job}/{name}"


def cctv_json(c, r=None, err=None, img=None) -> dict:
    out = {"id": c.id, "name": c.name, "lat": c.lat, "lon": c.lon, "along_km": round(c.along_km, 2),
           "distance_km": round(c.distance_km, 2), "error": err, "image": img}
    if r is not None:
        lv = traffic_level(r)
        out.update(level=lv, label=LEVELS[lv][0], color=LEVELS[lv][1], traffic=r.traffic,
                   incident=r.incident["판단"], weather=r.weather["판단"], crowd=r.crowd["판단"],
                   timeline=r.timeline, seconds=r.seconds_analyzed)
    return out


def threat_json(t, img=None) -> dict:
    return {"level": t.level, "level_name": t.level_name, "summary": t.summary(), "items": t.items, "image": img}


def is_public(request: Request | None) -> bool:
    """공개 주소(터널 등)로 들어온 요청인지. 노트북에서 localhost로 접속한 것만 '내부'로 봄."""
    if PUBLIC_DEMO:
        return True
    if request is None:
        return False
    host = request.headers.get("host", "").split(":")[0].lower()
    forwarded = request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for")
    return bool(forwarded) or host not in ("localhost", "127.0.0.1", "::1")


def live_locked(request: Request | None) -> bool:
    return is_public(request) and os.getenv("ALLOW_LIVE", "0") != "1"


def check_mode(demo: bool, request: Request | None = None) -> None:
    if demo:
        return
    if live_locked(request):
        raise HTTPException(403, "공개 시연 서버에서는 실시간 모드(ITS API)가 잠겨 있습니다. 시연 모드로 이용하세요.")
    if not HAS_KEY:
        raise HTTPException(400, "ITS 인증키가 없어 실시간 모드를 쓸 수 없습니다")


def cleanup_old_files() -> None:
    """하루 지난 분석 결과·업로드 파일 삭제 (공개 서버 저장공간 관리)."""
    import shutil

    limit = time.time() - KEEP_HOURS * 3600
    for p in RESULTS.iterdir():
        if p.is_dir() and p.stat().st_mtime < limit:
            shutil.rmtree(p, ignore_errors=True)
    for p in UPLOADS.iterdir():
        if p.is_file() and p.stat().st_mtime < limit:
            p.unlink(missing_ok=True)
    for jid in [j for j in JOBS if j[:14] < time.strftime("%Y%m%d%H%M%S", time.localtime(limit))]:
        JOBS.pop(jid, None)


# ------------------------------------------------------------------ 작업(분석) 관리
def start_job(fn, payload) -> str:
    cleanup_old_files()
    jid = time.strftime("%Y%m%d%H%M%S") + "_" + uuid.uuid4().hex[:6]
    JOBS[jid] = {"status": "queued", "progress": 0.0, "message": "대기 중", "result": None, "error": None}

    def progress(p, msg):
        JOBS[jid].update(progress=round(p, 3), message=msg)

    def run():
        with ANALYSIS_LOCK:
            JOBS[jid]["status"] = "running"
            try:
                res = fn(jid, payload, progress)
                JOBS[jid].update(status="done", progress=1.0, message="분석 완료", result=clean(res))
            except Exception as e:  # 오류 내용을 화면에 보여줌
                JOBS[jid].update(status="error", error=str(e), message="분석 실패")

    threading.Thread(target=run, daemon=True).start()
    return jid


# ------------------------------------------------------------------ 요청 형식
class IsrItem(BaseModel):
    id: str
    name: str
    source: str  # "isr/파일" 또는 "uploads/파일"
    ratio: float | None = None  # 기동로 비율 위치 (시연용)
    km: float | None = None  # 기동로 km 위치
    bearing: float | None = None  # 지점 기준 방위 (시연용)
    dist_km: float | None = None
    lat: float | None = None  # 지점 주변 고정 좌표 (업로드)
    lon: float | None = None


class RouteReq(BaseModel):
    start: list[float]
    end: list[float]
    start_name: str = "출발점"
    end_name: str = "도착점"
    buffer_km: float = 0.3
    max_cctvs: int = 6
    seconds: float = 10
    demo: bool = True
    isr: list[IsrItem] = []


class AreaReq(BaseModel):
    lat: float
    lon: float
    radius: float = 3.0
    place: str = "지정 지점"
    seconds: float = 10
    demo: bool = True
    isr: list[IsrItem] = []


def demo_isr_json() -> dict:
    d = json.loads((DATA / "demo_isr.json").read_text(encoding="utf-8"))
    for group in ("items", "near", "extra"):
        for it in d.get(group, []):
            it["source"] = it["source"].replace("data/", "", 1)  # "isr/xxx.jpg" 형태로
    return d


# ------------------------------------------------------------------ API
@app.get("/api/config")
def config(request: Request):
    saved = json.loads((DATA / "demo_cctvs.json").read_text(encoding="utf-8"))["real"]
    return {
        "has_key": HAS_KEY, "demo_default": True, "api_usage": api_usage(), "api_limit": API_LIMIT,
        "live_locked": live_locked(request), "public_demo": is_public(request), "max_upload_mb": 30 if is_public(request) else 200,
        "history_enabled": history.ENABLED,
        "places": PLACES, "demo_isr": demo_isr_json(),
        "saved_real": [{"name": s["name"], "saved_at": s.get("saved_at", "?")} for s in saved],
        "mobility": MOBILITY, "levels": LEVELS,
    }


@app.post("/api/route")
def route_info(req: RouteReq, request: Request):
    check_mode(req.demo, request)
    route = route_for(req.start, req.end)
    error = None
    try:
        on_route = route_cctvs(req.start, req.end, req.buffer_km, req.demo)
    except Exception as e:
        on_route, error = [], str(e)
    picks = {c.id for c in pick_evenly(on_route, req.max_cctvs)}
    return clean({
        "route": {"coords": route.coords, "distance_km": route.distance_km, "duration_min": route.duration_min,
                  "provider": route.provider, "total_km": float(route.cum_km[-1])},
        "cctvs": [dict(cctv_json(c), picked=c.id in picks) for c in on_route],
        "error": error, "api_usage": api_usage(),
    })


@app.post("/api/nearby")
def nearby(req: AreaReq, request: Request):
    check_mode(req.demo, request)
    error = None
    try:
        items = near_cctvs(req.lat, req.lon, req.radius, req.demo)
    except Exception as e:
        items, error = [], str(e)
    return clean({"cctvs": [dict(cctv_json(c), bearing=round(bearing_distance(req.lat, req.lon, c.lat, c.lon)[0]))
                            for c in items], "error": error, "api_usage": api_usage()})


@app.post("/api/upload")
async def upload(request: Request, file: UploadFile = File(...)):
    max_mb = 30 if is_public(request) else 200
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ISR_EXT:
        raise HTTPException(400, f"지원하지 않는 형식입니다: {ext}")
    name = f"{uuid.uuid4().hex[:8]}{ext}"
    data = await file.read()
    if len(data) > max_mb * 1024 * 1024:
        raise HTTPException(400, f"파일이 너무 큽니다 (최대 {max_mb}MB)")
    (UPLOADS / name).write_bytes(data)
    return {"source": f"uploads/{name}", "name": f"[업로드] {file.filename}", "id": name.split('.')[0]}


def run_route_job(jid: str, req: RouteReq, progress):
    from src.threat import analyze_isr

    route = route_for(req.start, req.end)
    total = float(route.cum_km[-1])
    on_route = route_cctvs(req.start, req.end, req.buffer_km, req.demo)
    picks = pick_evenly(on_route, req.max_cctvs)
    isrs = []
    for it in req.isr:
        km = total * it.ratio if it.ratio is not None else min(float(it.km or 0), total)
        lat, lon = route.point_at(km)
        isrs.append(IsrInput(it.id, it.name, resolve_source(it.source), km, lat, lon))
    n = max(len(picks) + len(isrs), 1)
    analyzed, isr_results, cctv_imgs, isr_imgs = [], [], {}, {}
    for k, c in enumerate(picks):
        progress(k / n, f"📹 {c.name} 교통 분석 중 ({k + 1}/{n})")
        try:
            r = analyze_video(c.source, max_seconds=req.seconds, start_seconds=c.start_seconds)
            analyzed.append((c, r, None))
            cctv_imgs[c.id] = save_img(r.snapshot, jid, f"cctv_{k}.jpg")
        except Exception as e:
            analyzed.append((c, None, str(e)))
    for k, i in enumerate(isrs):
        progress((len(picks) + k) / n, f"🛰️ {i.name} 위협 분석 중 ({len(picks) + k + 1}/{n})")
        try:
            t = analyze_isr(i.source, i.name)
            isr_results.append((i, t))
            isr_imgs[i.id] = save_img(t.snapshot, jid, f"isr_{k}.jpg")
        except Exception as e:
            progress((len(picks) + k) / n, f"{i.name}: {e}")
    progress(0.97, "기동 가능성 판단·우회로 탐색 중")
    segs = build_segments(route, analyzed, isr_results)
    verdict, color, worst = overall(segs)
    block = [(i.lat, i.lon) for s in segs if s.mobility == 3 for i, t in s.threats if t.level == 3]
    block += [(s.cctv.lat, s.cctv.lon) for s in segs if s.level == 4 and s.cctv]
    det = find_detour(route, tuple(req.start), tuple(req.end), block) if block else None
    alt = None
    if det:
        alt = {"distance_km": det.distance_km, "duration_min": det.duration_min, "avoids": True,
               "delta_min": (det.duration_min - route.duration_min) if route.duration_min else None, "coords": det.coords}
    now = datetime.now()
    report = make_report(route, req.start_name, req.end_name, len(on_route), segs, now, alternative=alt)
    if req.demo:
        report += "\n   (시연 모드: 일부 CCTV·ISR 영상은 공개 자료를 기동로 위에 가상 배치한 결과입니다.)"
    hist_err = history.save(clean({
        "kind": "route", "title": f"{req.start_name} → {req.end_name}", "verdict_text": verdict, "mobility": worst,
        "threat_level": max((s.threat_level for s in segs), default=0), "demo": req.demo, "report": report,
        "summary": {"segments": [{"from_km": round(s.from_km, 1), "to_km": round(s.to_km, 1), "mobility": s.mobility,
                                  "traffic": s.label, "threat": s.threat_level} for s in segs],
                    "detour": {"distance_km": round(det.distance_km, 1), "duration_min": round(det.duration_min or 0)} if det else None},
    }))
    return {
        "time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "verdict": {"text": verdict, "color": color, "mobility": worst},
        "segments": [
            {"from_km": s.from_km, "to_km": s.to_km, "mobility": s.mobility, "mobility_label": s.mobility_label,
             "mobility_color": s.mobility_color, "traffic_level": s.level, "traffic_label": s.label,
             "threat_level": s.threat_level, "weather": s.weather_warning, "coords": route.slice(s.from_km, s.to_km),
             "cctv": cctv_json(s.cctv, s.result, s.error, cctv_imgs.get(s.cctv.id)) if s.cctv else None,
             "threats": [dict(threat_json(t, isr_imgs.get(i.id)), id=i.id, name=i.name, lat=i.lat, lon=i.lon,
                              along_km=i.along_km) for i, t in s.threats]}
            for s in segs
        ],
        "detour": alt,
        "report": report,
        "history_saved": history.ENABLED and hist_err is None,
        "history_error": hist_err,
    }


@app.post("/api/jobs/route")
def job_route(req: RouteReq, request: Request):
    check_mode(req.demo, request)
    return {"job_id": start_job(run_route_job, req)}


def run_area_job(jid: str, req: AreaReq, progress):
    from src.threat import analyze_isr

    cctvs = near_cctvs(req.lat, req.lon, req.radius, req.demo)
    isrs = []
    for it in req.isr:
        if it.lat is not None and it.lon is not None:
            la, lo = it.lat, it.lon
        else:
            la, lo = offset_point(req.lat, req.lon, it.bearing or 0, it.dist_km or 0)
        brg, dist = bearing_distance(req.lat, req.lon, la, lo)
        if dist <= req.radius:
            isrs.append({"id": it.id, "name": it.name, "source": resolve_source(it.source), "lat": la, "lon": lo,
                         "bearing": brg, "dist_km": dist})
    n = max(len(cctvs) + len(isrs), 1)
    cres, ires, out_c, out_i = [], [], [], []
    for k, c in enumerate(cctvs):
        progress(k / n, f"📹 {c.name} 교통 분석 중 ({k + 1}/{n})")
        try:
            r = analyze_video(c.source, max_seconds=req.seconds, start_seconds=c.start_seconds)
            cres.append((c, r, None))
            out_c.append(dict(cctv_json(c, r, None, save_img(r.snapshot, jid, f"cctv_{k}.jpg")),
                              bearing=round(bearing_distance(req.lat, req.lon, c.lat, c.lon)[0])))
        except Exception as e:
            cres.append((c, None, str(e)))
            out_c.append(cctv_json(c, None, str(e)))
    for k, i in enumerate(isrs):
        progress((len(cctvs) + k) / n, f"🛰️ {i['name']} 위협 분석 중 ({len(cctvs) + k + 1}/{n})")
        try:
            t = analyze_isr(i["source"], i["name"])
            ires.append((i, t))
            out_i.append(dict(threat_json(t, save_img(t.snapshot, jid, f"isr_{k}.jpg")),
                              **{k2: v for k2, v in i.items() if k2 != "source"}))
        except Exception as e:
            progress((len(cctvs) + k) / n, f"{i['name']}: {e}")
    a = area_assessment(cres, ires)
    now = datetime.now()
    report = make_area_report(req.place, req.lat, req.lon, req.radius, cres, ires, now)
    if req.demo:
        report += "\n   (시연 모드: 일부 CCTV·ISR 영상은 공개 자료를 기준 지점 주변에 가상 배치한 결과입니다.)"
    hist_err = history.save(clean({
        "kind": "area", "title": f"{req.place} 반경 {req.radius:g}km", "verdict_text": a["text"], "mobility": a["mobility"],
        "threat_level": a["threat"], "demo": req.demo, "report": report,
        "summary": {"lat": req.lat, "lon": req.lon, "radius_km": req.radius, "traffic": a["traffic"],
                    "isr": [{"bearing": round(i["bearing"]), "dist_km": round(i["dist_km"], 1), "level": t.level} for i, t in ires]},
    }))
    return {
        "time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "assessment": {k: v for k, v in a.items() if k != "nearest"},
        "cctvs": out_c, "isr": out_i, "report": report,
        "history_saved": history.ENABLED and hist_err is None, "history_error": hist_err,
    }


@app.post("/api/jobs/area")
def job_area(req: AreaReq, request: Request):
    check_mode(req.demo, request)
    return {"job_id": start_job(run_area_job, req)}


@app.get("/api/history")
def history_list():
    """최근 분석 기록 (Supabase). 연결 안 돼 있으면 enabled=false."""
    if not history.ENABLED:
        return {"enabled": False, "items": []}
    try:
        return {"enabled": True, "items": history.recent()}
    except Exception as e:
        return {"enabled": True, "items": [], "error": f"기록을 불러오지 못했습니다 ({type(e).__name__})"}


@app.get("/api/history/{rid}")
def history_item(rid: int):
    if not history.ENABLED:
        raise HTTPException(404, "분석 기록 저장소(Supabase)가 연결돼 있지 않습니다")
    row = history.get(rid)
    if not row:
        raise HTTPException(404, "기록을 찾을 수 없습니다")
    return row


@app.get("/api/jobs/{jid}")
def job_status(jid: str):
    if jid not in JOBS:
        raise HTTPException(404, "작업을 찾을 수 없습니다")
    return JOBS[jid]


@app.post("/api/save_demo")
def save_demo(req: RouteReq, request: Request):
    if is_public(request):
        raise HTTPException(403, "시연 목록 저장은 노트북(localhost)에서만 할 수 있습니다")
    """실시간 모드에서 받은 경로 CCTV를 시연 목록에 저장 (이미 받은 목록 사용, 추가 API 호출 없음)."""
    if req.demo:
        raise HTTPException(400, "실시간 모드에서만 저장할 수 있습니다")
    picks = pick_evenly(route_cctvs(req.start, req.end, req.buffer_km, False), req.max_cctvs)
    return {"saved_total": save_demo_real(picks), "added": len(picks)}


@app.get("/api/check_saved")
def check_saved():
    """저장된 실제 CCTV 영상 주소가 아직 재생되는지 (API 호출 없음)."""
    saved = json.loads((DATA / "demo_cctvs.json").read_text(encoding="utf-8"))["real"]
    out = []
    for s in saved:
        cap = cv2.VideoCapture(s["source"], cv2.CAP_FFMPEG,
                               [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 8000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 8000])
        ok = bool(cap.isOpened() and cap.read()[0])
        cap.release()
        out.append({"name": s["name"], "ok": ok, "saved_at": s.get("saved_at", "?")})
    return out


app.mount("/media", StaticFiles(directory=str(RESULTS)), name="media")
app.mount("/", StaticFiles(directory=str(WEB), html=True), name="web")
