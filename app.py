"""지능형 기동지원 군사상황 정보판단 프로그램 (Streamlit).

실행: .venv\\Scripts\\streamlit.exe run app.py
"""

import json
import uuid
from datetime import datetime
from pathlib import Path

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from src import ui
from src.analyzer import analyze_video
from src.cctv_source import LocalCatalogSource, get_source
from src.report import LEVELS, MOBILITY, IsrInput, build_segments, make_report, overall
from src.route import PLACES, cctvs_along_route, demo_cctvs_along_route, find_detour, get_route, pick_evenly

PROJ = Path(__file__).resolve().parent
UPLOAD_DIR = PROJ / "data" / "uploads"
TITLE = "지능형 기동지원 군사상황 정보판단 프로그램"
SUBTITLE = (
    "기동로 위 공개 도로 CCTV와 ISR·UAV 영상을 AI로 분석해 "
    "구간별 기동 가능성(Go / Slow-Go / No-Go)과 우회로·조치 건의를 만듭니다."
)
MAP_STYLES = ["🗺️ 일반 지도", "🛰️ 위성 지도", "🌙 상황판 지도"]
# 상황판 지도: OSM 타일만 반전해 어둡게 (경로·마커 색은 그대로)
DARK_MAP_CSS = "<style>.leaflet-tile-pane{filter:invert(1) hue-rotate(180deg) brightness(0.85) contrast(0.9);}</style>"
ESRI_IMAGERY = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
ESRI_LABELS = "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}"
MARKER_COLOR = {0: "gray", 1: "green", 2: "orange", 3: "red", 4: "darkred"}
THREAT_MARKER = {0: "gray", 1: "beige", 2: "orange", 3: "red"}
ISR_TYPES = ["jpg", "jpeg", "png", "webp", "mp4", "webm", "avi", "mov", "ogv"]


def make_map(center, zoom: int, style: str) -> folium.Map:
    """선택한 바탕 지도로 지도를 만듭니다. (키가 필요 없는 공개 타일만 사용)"""
    if style == MAP_STYLES[1]:
        fmap = folium.Map(location=center, zoom_start=zoom, tiles=None)
        folium.TileLayer(ESRI_IMAGERY, attr="Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics", name="위성").add_to(fmap)
        folium.TileLayer(ESRI_LABELS, attr="© Esri", name="지명", overlay=True).add_to(fmap)
        return fmap
    fmap = folium.Map(location=center, zoom_start=zoom, tiles="OpenStreetMap")
    if style == MAP_STYLES[2]:
        fmap.get_root().header.add_child(folium.Element(DARK_MAP_CSS))
    return fmap


def map_style_picker(key: str) -> str:
    return st.radio("바탕 지도", MAP_STYLES, index=0, horizontal=True, key=key, label_visibility="collapsed")


st.set_page_config(page_title=TITLE, page_icon="🎖️", layout="wide")
st.markdown(ui.CSS, unsafe_allow_html=True)

ss = st.session_state
ss.setdefault("route_result", None)
ss.setdefault("near_results", {})
ss.setdefault("near_lat", 37.4870)
ss.setdefault("near_lon", 127.0340)
ss.setdefault("isr_items", [])  # [{"id","name","source", "ratio" 또는 "km"}]
ss.setdefault("isr_demo_loaded", False)


@st.cache_resource
def load_source():
    return get_source()


@st.cache_data(ttl=3600, show_spinner="기동로 탐색 중...")
def cached_route(start, end):
    return get_route(start, end)


@st.cache_data(ttl=86400, show_spinner="기동로 위 CCTV 조회 중...")
def cached_route_cctvs(_source, route_key, _route, buffer_km):
    # ITS API 월 호출 한도가 있어 하루 캐시 (영상 주소가 약 하루 유지됨, 파일 저장본도 따로 있음)
    return cctvs_along_route(_source, _route, buffer_km)


@st.cache_data(ttl=86400, show_spinner="주변 CCTV 조회 중...")
def cached_nearby(_source, lat, lon, radius):
    return _source.find_nearby(lat, lon, radius)


def demo_isr():
    return json.loads((PROJ / "data" / "demo_isr.json").read_text(encoding="utf-8"))


def isr_inputs(route) -> list[IsrInput]:
    """세션의 ISR 목록을 현재 기동로 위 위치로 바꿉니다."""
    total = float(route.cum_km[-1])
    out = []
    for it in ss.isr_items:
        km = total * it["ratio"] if "ratio" in it else min(float(it["km"]), total)
        lat, lon = route.point_at(km)
        out.append(IsrInput(it["id"], it["name"], it["source"], km, lat, lon))
    return sorted(out, key=lambda i: i.along_km)


def show_detail(r):
    """CCTV 한 개의 분석 상세."""
    a, b = st.columns([3, 2])
    with a:
        if r.snapshot is not None:
            st.image(r.snapshot, caption="탐지 결과 (초록: 차량, 주황: 사람·모자이크, 파랑: 자전거)", width="stretch")
        if r.timeline:
            df = pd.DataFrame(r.timeline).rename(columns={"t": "초", "vehicles": "차량", "persons": "보행자"})
            st.line_chart(df.set_index("초"))
    with b:
        st.markdown(f"**분석 구간:** {r.seconds_analyzed}초, {r.frames_analyzed}프레임")
        for title, data in (("🚗 교통", r.traffic), ("🚨 돌발상황", r.incident), ("🌤️ 날씨·시야", r.weather), ("👥 군중", r.crowd)):
            st.markdown(f"**{title}: {data['판단']}**")
            st.json({k: v for k, v in data.items() if k != "판단"}, expanded=False)


