-- 지능형 기동지원 군사상황 정보판단 프로그램: Supabase 표
-- Supabase 대시보드 → SQL Editor에 붙여넣고 Run (여러 번 실행해도 안전)

-- 1) 분석 기록 -------------------------------------------------------------
create table if not exists public.analyses (
  id            bigint generated always as identity primary key,
  created_at    timestamptz not null default now(),
  kind          text not null,          -- 'route' (기동로) 또는 'area' (지점 주변)
  title         text,                   -- 예: 서울 → 천안 / 서울 서초 반경 3km
  verdict_text  text,                   -- 종합 판단 문장
  mobility      int,                    -- 0 미확인 / 1 Go / 2 Slow-Go / 3 No-Go
  threat_level  int,                    -- 0 없음 / 1 주의 / 2 경계 / 3 위험
  demo          boolean default true,   -- 시연 모드 결과 여부
  report        text,                   -- 상황 보고 전문
  summary       jsonb                   -- 구간·위협 요약
);
create index if not exists analyses_created_at_idx on public.analyses (created_at desc);

-- 2) 분석 서버(노트북) 상태: 현재 공개 주소와 마지막 신호 시각 --------------
create table if not exists public.server_status (
  id          int primary key default 1,
  api_base    text,
  online      boolean default false,
  updated_at  timestamptz not null default now(),
  constraint single_row check (id = 1)
);
insert into public.server_status (id, online) values (1, false) on conflict (id) do nothing;

-- 3) 보안 (RLS) ------------------------------------------------------------
-- 웹페이지(공개 anon 키)는 '읽기'만 가능, 쓰기는 노트북 분석 서버(service_role 키)만.
alter table public.analyses enable row level security;
alter table public.server_status enable row level security;

drop policy if exists "공개 읽기" on public.analyses;
create policy "공개 읽기" on public.analyses for select to anon using (true);

drop policy if exists "공개 읽기" on public.server_status;
create policy "공개 읽기" on public.server_status for select to anon using (true);
