-- Reference copy — src/lib/db.ts bootstraps this table automatically
-- (create table if not exists) on first use per instance, so fresh Neon
-- branches need no hand-applied migration. Keep both in sync.

create table if not exists reservations (
  id         bigint generated always as identity primary key,
  email      text not null unique,          -- stored lowercased; app normalizes
  name       text not null,
  created_at timestamptz not null default now()
);

-- Delivery order = reservation order:
--   select email, name, created_at from reservations order by created_at, id;