source = load_source()
no_key = isinstance(source, LocalCatalogSource)
# ITS API 월 호출 한도(5,000건)를 아끼려고 항상 시연 모드(API 호출 없음)로 시작. 연동할 때만 직접 끔.
ss.setdefault("demo_mode", True)
if ss.demo_mode and not ss.isr_demo_loaded:
    ss.isr_items = [dict(it) for it in demo_isr()["items"]] + ss.isr_items
    ss.isr_demo_loaded = True

# ------------------------------------------------------------------ 사이드바
with st.sidebar:
    st.header("⚙️ 설정")
    st.toggle("시연 모드 (API 호출 없음)", key="demo_mode", disabled=no_key,
              help="켜짐: ITS API를 부르지 않고 저장된 실제 CCTV + 공개 샘플 영상 + 시연용 ISR로 동작. "
                   "끄면 실시간 모드로 ITS API를 호출합니다 (월 5,000건 한도).")
    if not no_key:
        from src.cctv_source import api_usage

        used = api_usage()
        st.caption(f"📊 이번 달 ITS API 호출: **{used:,} / 5,000건**" + (" ⚠️" if used > 4000 else ""))
        if not ss.demo_mode:
            st.warning("실시간 모드: 경로·지점을 바꿀 때마다 ITS API를 호출합니다. 같은 조회는 하루 동안 저장본을 씁니다.")
    _saved = json.loads((PROJ / "data" / "demo_cctvs.json").read_text(encoding="utf-8"))["real"]
    st.caption(f"💾 시연용 실제 CCTV {len(_saved)}개 저장됨 (가장 오래된 저장: {min((s.get('saved_at', '?') for s in _saved), default='-')})")
    if st.button("저장된 실제 CCTV 재생 확인 (API 호출 없음)", key="check_saved", width="stretch"):
        import cv2

        for s in _saved:
            cap = cv2.VideoCapture(s["source"], cv2.CAP_FFMPEG,
                                   [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 8000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 8000])
            ok = cap.isOpened() and cap.read()[0]
            cap.release()
            st.caption(f"{'✅' if ok else '❌'} {s['name']}" + ("" if ok else " — 만료됨, 실시간 모드에서 다시 받아 저장 필요"))
    seconds = st.slider("CCTV당 분석 시간 (초)", 4, 20, 10, help="길수록 정확하지만 오래 걸립니다.")
    if seconds < 10:
        st.caption("⚠️ 10초 미만이면 돌발상황(8초 이상 정차)을 판단할 수 없습니다.")
    max_cctvs = st.slider("기동로 분석 CCTV 수 (최대)", 2, 15, 6, help="경로 전체에 고르게 골라 분석합니다.")
    buffer_km = st.slider("기동로 CCTV 검색 폭 (km)", 0.1, 1.0, 0.3, 0.1, help="경로에서 이만큼 안에 있는 CCTV만 씁니다.")
    st.caption(f"예상 소요: CCTV {max_cctvs}개 × 약 {seconds + 5}초 + ISR {len(ss.isr_items)}건")
    st.divider()
    st.caption("교통 영상: " + ("시연용 (실제 CCTV 일부 + 공개 샘플)" if ss.demo_mode else source.name))
    st.caption("위협 탐지: YOLOE (글로 대상 지정, 학습 없음)")
    st.caption("경로: OSRM (OpenStreetMap 도로망)")

demo = ss.demo_mode
st.markdown(ui.banner(demo), unsafe_allow_html=True)
st.markdown(ui.header(TITLE, SUBTITLE), unsafe_allow_html=True)

tab_route, tab_near = st.tabs(["🛣️ 기동로 분석", "📍 지점 주변 분석"])

