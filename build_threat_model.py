"""위협 탐지 모델을 한 번 만들어 저장합니다.

YOLOE에 위협 대상 문구(src/threat_classes.py)를 넣고 models/threat_yoloe.pt로 저장합니다.
이 과정에만 문구 해석용 파일(models/mobileclip2_b.ts, 242MB)이 필요하고,
저장된 모델은 그 파일 없이 바로 씁니다. 대상 문구를 바꾸면 이 파일을 다시 실행하세요.

실행: .venv\\Scripts\\python.exe build_threat_model.py
"""

import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
PROJ = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJ))

from ultralytics import YOLOE  # noqa: E402

from src.threat_classes import THREAT_CLASSES  # noqa: E402

os.chdir(PROJ / "models")  # mobileclip2_b.ts를 이 폴더에서 찾도록
model = YOLOE("yoloe-26s-seg.pt")
prompts = [c["prompt"] for c in THREAT_CLASSES]
model.set_classes(prompts)
model.save("threat_yoloe.pt")
print("저장 완료: models/threat_yoloe.pt", f"(대상 {len(prompts)}개)")
