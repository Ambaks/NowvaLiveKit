import { neon } from "@neondatabase/serverless";

export type InsertResult = "inserted" | "duplicate";

/* Caller passes an already-lowercased email and owns the fallback policy —
   this throws on connection/query failure. */
export async function insertReservation(
  databaseUrl: string,
  name: string,
  email: string,
): Promise<InsertResult> {
  const sql = neon(databaseUrl);
  const rows = await sql`
    insert into reservations (email, name)
    values (${email}, ${name})
    on conflict (email) do nothing
    returning id
  `;
  return rows.length > 0 ? "inserted" : "duplicate";
}
