import { createHash } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";
import { Resend } from "resend";
import { preorderSchema } from "@/lib/validation";
import { CONTACT_EMAIL } from "@/lib/constants";
import { insertReservation, recordRateEvent } from "@/lib/db";
import {
  confirmationHtml,
  confirmationSubject,
  confirmationText,
} from "@/lib/preorder-email";

const WINDOW_MS = 10 * 60 * 1000;
const MAX_PER_WINDOW = 5;
const MAX_TRACKED_IPS = 1000;
const RATE_CHECK_TIMEOUT_MS = 2000;

/* Per-instance rate limit — good enough for a launch page. */
const hits = new Map<string, number[]>();

function rateLimited(ipHash: string): boolean {
  const now = Date.now();
  if (hits.size > MAX_TRACKED_IPS) {
    for (const [key, stamps] of hits) {
      if (now - (stamps[stamps.length - 1] ?? 0) > WINDOW_MS) hits.delete(key);
    }
    /* Every entry still fresh (distributed burst) — drop the counters
       rather than grow unboundedly; losing them is fine for a soft limit. */
    if (hits.size > MAX_TRACKED_IPS) hits.clear();
  }
  const recent = (hits.get(ipHash) ?? []).filter((t) => now - t < WINDOW_MS);
  recent.push(now);
  hits.set(ipHash, recent);
  return recent.length > MAX_PER_WINDOW;
}

function tooManyRequests(): NextResponse {
  return NextResponse.json(
    { ok: false, error: "Too many requests — please try again in a few minutes." },
    { status: 429 },
  );
}

function clientIp(request: NextRequest): string {
  const real = request.headers.get("x-real-ip");
  if (real) return real.trim();
  /* Rightmost x-forwarded-for entry is the one our own proxy appended —
     leftmost entries are client-controlled and spoofable. */
  const forwarded = request.headers.get("x-forwarded-for");
  if (!forwarded) return "unknown";
  const parts = forwarded.split(",");
  return parts[parts.length - 1].trim();
}

