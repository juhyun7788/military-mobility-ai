@echo off
chcp 65001 >nul
REM 지능형 기동지원 군사상황 정보판단 프로그램 - 웹사이트 실행
REM 이 파일을 더블클릭하면 분석 서버가 켜지고 브라우저가 열립니다. 끄려면 이 창을 닫으세요.
cd /d "%~dp0"
start "" http://localhost:8000
.venv\Scripts\python.exe -m uvicorn server.api:app --host 127.0.0.1 --port 8000
pause