# ================================================================== 기동로 분석
with tab_route:
    names = list(PLACES) + ["직접 입력 (위도·경도)"]
    c1, c2 = st.columns(2)
    points = {}
    for col, label, default in ((c1, "출발점", 0), (c2, "도착점", names.index("천안"))):
        with col:
            choice = st.selectbox(label, names, index=default, key=f"{label}_sel")
            if choice in PLACES:
                points[label] = (choice, PLACES[choice])
            else:
                la = st.number_input(f"{label} 위도", value=37.50, format="%.5f", key=f"{label}_lat")
                lo = st.number_input(f"{label} 경도", value=127.00, format="%.5f", key=f"{label}_lon")
                points[label] = (f"({la:.4f}, {lo:.4f})", (la, lo))

    (start_name, start), (end_name, end) = points["출발점"], points["도착점"]
    if start == end:
        st.warning("출발점과 도착점이 같습니다.")
        st.stop()

    route = cached_route(start, end)
    total_km = float(route.cum_km[-1])
    on_route = []
    if demo:
        on_route = demo_cctvs_along_route(route, buffer_km)
    else:
        try:
            on_route = cached_route_cctvs(source, (start, end, buffer_km), route, buffer_km)
        except Exception as e:
            st.error(f"CCTV 조회 실패: {e}")
            st.button(
                "🎬 시연 모드로 전환 (API 없이 끝까지 보기)", type="primary",
                on_click=lambda: ss.update(demo_mode=True), key="to_demo",
            )
    picks = pick_evenly(on_route, max_cctvs)
    if not demo and picks:
        if st.button(f"💾 이 경로의 실제 CCTV {len(picks)}개를 시연용으로 저장 (API 없이 약 하루 재생)", key="save_demo"):
            from src.route import save_demo_real

            n = save_demo_real(picks)
            st.success(f"시연 목록에 실제 CCTV {n}개를 저장했습니다. 시연 모드에서 API 호출 없이 이 영상들을 씁니다.")
    isrs = isr_inputs(route)
    route_key = (start, end, buffer_km, demo, tuple(i.id for i in isrs))

    # -------------------------------------------------- ISR·UAV 영상 입력
    with st.expander(f"🛰️ ISR·UAV 영상 — 기동로 위협 분석 ({len(isrs)}건)", expanded=not ss.route_result):
        lc, rc = st.columns([3, 2])
        with lc:
            if isrs:
                st.dataframe(
                    pd.DataFrame([{"위치(km)": round(i.along_km, 1), "ISR 영상": i.name,
                                   "형식": "사진" if Path(i.source).suffix.lower() in (".jpg", ".jpeg", ".png", ".webp") else "동영상"}
                                  for i in isrs]),
                    hide_index=True, width="stretch",
                )
                if st.button("ISR 목록 비우기", key="isr_clear"):
                    ss.isr_items = []
                    st.rerun()
            else:
                st.info("ISR·UAV 영상이 없습니다. 오른쪽에서 사진·영상을 올리고 기동로 위 위치를 지정하세요.")
            st.caption("실제 UAV 영상에는 촬영 위치 정보(MISB KLV)가 들어 있어 자동 배치가 가능합니다. 이번 버전은 위치를 직접 지정합니다.")
        with rc:
            up = st.file_uploader("UAV·ISR 사진/영상 올리기", type=ISR_TYPES, key="isr_upload")
            km = st.slider("기동로 위 위치 (km)", 0.0, max(total_km, 1.0), round(total_km / 2, 1), 0.5, key="isr_km")
            extra = demo_isr()["extra"]
            pick_extra = st.selectbox("또는 시연용 ISR 사진", ["선택 안 함"] + [e["name"] for e in extra], key="isr_extra")
            if st.button("➕ 기동로에 추가", width="stretch", disabled=up is None and pick_extra == "선택 안 함"):
                if up is not None:
                    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
                    path = UPLOAD_DIR / f"{uuid.uuid4().hex[:8]}{Path(up.name).suffix.lower()}"
                    path.write_bytes(up.getbuffer())
                    ss.isr_items.append({"id": path.stem, "name": f"[업로드] {up.name}", "source": str(path), "km": km})
                else:
                    e = next(e for e in extra if e["name"] == pick_extra)
                    ss.isr_items.append({"id": uuid.uuid4().hex[:8], "name": e["name"], "source": str(PROJ / e["source"]), "km": km})
                st.rerun()

    res = ss.route_result if ss.route_result and ss.route_result["key"] == route_key else None
    segs = build_segments(route, res["analyzed"], res["isr_results"]) if res else None
    verdict, vcolor, worst = overall(segs) if segs else (None, None, 0)
    detour = res["detour"] if res else None
    threat_by_id = {isr.id: t for isr, t in res["isr_results"]} if res else {}

    st.markdown(ui.steps(3 if segs else 2 if (picks or isrs) else 1), unsafe_allow_html=True)

    nogo = sum(1 for s in segs if s.mobility == 3) if segs else None
    max_threat = max((t.level for t in threat_by_id.values()), default=0)
    st.markdown(
        ui.kpis(
            [
                ("기동로 거리", f"{route.distance_km:.1f} <small>km</small>", None),
                ("평시 예상 시간", f"{route.duration_min:.0f} <small>분</small>" if route.duration_min else "-", None),
                ("분석 CCTV", f"{len(picks)} <small>/ {len(on_route)}개</small>", None),
                ("ISR 위협", (f"{['없음', '주의', '경계', '위험'][max_threat]} <small>{len(isrs)}건</small>" if segs
                              else f"{len(isrs)} <small>건 대기</small>"),
                 ["#2e7d32", "#f9a825", "#e65100", "#c62828"][max_threat] if segs else None),
                ("기동 불가 구간", f"{nogo} <small>개</small>" if segs else "<small>분석 전</small>",
                 vcolor if segs else "#455a64"),
            ]
        ),
        unsafe_allow_html=True,
    )
    if route.provider.startswith("직선"):
        st.warning("경로 서비스에 연결하지 못해 직선 경로로 대신했습니다. CCTV가 적게 잡힐 수 있습니다.")
    if not demo and getattr(source, "stale", False):
        st.warning("ITS API를 쓸 수 없어 이전에 저장한 CCTV 목록을 씁니다. 영상 주소가 만료돼 분석이 실패할 수 있습니다.")

    if segs:
        st.markdown(ui.verdict_box(verdict, vcolor, worst == 2, f"{res['time']:%Y-%m-%d %H:%M:%S}"), unsafe_allow_html=True)
        if detour:
            delta = (detour.duration_min - route.duration_min) if (detour.duration_min and route.duration_min) else None
            st.markdown(
                f"<div class='verdict' style='background:#5e35b1;color:#fff;font-size:1rem'>"
                f"<span>↪ 우회로 건의 · {detour.distance_km:.0f}km, 예상 {detour.duration_min:.0f}분"
                + (f" (현 경로 대비 {delta:+.0f}분)" if delta is not None else "")
                + " · 위협 지점 2km 이상 회피 · 지도에 보라색 점선</span></div>",
                unsafe_allow_html=True,
            )

    st.markdown(
        ui.route_strip(total_km, start_name, end_name, segs, [c.along_km for c in picks],
                       [(i.along_km, threat_by_id[i.id].level if i.id in threat_by_id else 0) for i in isrs]),
        unsafe_allow_html=True,
    )

    left, right = st.columns([3, 2])
    with left:
        style = map_style_picker("route_map_style")
        center, zoom = ui.fit_view(route.coords + (detour.coords if detour else []))
        fmap = make_map(center, zoom, style)
        if detour:
            folium.PolyLine(detour.coords, color="#7e57c2", weight=6, opacity=0.95, dash_array="10,8",
                            tooltip=f"우회로 {detour.distance_km:.0f}km / {detour.duration_min:.0f}분").add_to(fmap)
        if segs:
            for s in segs:
                folium.PolyLine(
                    route.slice(s.from_km, s.to_km), color=s.mobility_color, weight=8, opacity=0.9,
                    tooltip=f"{s.from_km:.0f}~{s.to_km:.0f}km {s.mobility_label}",
                ).add_to(fmap)
        else:
            folium.PolyLine(route.coords, color="#4a90d9", weight=6, opacity=0.8, tooltip="기동로").add_to(fmap)
        pick_ids = {c.id for c in picks}
        for c in on_route:
            if c.id not in pick_ids:
                folium.CircleMarker([c.lat, c.lon], radius=3, color="#78909c", fill=True, tooltip=c.name).add_to(fmap)
        seg_by_id = {s.cctv.id: s for s in segs if s.cctv} if segs else {}
        for c in picks:
            s = seg_by_id.get(c.id)
            tip = f"📹 {c.name} ({c.along_km:.0f}km)" + (f" · 교통 {s.label}" if s else "")
            folium.Marker(
                [c.lat, c.lon], tooltip=tip,
                icon=folium.Icon(color=MARKER_COLOR[s.level] if s else "blue", icon="video-camera", prefix="fa"),
            ).add_to(fmap)
        for i in isrs:
            t = threat_by_id.get(i.id)
            tip = f"🛰️ {i.name} ({i.along_km:.0f}km)" + (f" · 위협 {t.level_name}: {t.summary()}" if t else " · 분석 전")
            folium.Marker(
                [i.lat, i.lon], tooltip=tip,
                icon=folium.Icon(color=THREAT_MARKER[t.level] if t else "cadetblue",
                                 icon="exclamation-triangle" if t and t.level >= 2 else "plane", prefix="fa"),
            ).add_to(fmap)
            if t and t.level >= 3:
                folium.Circle([i.lat, i.lon], radius=2000, color="#c62828", fill=True, fill_opacity=0.12,
                              tooltip="위협 지점 반경 2km").add_to(fmap)
        folium.Marker(start, tooltip=f"출발: {start_name}", icon=folium.Icon(color="black", icon="play", prefix="fa")).add_to(fmap)
        folium.Marker(end, tooltip=f"도착: {end_name}", icon=folium.Icon(color="black", icon="flag", prefix="fa")).add_to(fmap)
        st_folium(
            fmap, height=490, use_container_width=True, returned_objects=[],
            center=center, zoom=zoom,
            key=f"route_map_{abs(hash(route_key))}_{MAP_STYLES.index(style)}_{bool(res)}",
        )

    with right:
        if not picks and not isrs:
            st.info("기동로 위에서 CCTV를 찾지 못했고 ISR 영상도 없습니다. 검색 폭을 넓히거나 ISR 영상을 추가하세요.")
        else:
            st.markdown("**분석 대상**")
            rows = [
                {
                    "위치(km)": round(c.along_km, 1), "구분": "📹 CCTV", "이름": c.name,
                    "결과": (f"{ui.STATUS_ICON[seg_by_id[c.id].level]} {seg_by_id[c.id].label}" if c.id in seg_by_id else "⏳ 대기"),
                }
                for c in picks
            ] + [
                {
                    "위치(km)": round(i.along_km, 1), "구분": "🛰️ ISR", "이름": i.name,
                    "결과": (f"{ui.THREAT_ICON[threat_by_id[i.id].level]} {threat_by_id[i.id].level_name}"
                             if i.id in threat_by_id else "⏳ 대기"),
                }
                for i in isrs
            ]
            st.dataframe(pd.DataFrame(rows).sort_values("위치(km)"), hide_index=True, width="stretch",
                         height=min(40 + 35 * len(rows), 360))
            if st.button(f"▶ 분석 시작 (CCTV {len(picks)} · ISR {len(isrs)})", type="primary", width="stretch"):
                from src.threat import analyze_isr

                n = len(picks) + len(isrs)
                bar = st.progress(0.0, text="분석 준비 중...")
                analyzed, isr_results = [], []
                for k, c in enumerate(picks):
                    bar.progress(k / n, text=f"📹 {c.name} 교통 분석 중... ({k + 1}/{n})")
                    try:
                        analyzed.append((c, analyze_video(c.source, max_seconds=seconds, start_seconds=c.start_seconds), None))
                    except Exception as e:
                        analyzed.append((c, None, str(e)))
                for k, i in enumerate(isrs, len(picks)):
                    bar.progress(k / n, text=f"🛰️ {i.name} 위협 분석 중... ({k + 1}/{n})")
                    try:
                        isr_results.append((i, analyze_isr(i.source, i.name)))
                    except Exception as e:
                        st.warning(f"{i.name}: {e}")
                bar.progress(0.97, text="기동 가능성 판단·우회로 탐색 중...")
                tmp = build_segments(route, analyzed, isr_results)
                block = [(i.lat, i.lon) for s in tmp if s.mobility == 3 for i, t in s.threats if t.level == 3]
                block += [(s.cctv.lat, s.cctv.lon) for s in tmp if s.level == 4 and s.cctv]
                det = find_detour(route, start, end, block) if block else None
                bar.progress(1.0, text="분석 완료")
                ss.route_result = {"key": route_key, "analyzed": analyzed, "isr_results": isr_results,
                                   "detour": det, "total": len(on_route), "time": datetime.now()}
                st.rerun()

    if segs:
        r_isr, r_cam, r_tab, r_rep, r_det = st.tabs(
            ["🛰️ ISR 위협", "📷 CCTV 화면", "📋 구간별 기동 판단", "📝 상황 보고", "🔍 상세 분석"]
        )

        with r_isr:
            if not res["isr_results"]:
                st.info("분석한 ISR·UAV 영상이 없습니다.")
            for isr, t in sorted(res["isr_results"], key=lambda x: x[0].along_km):
                a, b = st.columns([3, 2])
                with a:
                    if t.snapshot is not None:
                        st.image(t.snapshot, width="stretch")
                with b:
                    st.markdown(
                        f"<div class='cam-cap' style='font-size:1rem'>"
                        f"<span class='badge' style='background:{['#2e7d32', '#f9a825', '#e65100', '#c62828'][t.level]};"
                        f"color:{'#111' if t.level == 1 else '#fff'}'>위협 {t.level_name}</span> "
                        f"<b>{isr.along_km:.0f}km</b> {isr.name}</div>",
                        unsafe_allow_html=True,
                    )
                    if t.items:
                        st.dataframe(pd.DataFrame([{k: v for k, v in i.items() if not k.startswith("_")} for i in t.items]),
                                     hide_index=True, width="stretch")
                    else:
                        st.caption("탐지된 위협 후보 없음")
                    st.caption("상자 색: 빨강 위험 / 주황 경계 / 노랑 주의 / 회색 민간. 종류는 추정이며 최종 식별은 사람이 확인합니다.")
                st.divider()

        with r_cam:
            cols = st.columns(3)
            for k, s in enumerate([s for s in segs if s.cctv]):
                with cols[k % 3]:
                    if s.result is not None and s.result.snapshot is not None:
                        st.image(s.result.snapshot, width="stretch")
                    else:
                        st.markdown(
                            "<div style='height:150px;display:flex;align-items:center;justify-content:center;"
                            "background:#172231;border-radius:6px;color:#8a9bb0'>영상 수신 실패</div>",
                            unsafe_allow_html=True,
                        )
                    extra = ""
                    if s.result is not None:
                        extra = f" · 차량 {s.result.traffic['평균 차량 수(화면당)']}대"
                        if s.weather_warning:
                            extra += f" · ⚠️ {s.weather_warning}"
                    st.markdown(
                        f"<div class='cam-cap'>{ui.badge(s.level)} <b>{s.from_km:.0f}~{s.to_km:.0f}km</b> "
                        f"{s.cctv.name}{extra}</div>",
                        unsafe_allow_html=True,
                    )

        with r_tab:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "구간(km)": f"{s.from_km:.0f}~{s.to_km:.0f}",
                            "기동 가능성": f"{ui.MOB_ICON[s.mobility]} {s.mobility_label}",
                            "교통": f"{ui.STATUS_ICON[s.level]} {s.label}",
                            "ISR 위협": (", ".join(f"{t.level_name}({t.summary()})" for _, t in s.threats) if s.threats else "-"),
                            "CCTV": s.cctv.name if s.cctv else "-",
                            "기상·시야": s.result.weather["판단"] if s.result else None,
                        }
                        for s in segs
                    ]
                ),
                hide_index=True, width="stretch",
            )
            st.caption("기동 불가(No-Go): 돌발상황 또는 위협 '위험' / 제한적 기동(Slow-Go): 서행·정체 또는 위협 주의·경계 / 기동 가능(Go): 원활하고 위협 없음")

        with r_rep:
            alt = None
            if detour:
                alt = {
                    "distance_km": detour.distance_km, "duration_min": detour.duration_min, "avoids": True,
                    "delta_min": (detour.duration_min - route.duration_min) if route.duration_min else None,
                }
            report = make_report(route, start_name, end_name, res["total"], segs, res["time"], alternative=alt)
            if demo:
                report += "\n   (시연 모드: 일부 CCTV·ISR 영상은 공개 자료를 기동로 위에 가상 배치한 결과입니다.)"
            st.code(report, language=None)
            st.download_button(
                "📥 보고서 내려받기 (.txt)", report.encode("utf-8"),
                file_name=f"기동로_군사상황보고_{res['time']:%Y%m%d_%H%M}.txt", mime="text/plain",
            )

        with r_det:
            for s in [s for s in segs if s.cctv]:
                with st.expander(f"{s.from_km:.0f}~{s.to_km:.0f}km {s.cctv.name} — {s.label}"):
                    if s.result is None:
                        st.error(s.error or "영상 수신 실패")
                    else:
                        show_detail(s.result)

