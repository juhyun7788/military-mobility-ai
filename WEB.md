# 웹사이트 버전 실행·배포 안내

## 내 컴퓨터에서 실행

`cctv_demo` 폴더의 **`run_web.bat`을 더블클릭**하면 분석 서버가 켜지고 브라우저가 열립니다.
끄려면 검은 창을 닫으세요.

직접 실행하려면 (cctv_demo 폴더에서):

```
.venv\Scripts\python.exe -m uvicorn server.api:app --host 127.0.0.1 --port 8000
```

브라우저 주소: http://localhost:8000

- 항상 **시연 모드(ITS API 호출 없음)**로 시작합니다.
- 실시간 모드로 바꾸면 확인 창이 뜹니다.
- 사이드바에서 이번 달 API 호출 수를 볼 수 있습니다.

## 구성

```
cctv_demo/
├─ web/                웹페이지 (HTML·CSS·JS) ← 나중에 Vercel
│  ├─ index.html, style.css, app.js
│  └─ config.js        분석 서버 주소 (API_BASE)
├─ server/api.py       분석 서버 (FastAPI) ← PC·클라우드 서버
├─ src/                분석 코드 (CCTV 교통, ISR 위협, 경로, 보고서) — Streamlit판과 공용
├─ data/               시연용 CCTV·ISR·샘플 영상, 분석 결과(results)·업로드(uploads)
├─ models/             AI 모델
├─ run_web.bat         더블클릭 실행
└─ app.py              예전 Streamlit 화면 (그대로 쓸 수 있음)
```

### 분석 서버 API

| 주소 | 하는 일 |
|---|---|
| `GET /api/config` | 지명 목록, 시연용 ISR, API 호출 수, 저장된 실제 CCTV |
| `POST /api/route` | 기동로와 경로 위 CCTV (시연 모드면 API 호출 없음) |
| `POST /api/nearby` | 지점 주변 CCTV |
| `POST /api/upload` | ISR 사진·영상 올리기 |
| `POST /api/jobs/route`, `POST /api/jobs/area` | 분석 시작 (백그라운드 작업 번호 돌려줌) |
| `GET /api/jobs/{번호}` | 진행률·결과 |
| `POST /api/save_demo` | 실시간으로 받은 경로 CCTV를 시연용으로 저장 |
| `GET /api/check_saved` | 저장된 실제 CCTV가 아직 재생되는지 (API 호출 없음) |

## 나중에 GitHub · Vercel · Supabase로 배포할 때 (아직 연동 안 함)

1. **GitHub**
   - `cctv_demo` 폴더를 저장소로 올립니다.
   - `.gitignore`가 `.env`(인증키), `.venv`, 실행 중 생긴 파일, 242MB 모델 파일을 제외합니다.
2. **Vercel: 웹페이지만**
   - `web/` 폴더를 정적 사이트로 배포합니다.
   - `web/config.js`의 `API_BASE`에 분석 서버 주소를 넣습니다.
3. **분석 서버는 Vercel에 올릴 수 없습니다**
   - YOLO·PyTorch 모델(수백 MB), 실시간 영상 처리, 1분 넘는 분석 작업이 Vercel 서버리스 제한(용량·실행 시간)을 넘습니다.
   - 내 PC에서 돌리고 외부 주소를 열거나(예: Cloudflare Tunnel), 클라우드 VM(GPU가 있으면 더 빠름)에서 실행합니다.
   - 서버는 다른 주소의 웹페이지 요청을 이미 허용(CORS)하도록 설정돼 있습니다.
4. **Supabase**
   - 분석 결과(종합 판단, 보고서), 결과 이미지, 올린 ISR 파일을 저장하는 용도에 맞습니다(데이터베이스 + Storage).
   - 지금은 결과가 서버의 `data/results/`에 파일로만 남습니다.
