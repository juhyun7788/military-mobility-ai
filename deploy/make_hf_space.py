"""Hugging Face Spaces에 올릴 폴더(deploy/hf_space)를 만듭니다.

실행 (cctv_demo 폴더에서):  .venv\\Scripts\\python.exe deploy\\make_hf_space.py

- 실행에 필요한 파일만 복사합니다 (서버, 분석 코드, 웹페이지, 시연용 자료, 실행용 모델 2개).
- .env(인증키)는 절대 복사하지 않습니다. 공개 시연판은 시연 모드 전용이라 키가 필요 없습니다.
- 만든 폴더 내용을 그대로 Space에 올리면 됩니다 (deploy/HF_SPACES.md 참고).
"""

import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
PROJ = Path(__file__).resolve().parent.parent
OUT = PROJ / "deploy" / "hf_space"
TEMPLATE = PROJ / "deploy" / "hf_space_template"

FILES = [
    "server/__init__.py", "server/api.py", "server/history.py",
    "src/__init__.py", "src/analyzer.py", "src/cctv_source.py", "src/report.py", "src/route.py",
    "src/threat.py", "src/threat_classes.py",
    "data/demo_cctvs.json", "data/demo_isr.json", "data/cctv_catalog.json",
    "data/videos/SOURCES.md", "data/videos/congestion.webm", "data/videos/freeway.ogv",
    "data/videos/person-bicycle-car-detection.mp4",
    "models/yolo11n.pt", "models/threat_yoloe.pt",
]
DIRS = ["web", "data/isr"]
NEVER = {".env"}


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    for f in TEMPLATE.iterdir():
        shutil.copy2(f, OUT / f.name)
    for rel in FILES:
        src = PROJ / rel
        if not src.exists():
            if rel == "src/__init__.py":
                (OUT / rel).parent.mkdir(parents=True, exist_ok=True)
                (OUT / rel).write_text("", encoding="utf-8")
                continue
            raise SystemExit(f"없는 파일: {rel}")
        (OUT / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, OUT / rel)
    for rel in DIRS:
        shutil.copytree(PROJ / rel, OUT / rel, dirs_exist_ok=True)

    leaked = [p for p in OUT.rglob("*") if p.name in NEVER]
    if leaked:
        raise SystemExit(f"비밀 파일이 들어갔습니다, 중단: {leaked}")

    total = 0
    print(f"만든 폴더: {OUT}")
    for p in sorted(OUT.rglob("*")):
        if p.is_file():
            size = p.stat().st_size
            total += size
            mark = "  (10MB 넘음: 업로드 시 LFS로 처리됨)" if size > 10 * 1024 * 1024 else ""
            print(f"  {p.relative_to(OUT)}  {size / 1024 / 1024:.1f}MB{mark}")
    print(f"합계 {total / 1024 / 1024:.1f}MB")


if __name__ == "__main__":
    main()
