"""노트북 분석 서버를 인터넷에 공개하고(Cloudflare 임시 터널), 현재 주소를 Supabase에 알립니다.

실행 (cctv_demo 폴더에서):  .venv\\Scripts\\python.exe deploy\\run_public.py   (또는 run_public.bat 더블클릭)

하는 일
1. 분석 서버를 켭니다 (http://localhost:8000).
2. cloudflared로 임시 공개 주소(https://xxxx.trycloudflare.com)를 엽니다. 계정 필요 없음, 켤 때마다 주소가 바뀜.
3. 그 주소를 Supabase server_status 표에 적고, 1분마다 '살아 있음' 신호를 보냅니다.
   → Vercel 웹페이지가 이 주소를 읽어 자동으로 노트북 서버에 연결합니다.
4. 이 창을 닫거나 Ctrl+C로 끄면 '꺼짐'으로 알립니다.

공개 주소로 들어온 방문자는 실시간 모드(ITS API)와 시연 목록 저장이 잠겨 있습니다. 노트북(localhost)에서는 그대로 쓸 수 있습니다.
"""

import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
PROJ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJ))

from server import history  # noqa: E402

PORT = 8000
URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def find_cloudflared() -> str:
    for p in (shutil.which("cloudflared"),
              r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
              r"C:\Program Files\cloudflared\cloudflared.exe"):
        if p and Path(p).exists():
            return p
    raise SystemExit("cloudflared가 없습니다. 설치: winget install --id Cloudflare.cloudflared")


def main():
    if not history.ENABLED:
        print("⚠️ .env에 SUPABASE_URL, SUPABASE_SERVICE_KEY가 없어 웹페이지 자동 연결이 안 됩니다. (서버·터널은 켭니다)")
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "server.api:app", "--host", "127.0.0.1", "--port", str(PORT)], cwd=PROJ,
    )
    tunnel = subprocess.Popen(
        [find_cloudflared(), "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{PORT}"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
    )
    public_url = None
    deadline = time.time() + 60
    while time.time() < deadline and public_url is None:
        line = tunnel.stdout.readline()
        if not line:
            time.sleep(0.2)
            continue
        m = URL_RE.search(line)
        if m:
            public_url = m.group(0)
    if not public_url:
        print("공개 주소를 받지 못했습니다. 인터넷 연결을 확인하세요.")
        server.terminate()
        tunnel.terminate()
        return

    # 터널 로그는 계속 읽어서 버림 (버퍼가 차서 멈추지 않도록)
    threading.Thread(target=lambda: [None for _ in tunnel.stdout], daemon=True).start()

    print("=" * 60)
    print(f"  분석 서버 공개 주소: {public_url}")
    print(f"  노트북에서 직접 쓰기: http://localhost:{PORT}")
    print("  이 창을 닫으면 공개가 끝납니다.")
    print("=" * 60)
    err = history.set_status(public_url, True)
    print("  Supabase에 주소 알림: " + ("완료 (웹페이지가 자동 연결)" if err is None else err))

    try:
        while server.poll() is None and tunnel.poll() is None:
            time.sleep(60)
            history.set_status(public_url, True)  # 살아 있음 신호
    except KeyboardInterrupt:
        pass
    finally:
        history.set_status(None, False)
        print("공개를 끝냈습니다 (Supabase에 '꺼짐' 알림).")
        for p in (tunnel, server):
            p.terminate()


if __name__ == "__main__":
    main()
