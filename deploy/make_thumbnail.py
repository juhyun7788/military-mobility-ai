"""갤러리용 섬네일 만들기 (1280x800, 16:10) — 웹 화면과 같은 밝은 색상(시안 B-3).

녹화 시연 결과(web/replay/)의 실제 분석 사진과 구간 판단으로 그립니다.
실행 (cctv_demo 폴더에서):  .venv\\Scripts\\python.exe deploy\\make_thumbnail.py [CCTV사진번호] [ISR사진번호]
결과: deploy/thumbnail.png
"""

import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

PROJ = Path(__file__).resolve().parent.parent
REPLAY = PROJ / "web" / "replay"
OUT = PROJ / "deploy" / "thumbnail.png"
cam_i = int(sys.argv[1]) if len(sys.argv) > 1 else 0
isr_i = int(sys.argv[2]) if len(sys.argv) > 2 else 2

W, H = 1280, 800
F, FR = r"C:\Windows\Fonts\malgunbd.ttf", r"C:\Windows\Fonts\malgun.ttf"


def font(size, bold=True):
    return ImageFont.truetype(F if bold else FR, size)


def rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# 웹 화면 색 (web/style.css)
BG, PANEL, LINE = rgb("#eef2f6"), rgb("#ffffff"), rgb("#cfd8e3")
TEXT, SOFT, MUTED = rgb("#0d1724"), rgb("#34465c"), rgb("#5a6b80")
GO, SLOW, NOGO = rgb("#2e7d32"), rgb("#f9a825"), rgb("#c62828")
BLUE, PURPLE, TEAL = rgb("#1e6fd0"), rgb("#6a4bc4"), rgb("#00838f")
MOB = {1: GO, 2: SLOW, 3: NOGO}

b = json.loads((REPLAY / "replay.json").read_text(encoding="utf-8"))
route = b["route"]
res = route["result"]
total = route["info"]["route"]["total_km"]

img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)
# 은은한 격자 + 왼쪽 위 연한 초록 빛
for x in range(0, W, 40):
    d.line([(x, 0), (x, H)], fill=(228, 234, 241), width=1)
for y in range(0, H, 40):
    d.line([(0, y), (W, y)], fill=(228, 234, 241), width=1)
glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
ImageDraw.Draw(glow).ellipse([-300, -360, 760, 560], fill=(46, 125, 50, 34))
img.paste(glow.filter(ImageFilter.GaussianBlur(90)), (0, 0), glow.filter(ImageFilter.GaussianBlur(90)))
d = ImageDraw.Draw(img)


def card(photo, box, color, label):
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    r = max(w / photo.width, h / photo.height)
    ph = photo.resize((int(photo.width * r), int(photo.height * r)), Image.LANCZOS)
    left, top = (ph.width - w) // 2, (ph.height - h) // 2
    ph = ph.crop((left, top, left + w, top + h))
    sh = Image.new("RGBA", (w + 60, h + 60), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([30, 36, w + 30, h + 36], 16, fill=(20, 40, 70, 70))
    sh = sh.filter(ImageFilter.GaussianBlur(14))
    img.paste(sh, (x1 - 30, y1 - 30), sh)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], 14, fill=255)
    img.paste(ph, (x1, y1), mask)
    dd = ImageDraw.Draw(img)
    dd.rounded_rectangle([x1, y1, x2, y2], 14, outline=color, width=5)
    tf = font(20)
    tw = dd.textlength(label, font=tf)
    dd.rounded_rectangle([x1 + 14, y1 + 14, x1 + 36 + tw, y1 + 50], 8, fill=color)
    dd.text((x1 + 25, y1 + 17), label, font=tf, fill=(255, 255, 255))


cam = Image.open(REPLAY / f"route_cctv_{cam_i}.jpg").convert("RGB")
isr = Image.open(REPLAY / f"route_isr_{isr_i}.jpg").convert("RGB")
card(cam, (690, 60, 1230, 370), BLUE, "CCTV 교통 분석 · 정체·돌발")
card(isr, (770, 310, 1250, 552), NOGO, "ISR·UAV 위협 탐지")
d = ImageDraw.Draw(img)

