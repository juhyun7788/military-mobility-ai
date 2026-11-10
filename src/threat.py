"""ISR·UAV 영상(사진 또는 동영상)에서 기동로 위협 후보를 탐지합니다.

- 학습 없이 글로 대상을 지정하는 YOLOE 모델(models/threat_yoloe.pt) 사용
- 세부 종류(전차/장갑차/자주포)는 자주 헷갈리므로 '기갑·화력 차량' 묶음으로 판단하고 세부 종류는 '추정'으로만 표시
- 사람은 '병력(인원)' 수만 세고, 결과 이미지에서는 모자이크 처리 (개인 식별 없음)
- 판단 보조용: 최종 판단은 사람이 합니다
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from .threat_classes import THREAT_CLASSES, THREAT_LEVELS

PROJECT_DIR = Path(__file__).resolve().parent.parent
MODEL_PATH = PROJECT_DIR / "models" / "threat_yoloe.pt"
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

# 판단 묶음: 세부 종류를 묶어서 위협 수준을 정함
GROUPS = {
    "기갑": "기갑·화력 차량",
    "화력": "기갑·화력 차량",
    "기동·보급": "군용 차량(트럭·전술차량)",
    "병력": "병력(인원)",
    "장애물": "도로 장애물·파손",
    "징후": "연기·화재 징후",
}
MIN_CONF = 0.25  # 이보다 낮으면 버림
SURE_CONF = 0.40  # 위험(3) 판단에 필요한 최소 신뢰도. 미만이면 '경계(확인 필요)'로 낮춤

_model = None


def _get_model():
    global _model
    if _model is None:
        from ultralytics import YOLOE

        _model = YOLOE(str(MODEL_PATH))
    return _model


@dataclass
class ThreatResult:
    source_name: str
    level: int = 0  # 0 없음 / 1 주의 / 2 경계 / 3 위험
    items: list = field(default_factory=list)  # [{"묶음", "수량", "최고 신뢰도", "추정 종류", "위협"}]
    frames: int = 0
    snapshot: np.ndarray | None = None  # RGB

    @property
    def level_name(self) -> str:
        return THREAT_LEVELS[self.level]

    def summary(self) -> str:
        if not self.items:
            return "위협 후보 없음"
        return ", ".join(f"{i['묶음']} {i['수량']}" for i in self.items)


def _frames(source: str, max_seconds: float, sample_fps: float):
    """사진이면 1장, 동영상이면 초당 sample_fps장."""
    if Path(source).suffix.lower() in IMAGE_EXT:
        img = cv2.imread(source)
        if img is None:
            raise RuntimeError("ISR 사진을 열 수 없습니다")
        yield img
        return
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise RuntimeError("ISR 영상을 열 수 없습니다")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    stride = max(1, round(fps / sample_fps))
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok or idx / fps > max_seconds:
            break
        if idx % stride == 0:
            yield frame
        idx += 1
    cap.release()


LEVEL_RGB = {3: (220, 40, 40), 2: (255, 140, 0), 1: (255, 215, 0), 0: (170, 170, 170)}
_FONT_CANDIDATES = [r"C:\Windows\Fonts\malgunbd.ttf", r"C:\Windows\Fonts\malgun.ttf",
                    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"]


def _font(size: int):
    from PIL import ImageFont

    for p in _FONT_CANDIDATES:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def _mosaic(img: np.ndarray, x1: int, y1: int, x2: int, y2: int) -> None:
    roi = img[y1:y2, x1:x2]
    if roi.size:
        h, w = roi.shape[:2]
        k = max(1, w // 6)
        img[y1:y2, x1:x2] = cv2.resize(cv2.resize(roi, (max(1, w // k), max(1, h // k))), (w, h), interpolation=cv2.INTER_NEAREST)


def _draw(frame: np.ndarray, dets: list[tuple]) -> np.ndarray:
    """탐지 상자 + 한글 이름표 (위협 수준 색). 사람은 모자이크."""
    from PIL import Image, ImageDraw

    img = frame.copy()
    h, w = img.shape[:2]
    for (x1, y1, x2, y2), info, _ in dets:
        if "인" in info["label"] and info["kind"] in ("병력", "민간"):
            _mosaic(img, *map(int, (max(x1, 0), max(y1, 0), min(x2, w), min(y2, h))))
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil)
    lw = max(2, w // 400)
    font = _font(max(14, w // 55))
    # 낮은 위협부터 그려서 높은 위협 이름표가 위에 오도록
    for (x1, y1, x2, y2), info, conf in sorted(dets, key=lambda d: d[1]["threat"]):
        lvl = 2 if info["threat"] == 3 and conf < SURE_CONF else info["threat"]  # 표와 같은 기준으로 낮춤
        c = LEVEL_RGB[lvl]
        draw.rectangle([x1, y1, x2, y2], outline=c, width=lw)
        tag = f"{THREAT_LEVELS[lvl] if lvl else '민간'} · {info['label']} {conf:.2f}"
        tb = draw.textbbox((0, 0), tag, font=font)
        tw, th = tb[2] - tb[0] + 10, tb[3] - tb[1] + 8
        ty = y1 - th if y1 - th >= 0 else y1
        draw.rectangle([x1, ty, x1 + tw, ty + th], fill=c)
        draw.text((x1 + 5, ty + 2 - tb[1]), tag, font=font, fill=(17, 17, 17) if lvl in (1, 0) else (255, 255, 255))
    return np.array(pil)


def _detect(model, frame: np.ndarray, tile: bool) -> list[tuple]:
    """전체 화면 + (큰 영상이면) 2×2 겹침 분할 탐지 후 합칩니다. 높은 곳에서 찍은 UAV 영상의 작은 차량을 놓치지 않기 위함."""
    import torch
    from torchvision.ops import nms

    h, w = frame.shape[:2]
    crops = [(0, 0, frame)]
    if tile:
        th, tw = int(h * 0.6), int(w * 0.6)
        for oy in (0, h - th):
            for ox in (0, w - tw):
                crops.append((ox, oy, frame[oy:oy + th, ox:ox + tw]))
    boxes, confs, clss = [], [], []
    for ox, oy, img in crops:
        r = model.predict(img, conf=MIN_CONF, verbose=False)[0]
        if r.boxes is None or len(r.boxes) == 0:
            continue
        b = r.boxes.xyxy.cpu().numpy() + np.array([ox, oy, ox, oy])
        boxes.append(b)
        confs.append(r.boxes.conf.cpu().numpy())
        clss.append(r.boxes.cls.cpu().numpy().astype(int))
    if not boxes:
        return []
    b, p, c = np.concatenate(boxes), np.concatenate(confs), np.concatenate(clss)
    keep = nms(torch.tensor(b, dtype=torch.float32), torch.tensor(p, dtype=torch.float32), 0.5).numpy()
    # 같은 묶음끼리 한 상자가 다른 상자 안에 대부분 들어가면(겹친 면적 ≥ 작은 상자의 50%) 하나로 봄
    # (분할 탐지 경계에서 잘린 상자, 전차를 '장갑차'와 '다연장로켓'으로 이중 탐지하는 경우)
    def grp(i):
        info = THREAT_CLASSES[c[i]]
        return GROUPS.get(info["kind"], info["kind"])

    final: list[int] = []
    for i in sorted(keep, key=lambda i: -p[i]):
        bi = b[i]
        area_i = max((bi[2] - bi[0]) * (bi[3] - bi[1]), 1e-6)
        dup = False
        for j in final:
            if grp(j) != grp(i):
                continue
            bj = b[j]
            iw = max(0.0, min(bi[2], bj[2]) - max(bi[0], bj[0]))
            ih = max(0.0, min(bi[3], bj[3]) - max(bi[1], bj[1]))
            area_j = max((bj[2] - bj[0]) * (bj[3] - bj[1]), 1e-6)
            if iw * ih / min(area_i, area_j) >= 0.5:
                dup = True
                break
        if not dup:
            final.append(i)
    return [(b[i], THREAT_CLASSES[c[i]], float(p[i])) for i in final]


def analyze_isr(source: str, name: str = "", max_seconds: float = 10.0, sample_fps: float = 2.0) -> ThreatResult:
    """ISR 사진·영상의 위협 후보를 묶음별로 판단합니다.

    - 동영상은 같은 묶음이 여러 장면(2장 이상, 분석 장면의 25% 이상)에서 보여야 '확인'으로 칩니다.
      한두 장면에만 잠깐 나온 탐지는 '일시 탐지'로 보고 주의 수준으로 낮춥니다.
    """
    model = _get_model()
    res = ThreatResult(source_name=name or Path(source).name)
    group_max_count: dict[str, int] = defaultdict(int)
    group_best_conf: dict[str, float] = defaultdict(float)
    group_kinds: dict[str, Counter] = defaultdict(Counter)
    group_threat: dict[str, int] = defaultdict(int)  # 묶음 안에서 실제 탐지된 종류의 최고 위협 수준
    group_frames: dict[str, int] = defaultdict(int)  # 몇 장면에서 보였나
    best = (-1, None)

    for frame in _frames(source, max_seconds, sample_fps):
        dets = _detect(model, frame, tile=max(frame.shape[:2]) >= 1000)
        counts = Counter()
        for _, info, p in dets:
            if info["threat"] == 0:
                continue
            g = GROUPS[info["kind"]]
            counts[g] += 1
            group_best_conf[g] = max(group_best_conf[g], p)
            group_kinds[g][info["label"]] += 1
            group_threat[g] = max(group_threat[g], info["threat"])
        for g, n in counts.items():
            group_max_count[g] = max(group_max_count[g], n)
            group_frames[g] += 1
        score = sum(i["threat"] for _, i, _ in dets)
        if score > best[0]:
            best = (score, _draw(frame, dets))
        res.frames += 1

    if res.frames == 0:
        raise RuntimeError("분석할 ISR 프레임이 없습니다")

    for g, n in sorted(group_max_count.items(), key=lambda kv: -group_threat[kv[0]]):
        lvl = group_threat[g]
        notes = []
        if res.frames > 1 and group_frames[g] < max(2, 0.25 * res.frames):
            lvl = min(lvl, 1)
            notes.append(f"일시 탐지 {group_frames[g]}/{res.frames}장면")
        elif lvl == 3 and group_best_conf[g] < SURE_CONF:
            lvl = 2  # 신뢰도가 낮으면 '경계'로 낮춤
            notes.append("신뢰도 낮음")
        res.items.append(
            {
                "묶음": g,
                "수량": f"{n}대" if "차량" in g else f"{n}개" if "장애물" in g or "징후" in g else f"{n}명",
                "최고 신뢰도": round(group_best_conf[g], 2),
                "AI 추정 종류(참고)": ", ".join(k for k, _ in group_kinds[g].most_common(2)),
                "위협": THREAT_LEVELS[lvl] + (f" (확인 필요: {', '.join(notes)})" if notes else ""),
                "_level": lvl,
            }
        )
    res.level = max((i["_level"] for i in res.items), default=0)
    res.snapshot = best[1]
    return res
