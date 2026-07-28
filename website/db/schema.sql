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

-- Durable preorder rate limiting. Only SHA-256 hashes of client IPs are
-- stored; the app prunes events older than 24 hours on each check.
-- Also bootstrapped by src/lib/db.ts on first use, so a fresh database
-- works without a hand-applied migration.
create table if not exists preorder_rate_events (
  ip_hash    text not null,
  created_at timestamptz not null default now()
);

create index if not exists preorder_rate_events_ip_hash_created_at_idx
  on preorder_rate_events (ip_hash, created_at);

-- Lets the 24-hour prune in recordRateEvent avoid a sequential scan.
create index if not exists preorder_rate_events_created_at_idx
  on preorder_rate_events (created_at);