# 왼쪽: 행사 표시 + 제목 (웹 머리글처럼 왼쪽 초록 막대)
tag = "SKKU 바이브코딩 해커톤 · AX"
tw = d.textlength(tag, font=font(20))
d.rounded_rectangle([60, 62, 60 + tw + 32, 100], 8, fill=rgb("#e3f4e5"), outline=GO, width=2)
d.text((76, 66), tag, font=font(20), fill=rgb("#1b5e20"))
d.rectangle([60, 132, 69, 324], fill=GO)
for i, line in enumerate(["지능형 기동지원", "군사상황", "정보판단 프로그램"]):
    d.text((88, 124 + i * 68), line, font=font(58), fill=TEXT)
for i, s in enumerate(["공개 도로 CCTV + ISR·UAV 영상을 AI로 융합해", "기동로 구간별 기동 가능성과 우회로를 판단"]):
    d.text((90, 352 + i * 36), s, font=font(26, bold=False), fill=SOFT)

# 판단 배지
x = 90
for t, c, fg in [("Go", GO, (255, 255, 255)), ("Slow-Go", SLOW, (17, 17, 17)), ("No-Go", NOGO, (255, 255, 255))]:
    tw = d.textlength(t, font=font(26))
    d.rounded_rectangle([x, 452, x + tw + 36, 498], 23, fill=c)
    d.text((x + 18, 456), t, font=font(26), fill=fg)
    x += tw + 52

# 아래: 기동로 구간 판단 띠 (녹화 시연의 실제 판단)
px1, py1, px2, py2 = 40, 600, 1240, 772
d.rounded_rectangle([px1, py1, px2, py2], 12, fill=PANEL, outline=LINE, width=2)
y0 = 676
title = f"기동로 구간 판단  {route['start'].split(' (')[0]} → {route['end']} {round(total)}km"
d.text((60, 614), title, font=font(22), fill=MUTED)
sx1, sx2 = 60, 1220
X = lambda km: sx1 + (sx2 - sx1) * km / total
for s in res["segments"]:
    d.rectangle([X(s["from_km"]), y0, X(s["to_km"]) - 3, y0 + 30], fill=MOB.get(s["mobility"], rgb("#9e9e9e")))
for it in route["isr"]:  # ISR 위협 지점
    cx = X(it["ratio"] * total)
    d.polygon([(cx, y0 + 36), (cx - 12, y0 + 58), (cx + 12, y0 + 58)], fill=rgb("#ffb300"))
    d.text((cx - 3, y0 + 37), "!", font=font(16), fill=(17, 17, 17))
# 우회로 건의 (기동 불가 구간 위를 보라 점선 호로)
nogo = [s for s in res["segments"] if s["mobility"] == 3]
if res.get("detour") and nogo:
    a1, a2 = X(min(s["from_km"] for s in nogo[1:] or nogo)), X(total) - 30
    p = lambda t: (a1 + (a2 - a1) * t, y0 - 6 - math.sin(math.pi * t) * 30)
    for i in range(0, 30, 2):
        d.line([p(i / 30), p((i + 1) / 30)], fill=PURPLE, width=5)
    d.text((a1 + (a2 - a1) * 0.36, y0 - 64), "우회로 건의", font=font(20), fill=PURPLE)
d.text((sx1, y0 + 62), "▶ 서울", font=font(20), fill=SOFT)
d.text((sx2 - 44, y0 + 62), route["end"], font=font(20), fill=SOFT)

# 기술
tech = "YOLO11 · YOLOE · ByteTrack · OSRM · FastAPI · Vercel · Supabase"
d.text((W - 60 - d.textlength(tech, font=font(18, False)), 566), tech, font=font(18, False), fill=MUTED)

img.save(OUT)
print(OUT, img.size)
