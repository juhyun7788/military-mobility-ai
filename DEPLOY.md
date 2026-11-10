# 배포 구성 (2026-11-10)

| 구성 | 주소 / 위치 | 역할 |
|---|---|---|
| 웹페이지 | **https://military-mobility-ai.vercel.app** (Vercel, `web/` 폴더) | 화면. GitHub `main`에 올리면 자동 재배포 |
| 코드 | https://github.com/juhyun7788/military-mobility-ai (공개) | `.env`(인증키)는 올라가지 않음 |
| 분석 서버 | **내 노트북** (`run_public.bat`) | AI 분석. Cloudflare 임시 터널로 공개 주소 생성 |
| 기록 | Supabase 프로젝트 `juhyun-Military-Aware` | 분석 기록·보고서(`analyses`), 노트북 서버 현재 주소(`server_status`) |

```
[Vercel 웹페이지] ──(trycloudflare 공개 주소)──> [노트북 분석 서버]
        │                                          │
        └── 기록·서버 주소 읽기(공개 키) ── [Supabase] ── 기록 저장·주소 알림(비밀 키) ──┘
```

## 시연할 때

1. 노트북에서 **`run_public.bat` 더블클릭** → 검은 창에 공개 주소와 "Supabase에 주소 알림: 완료"가 나오면 준비 끝
2. 아무 브라우저에서 https://military-mobility-ai.vercel.app 접속 → 자동으로 노트북 서버에 연결
3. 끝나면 검은 창 닫기 → 사이트는 "분석 서버 꺼짐" 화면이 되고, **지난 분석 기록·보고서는 계속 보임**

- 노트북 자체에서는 http://localhost:8000 으로도 씁니다 (실시간 모드·시연 목록 저장은 여기서만 가능).
- 공개 주소는 켤 때마다 바뀌지만, 웹페이지가 Supabase에서 읽어 오므로 따로 바꿀 필요가 없습니다.
- 공개 주소로 들어온 방문자: 실시간 모드(ITS API) 잠금, 시연 목록 저장 잠금, 업로드 30MB 제한.

## 공개 사이트에서 실시간 모드 쓰기

방문자 누구나 실시간 모드(국가교통정보센터 ITS API)를 쓸 수 있고, **전환할 때 비밀번호를 확인**합니다.

- **비밀번호: `12345`** (포트폴리오 설명에 공개)
- 사용법: 사이드바의 **시연 모드 스위치를 끄면** 비밀번호 입력 창이 뜨고, 맞으면 실시간 모드로 바뀜
- 확인은 그 브라우저 탭에서만 유지 (탭을 닫거나 사이드바 "해제"를 누르면 다시 시연 모드)
- 한도 보호
  - 공개 사이트의 실시간 호출은 **하루 300건**까지 (`.env`의 `LIVE_DAILY_LIMIT`로 조정)
  - 비밀번호를 10분 안에 5번 틀리면 그 접속은 10분간 차단
  - ITS API 월 한도는 5,000건, 사이드바에서 이번 달·오늘 사용량 확인 가능
- 비밀번호를 바꾸려면 `.env`의 `ADMIN_PASSCODE`만 고치고 `run_public.bat` 재실행

## 키·설정

- `.env` (노트북에만): `ITS_API_KEY`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`(공개), `SUPABASE_SERVICE_KEY`(비밀)
- `web/config.js`: Supabase 주소와 **공개 키만** (`deploy/make_web_config.py`로 생성)
- Supabase 표 만들기: `deploy/supabase_schema.sql` (RLS: 공개 키는 읽기만, 쓰기는 비밀 키)

## 할 일 (권장)

- **Supabase 비밀 키 교체:** 설정 중 채팅에 노출됐으므로 새로 만들고 예전 키 삭제
  1. Supabase → Project Settings → API Keys → Secret keys → **New secret key**
  2. `.env`의 `SUPABASE_SERVICE_KEY`를 새 키로 바꾸고 `run_public.bat` 다시 실행
  3. 예전 키 옆 ⋮ → Delete
- **Vercel의 GitHub 접근 범위 좁히기:** GitHub → Settings → Applications → Vercel → Configure → Only select repositories → `military-mobility-ai`

## 참고

- Hugging Face Spaces: Docker Space가 유료(PRO)로 바뀌어 사용하지 않음 (`deploy/hf_space_template`는 남겨 둠)
- 노트북이 꺼져 있으면 새 분석은 불가 (지난 기록만 열람)
