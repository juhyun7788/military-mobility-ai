# 인수인계 정리 — 지능형 기동지원 군사상황 정보판단 프로그램

2026-11-10 기준 (2026-11-11 새 PC로 옮김 — 5절 참고). 다른 계정(또는 새 Claude 대화)에서 이어서 작업할 때 **이 파일부터 읽으면** 됩니다.
배포·운영 세부는 `DEPLOY.md`, 기능·실행 설명은 `README.md`, 시연용 사진 출처는 `data/isr/SOURCES.md`.

---

## 1. 한 줄 요약

출발점·도착점(또는 기준 지점)만 정하면 경로 위 **공개 도로 CCTV(국가교통정보센터 ITS)** 와 **ISR·UAV 영상**을 AI로 융합 분석해
구간별 기동 가능성(**Go / Slow-Go / No-Go**), **우회로**, **상황 보고서**를 자동으로 만드는 웹 프로그램.
SKKU 바이브코딩 해커톤(2026 보수교육 3기) 제출작.

## 2. 주소

| 구분 | 주소 |
|---|---|
| 웹 사이트 (Vercel) | https://military-mobility-ai.vercel.app |
| 녹화된 시연 (서버 없이) | https://military-mobility-ai.vercel.app/?replay |
| 소스코드 (GitHub, 공개) | https://github.com/juhyun7788/military-mobility-ai |
| 해커톤 갤러리 작품 | https://skku-vibecoding-gallery.vercel.app/project/pj_ms_mwa1tit55c7qq (제작자 표시 "AI 비전") |
| 기록 DB (Supabase) | 프로젝트 `juhyun-Military-Aware` (ref `pmeyqgcgctvnchmvmony`), 표 `analyses`·`server_status` |
| 로컬 폴더 | `C:\Users\msi\OneDrive\Desktop\AX 보수교육\cctv_demo` (2026-11-11부터. 이전 PC는 `C:\Users\prett\...`) |

- 공개 사이트 **실시간 모드 비밀번호: `12345`** (포트폴리오에 공개하기로 함, `.env`의 `ADMIN_PASSCODE`)
- 각 서비스 로그인은 원래 계정에 묶여 있음. 계정을 바꾸면 GitHub push, Vercel·Supabase 관리, 갤러리 수정 권한이 그 계정에 있는지 먼저 확인할 것.

## 3. 구성

```
[Vercel 웹 web/] ──(Cloudflare 임시 터널 주소)──> [노트북 분석 서버 server/api.py]
       │                                               │
       └─ 기록·서버 주소 읽기(공개 키) ─ [Supabase] ─ 기록 저장·주소 알림(비밀 키) ─┘
```

- **분석 서버는 노트북에서만** 돎 (HF Docker Space는 유료라 포기). 노트북에서 `run_public.bat` 실행 → 터널 주소를 Supabase에 1분마다 알림 → 웹이 자동 연결.
- 서버가 꺼져 있으면 웹은 "분석 서버 꺼짐" 화면 + **녹화된 시연 보기** 버튼 + 지난 분석 기록만 보여 줌.
- 터널 실행(`run_public.bat`)은 Claude 자동 실행이 막혀 있어 **사용자가 직접 더블클릭**해야 함. 서버 코드(`server/`, `src/`)를 바꾸면 다시 실행해야 반영됨. 웹(`web/`)만 바꾸면 GitHub push → Vercel 자동 배포.

## 4. 폴더 안내

| 경로 | 내용 |
|---|---|
| `server/api.py` | FastAPI 분석 서버 (경로·주변 CCTV 조회, 분석 작업, 업로드, 관리자 비밀번호, 하루 호출 상한) |
| `server/history.py` | Supabase 기록 저장·조회 |
| `src/` | `analyzer.py`(YOLO11 + ByteTrack 교통), `threat.py`·`threat_classes.py`(YOLOE 위협), `route.py`(OSRM 경로·우회로·시연 CCTV), `report.py`(판단·보고서), `cctv_source.py`(ITS API, 캐시, 호출 수 기록) |
| `web/` | 정적 웹 (`index.html`, `app.js`, `style.css`, `config.js`=Supabase 주소·공개 키만) |
| `web/replay/` | 녹화된 시연 데이터 (`deploy/make_replay.py`로 생성) |
| `web/isr/` | 시연용 ISR 사진 썸네일 (갤러리 표시용) |
| `data/demo_cctvs.json` | 시연 모드용 실제 CCTV(저장본) + 샘플 영상 배치 |
| `data/demo_isr.json`, `data/isr/` | 시연용 ISR 사진 15장 (기본 배치 기동로 4·지점 주변 4, 나머지는 갤러리에서 선택) |
| `deploy/` | `run_public.py`(터널+주소 알림), `make_replay.py`, `make_thumbnail.py`, `make_web_config.py`, `supabase_schema.sql`, `thumbnail.png`, `gallery_submission.md` |
| `models/` | `yolo11n.pt`, `threat_yoloe.pt`는 GitHub에 있음. `mobileclip2_b.ts`(254MB)·`yoloe-26s-seg.pt`는 위협 모델을 다시 만들 때만 필요하고 GitHub에 없음 |

## 5. 실행 방법 (cctv_demo 폴더)

| 목적 | 방법 |
|---|---|
| 내 PC에서만 보기 | `run_web.bat` → http://localhost:8000 (비밀번호 없이 실시간 모드 가능) |
| 공개 사이트와 연결 | `run_public.bat` (검은 창에 "Supabase에 주소 알림: 완료" 나오면 준비 끝, 닫으면 종료) |
| 녹화 시연 다시 만들기 | `.venv\Scripts\python.exe deploy\make_replay.py` → commit·push |
| 갤러리 섬네일 다시 만들기 | `.venv\Scripts\python.exe deploy\make_thumbnail.py` |

