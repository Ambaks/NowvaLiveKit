-- Applied once by hand: Neon console SQL editor, or
--   psql "$DATABASE_URL" -f db/schema.sql
-- No migration framework; this file is the source of truth.

create table if not exists reservations (
  id         bigint generated always as identity primary key,
  email      text not null unique,          -- stored lowercased; app normalizes
  name       text not null,
  created_at timestamptz not null default now()
);

-- Delivery order = reservation order:
--   select email, name, created_at from reservations order by created_at, id;
