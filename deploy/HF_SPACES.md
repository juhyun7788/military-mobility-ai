# Hugging Face Spaces 올리기 (공개 시연판)

아직 올리지 않았습니다. 아래는 올릴 때의 순서입니다.

## 1. 올릴 폴더 만들기

`cctv_demo` 폴더에서 실행:

```
.venv\Scripts\python.exe deploy\make_hf_space.py
```

- `deploy\hf_space` 폴더가 새로 만들어집니다(약 67MB).
- 서버, 분석 코드, 웹페이지, 시연용 자료, 실행용 모델 2개만 들어갑니다.
- `.env`(인증키)는 들어가지 않습니다.
- 시연용 실제 CCTV를 새로 저장했다면, 올리기 직전에 이 명령을 다시 실행해 최신 목록을 넣으세요.

## 2. Space 만들기 (직접 하셔야 합니다)

1. huggingface.co에 가입하고 로그인합니다.
2. 오른쪽 위 **New → Space**를 누릅니다.
3. 다음처럼 설정합니다.
   - Space name: 예) `military-mobility-demo`
   - SDK: **Docker** → Blank
   - Hardware: **CPU basic (무료)**
   - Visibility: Public (포트폴리오용) 또는 Private

## 3. 파일 올리기

- **웹에서 올리기 (가장 쉬움):**
  1. Space의 **Files → Add file → Upload files**를 누릅니다.
  2. `deploy\hf_space` 안의 파일과 폴더를 모두 끌어다 놓습니다.
  3. 10MB가 넘는 파일(모델·영상 3개)도 웹 업로드가 알아서 처리합니다.
- **명령으로 올리기:** `huggingface_hub`를 설치하고 로그인한 뒤, `hf_space` 폴더를 올리는 방법도 있습니다.

올리면 자동으로 빌드가 시작되고, 몇 분 뒤 `https://huggingface.co/spaces/<아이디>/<Space이름>`에서 열립니다.

## 4. 설정 (선택)

| 설정 | 기본값 | 바꾸는 곳 |
|---|---|---|
| `PUBLIC_DEMO=1` | Dockerfile에 들어 있음 | 공개 서버 모드 (실시간 잠금, 업로드 30MB 제한, 하루 지난 결과 자동 삭제) |
| `ALLOW_LIVE=1` | 없음 (잠금) | Space **Settings → Variables**. 실시간 모드를 열 때만 |
| `ITS_API_KEY` | 없음 | Space **Settings → Secrets**. 실시간 모드를 열 때만 (공개 Space에서는 비추천: 방문자가 월 5,000건 한도를 씀) |

## 알아둘 점

- **분석 속도:** 무료 CPU라 기동로 분석에 1~3분 걸릴 수 있습니다. 한동안 접속이 없으면 잠들어서, 첫 접속 때 깨어나는 데 시간이 걸립니다.
- **실제 CCTV 영상**
  - 저장한 실제 CCTV 영상은 약 하루 뒤 만료됩니다.
  - Space 서버는 해외에 있어서 국내 CCTV 영상이 열리지 않을 수도 있습니다.
  - 어느 경우든 자동으로 공개 샘플 영상으로 대신해서 시연은 끊기지 않습니다. 시연 목록을 새로 하려면 내 PC에서 실시간 모드로 저장한 뒤 1번부터 다시 올리세요.
- **라이선스:** Ultralytics YOLO는 AGPL-3.0입니다. 공개 Space는 소스가 공개되므로 조건에 맞습니다(README에 표시함).
- **아직 확인 못 한 것:** 내 PC에 Docker가 없어 Docker 빌드 자체는 시험하지 못했습니다. 같은 폴더를 내 PC에서 공개 시연 모드로 실행하는 것까지만 확인했고, 실제 빌드는 Space에 올릴 때 처음 확인됩니다.
