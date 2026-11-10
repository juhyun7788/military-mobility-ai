@echo off
chcp 65001 >nul
REM 노트북 분석 서버를 인터넷에 공개 (Vercel 웹페이지가 자동 연결). 끄려면 이 창을 닫으세요.
cd /d "%~dp0"
.venv\Scripts\python.exe deploy\run_public.py
pause
