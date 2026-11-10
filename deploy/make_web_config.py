"""web/config.js를 .env의 SUPABASE_URL, SUPABASE_ANON_KEY로 만듭니다 (공개용 값만).

실행 (cctv_demo 폴더에서):  .venv\\Scripts\\python.exe deploy\\make_web_config.py
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
PROJ = Path(__file__).resolve().parent.parent
load_dotenv(PROJ / ".env")
url = os.getenv("SUPABASE_URL", "").rstrip("/")
anon = os.getenv("SUPABASE_ANON_KEY", "")
service = os.getenv("SUPABASE_SERVICE_KEY", "")
if not url or not anon:
    raise SystemExit(".env에 SUPABASE_URL과 SUPABASE_ANON_KEY를 넣어 주세요.")
if service and anon == service:
    raise SystemExit("SUPABASE_ANON_KEY에 service_role 키가 들어 있습니다. 공개용(anon/publishable) 키를 넣어 주세요.")

text = (PROJ / "web" / "config.js").read_text(encoding="utf-8")
lines = []
for line in text.splitlines():
    if line.startswith("window.SUPABASE_URL"):
        line = f"window.SUPABASE_URL = {json.dumps(url)};"
    elif line.startswith("window.SUPABASE_ANON_KEY"):
        line = f"window.SUPABASE_ANON_KEY = {json.dumps(anon)};"
    lines.append(line)
(PROJ / "web" / "config.js").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("web/config.js 작성 완료 (Supabase 주소·공개 키)")
