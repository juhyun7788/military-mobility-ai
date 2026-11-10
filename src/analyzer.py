"""CCTV 영상분석.

사전학습 YOLO(COCO)로 차량·사람을 탐지·추적하고, 간단한 규칙으로
교통 상황, 돌발상황(정차 의심), 날씨·시야, 군중 밀집도를 판단합니다.

개인정보 보호: 얼굴·번호판 인식은 하지 않으며, 결과 이미지의 사람 영역은 흐리게 처리합니다.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

PROJECT_DIR = Path(__file__).resolve().parent.parent
MODEL_PATH = PROJECT_DIR / "models" / "yolo11n.pt"

# COCO 클래스 번호
PERSON = 0
BICYCLE = 1
VEHICLES = {2: "승용차", 3: "오토바이", 5: "버스", 7: "트럭"}
TARGET_CLASSES = [PERSON, BICYCLE, *VEHICLES]

_model = None


def _get_model():
    global _model
    if _model is None:
        from ultralytics import YOLO

        _model = YOLO(str(MODEL_PATH))
    return _model


def _new_tracker(sample_fps: float):
    """ByteTrack 추적기. 영상마다 새로 만들어 추적 ID가 섞이지 않게 합니다."""
    from types import SimpleNamespace

    from ultralytics.trackers.byte_tracker import BYTETracker

    args = SimpleNamespace(
        track_high_thresh=0.2,
        track_low_thresh=0.1,
        new_track_thresh=0.2,
        track_buffer=int(sample_fps * 3),  # 3초 동안 가려져도 같은 차량으로 유지
        match_thresh=0.8,
        fuse_score=True,
    )
    return BYTETracker(args)


@dataclass
class AnalysisResult:
    frames_analyzed: int = 0
    seconds_analyzed: float = 0.0
    traffic: dict = field(default_factory=dict)
    incident: dict = field(default_factory=dict)
    weather: dict = field(default_factory=dict)
    crowd: dict = field(default_factory=dict)
    timeline: list = field(default_factory=list)  # 초 단위 [{"t", "vehicles", "persons"}]
    snapshot: np.ndarray | None = None  # RGB, 사람 영역 흐림 처리


# ---------------------------------------------------------------- 날씨·시야
def frame_conditions(frame_bgr: np.ndarray) -> dict:
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    lower = hsv[hsv.shape[0] // 2 :]
    snow_like = (lower[..., 2] > 200) & (lower[..., 1] < 30)
    return {
        "brightness": float(hsv[..., 2].mean()),
        "contrast": float(gray.std()),
        "sharpness": float(cv2.Laplacian(gray, cv2.CV_64F).var()),
        "snow_ratio": float(snow_like.mean()),
    }


def judge_weather(stats: list[dict]) -> dict:
    if not stats:
        return {"판단": "판단 불가"}
    m = {k: float(np.mean([s[k] for s in stats])) for k in stats[0]}
    notes = []
    if m["brightness"] < 60:
        notes.append("야간 또는 어두움")
    # 안개는 대비와 선명도가 함께 떨어지는 경우로 봅니다 (회색 노면만 보이는 화면을 안개로 오인하지 않도록)
    if m["contrast"] < 20 and m["sharpness"] < 30 and m["brightness"] >= 60:
        notes.append("안개·연무 의심 (대비·선명도 낮음)")
    elif m["sharpness"] < 15:
        notes.append("시야 흐림 의심 (비·렌즈 오염 등)")
    if m["snow_ratio"] > 0.35:
        notes.append("노면 적설 의심")
    return {
        "판단": ", ".join(notes) if notes else "시야 양호",
        "밝기(0~255)": round(m["brightness"], 1),
        "대비": round(m["contrast"], 1),
        "선명도": round(m["sharpness"], 1),
        "흰 노면 비율": round(m["snow_ratio"], 3),
        "방식": "밝기·대비·선명도 기반 규칙 (참고용 추정)",
    }


# ---------------------------------------------------------------- 결과 이미지
def _snapshot(frame_bgr: np.ndarray, boxes, classes) -> np.ndarray:
    img = frame_bgr.copy()
    for (x1, y1, x2, y2), c in zip(boxes, classes):
        x1, y1, x2, y2 = map(int, (x1, y1, x2, y2))
        if c == PERSON:
            roi = img[y1:y2, x1:x2]
            if roi.size:
                # 모자이크: 사람 영역을 가로 6칸 정도로 뭉개서 얼굴을 알아볼 수 없게 함
                h, w = roi.shape[:2]
                small = cv2.resize(roi, (max(1, w // max(1, w // 6)), max(1, h // max(1, w // 6))), interpolation=cv2.INTER_LINEAR)
                img[y1:y2, x1:x2] = cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)
            color = (0, 200, 255)
        elif c == BICYCLE:
            color = (255, 160, 0)
        else:
            color = (0, 220, 0)
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


# ---------------------------------------------------------------- 메인 분석
def analyze_video(
    source: str,
    max_seconds: float = 15.0,
    start_seconds: float = 0.0,
    sample_fps: float = 4.0,
    imgsz: int = 1280,
    stop_seconds: float = 4.0,
    conf: float = 0.25,
) -> AnalysisResult:
    """영상(파일 또는 스트림 URL)을 start_seconds부터 max_seconds초 동안 분석합니다.

    sample_fps: 초당 분석할 프레임 수 (CPU 부담 조절)
    imgsz: 탐지 해상도. 멀리 있는 작은 차량을 잡으려면 1280 이상이 필요합니다.
    """
    is_stream = str(source).startswith(("http://", "https://", "rtsp://"))
    if is_stream:
        # 실시간 스트림이 멈추면 기본 30초씩 기다리므로 10초로 줄임
        cap = cv2.VideoCapture(
            source,
            cv2.CAP_FFMPEG,
            [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 10000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 10000],
        )
    else:
        cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise RuntimeError("영상을 열 수 없습니다" + ("" if is_stream else f": {source}"))
    # 스트림이 느리게 들어와도 전체 분석이 너무 길어지지 않도록 실제 시간 상한을 둠
    deadline = time.monotonic() + max_seconds * 3 + 15
    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 0 or fps > 120:
        fps = 25.0
    stride = max(1, round(fps / sample_fps))
    if start_seconds > 0:
        cap.set(cv2.CAP_PROP_POS_MSEC, start_seconds * 1000)
    model = _get_model()
    tracker = _new_tracker(sample_fps)

    res = AnalysisResult()
    tracks: dict[int, list[tuple[float, float, float]]] = defaultdict(list)  # id -> [(t, cx, cy)]
    track_cls: dict[int, int] = {}
    per_sec: dict[int, dict] = defaultdict(lambda: {"vehicles": [], "persons": []})
    v_counts, p_counts, cond_stats = [], [], []
    best = (-1, None)  # (탐지 수, 스냅샷)
    diag = None
    idx = 0

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t = idx / fps
        if t > max_seconds or time.monotonic() > deadline:
            break
        if idx % stride:
            idx += 1
            continue
        if diag is None:
            diag = float(np.hypot(*frame.shape[:2]))

        # 1) 탐지: 화면에 보이는 모든 차량·사람 (개수 집계용)
        det = model.predict(frame, classes=TARGET_CLASSES, conf=conf, imgsz=imgsz, verbose=False)[0].boxes.cpu().numpy()
        boxes, classes = det.xyxy, det.cls.astype(int)

        nv = int(sum(c in VEHICLES for c in classes))
        npers = int(sum(c == PERSON for c in classes))
        v_counts.append(nv)
        p_counts.append(npers)
        per_sec[int(t)]["vehicles"].append(nv)
        per_sec[int(t)]["persons"].append(npers)

        # 2) 추적: 같은 차량을 프레임 사이에 이어 붙여 이동량·정지 여부 계산
        for row in tracker.update(det, frame):
            x1, y1, x2, y2, tid, score, c = row[:7]
            tid, c = int(tid), int(c)
            if c not in VEHICLES:
                continue
            # (시각, 중심 x, 중심 y, 박스 크기, 신뢰도)
            tracks[tid].append((t, (x1 + x2) / 2, (y1 + y2) / 2, float(np.hypot(x2 - x1, y2 - y1)), float(score)))
            track_cls[tid] = c

        if res.frames_analyzed % 10 == 0:
            cond_stats.append(frame_conditions(frame))
        if len(boxes) > best[0]:
            best = (len(boxes), _snapshot(frame, boxes, classes))

        res.frames_analyzed += 1
        res.seconds_analyzed = round(t, 1)
        idx += 1
    cap.release()

    if res.frames_analyzed == 0:
        raise RuntimeError("분석할 프레임이 없습니다.")

    # --- 교통: 이동량을 '차량 크기' 단위로 잼 (멀리 있는 차는 화면에서 조금만 움직여도 실제로는 많이 움직임)
    moving_speeds, stopped, fixed_objects, long_tracks = [], [], [], 0
    for tid, pts in tracks.items():
        if len(pts) < 3:
            continue
        dur = pts[-1][0] - pts[0][0]
        if dur <= 0:
            continue
        size = float(np.median([p[3] for p in pts])) or 1.0
        conf_mean = float(np.mean([p[4] for p in pts]))
        moved = np.hypot(pts[-1][1] - pts[0][1], pts[-1][2] - pts[0][2]) / size  # 차량 몇 대 길이만큼 움직였나
        jitter = float(np.std([p[1] for p in pts]) + np.std([p[2] for p in pts])) / size
        if dur >= stop_seconds:
            long_tracks += 1
            if moved < 0.5:
                info = {
                    "추적ID": int(tid),
                    "종류": VEHICLES[track_cls[tid]],
                    "정지 시간(초)": round(dur, 1),
                    "신뢰도": round(conf_mean, 2),
                    "박스 흔들림": round(jitter, 3),
                    "위치(x,y)": (int(pts[-1][1]), int(pts[-1][2])),
                }
                # 화면 글자(지점명·숫자)·표지판 같은 고정 물체: 박스가 전혀 흔들리지 않고 신뢰도가 아주 높지는 않음
                # (실제 CCTV 측정: 화면 글자 흔들림 0.007~0.023 / 신뢰도 0.34~0.69, 정체 줄의 차량 흔들림 0.07~0.16)
                # 한계: 멀리서 흐릿하게 보이며 완전히 멈춘 차량도 여기로 빠질 수 있음
                if jitter < 0.03 and conf_mean < 0.75:
                    fixed_objects.append(info)
                else:
                    stopped.append(info)
                continue
        moving_speeds.append(moved / dur)
    long_tracks -= len(fixed_objects)
    stopped_ratio = len(stopped) / long_tracks if long_tracks > 0 else 0.0

    avg_v = float(np.mean(v_counts))
    avg_speed = float(np.median(moving_speeds)) if moving_speeds else 0.0
    # 화면에 보이는 차량 수는 카메라마다 크게 달라서, 판단은 '멈춘 차량 비율'로 함
    if avg_v < 1:
        level = "차량 거의 없음"
    elif stopped_ratio > 0.5:
        level = "정체"
    elif stopped_ratio > 0.2:
        level = "서행"
    else:
        level = "원활"
    kinds = defaultdict(int)
    for tid, c in track_cls.items():
        kinds[VEHICLES[c]] += 1
    res.traffic = {
        "판단": level,
        "평균 차량 수(화면당)": round(avg_v, 1),
        "최대 차량 수": int(max(v_counts)),
        "누적 차량 수(추적 기준)": len(track_cls),
        "차종별": dict(kinds),
        "멈춘 차량 비율": f"{stopped_ratio:.0%}",
        "이동 속도(차량 길이/초)": round(avg_speed, 2),
    }

    # --- 돌발상황: 대부분 움직이는데 1~2대만 분석 시간 내내 멈춰 있으면 의심
    # (여러 대가 함께 멈추거나 잠깐 섰다 가는 것은 정체 줄로 봄)
    # 돌발 후보는 더 엄격하게: 8초 이상, 박스가 안정적(추적 ID가 이웃 차량과 뒤바뀐 경우 제외), 신뢰도 0.5 이상
    # (실제 CCTV 확인: ID가 바뀐 가짜 정차는 흔들림 0.17~0.21)
    incident_seconds = max(8.0, 0.8 * res.seconds_analyzed)
    long_stopped = [
        s for s in stopped if s["정지 시간(초)"] >= incident_seconds and s["박스 흔들림"] < 0.12 and s["신뢰도"] >= 0.5
    ]
    if not stopped:
        verdict = "이상 없음"
    elif long_stopped and len(stopped) <= 2 and stopped_ratio <= 0.2:
        verdict = f"돌발상황 의심: 다른 차량은 움직이는데 {len(long_stopped)}대가 계속 멈춰 있음"
    elif stopped_ratio > 0.2:
        verdict = f"정체로 인한 정차 {len(stopped)}대 (돌발상황 아님)"
    else:
        verdict = f"이상 없음 (잠깐 멈춘 차량 {len(stopped)}대)"
    res.incident = {
        "판단": verdict,
        "정차 의심 차량": stopped,
        "제외한 고정 물체(오탐 의심)": fixed_objects,
        "기준": (
            f"{stop_seconds:.0f}초 동안 차량 길이의 절반도 움직이지 않으면 정차로 봄. "
            "1~2대만 8초 이상(분석 시간의 80% 이상) 안정적으로 멈춰 있으면 돌발 의심, 여러 대가 함께 멈추거나 잠깐 서면 정체로 봄. "
            "화면 글자·표지판처럼 박스가 전혀 흔들리지 않는 탐지는 제외 (뚜렷하게 보이는 차량은 유지)"
        ),
    }

    # --- 군중
    avg_p = float(np.mean(p_counts))
    crowd = "없음" if avg_p < 0.5 else "낮음" if avg_p < 5 else "보통" if avg_p < 15 else "높음"
    res.crowd = {"판단": crowd, "평균 보행자 수": round(avg_p, 1), "최대 보행자 수": int(max(p_counts))}

    res.weather = judge_weather(cond_stats)
    res.timeline = [
        {"t": s, "vehicles": round(float(np.mean(d["vehicles"])), 1), "persons": round(float(np.mean(d["persons"])), 1)}
        for s, d in sorted(per_sec.items())
    ]
    res.snapshot = best[1]
    return res
