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