export async function POST(request: NextRequest) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ ok: false, error: "Invalid request" }, { status: 400 });
  }

  const parsed = preorderSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { ok: false, error: "Please check your name and email." },
      { status: 400 },
    );
  }
  const { name, email, company } = parsed.data;

  /* Filled honeypot → bots get a quiet 200, never a tip-off. */
  if (company && company.length > 0) {
    return NextResponse.json({ ok: true });
  }

  /* Both limiter layers key on the hash, never the raw address — the
     privacy page promises the IP itself is not stored anywhere. */
  const ipHash = createHash("sha256").update(clientIp(request)).digest("hex");
  if (rateLimited(ipHash)) {
    return tooManyRequests();
  }

  /* Durable second layer — the in-memory map resets on every cold start and
     multiplies across instances. Only the SHA-256 of the IP is stored, and
     events older than 24 hours are pruned on each check. Fails open: the
     rate limiter must never block a real preorder. */
  const databaseUrl = process.env.DATABASE_URL;
  if (!databaseUrl) {
    console.error("[preorder] DATABASE_URL is not set — durable rate limit skipped");
  } else {
    try {
      /* A hung Neon call must not stall the request — timeout joins the
         thrown-error path and fails open. */
      const attempts = await Promise.race([
        recordRateEvent(databaseUrl, ipHash, WINDOW_MS),
        new Promise<never>((_, reject) =>
          setTimeout(
            () => reject(new Error("rate check timed out")),
            RATE_CHECK_TIMEOUT_MS,
          ),
        ),
      ]);
      if (attempts > MAX_PER_WINDOW) {
        return tooManyRequests();
      }
    } catch (err) {
      console.error("[preorder] durable rate check failed — failing open:", err);
    }
  }

  if (process.env.PREORDER_DRY_RUN === "1") {
    console.log("[preorder:dry-run]", { name, email });
    return NextResponse.json({ ok: true });
  }

  /* The Vercel project has the key stored as RESEND_APIKEY (no underscore);
     accept both names so the deployed form works either way. */
  const apiKey = process.env.RESEND_API_KEY ?? process.env.RESEND_APIKEY;
  if (!apiKey) {
    console.error("[preorder] RESEND_API_KEY is not set");
    return NextResponse.json(
      { ok: false, error: "Reservations are briefly offline. Please email us instead." },
      { status: 500 },
    );
  }

  const resend = new Resend(apiKey);
  const normalizedEmail = email.toLowerCase();

  /* Capture the lead in Postgres before any Resend call so an email outage
     can't lose it. Missing config or a failed insert falls back to
     email-only capture. */
  let dbOutcome: "inserted" | "duplicate" | "failed" | "skipped" = "skipped";
  if (!databaseUrl) {
    console.error("[preorder] DATABASE_URL is not set — email-only fallback");
  } else {
    try {
      dbOutcome = await insertReservation(databaseUrl, name, normalizedEmail);
    } catch (err) {
      dbOutcome = "failed";
      console.error("[preorder] db insert failed — email-only fallback:", err);
    }
  }

  /* Internal alert — skipped for duplicates. Its failure is only fatal when
     the database didn't capture the lead either. */
  if (dbOutcome !== "duplicate") {
    try {
      const { error } = await resend.emails.send({
        from: "Nowva Preorders <info@nowvasports.com>",
        to: process.env.PREORDER_TO ?? CONTACT_EMAIL,
        replyTo: email,
        subject: `New preorder reservation — ${name}`,
        text: [
          "New founding-batch reservation",
          "",
          `Name:  ${name}`,
          `Email: ${email}`,
          `Time:  ${new Date().toISOString()}`,
        ].join("\n"),
      });
      if (error) throw new Error(error.message);
    } catch (err) {
      console.error(
        `[preorder] alert send failed for ${normalizedEmail} (db=${dbOutcome}):`,
        err,
      );
      if (dbOutcome !== "inserted") {
        return NextResponse.json(
          { ok: false, error: "We couldn't save your reservation. Please try again." },
          { status: 500 },
        );
      }
    }
  }

  /* Resend Audience keeps the broadcast list in step with the table.
     The audienceId form is deprecated in favor of segments but supported
     in resend@6.18; switch to `segments: [{ id }]` if the account
     migrates to Segments. */
  if (dbOutcome === "inserted") {
    const audienceId = process.env.RESEND_AUDIENCE_ID;
    if (!audienceId) {
      console.warn("[preorder] RESEND_AUDIENCE_ID is not set — audience sync skipped");
    } else {
      try {
        const { error } = await resend.contacts.create({
          audienceId,
          email: normalizedEmail,
          firstName: name,
        });
        if (error) throw new Error(error.message);
      } catch (err) {
        console.error("[preorder] audience sync failed:", err);
      }
    }
  }

  /* Customer confirmation — only when the database verified this is a new
     reservation. Without a DB answer ("skipped"/"failed") duplicates can't
     be detected, so sending would let repeat POSTs mail-bomb an arbitrary
     address; in those fallback modes the alert email captures the lead and
     the on-screen success message stands alone. A failure here logs
     instead of erroring the request. */
  if (dbOutcome === "inserted") {
    try {
      const { error } = await resend.emails.send({
        from: "Nowva <info@nowvasports.com>",
        to: email,
        replyTo: CONTACT_EMAIL,
        subject: confirmationSubject(),
        html: confirmationHtml(name),
        text: confirmationText(name),
      });
      if (error) throw new Error(error.message);
    } catch (err) {
      console.error(
        `[preorder] CRITICAL: confirmation send failed for ${normalizedEmail} (db=${dbOutcome}) — user saw success:`,
        err,
      );
    }
  }

  return NextResponse.json({ ok: true });
}
