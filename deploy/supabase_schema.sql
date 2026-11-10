-- 지능형 기동지원 군사상황 정보판단 프로그램: 분석 기록 표
-- Supabase 대시보드 → SQL Editor에 붙여넣고 Run

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

-- 행 단위 보안 켜기: 공개(anon) 키로는 읽기·쓰기 불가.
-- 분석 서버만 service_role 키로 읽고 씀 (service_role은 RLS를 우회).
alter table public.analyses enable row level security;

create index if not exists analyses_created_at_idx on public.analyses (created_at desc);
