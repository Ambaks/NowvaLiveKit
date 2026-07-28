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
