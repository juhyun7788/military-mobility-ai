"""기동로 구간 판단과 상황 보고 문안 생성.

구간마다 두 가지를 합쳐 기동 가능성을 판단합니다.
- 교통 (공개 도로 CCTV): 원활 / 서행 / 정체 / 돌발 의심
- 위협 (ISR·UAV 영상): 없음 / 주의 / 경계 / 위험
→ 기동 가능(Go) / 제한적 기동(Slow-Go) / 기동 불가(No-Go)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .analyzer import AnalysisResult
from .cctv_source import Cctv
from .route import Route

# 교통 단계: 숫자가 클수록 기동에 불리
LEVELS = {
    0: ("미확인", "#9e9e9e"),
    1: ("원활", "#2e7d32"),
    2: ("서행", "#f9a825"),
    3: ("정체", "#e65100"),
    4: ("돌발 의심", "#c62828"),
}

# 기동 가능성 단계
MOBILITY = {
    0: ("미확인", "#9e9e9e"),
    1: ("기동 가능 (Go)", "#2e7d32"),
    2: ("제한적 기동 (Slow-Go)", "#f9a825"),
    3: ("기동 불가 (No-Go)", "#c62828"),
}
THREAT_COLOR = {0: "#9e9e9e", 1: "#f9a825", 2: "#e65100", 3: "#c62828"}


@dataclass
class IsrInput:
    """기동로 위 한 지점의 ISR·UAV 영상."""

    id: str
    name: str
    source: str
    along_km: float
    lat: float = 0.0
    lon: float = 0.0


@dataclass
class Segment:
    from_km: float
    to_km: float
    cctv: Cctv | None
    result: AnalysisResult | None
    error: str | None = None
    threats: list = field(default_factory=list)  # [(IsrInput, ThreatResult)]

    @property
    def level(self) -> int:
        """교통 단계."""
        r = self.result
        if r is None:
            return 0
        if r.incident["판단"].startswith("돌발상황 의심"):
            return 4
        return {"정체": 3, "서행": 2}.get(r.traffic["판단"], 1)

    @property
    def label(self) -> str:
        return LEVELS[self.level][0]

    @property
    def color(self) -> str:
        return LEVELS[self.level][1]

    @property
    def threat_level(self) -> int:
        return max((t.level for _, t in self.threats), default=0)

    @property
    def mobility(self) -> int:
        t, tr = self.threat_level, self.level
        if tr == 4 or t == 3:
            return 3
        if tr in (2, 3) or t in (1, 2):
            return 2
        if tr == 1:
            return 1
        return 0

    @property
    def mobility_label(self) -> str:
        return MOBILITY[self.mobility][0]

    @property
    def mobility_color(self) -> str:
        return MOBILITY[self.mobility][1]

    @property
    def weather_warning(self) -> str | None:
        if self.result is None:
            return None
        w = self.result.weather["판단"]
        return None if w == "시야 양호" else w


def build_segments(
    route: Route,
    analyzed: list[tuple[Cctv, AnalysisResult | None, str | None]],
    isr_results: list | None = None,
) -> list[Segment]:
    """분석한 CCTV마다 경로 구간을 하나씩 맡기고(이웃 CCTV와의 중간 지점에서 나눔), ISR 위협을 해당 구간에 붙입니다."""
    analyzed = sorted(analyzed, key=lambda x: x[0].along_km)
    total = float(route.cum_km[-1])
    segs = []
    for i, (c, r, err) in enumerate(analyzed):
        a = 0.0 if i == 0 else (analyzed[i - 1][0].along_km + c.along_km) / 2
        b = total if i == len(analyzed) - 1 else (c.along_km + analyzed[i + 1][0].along_km) / 2
        segs.append(Segment(a, b, c, r, err))
    if not segs:
        segs = [Segment(0.0, total, None, None, "CCTV 없음")]
    for isr, tres in isr_results or []:
        for s in segs:
            if s.from_km <= isr.along_km <= s.to_km:
                s.threats.append((isr, tres))
                break
    return segs


def overall(segs: list[Segment]) -> tuple[str, str, int]:
    """(종합 판단, 색, 기동 단계)."""
    known = [s for s in segs if s.mobility > 0]
    if not known:
        return "판단 불가: 분석된 구간 없음", MOBILITY[0][1], 0
    worst = max(s.mobility for s in known)
    threat = max((s.threat_level for s in segs), default=0)
    if worst == 3:
        text = "기동 불가 구간 있음: 우회로 검토 및 위협 확인 필요"
    elif worst == 2:
        text = "제한적 기동: 일부 구간 지연·위협 징후"
    else:
        text = "기동 가능: 전 구간 양호"
    if threat:
        text += f" / ISR 위협 {['', '주의', '경계', '위험'][threat]}"
    if any(s.weather_warning for s in known):
        text += " / 기상·시야 저하 의심"
    return text, MOBILITY[worst][1], worst


def traffic_level(r: AnalysisResult | None) -> int:
    """CCTV 분석 결과의 교통 단계 (Segment.level과 같은 기준)."""
    if r is None:
        return 0
    if r.incident["판단"].startswith("돌발상황 의심"):
        return 4
    return {"정체": 3, "서행": 2}.get(r.traffic["판단"], 1)


def mobility_of(traffic: int, threat: int) -> int:
    """교통 단계와 위협 수준을 합친 기동 가능성 (Segment.mobility와 같은 기준)."""
    if traffic == 4 or threat == 3:
        return 3
    if traffic in (2, 3) or threat in (1, 2):
        return 2
    return 1 if traffic == 1 else 0


def area_assessment(cctv_results: list, isr_results: list) -> dict:
    """지점 주변 CCTV(교통)와 ISR(위협)을 합친 판단.

    cctv_results: [(Cctv, AnalysisResult|None, err)]
    isr_results:  [(dict(name, lat, lon, bearing, dist_km), ThreatResult)]
    """
    t_levels = [traffic_level(r) for _, r, _ in cctv_results if r is not None]
    traffic = max(t_levels, default=0)
    threat = max((t.level for _, t in isr_results), default=0)
    mob = mobility_of(traffic, threat)
    if mob == 0 and not t_levels and isr_results:
        mob = 1  # CCTV는 없지만 ISR상 위협이 없으면 기동 가능으로 봄
    nearest = None
    for info, t in isr_results:
        if t.level >= 2 and (nearest is None or info["dist_km"] < nearest[0]["dist_km"]):
            nearest = (info, t)
    if mob == 3:
        text = "기동 불가 (No-Go): 위협 또는 돌발상황 확인, 지역 진입 보류"
    elif mob == 2:
        text = "제한적 기동 (Slow-Go): 교통 지연 또는 위협 징후"
    elif mob == 1:
        text = "기동 가능 (Go): 교통 양호, 위협 없음"
    else:
        text = "판단 불가: 분석된 정보 없음"
    if nearest:
        info, t = nearest
        text += f" / 최근접 위협 방위 {info['bearing']:03.0f}° {info['dist_km']:.1f}km"
    return {"mobility": mob, "traffic": traffic, "threat": threat, "text": text,
            "color": MOBILITY[mob][1], "nearest": nearest}


def make_area_report(
    place: str, lat: float, lon: float, radius_km: float,
    cctv_results: list, isr_results: list, now: datetime | None = None,
) -> str:
    now = now or datetime.now()
    a = area_assessment(cctv_results, isr_results)
    lines = [
        "지점 주변 군사상황 정보판단 보고",
        "",
        f"1. 일시: {now:%Y-%m-%d %H:%M}",
        f"2. 기준 지점: {place} (위도 {lat:.4f}, 경도 {lon:.4f}), 반경 {radius_km:.1f}km",
        f"3. 정보 출처: 공개 도로 CCTV {len(cctv_results)}개, ISR·UAV 영상 {len(isr_results)}건",
        f"4. 종합 판단: {a['text']}",
        "5. 위협 정보 (ISR·UAV, 기준 지점에서 방위·거리)",
    ]
    if isr_results:
        for info, t in sorted(isr_results, key=lambda x: x[0]["dist_km"]):
            lines.append(f"  - 방위 {info['bearing']:03.0f}° {info['dist_km']:.1f}km [{info['name']}] 위협 {t.level_name}: {t.summary()}")
            for i in t.items:
                lines.append(f"      · {i['묶음']} {i['수량']} (AI 추정: {i['AI 추정 종류(참고)']}, 신뢰도 {i['최고 신뢰도']}) → {i['위협']}")
    else:
        lines.append("  - ISR 정보 없음")
    lines.append("6. 교통 상황 (CCTV)")
    if cctv_results:
        for c, r, err in sorted(cctv_results, key=lambda x: x[0].distance_km):
            if r is None:
                lines.append(f"  - {c.name} ({c.distance_km:.1f}km): 영상 수신 실패")
            else:
                lv = traffic_level(r)
                w = "" if r.weather["판단"] == "시야 양호" else f", 기상: {r.weather['판단']}"
                lines.append(
                    f"  - {c.name} ({c.distance_km:.1f}km): {LEVELS[lv][0]} "
                    f"(차량 평균 {r.traffic['평균 차량 수(화면당)']}대, 멈춤 {r.traffic['멈춘 차량 비율']}), "
                    f"보행자 {r.crowd['판단']}{w}"
                )
    else:
        lines.append("  - 반경 안 CCTV 없음")
    lines.append("7. 조치 건의")
    if a["mobility"] == 3:
        lines.append("  - 해당 지역 진입·통과 보류, 위협 지점 우회")
    if a["threat"] >= 2:
        lines.append("  - 위협 후보 지점 추가 정찰(UAV 재촬영 등)로 식별 확인")
    if a["traffic"] in (2, 3):
        lines.append("  - 교통 지연 고려, 통과 시간 조정")
    if a["mobility"] == 1:
        lines.append("  - 현 상황 기동 가능, 주기적 재확인")
    lines += [
        "",
        "※ AI 분석 결과는 판단 보조용이며 최종 판단은 지휘관이 합니다.",
        "   위협 종류는 추정이며, 개인 식별 정보는 분석하지 않습니다.",
    ]
    return "\n".join(lines)


def make_report(
    route: Route,
    start_name: str,
    end_name: str,
    total_cctvs: int,
    segs: list[Segment],
    now: datetime | None = None,
    alternative: dict | None = None,
) -> str:
    now = now or datetime.now()
    verdict, _, worst = overall(segs)
    n_cctv = sum(1 for s in segs if s.cctv is not None)
    threats = [(s, isr, t) for s in segs for isr, t in s.threats]
    lines = [
        "기동로 군사상황 정보판단 보고",
        "",
        f"1. 일시: {now:%Y-%m-%d %H:%M}",
        f"2. 기동로: {start_name} → {end_name} (약 {route.distance_km:.0f}km"
        + (f", 평시 예상 {route.duration_min:.0f}분" if route.duration_min else "")
        + ")",
        f"3. 정보 출처: 공개 도로 CCTV {total_cctvs}개 중 {n_cctv}개 분석, ISR·UAV 영상 {len(threats)}건 분석",
        f"4. 종합 판단: {verdict}",
        "5. 위협 정보 (ISR·UAV)",
    ]
    if threats:
        for s, isr, t in sorted(threats, key=lambda x: x[1].along_km):
            lines.append(f"  - {isr.along_km:.0f}km [{isr.name}] 위협 {t.level_name}: {t.summary()}")
            for i in t.items:
                lines.append(f"      · {i['묶음']} {i['수량']} (AI 추정: {i['AI 추정 종류(참고)']}, 신뢰도 {i['최고 신뢰도']}) → {i['위협']}")
    else:
        lines.append("  - 탐지된 위협 후보 없음")
    lines.append("6. 구간별 기동 가능성")
    for i, s in enumerate(segs, 1):
        traffic = "교통 미확인" if s.result is None else (
            f"교통 {s.label} (차량 평균 {s.result.traffic['평균 차량 수(화면당)']}대, 멈춤 {s.result.traffic['멈춘 차량 비율']})"
        )
        threat = f", 위협 {['없음', '주의', '경계', '위험'][s.threat_level]}" if s.threats else ""
        weather = f", 기상: {s.weather_warning}" if s.weather_warning else ""
        name = f" [{s.cctv.name}]" if s.cctv else ""
        lines.append(f"  {i}) {s.from_km:.0f}~{s.to_km:.0f}km{name} {s.mobility_label} - {traffic}{threat}{weather}")
    lines.append("7. 조치 건의")
    nogo = [s for s in segs if s.mobility == 3]
    slow = [s for s in segs if s.mobility == 2]
    if nogo:
        rng = ", ".join(f"{s.from_km:.0f}~{s.to_km:.0f}km" for s in nogo)
        lines.append(f"  - {rng} 구간 기동 불가 판단: 현 경로 기동 보류")
        if alternative:
            lines.append(
                f"  - 우회로 이용 건의: 대체 경로 {alternative['distance_km']:.0f}km"
                + (f", 예상 {alternative['duration_min']:.0f}분" if alternative.get("duration_min") else "")
                + (f" (현 경로 대비 {alternative['delta_min']:+.0f}분)" if alternative.get("delta_min") is not None else "")
                + (", 위협 지점 회피" if alternative.get("avoids") else ", 위협 지점 회피 여부 추가 확인 필요")
            )
        else:
            lines.append("  - 대체 경로 탐색 결과 없음: 출발·도착점 조정 또는 추가 정찰 필요")
    if threats:
        lines.append("  - 위협 후보 지점 추가 정찰(UAV 재촬영 등)로 식별 확인 후 최종 판단")
    if slow:
        lines.append("  - 제한적 기동 구간 시간 지연 고려, 차량 간격 유지")
    if any(s.weather_warning for s in segs):
        lines.append("  - 기상·시야 저하 의심 구간 감속")
    if worst <= 1 and not threats:
        lines.append("  - 현 경로로 기동 가능")
    lines += [
        "",
        "※ AI 분석 결과는 판단 보조용이며 최종 판단은 지휘관이 합니다.",
        "   위협 종류(전차·장갑차 등)는 추정이며, 개인 식별 정보는 분석하지 않습니다.",
        "   교통 분석은 상·하행을 구분하지 않습니다.",
    ]
    return "\n".join(lines)