# ================================================================== 지점 주변 분석
with tab_near:
    from src.report import area_assessment, make_area_report, traffic_level
    from src.route import bearing_distance, demo_cctvs_near, offset_point

    if demo and not ss.get("near_isr_demo_loaded"):
        ss.near_isr = [dict(it) for it in demo_isr().get("near", [])] + ss.get("near_isr", [])
        ss.near_isr_demo_loaded = True
    ss.setdefault("near_isr", [])
    ss.setdefault("near_result", None)

    st.caption("기준 지점 주변의 공개 도로 CCTV(교통)와 ISR·UAV 영상(위협)을 함께 분석해 지역 기동 가능성을 판단합니다.")
    a, b, c_, d_ = st.columns([3, 2, 2, 2])
    near_place = a.selectbox("기준 지점", ["직접 지정 (지도 클릭·좌표)"] + list(PLACES), key="near_place")
    if near_place in PLACES and (ss.near_lat, ss.near_lon) != PLACES[near_place] and ss.get("near_place_prev") != near_place:
        ss.near_lat, ss.near_lon = PLACES[near_place]
    ss.near_place_prev = near_place
    ss.near_lat = b.number_input("위도", value=float(ss.near_lat), format="%.5f", step=0.001)
    ss.near_lon = c_.number_input("경도", value=float(ss.near_lon), format="%.5f", step=0.001)
    radius = d_.slider("분석 반경 (km)", 0.5, 5.0, 3.0, 0.5)
    lat0, lon0 = ss.near_lat, ss.near_lon
    place_name = near_place if near_place in PLACES else "지정 지점"

    # CCTV
    try:
        near = demo_cctvs_near(lat0, lon0, radius) if demo else cached_nearby(source, round(lat0, 4), round(lon0, 4), radius)
    except Exception as e:
        st.error(f"CCTV 조회 실패: {e}")
        near = []
    for c in near:
        c.distance_km = round(bearing_distance(lat0, lon0, c.lat, c.lon)[1], 2)

    # ISR (기준 지점에서 방위·거리로 배치, 업로드는 지정 당시 좌표로 고정)
    near_isr = []
    for it in ss.near_isr:
        la, lo = (it["lat"], it["lon"]) if "lat" in it else offset_point(lat0, lon0, it["bearing"], it["dist_km"])
        brg, dist = bearing_distance(lat0, lon0, la, lo)
        if dist <= radius:
            near_isr.append({"id": it["id"], "name": it["name"], "source": it["source"], "lat": la, "lon": lo,
                             "bearing": brg, "dist_km": dist})

    with st.expander(f"🛰️ 주변 ISR·UAV 영상 ({len(near_isr)}건 / 반경 안)", expanded=not ss.near_result):
        lc, rc = st.columns([3, 2])
        with lc:
            if near_isr:
                st.dataframe(pd.DataFrame([{"방위(°)": f"{i['bearing']:03.0f}", "거리(km)": round(i["dist_km"], 1), "ISR 영상": i["name"]}
                                           for i in near_isr]), hide_index=True, width="stretch")
            else:
                st.info("반경 안에 ISR·UAV 영상이 없습니다. 오른쪽에서 올리고 방위·거리를 지정하세요.")
            if ss.near_isr and st.button("ISR 목록 비우기", key="near_isr_clear"):
                ss.near_isr = []
                st.rerun()
        with rc:
            up = st.file_uploader("UAV·ISR 사진/영상 올리기", type=ISR_TYPES, key="near_isr_upload")
            q1, q2 = st.columns(2)
            brg_in = q1.number_input("방위 (°, 북=0)", 0, 359, 90, 5, key="near_isr_brg")
            dist_in = q2.number_input("거리 (km)", 0.1, 5.0, 1.0, 0.1, key="near_isr_dist")
            extra = demo_isr()["extra"]
            pick_extra = st.selectbox("또는 시연용 ISR 사진", ["선택 안 함"] + [e["name"] for e in extra], key="near_isr_extra")
            if st.button("➕ 지점 주변에 추가", width="stretch", disabled=up is None and pick_extra == "선택 안 함", key="near_isr_add"):
                la, lo = offset_point(lat0, lon0, brg_in, dist_in)
                if up is not None:
                    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
                    path = UPLOAD_DIR / f"{uuid.uuid4().hex[:8]}{Path(up.name).suffix.lower()}"
                    path.write_bytes(up.getbuffer())
                    ss.near_isr.append({"id": path.stem, "name": f"[업로드] {up.name}", "source": str(path), "lat": la, "lon": lo})
                else:
                    e = next(e for e in extra if e["name"] == pick_extra)
                    ss.near_isr.append({"id": uuid.uuid4().hex[:8], "name": e["name"], "source": str(PROJ / e["source"]), "lat": la, "lon": lo})
                st.rerun()

    near_key = (round(lat0, 4), round(lon0, 4), radius, demo, tuple(i["id"] for i in near_isr), tuple(c.id for c in near))
    nres = ss.near_result if ss.near_result and ss.near_result["key"] == near_key else None
    assess = area_assessment(nres["cctv"], nres["isr"]) if nres else None
    cctv_by_id = {c.id: (r, err) for c, r, err in nres["cctv"]} if nres else {}
    isr_by_id = {info["id"]: t for info, t in nres["isr"]} if nres else {}

    st.markdown(
        ui.kpis([
            ("기준 지점", f"{place_name}", None),
            ("반경 안 CCTV", f"{len(near)} <small>개</small>", None),
            ("반경 안 ISR", f"{len(near_isr)} <small>건</small>", None),
            ("교통 (최악)", LEVELS[assess["traffic"]][0] if assess else "<small>분석 전</small>",
             LEVELS[assess["traffic"]][1] if assess else None),
            ("ISR 위협 (최고)", ["없음", "주의", "경계", "위험"][assess["threat"]] if assess else "<small>분석 전</small>",
             ["#2e7d32", "#f9a825", "#e65100", "#c62828"][assess["threat"]] if assess else None),
        ]),
        unsafe_allow_html=True,
    )
    if assess:
        st.markdown(ui.verdict_box(assess["text"], assess["color"], assess["mobility"] == 2,
                                   f"{nres['time']:%Y-%m-%d %H:%M:%S}"), unsafe_allow_html=True)

    left, right = st.columns([3, 2])
    with left:
        nstyle = map_style_picker("near_map_style")
        nmap = make_map([lat0, lon0], 13 if radius <= 2 else 12, nstyle)
        ring = assess["color"] if assess else "#4a90d9"
        folium.Circle([lat0, lon0], radius=radius * 1000, color=ring, weight=3, fill=True, fill_opacity=0.08,
                      tooltip=f"분석 반경 {radius}km").add_to(nmap)
        folium.Marker([lat0, lon0], tooltip=f"기준 지점: {place_name}", icon=folium.Icon(color="black", icon="crosshairs", prefix="fa")).add_to(nmap)
        for c in near:
            r, _ = cctv_by_id.get(c.id, (None, None))
            lv = traffic_level(r) if c.id in cctv_by_id else None
            folium.Marker(
                [c.lat, c.lon], tooltip=f"📹 {c.name} ({c.distance_km:.1f}km)" + (f" · 교통 {LEVELS[lv][0]}" if lv is not None else ""),
                icon=folium.Icon(color=MARKER_COLOR[lv] if lv is not None else "blue", icon="video-camera", prefix="fa"),
            ).add_to(nmap)
        for i in near_isr:
            t = isr_by_id.get(i["id"])
            folium.Marker(
                [i["lat"], i["lon"]],
                tooltip=f"🛰️ {i['name']} · 방위 {i['bearing']:03.0f}° {i['dist_km']:.1f}km" + (f" · 위협 {t.level_name}: {t.summary()}" if t else " · 분석 전"),
                icon=folium.Icon(color=THREAT_MARKER[t.level] if t else "cadetblue",
                                 icon="exclamation-triangle" if t and t.level >= 2 else "plane", prefix="fa"),
            ).add_to(nmap)
            if t and t.level >= 2:
                folium.PolyLine([[lat0, lon0], [i["lat"], i["lon"]]], color="#c62828" if t.level == 3 else "#e65100",
                                weight=2, dash_array="6,6").add_to(nmap)
            if t and t.level >= 3:
                folium.Circle([i["lat"], i["lon"]], radius=500, color="#c62828", fill=True, fill_opacity=0.15,
                              tooltip="위협 지점 반경 500m").add_to(nmap)
        out = st_folium(nmap, height=470, use_container_width=True, returned_objects=["last_clicked"],
                        center=[lat0, lon0], key=f"near_map_{MAP_STYLES.index(nstyle)}_{bool(nres)}")
        clicked = (out or {}).get("last_clicked")
        if clicked and (round(clicked["lat"], 5), round(clicked["lng"], 5)) != (round(lat0, 5), round(lon0, 5)):
            ss.near_lat, ss.near_lon = clicked["lat"], clicked["lng"]
            st.rerun()
        st.caption("지도를 클릭하면 기준 지점이 바뀝니다. 점선: 기준 지점 → 위협 지점")

    with right:
        rows = [{"구분": "📹 CCTV", "이름": c.name, "방위·거리": f"{bearing_distance(lat0, lon0, c.lat, c.lon)[0]:03.0f}° {c.distance_km:.1f}km",
                 "결과": (f"{ui.STATUS_ICON[traffic_level(cctv_by_id[c.id][0])]} {LEVELS[traffic_level(cctv_by_id[c.id][0])][0]}"
                          if c.id in cctv_by_id else "⏳ 대기")} for c in near]
        rows += [{"구분": "🛰️ ISR", "이름": i["name"], "방위·거리": f"{i['bearing']:03.0f}° {i['dist_km']:.1f}km",
                  "결과": (f"{ui.THREAT_ICON[isr_by_id[i['id']].level]} {isr_by_id[i['id']].level_name}" if i["id"] in isr_by_id else "⏳ 대기")}
                 for i in near_isr]
        if rows:
            st.markdown("**분석 대상**")
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=min(40 + 35 * len(rows), 360))
            if st.button(f"▶ 주변 융합 분석 (CCTV {len(near)} · ISR {len(near_isr)})", type="primary", width="stretch", key="near_run"):
                from src.threat import analyze_isr

                n = len(near) + len(near_isr)
                bar = st.progress(0.0)
                cres, ires = [], []
                for k, c in enumerate(near):
                    bar.progress(k / n, text=f"📹 {c.name} 교통 분석 중... ({k + 1}/{n})")
                    try:
                        cres.append((c, analyze_video(c.source, max_seconds=seconds, start_seconds=c.start_seconds), None))
                    except Exception as e:
                        cres.append((c, None, str(e)))
                for k, i in enumerate(near_isr, len(near)):
                    bar.progress(k / n, text=f"🛰️ {i['name']} 위협 분석 중... ({k + 1}/{n})")
                    try:
                        ires.append((i, analyze_isr(i["source"], i["name"])))
                    except Exception as e:
                        st.warning(f"{i['name']}: {e}")
                bar.progress(1.0, text="분석 완료")
                ss.near_result = {"key": near_key, "cctv": cres, "isr": ires, "time": datetime.now()}
                st.rerun()
        else:
            st.info("반경 안에 CCTV와 ISR 영상이 없습니다. 반경을 넓히거나 ISR 영상을 추가하세요.")

    if nres:
        n_isr, n_cam, n_rep = st.tabs(["🛰️ ISR 위협", "📷 CCTV 화면", "📝 지점 상황 보고"])
        with n_isr:
            if not nres["isr"]:
                st.info("분석한 ISR·UAV 영상이 없습니다.")
            for info, t in sorted(nres["isr"], key=lambda x: x[0]["dist_km"]):
                p, q = st.columns([3, 2])
                with p:
                    if t.snapshot is not None:
                        st.image(t.snapshot, width="stretch")
                with q:
                    st.markdown(
                        f"<div class='cam-cap' style='font-size:1rem'><span class='badge' "
                        f"style='background:{['#2e7d32', '#f9a825', '#e65100', '#c62828'][t.level]};color:{'#111' if t.level == 1 else '#fff'}'>"
                        f"위협 {t.level_name}</span> <b>방위 {info['bearing']:03.0f}° {info['dist_km']:.1f}km</b> {info['name']}</div>",
                        unsafe_allow_html=True,
                    )
                    if t.items:
                        st.dataframe(pd.DataFrame([{k: v for k, v in i.items() if not k.startswith("_")} for i in t.items]),
                                     hide_index=True, width="stretch")
                    else:
                        st.caption("탐지된 위협 후보 없음")
                st.divider()
        with n_cam:
            cols = st.columns(3)
            for k, (c, r, err) in enumerate(sorted(nres["cctv"], key=lambda x: x[0].distance_km)):
                with cols[k % 3]:
                    if r is not None and r.snapshot is not None:
                        st.image(r.snapshot, width="stretch")
                        lv = traffic_level(r)
                        st.markdown(f"<div class='cam-cap'>{ui.badge(lv)} {c.name} ({c.distance_km:.1f}km) · 차량 "
                                    f"{r.traffic['평균 차량 수(화면당)']}대 · 보행자 {r.crowd['판단']}</div>", unsafe_allow_html=True)
                    else:
                        st.error(f"{c.name}: {err or '영상 수신 실패'}")
        with n_rep:
            rep = make_area_report(place_name, lat0, lon0, radius, nres["cctv"], nres["isr"], nres["time"])
            if demo:
                rep += "\n   (시연 모드: 일부 CCTV·ISR 영상은 공개 자료를 기준 지점 주변에 가상 배치한 결과입니다.)"
            st.code(rep, language=None)
            st.download_button("📥 보고서 내려받기 (.txt)", rep.encode("utf-8"),
                               file_name=f"지점주변_군사상황보고_{nres['time']:%Y%m%d_%H%M}.txt", mime="text/plain", key="near_dl")

st.divider()
st.caption(
    "개인정보 보호: 얼굴·번호판 인식을 하지 않으며, 화면의 사람 영역은 모자이크 처리합니다. "
    "공개 도로 CCTV만 사용하고 특정 인물·차량을 추적하지 않습니다. 날씨·시야 판단은 참고용 추정입니다. "
    "영상 출처: 국가교통정보센터(its.go.kr) CCTV 화상자료 Open API / 시연용 샘플은 data/videos/SOURCES.md"
)
