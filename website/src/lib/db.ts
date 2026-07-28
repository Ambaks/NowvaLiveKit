import { neon, type NeonQueryFunction } from "@neondatabase/serverless";

export type InsertResult = "inserted" | "duplicate";

/* Mirrors db/schema.sql. Ran once per serverless instance so a fresh Neon
   branch (production, or per-preview branches from the Vercel integration)
   works without a hand-applied migration. */
let schemaEnsured = false;

async function ensureSchema(sql: NeonQueryFunction<false, false>): Promise<void> {
  if (schemaEnsured) return;
  await sql`
    create table if not exists reservations (
      id         bigint generated always as identity primary key,
      email      text not null unique,
      name       text not null,
      created_at timestamptz not null default now()
    )
  `;
  schemaEnsured = true;
}

/* Caller passes an already-lowercased email and owns the fallback policy —
   this throws on connection/query failure. */
export async function insertReservation(
  databaseUrl: string,
  name: string,
  email: string,
): Promise<InsertResult> {
  const sql = neon(databaseUrl);
  await ensureSchema(sql);
  const rows = await sql`
    insert into reservations (email, name)
    values (${email}, ${name})
    on conflict (email) do nothing
    returning id
  `;
  return rows.length > 0 ? "inserted" : "duplicate";
}

/* db/schema.sql stays the source of truth; this bootstrap only guarantees
   the rate-events table exists so a fresh database needs no hand-applied
   migration before rate limiting works. Runs once per instance; a failed
   attempt clears the cache so the next call retries. */
let rateEventsReady: Promise<void> | null = null;

function ensureRateEventsTable(databaseUrl: string): Promise<void> {
  if (!rateEventsReady) {
    const sql = neon(databaseUrl);
    rateEventsReady = (async () => {
      await sql`
        create table if not exists preorder_rate_events (
          ip_hash    text not null,
          created_at timestamptz not null default now()
        )
      `;
      await sql`
        create index if not exists preorder_rate_events_ip_hash_created_at_idx
          on preorder_rate_events (ip_hash, created_at)
      `;
      await sql`
        create index if not exists preorder_rate_events_created_at_idx
          on preorder_rate_events (created_at)
      `;
    })();
    rateEventsReady.catch(() => {
      rateEventsReady = null;
    });
  }
  return rateEventsReady;
}

/* One round trip: prune events older than 24 hours (the retention promise
   on the privacy page), record this attempt, and return how many attempts
   the ip_hash has made inside the window — including this one. Only
   SHA-256 hashes ever reach the database. Throws on connection/query
   failure; the caller owns the fail-open policy. */
export async function recordRateEvent(
  databaseUrl: string,
  ipHash: string,
  windowMs: number,
): Promise<number> {
  const sql = neon(databaseUrl);
  await ensureRateEventsTable(databaseUrl);
  const rows = await sql`
    with pruned as (
      delete from preorder_rate_events
      where created_at < now() - interval '24 hours'
    ),
    recorded as (
      insert into preorder_rate_events (ip_hash) values (${ipHash})
      returning 1
    )
    select
      (select count(*) from recorded)::int
        + (
          select count(*)
          from preorder_rate_events
          where ip_hash = ${ipHash}
            and created_at > now() - ${windowMs} * interval '1 millisecond'
        )::int as recent
  `;
  return Number(rows[0].recent);
}
