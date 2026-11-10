"""상황판 스타일 화면 조각 (HTML/CSS)."""

from __future__ import annotations

from html import escape

from .report import LEVELS, Segment

CSS = """
<style>
.block-container {padding-top: 3.2rem; max-width: 1400px;}
[data-testid="stHeader"] {background: rgba(14,22,33,0.85);}
.verdict {display:flex; justify-content:space-between; align-items:center; gap:12px; flex-wrap:wrap;}
.verdict .when {font-size:0.85rem; font-weight:500; opacity:0.85;}
.cls-banner {background:#1f3d2b; color:#9be7a8; border:1px solid #2e7d32; border-radius:6px;
  padding:4px 12px; font-size:0.8rem; letter-spacing:0.08em; text-align:center; margin-bottom:10px;}
.cls-banner.demo {background:#3d321f; color:#ffd180; border-color:#f9a825;}
.hdr {display:flex; align-items:center; gap:16px; padding:16px 20px; margin:4px 0 16px 0; border-radius:10px;
  background:linear-gradient(90deg,#14281c 0%,#172231 60%,#0e1621 100%); border:1px solid #2e5a3a;
  border-left:6px solid #4caf50;}
.hdr-icon {font-size:2.8rem; line-height:1;}
div.hdr div.hdr-title {font-size:2.5rem !important; font-weight:900; margin:0; line-height:1.2; color:#ffffff;
  letter-spacing:-0.01em; text-shadow:0 2px 6px rgba(0,0,0,0.5);}
div.hdr div.hdr-sub {color:#c9d6e3; margin:6px 0 0 0; font-size:1.1rem !important;}
@media (max-width: 800px) {div.hdr div.hdr-title {font-size:1.7rem !important;} .hdr-icon {font-size:2rem;}}
.steps {display:flex; gap:8px; margin:6px 0 16px 0; flex-wrap:wrap;}
.step {flex:1; min-width:150px; padding:8px 12px; border-radius:6px; background:#172231; color:#7d8ea3;
  border:1px solid #243246; font-size:0.9rem;}
.step.done {color:#9be7a8; border-color:#2e7d32;}
.step.active {color:#fff; border-color:#4caf50; background:#1c2b20; font-weight:700;}
.kpis {display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; margin-bottom:14px;}
.kpi {background:#172231; border:1px solid #243246; border-left:4px solid #4a90d9; border-radius:6px; padding:10px 14px;}
.kpi .lbl {color:#8a9bb0; font-size:0.8rem;}
.kpi .val {font-size:1.45rem; font-weight:800; color:#e6edf3; margin-top:2px;}
.kpi .val small {font-size:0.85rem; font-weight:500; color:#8a9bb0;}
.verdict {padding:14px 18px; border-radius:8px; color:#fff; font-size:1.15rem; font-weight:800; margin:6px 0 4px 0;}
.strip-wrap {background:#172231; border:1px solid #243246; border-radius:8px; padding:14px 16px 8px 16px; margin:8px 0 14px 0;}
.strip-title {color:#8a9bb0; font-size:0.8rem; margin-bottom:22px;}
.strip {position:relative; height:26px; display:flex; border-radius:4px; overflow:visible;}
.strip .seg {height:100%; border-right:2px solid #0e1621;}
.strip .cam {position:absolute; top:-18px; transform:translateX(-50%); font-size:0.75rem; color:#e6edf3;}
.strip .cam::after {content:''; display:block; width:2px; height:10px; background:#e6edf3; margin:0 auto;}
.strip .cam.isr {top:28px; font-size:0.9rem;}
.strip .cam.isr::after {display:none;}
.strip-wrap {padding-bottom:22px !important;}
.strip-axis {display:flex; justify-content:space-between; color:#8a9bb0; font-size:0.78rem; margin-top:26px;}
.legend {display:flex; gap:14px; flex-wrap:wrap; color:#9fb0c3; font-size:0.8rem; margin-top:6px;}
.legend span::before {content:'■ '; color:var(--c);}
.badge {display:inline-block; padding:1px 8px; border-radius:10px; color:#fff; font-size:0.78rem; font-weight:700;}
.cam-cap {font-size:0.85rem; color:#c9d4e0; margin:-6px 0 14px 0;}
</style>
"""


def banner(demo: bool) -> str:
    if demo:
        return "<div class='cls-banner demo'>시연 모드 · 실제 CCTV 일부 + 공개 샘플 영상 · 훈련·교육용</div>"
    return "<div class='cls-banner'>실시간 · 공개 도로 CCTV(국가교통정보센터) 기반 · 훈련·교육용</div>"


def header(title: str, sub: str) -> str:
    return (
        "<div class='hdr'><div>"
        f"<div class='hdr-title'>{escape(title)}</div><div class='hdr-sub'>{escape(sub)}</div>"
        "</div></div>"
    )


