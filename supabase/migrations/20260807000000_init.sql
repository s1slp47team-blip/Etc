-- 맛집 브리핑 — Supabase 스키마
--
-- 기존 food_briefing_app.py는 모든 상태를 파이썬 프로세스 메모리에 두었다.
--   검색캐시 / 상세캐시 / _상세결과캐시 / _인증맵캐시 / _내맛집캐시
-- 이 때문에 Render 무료 티어가 슬립하거나 재배포될 때마다 캐시가 통째로 사라졌다.
-- 여기서는 같은 캐시들을 Postgres로 옮겨 재시작과 무관하게 유지한다.

-- ── 1. 범용 KV 캐시 ────────────────────────────────────────────
-- scope 로 용도를 구분한다:
--   search  : (동네·조건) → {center, places}          — 기존 검색캐시
--   detail  : (동네·조건) → [enriched items]          — 기존 상세캐시
--   place   : 카카오 place id → panel3 요약           — 기존 _상세결과캐시
--   cert    : (좌표격자·반경) → {정규화상호: [배지]}   — 기존 _인증맵캐시
--   photo   : 카카오 place id → og:image URL          — 기존 _카카오사진 결과
create table if not exists public.kv_cache (
  scope      text        not null,
  key        text        not null,
  value      jsonb       not null,
  expires_at timestamptz not null,
  created_at timestamptz not null default now(),
  primary key (scope, key)
);

-- 만료분 정리를 위한 인덱스 (아래 purge_expired_cache 가 사용)
create index if not exists kv_cache_expires_idx on public.kv_cache (expires_at);

-- ── 2. 내 저장 맛집 (네이버지도 공유 리스트) ──────────────────
-- 기존에는 1시간 메모리 캐시라 재시작마다 네이버를 다시 크롤링했다.
-- 이제 테이블에 남으므로 갱신 주기가 지나기 전에는 외부 호출이 아예 없다.
create table if not exists public.my_places (
  id         bigint generated always as identity primary key,
  name       text   not null,
  lat        double precision not null,
  lng        double precision not null,
  folder     text   not null default '저장',
  norm_name  text   not null,          -- _이름정규화 결과 (매칭용)
  updated_at timestamptz not null default now()
);

create index if not exists my_places_norm_idx on public.my_places (norm_name);
create index if not exists my_places_geo_idx  on public.my_places (lat, lng);

-- 마지막 동기화 시각 (단일 행). 갱신 주기 판단에만 쓴다.
create table if not exists public.my_places_sync (
  id           boolean primary key default true check (id),
  refreshed_at timestamptz not null default now(),
  link_count   int not null default 0,
  place_count  int not null default 0,
  constraint my_places_sync_single check (id)
);

-- ── 3. 브리핑 잡 (청크 처리) ──────────────────────────────────
-- Edge Function 은 요청당 실행시간 제한이 있어, 30~100곳을 한 번에 처리하던
-- 브리핑생성()을 그대로 옮길 수 없다. 잡을 만들고 클라이언트가 청크 단위로
-- 나눠 호출하게 한다 — 제한을 피하면서 결과가 점진적으로 표시되는 이점도 있다.
create table if not exists public.briefing_jobs (
  id           uuid primary key default gen_random_uuid(),
  cache_key    text        not null,   -- kv_cache(detail) 에 최종 저장할 키
  neighborhood text        not null,   -- Gemini 프롬프트의 "동네"
  places       jsonb       not null,   -- 검색 결과 원본 (순서 = index)
  total        int         not null,
  cursor       int         not null default 0,   -- 다음에 처리할 시작 index
  failed       int         not null default 0,   -- 요약 실패한 가게 수
  status       text        not null default 'running',  -- running | done | error
  error        text,
  created_at   timestamptz not null default now()
);

create index if not exists briefing_jobs_created_idx on public.briefing_jobs (created_at);

-- 청크 결과. 여러 청크가 동시에 끝나도 서로 덮어쓰지 않도록 행 단위로 저장한다.
create table if not exists public.briefing_items (
  job_id uuid not null references public.briefing_jobs (id) on delete cascade,
  idx    int  not null,
  item   jsonb not null,
  primary key (job_id, idx)
);

-- ── 4. 청크 원자적 배정 ───────────────────────────────────────
-- 클라이언트가 step 을 병렬로 호출해도 같은 구간을 두 번 처리하지 않도록,
-- 행 잠금을 걸고 cursor 를 옮기면서 구간을 배정한다.
create or replace function public.claim_briefing_chunk(p_job uuid, p_size int)
returns table (start_idx int, end_idx int)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_cursor int;
  v_total  int;
begin
  select cursor, total into v_cursor, v_total
    from public.briefing_jobs
   where id = p_job
   for update;

  if not found then
    return;                      -- 잡 없음 → 빈 결과
  end if;

  if v_cursor >= v_total then    -- 더 배정할 구간 없음
    start_idx := v_total;
    end_idx   := v_total;
    return next;
    return;
  end if;

  update public.briefing_jobs
     set cursor = least(v_cursor + p_size, v_total)
   where id = p_job;

  start_idx := v_cursor;
  end_idx   := least(v_cursor + p_size, v_total);
  return next;
end;
$$;

-- 요약이 빠진 가게 수 누적. 스텝이 병렬로 돌아도 값이 유실되지 않도록 원자적 증가.
create or replace function public.bump_briefing_failed(p_job uuid, p_n int)
returns void
language sql
security definer
set search_path = public
as $$
  update public.briefing_jobs set failed = failed + p_n where id = p_job;
$$;

-- ── 5. 만료 데이터 정리 ───────────────────────────────────────
-- pg_cron 을 쓸 수 있으면 스케줄을 걸고, 아니면 Edge Function 이 가끔 호출한다.
create or replace function public.purge_expired_cache()
returns void
language sql
security definer
set search_path = public
as $$
  delete from public.kv_cache where expires_at < now();
  delete from public.briefing_jobs where created_at < now() - interval '1 day';
$$;

-- ── 6. RLS ────────────────────────────────────────────────────
-- 정책을 하나도 두지 않고 RLS 를 켜면 anon/authenticated 키로는 아무것도 못 읽는다.
-- Edge Function 만 service_role 키로 접근하며, service_role 은 RLS 를 우회한다.
-- (프론트는 Edge Function 을 통해서만 데이터에 닿는다)
alter table public.kv_cache       enable row level security;
alter table public.my_places      enable row level security;
alter table public.my_places_sync enable row level security;
alter table public.briefing_jobs  enable row level security;
alter table public.briefing_items enable row level security;

-- SECURITY DEFINER 함수는 기본적으로 PUBLIC 에 실행 권한이 열린다. RLS 를 우회하므로
-- 클라이언트 롤에서는 닫아둔다 (service_role 은 별도로 권한을 갖는다).
-- anon/authenticated 는 Supabase 에만 있는 롤이라 존재할 때만 처리한다.
do $$
declare
  fn text;
  r  text;
begin
  foreach fn in array array[
    'public.claim_briefing_chunk(uuid, int)',
    'public.bump_briefing_failed(uuid, int)',
    'public.purge_expired_cache()'
  ] loop
    execute format('revoke all on function %s from public', fn);
    foreach r in array array['anon', 'authenticated'] loop
      if exists (select 1 from pg_roles where rolname = r) then
        execute format('revoke all on function %s from %I', fn, r);
      end if;
    end loop;
    if exists (select 1 from pg_roles where rolname = 'service_role') then
      execute format('grant execute on function %s to service_role', fn);
    end if;
  end loop;
end $$;