- 파이썬은 가상환경 `.venv` (Python 3.12) 사용. 현재 PC는 NVIDIA RTX 4060 → GPU 추론 (PyTorch 2.6.0+cu124).
- git: `C:\Program Files\Git\cmd\git.exe`, cloudflared: `C:\Program Files (x86)\cloudflared\` (`winget install --id Cloudflare.cloudflared`).

### 다른 PC로 옮길 때

- `.venv`는 만든 PC의 파이썬 경로에 묶여 있어 옮기면 안 돌아감 → 새 PC에서 다시 만들기:
  `py -3.12 -m venv .venv` → (GPU 있으면) `.venv\Scripts\python.exe -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124` → `.venv\Scripts\python.exe -m pip install -r requirements.txt`
  (이전 PC의 가상환경은 `.venv_old_prett`로 남겨 둠, git 제외. 필요 없으면 지워도 됨)
- `.bat` 파일은 반드시 CRLF 줄바꿈이어야 함. LF면 한글 주석 때문에 창이 바로 꺼짐 (". was unexpected at this time."). `.gitattributes`로 CRLF 고정함.
- 분석 서버 두 개(`run_web.bat`, `run_public.bat`)는 같은 8000번 포트를 쓰므로 하나만 켤 것.

## 6. 지금까지 만든 기능 (요약)

1. **기동로 분석**: 출발·도착점(목록 또는 위도·경도 직접 입력 → "🧭 기동로 반영" 단추/Enter) → OSRM 경로 → 경로 위 CCTV 자동 선택·분석 → 구간별 판단, 기동 불가 시 위협 지점을 2km 이상 피하는 우회로
2. **교통 판단**: YOLO11n + ByteTrack, 원활·서행·정체·돌발(장시간 정차), CCTV 화면 글자·추적 오류 보정
3. **ISR·UAV 위협 탐지**: YOLOE 글 지정 탐지(기갑·화력 차량, 군용 차량, 병력, 도로 장애물, 연기·화재), 큰 사진 분할 탐지, 얼굴 모자이크
4. **지점 주변 융합 분석**: 기준 지점(목록·지도 클릭·좌표 → "📍 지점 반영") 반경의 CCTV + ISR을 방위·거리로 함께 판단
5. **상황 보고서** 자동 작성·복사·내려받기, **분석 기록**(Supabase)
6. **시연 모드(기본, API 호출 없음)** / **실시간 모드**(비밀번호 12345, 공개 사이트 하루 300건 상한, 5회 틀리면 10분 차단)
7. **녹화된 시연**: 서버 없이 분석 화면 전체 재생 (`?replay`)
8. **ISR 사진 갤러리**: 시연용 사진 15장을 썸네일로 골라 추가
9. **화면 색상**: 2026-11-10 사용자 선택으로 밝은 주간 라이트 + 역할별 색 단추(시안 B-3)
   - 반영=파랑, ISR 추가=보라, 분석 시작=초록, 저장·내려받기=청록, 비우기=빨강 테두리, 큰 탭은 탭마다 색

## 7. 작업 원칙 (이어서 작업할 때 지킬 것)

- **ITS API는 아껴 쓰기**: 월 5,000건 한도. 제작·검토 중에는 시연 모드로만 하고, API 호출은 **사용자가 직접 연동할 때만**. 호출 수는 `data/cache/api_usage.json`에 기록됨.
- **`.env`는 절대 커밋하지 않기** (ITS 키, Supabase 비밀 키, 비밀번호). push 전에 올라가는 파일에 `.env`·비밀 키가 없는지 확인.
- Supabase 비밀 키 교체는 사용자가 하지 않기로 결정함 (다시 권하지 않기).
- 군사 활용 범위: 기동로 상황판단·재난 지원 보조. 최종 판단은 사람, **타격 지정 없음, 개인 식별 없음, 공개 자료만**.
- 커밋 메시지 끝에 공동 작성자 줄을 붙여 왔음 (`Co-Authored-By: Claude …`).
- `data/demo_cctvs.json`에 커밋 안 된 변경(사용자가 실시간 모드에서 저장한 CCTV)이 있음 — 사용자 확인 전까지 그대로 둘 것.

## 8. 한계·알려진 문제

- 분석 서버가 노트북이라 노트북이 꺼지면 새 분석 불가 (녹화 시연·기록만 가능).
- ITS 영상 주소는 약 하루 지나면 만료될 수 있음 → 시연용 저장 CCTV는 가끔 실시간 모드에서 다시 저장 필요.
- 상·하행 구분 없음.
- 위협 탐지 한계: 전차·장갑차 세부 구분 어려움(묶어서 판단), 바리케이드 미탐지·불타는 민간 차량을 기갑으로 오탐하는 사례 있음 (`data/isr/SOURCES.md`).
- Cloudflare 임시 터널 주소는 켤 때마다 바뀜 (Supabase로 자동 연결되므로 문제 없음).

## 9. 남은 할 일 (선택)

- 갤러리 등록 글 '제작 후기'의 "서버가 꺼져 있을 때는 지난 분석 기록과 보고서만 볼 수 있습니다" → 녹화 시연 안내로 고치기 (`deploy/gallery_submission.md`에는 반영됨, 갤러리 사이트는 아직)
- Vercel의 GitHub 앱 접근 범위를 이 저장소로만 좁히기 (GitHub → Settings → Applications → Vercel → Configure)
- 대체 CCTV 데이터(UTIC 키 신청 예정, 도로공사·공공데이터포털)는 나중에 정리하기로 함
- 상·하행 구분, 발표 자료