def steps(current: int) -> str:
    names = ["① 기동로 설정", "② CCTV 영상 분석", "③ 상황 판단·보고"]
    out = []
    for i, n in enumerate(names, 1):
        cls = "done" if i < current else "active" if i == current else ""
        mark = " ✓" if i < current else ""
        out.append(f"<div class='step {cls}'>{n}{mark}</div>")
    return f"<div class='steps'>{''.join(out)}</div>"


def kpis(items: list[tuple[str, str, str | None]]) -> str:
    """items: (라벨, 값 HTML, 왼쪽 띠 색 또는 None)."""
    cards = []
    for label, value, color in items:
        style = f" style='border-left-color:{color}'" if color else ""
        cards.append(f"<div class='kpi'{style}><div class='lbl'>{escape(label)}</div><div class='val'>{value}</div></div>")
    return f"<div class='kpis'>{''.join(cards)}</div>"


STATUS_ICON = {0: "⚪", 1: "🟢", 2: "🟡", 3: "🟠", 4: "🔴"}


def text_color(level: int) -> str:
    """배경색 위 글자색 (노랑 배경엔 어두운 글자)."""
    return "#111" if level == 2 else "#fff"


def badge(level: int) -> str:
    name, color = LEVELS[level]
    return f"<span class='badge' style='background:{color};color:{text_color(level)}'>{name}</span>"


MOB_ICON = {0: "⚪", 1: "🟢", 2: "🟡", 3: "🔴"}
THREAT_ICON = {0: "⚪", 1: "🟡", 2: "🟠", 3: "🔴"}


def verdict_box(text: str, color: str, dark_text: bool, when: str) -> str:
    fg = "#111" if dark_text else "#fff"
    return (
        f"<div class='verdict' style='background:{color};color:{fg}'>"
        f"<span>종합 판단 · {escape(text)}</span><span class='when'>분석 {escape(when)}</span></div>"
    )


def fit_view(coords: list[tuple[float, float]], width_px: int = 820, height_px: int = 470) -> tuple[tuple[float, float], int]:
    """경로 전체가 지도에 들어오는 중심과 확대 수준."""
    import math

    lats, lons = [p[0] for p in coords], [p[1] for p in coords]
    center = ((min(lats) + max(lats)) / 2, (min(lons) + max(lons)) / 2)
    lat_span = max(max(lats) - min(lats), 0.005) * 1.25 / math.cos(math.radians(center[0]))
    lon_span = max(max(lons) - min(lons), 0.005) * 1.25
    z_lat = math.log2(360 * height_px / (256 * lat_span))
    z_lon = math.log2(360 * width_px / (256 * lon_span))
    return center, max(4, min(15, int(min(z_lat, z_lon))))


def route_strip(
    total_km: float, start: str, end: str, segs: list[Segment] | None, cams_km: list[float],
    isr_km: list[tuple[float, int]] | None = None,
) -> str:
    """출발~도착을 한 줄 막대로: 구간별 기동 가능성 색 + CCTV(📹)·ISR(⚠/🛰️) 위치."""
    from .report import MOBILITY

    total_km = max(total_km, 0.1)
    if segs:
        parts = "".join(
            f"<div class='seg' title='{s.from_km:.0f}~{s.to_km:.0f}km {escape(s.mobility_label)}' "
            f"style='width:{(s.to_km - s.from_km) / total_km * 100:.2f}%;background:{s.mobility_color}'></div>"
            for s in segs
        )
    else:
        parts = "<div class='seg' style='width:100%;background:#37474f'></div>"
    cams = "".join(f"<div class='cam' style='left:{min(max(k / total_km * 100, 0), 100):.2f}%'>📹</div>" for k in cams_km)
    for km, lvl in isr_km or []:
        icon = "⚠️" if lvl >= 2 else "🛰️"
        cams += f"<div class='cam isr' style='left:{min(max(km / total_km * 100, 0), 100):.2f}%'>{icon}</div>"
    q = [f"{total_km * f:.0f}km" for f in (0.25, 0.5, 0.75)]
    legend = "".join(f"<span style='--c:{c}'>{n}</span>" for n, c in MOBILITY.values())
    return (
        "<div class='strip-wrap'>"
        "<div class='strip-title'>기동로 구간별 기동 가능성 (출발 → 도착 · 📹 CCTV · 🛰️/⚠️ ISR 위협 지점)</div>"
        f"<div class='strip'>{parts}{cams}</div>"
        f"<div class='strip-axis'><span>▶ {escape(start)} 0km</span><span>{q[0]}</span><span>{q[1]}</span>"
        f"<span>{q[2]}</span><span>{escape(end)} {total_km:.0f}km ⚑</span></div>"
        f"<div class='legend'>{legend}</div>"
        "</div>"
    )
